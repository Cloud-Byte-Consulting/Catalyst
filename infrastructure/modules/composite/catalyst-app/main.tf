# ---------------------------------------------------------------------------
# catalyst-app — L4 per-application composite (ADR-015 §Tier responsibilities).
#
# Reads upstream tenant baseline state via terraform_remote_state (strictly
# upward per ADR-015 §Cross-tier reference contract). Owns the resources
# listed for L4 in ADR-015: ECR repo, exec role, log group, ALB rule, and
# a per-app catalog row in the platform-state DynamoDB table.
#
# Backend configuration for this module's OWN state is supplied by the
# caller at apply time (`-backend-config="key=catalyst/tenants/${tenant}/
# environments/${env}/apps/${app}.tfstate"`); the root configuration that
# wraps this module declares `backend "s3" {}` with no inline key.
# ---------------------------------------------------------------------------

locals {
  construct_address  = "${var.tenant}/${var.environment}/shared/${var.project}/${var.app}"
  resource_name      = "${var.tenant}-${var.project}-${var.app}"
  log_group_name     = "/aws/catalyst/${var.tenant}/${var.environment}/${var.project}/${var.app}"
  is_web_service     = var.service_type == "web-service"
  alb_path_pattern   = "/${var.tenant}/${var.environment}/${var.project}/${var.app}/*"
  catalog_record_key = "APP#${local.construct_address}"
  catalog_record_sk  = "META"

  # The Lambda-exec / ECS-task assume-role choice is the only meaningful
  # split between web-service|worker|batch at the IAM layer for the L4
  # composite. ALB / fan-out wiring lives further down and is gated by
  # local.is_web_service so worker/batch shapes simply skip those resources.
  assume_service = var.service_type == "batch" ? "ecs-tasks.amazonaws.com" : "lambda.amazonaws.com"
}

# ---------------------------------------------------------------------------
# Upstream tenant baseline state (ADR-015 §Cross-tier reference contract).
#
# Reference direction MUST be strictly upward: L4 -> L2 (the tenant
# baseline state produced by the tenant-onboarding composite from #168).
# Outputs we expect: iam_group_names, ssm_parameter_arns, etc. — they are
# read here as a contract test (the module fails at plan time if the
# tenant has not been onboarded yet, surfacing the dependency cleanly).
# ---------------------------------------------------------------------------

data "terraform_remote_state" "tenant" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "catalyst/tenants/${var.tenant}/baseline.tfstate"
    region = var.aws_region
  }
}

# ---------------------------------------------------------------------------
# Per-app customer-managed KMS keys (ADR-016).
#
# Each L4 catalyst-app composite owns its own pair of CMKs (data +
# artifact) so a single app's key compromise never blasts outside the
# tenant/env/project/app blast radius defined by the construct address.
# The module emits aliases `alias/catalyst/data` and `alias/catalyst/
# artifacts` — they're unique because each instance is in its own
# Terraform state file (per-app `.tfstate` per ADR-015 §L4).
#
# CONFLICT-AVOIDANCE NOTE: this is the only new block this PR adds to
# main.tf; #62 and #230 parallel agents are also editing this file.
# ---------------------------------------------------------------------------

module "kms" {
  source = "../../kms"

  admin_role_arn     = var.kms_admin_role_arn
  consumer_role_arns = [aws_iam_role.exec.arn]

  tags = {
    "catalyst:construct" = local.construct_address
    "catalyst:tenant"    = var.tenant
    "catalyst:project"   = var.project
    "catalyst:app"       = var.app
    "catalyst:tier"      = "L4"
  }
}

# ---------------------------------------------------------------------------
# ECR repository for the application's container images.
#
# Naming: {tenant}-{project}-{app} (matches ADR-007 Tier 2 contract and
# the existing v1 stub-handler ARN shape). Scan-on-push + immutable tags
# satisfy ADR-005 supply-chain controls. Per ADR-016 the repository
# encrypts images at rest with the per-app `catalyst_artifact_key`;
# encryption_type cannot be changed in place, so an existing AES256 repo
# must be recreated (runbook in ADR-016 §Migration).
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "app" {
  name                 = local.resource_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = module.kms.artifact_key_arn
  }

  tags = {
    "catalyst:construct" = local.construct_address
    "catalyst:tenant"    = var.tenant
    "catalyst:project"   = var.project
    "catalyst:app"       = var.app
    "catalyst:tier"      = "L4"
  }
}

# ---------------------------------------------------------------------------
# Application execution role.
#
# A single least-privilege role per app: assume-role principal switches
# between Lambda (default + worker) and ECS-tasks (batch) based on
# service_type. CloudWatch Logs write is the only inline permission;
# additional policies (DynamoDB, S3, etc.) are attached by app teams
# through a separate config endpoint that is OUT OF SCOPE for this PR
# (per the issue scope statement).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = [local.assume_service]
    }
  }
}

resource "aws_iam_role" "exec" {
  name               = "${local.resource_name}-${var.service_type == "batch" ? "task" : "exec"}"
  assume_role_policy = data.aws_iam_policy_document.assume.json

  tags = {
    "catalyst:construct" = local.construct_address
    "catalyst:tier"      = "L4"
  }
}

data "aws_iam_policy_document" "exec_logs" {
  statement {
    sid    = "AppLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    # Scope to this app's log group only — least privilege.
    resources = [
      "${aws_cloudwatch_log_group.app.arn}",
      "${aws_cloudwatch_log_group.app.arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "exec_inline" {
  name   = "${local.resource_name}-logs"
  role   = aws_iam_role.exec.id
  policy = data.aws_iam_policy_document.exec_logs.json
}

# ---------------------------------------------------------------------------
# CloudWatch log group for the application.
#
# Path mirrors ADR-007's `/aws/catalyst/{construct_address}` convention
# but uses the explicit four-segment L4 form so the segment order matches
# the state-key hierarchy from ADR-015 exactly.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "app" {
  name              = local.log_group_name
  retention_in_days = var.log_retention_days
  kms_key_id        = module.kms.artifact_key_arn

  tags = {
    "catalyst:construct" = local.construct_address
    "catalyst:tier"      = "L4"
  }
}

# ---------------------------------------------------------------------------
# ALB listener rule for web-service apps.
#
# Worker and batch shapes skip this entirely (count=0). The rule routes
# /${tenant}/${env}/${project}/${app}/* to the supplied target group;
# operators wire the per-app target group elsewhere (the construct address
# in the path is the dispatch key).
# ---------------------------------------------------------------------------

resource "aws_lb_listener_rule" "app" {
  count = local.is_web_service && var.alb_listener_arn != "" ? 1 : 0

  listener_arn = var.alb_listener_arn
  priority     = null

  action {
    type             = "forward"
    target_group_arn = var.alb_target_group_arn
  }

  condition {
    path_pattern {
      values = [local.alb_path_pattern]
    }
  }

  tags = {
    "catalyst:construct" = local.construct_address
    "catalyst:tier"      = "L4"
  }
}

# ---------------------------------------------------------------------------
# Catalog row in the platform-state DynamoDB table.
#
# The L1 catalog table already exists (provisioned by modules/dynamodb at
# bootstrap). The catalyst-app composite adds a single row keyed on the
# construct address so the API can enumerate per-app metadata without
# scanning provider state.
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table_item" "catalog" {
  table_name = var.catalog_table_name
  hash_key   = "pk"
  range_key  = "sk"

  item = jsonencode({
    pk = { S = local.catalog_record_key }
    sk = { S = local.catalog_record_sk }

    construct_address = { S = local.construct_address }
    tenant            = { S = var.tenant }
    environment       = { S = var.environment }
    project           = { S = var.project }
    app               = { S = var.app }
    service_type      = { S = var.service_type }
    ecr_uri           = { S = aws_ecr_repository.app.repository_url }
    execution_role    = { S = aws_iam_role.exec.arn }
    log_group         = { S = aws_cloudwatch_log_group.app.name }
    tier              = { S = "L4" }
  })
}

# ---------------------------------------------------------------------------
# SVC-8 (#62) — ADR-009 ECS alternate-runtime wiring (additive, opt-in).
#
# When var.enable_ecs_runtime = true the composite instantiates the shared
# modules/ecs-alb in task-definition mode, producing:
#   - aws_ecs_task_definition (catalyst-api, Fargate, awsvpc)
#   - aws_iam_role.ecs_execution (ECR pull + logs + secrets, scoped)
#   - aws_iam_role.ecs_task      (DynamoDB + SSM + CloudWatch metrics)
#
# Gated by count so Lambda-only deployments (the ADR-009 default) are
# unchanged. ECS autoscaling (#230) and CMK migration (#228) are wired in
# their own opt-in blocks below.
# ---------------------------------------------------------------------------

module "ecs_runtime" {
  count  = var.enable_ecs_runtime ? 1 : 0
  source = "../../ecs-alb"

  name_prefix           = local.resource_name
  vpc_id                = var.ecs_vpc_id
  public_subnet_ids     = var.ecs_public_subnet_ids
  alb_security_group_id = var.ecs_alb_security_group_id
  target_group_type     = "ip"

  enable_task_definition = true
  container_image_uri    = var.ecs_container_image_uri
  ecr_repository_name    = aws_ecr_repository.app.name
  log_group_name         = aws_cloudwatch_log_group.app.name
  dynamodb_table_name    = var.catalog_table_name
  catalyst_log_level     = var.ecs_log_level
  container_extra_env    = var.ecs_container_extra_env
}

# ---------------------------------------------------------------------------
# Aurora Serverless v2 (ADR-019 / issue #229) — OPT-IN.
#
# Provisioned only when `var.enable_aurora_serverless = true`. Pattern
# mirrors the gated `enable_ecs_runtime` block from #62 — callers
# that don't need RDS keep DynamoDB-only persistence and pay zero cost.
#
# Resource encryption uses the per-app `module.kms.data_key_arn`
# (catalyst_data_key from ADR-016) so a single key revocation blackholes
# the entire app's data plane (DynamoDB + Aurora).
# ---------------------------------------------------------------------------

data "aws_caller_identity" "aurora_consumer" {
  count = var.enable_aurora_serverless ? 1 : 0
}

data "aws_region" "aurora_consumer" {
  count = var.enable_aurora_serverless ? 1 : 0
}

module "aurora" {
  count = var.enable_aurora_serverless ? 1 : 0

  source = "../../aurora-serverless"

  name                        = local.resource_name
  vpc_id                      = var.aurora_vpc_id
  private_subnet_ids          = var.aurora_private_subnet_ids
  consumer_security_group_ids = var.aurora_consumer_security_group_ids
  kms_key_arn                 = module.kms.data_key_arn
  engine_version              = var.aurora_engine_version
  min_capacity                = var.aurora_min_capacity
  max_capacity                = var.aurora_max_capacity

  tags = {
    "catalyst:construct" = local.construct_address
    "catalyst:tenant"    = var.tenant
    "catalyst:project"   = var.project
    "catalyst:app"       = var.app
    "catalyst:tier"      = "L4"
  }
}

# Attach the `rds-db:connect` IAM policy on the runtime exec role so the
# app can authenticate to Aurora as the IAM-mapped `catalyst_app` role via
# RDS IAM auth tokens. Resource ARN shape per the AWS docs:
#   arn:aws:rds-db:{region}:{account}:dbuser:{cluster_resource_id}/{db_user}
data "aws_iam_policy_document" "aurora_connect" {
  count = var.enable_aurora_serverless ? 1 : 0

  statement {
    sid    = "AllowRDSIamAuth"
    effect = "Allow"
    actions = [
      "rds-db:connect",
    ]
    resources = [
      "arn:aws:rds-db:${data.aws_region.aurora_consumer[0].region}:${data.aws_caller_identity.aurora_consumer[0].account_id}:dbuser:${module.aurora[0].cluster_resource_id}/${module.aurora[0].app_db_user}",
    ]
  }
}

resource "aws_iam_role_policy" "aurora_connect" {
  count = var.enable_aurora_serverless ? 1 : 0

  name   = "${local.resource_name}-aurora-connect"
  role   = aws_iam_role.exec.id
  policy = data.aws_iam_policy_document.aurora_connect[0].json
}
