# ---------------------------------------------------------------------------
# SVC-8 — ECS task EXECUTION role (per ADR-009 §IAM roles per runtime).
#
# The execution role is assumed by the ECS agent / Fargate runtime ITSELF
# (principal: ecs-tasks.amazonaws.com) to:
#   - Pull the application image from ECR
#   - Write container stdout/stderr to CloudWatch Logs
#   - Decrypt Secrets Manager values referenced in the task definition
#
# It is distinct from the *task* role (iam-task.tf), which is the
# application's own AWS identity. Lambda collapses both into one execution
# role; ECS keeps them split per ADR-009.
#
# All resources here are gated by var.enable_task_definition so a
# Lambda-only deployment does not provision unused IAM surface.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {
  count = var.enable_task_definition && var.aws_account_id == "" ? 1 : 0
}

data "aws_region" "current" {
  count = var.enable_task_definition && var.aws_region == "" ? 1 : 0
}

locals {
  # Account ID and region are resolved from explicit vars when supplied
  # (tftest path, since data.aws_caller_identity hits STS during plan).
  # Fall back to the data sources for real applies where creds exist.
  ecs_account_id = var.enable_task_definition ? (
    var.aws_account_id != "" ? var.aws_account_id : data.aws_caller_identity.current[0].account_id
  ) : ""
  ecs_region = var.enable_task_definition ? (
    var.aws_region != "" ? var.aws_region : data.aws_region.current[0].region
  ) : ""

  # ARN of the catalyst-api ECR repo. Caller passes in the repository URL or
  # name; we always normalise to an explicit ARN to avoid cross-account
  # ambiguity. Pattern matches the L1 modules/ecr resource shape.
  catalyst_api_ecr_arn = var.enable_task_definition ? (
    "arn:aws:ecr:${local.ecs_region}:${local.ecs_account_id}:repository/${var.ecr_repository_name}"
  ) : ""

  catalyst_log_group_arn = var.enable_task_definition ? (
    "arn:aws:logs:${local.ecs_region}:${local.ecs_account_id}:log-group:${var.log_group_name}"
  ) : ""

  # Secrets Manager: scope to catalyst-* secret names only (per issue #62
  # scope). The trailing -* allows the AWS-mandated random suffix that
  # Secrets Manager appends to every secret ARN.
  catalyst_secrets_arn_pattern = var.enable_task_definition ? (
    "arn:aws:secretsmanager:${local.ecs_region}:${local.ecs_account_id}:secret:catalyst-*"
  ) : ""
}

data "aws_iam_policy_document" "ecs_execution_assume" {
  count = var.enable_task_definition ? 1 : 0

  statement {
    sid     = "EcsTasksAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  count              = var.enable_task_definition ? 1 : 0
  name               = "${var.name_prefix}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_execution_assume[0].json

  tags = {
    "catalyst:role" = "ecs-execution"
    "catalyst:adr"  = "ADR-009"
  }
}

# ECR: pull the catalyst-api image. GetAuthorizationToken is account-scoped
# by AWS (it does not accept a resource list), so it appears in its own
# statement; the per-repo actions are scoped to the catalyst-api repo ARN.
data "aws_iam_policy_document" "ecs_execution_inline" {
  count = var.enable_task_definition ? 1 : 0

  statement {
    sid    = "EcrAuthToken"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "EcrPullCatalystApi"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = [local.catalyst_api_ecr_arn]
  }

  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      local.catalyst_log_group_arn,
      "${local.catalyst_log_group_arn}:*",
    ]
  }

  statement {
    sid    = "SecretsManagerReadCatalyst"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [local.catalyst_secrets_arn_pattern]
  }
}

resource "aws_iam_role_policy" "ecs_execution_inline" {
  count  = var.enable_task_definition ? 1 : 0
  name   = "${var.name_prefix}-ecs-execution-inline"
  role   = aws_iam_role.ecs_execution[0].id
  policy = data.aws_iam_policy_document.ecs_execution_inline[0].json
}

output "ecs_execution_role_arn" {
  value       = try(aws_iam_role.ecs_execution[0].arn, null)
  description = "ARN of the ECS task execution role (image pull + log write + secrets read). Null when enable_task_definition = false."
}
