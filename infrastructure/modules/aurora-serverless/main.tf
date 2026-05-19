# ---------------------------------------------------------------------------
# Aurora Serverless v2 (PostgreSQL 16) — ADR-019 / issue #229.
#
# Module shape (per ADR-019 §Decision):
#   - aws_rds_cluster: aurora-postgresql 16, engine_mode "provisioned" with
#     serverless_v2_scaling_configuration. Encryption at rest uses the
#     catalyst_data_key CMK (ADR-016). IAM database authentication is on.
#   - aws_rds_cluster_instance: at least one writer (db.serverless), with
#     Performance Insights enabled and pointing at the same CMK.
#   - aws_db_subnet_group: built from var.private_subnet_ids (>=2 AZs).
#   - aws_security_group: ingress on 5432 ONLY from var.consumer_security_group_ids
#     (the runtime ECS/Lambda SGs from modules/security-groups).
#   - aws_rds_cluster_parameter_group: log_statement = "ddl" + slow-query
#     capture; log_statement = "all" was rejected as too noisy for any tier
#     above dev.
#   - aws_secretsmanager_secret: break-glass master password. NOT used by
#     app traffic; rotation is intentionally NOT configured here (separate
#     follow-up that pairs with a Secrets-Manager CMK — see ADR-019 §Out
#     of scope).
#   - null_resource bootstrap (Approach A from the Decision Log on #229):
#     a local-exec running `psql` against the cluster to create the
#     application database + catalyst_app role + GRANT rds_iam. SQL is in
#     bootstrap.sql.tftpl so it's version-controlled.
#
# This module is OPT-IN from modules/composite/catalyst-app (gated by
# var.enable_aurora_serverless there); callers that don't need RDS pay
# zero cost.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  cluster_identifier = "${var.name}-cluster"

  base_tags = merge({
    "catalyst:tier"      = "L4"
    "catalyst:construct" = "shared/aurora-serverless"
    "Name"               = var.name
  }, var.tags)
}

# ---------------------------------------------------------------------------
# Security group — ingress on 5432 only from runtime ENIs (ECS/Lambda SGs).
# No CIDR-based ingress is opened; this enforces the "private network only"
# rule from ADR-010 §Egress + the ECS task / Lambda VPC config from #62/#230.
#
# Egress is intentionally left at the AWS default (all-allow) because the
# cluster's own outbound (logs, metrics) needs unrestricted talk to AWS
# service endpoints. The SG attaches only to the cluster ENI which has no
# arbitrary code-execution surface, so unrestricted egress is bounded.
# tfsec:ignore:aws-ec2-no-public-egress-sgr
# ---------------------------------------------------------------------------

resource "aws_security_group" "cluster" {
  name_prefix = "${var.name}-aurora-"
  description = "Aurora Serverless v2 cluster SG. Ingress: 5432/tcp from runtime SGs only. Egress: AWS service endpoints (logs, KMS) — bounded because the SG attaches only to the cluster ENI."
  vpc_id      = var.vpc_id

  tags = local.base_tags
}

# Default-allow egress is OK on the cluster SG because the cluster ENI does
# not execute customer code — it talks to CloudWatch / KMS / Performance
# Insights endpoints only.
# tfsec:ignore:aws-ec2-no-public-egress-sgr
resource "aws_vpc_security_group_egress_rule" "cluster_all" {
  security_group_id = aws_security_group.cluster.id
  description       = "Cluster outbound for CloudWatch Logs + KMS + Performance Insights APIs."
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_ingress_rule" "from_consumer" {
  for_each = toset(var.consumer_security_group_ids)

  description                  = "Allow runtime SG to reach Aurora on 5432/tcp"
  security_group_id            = aws_security_group.cluster.id
  referenced_security_group_id = each.value
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

# ---------------------------------------------------------------------------
# DB subnet group — uses the VPC's private subnets so the cluster ENI has
# no public-internet path. Aurora requires >=2 AZs (validation enforces).
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "this" {
  name        = "${var.name}-subnets"
  description = "Private subnets for the ${var.name} Aurora Serverless v2 cluster."
  subnet_ids  = var.private_subnet_ids

  tags = local.base_tags
}

# ---------------------------------------------------------------------------
# Cluster parameter group.
#
# log_statement = "ddl"   — log every DDL statement (CREATE/ALTER/DROP) so
#                           schema drift is auditable. "all" is too noisy
#                           and was explicitly rejected in the Decision Log.
# log_min_duration_statement = 1000 — capture queries slower than 1s into
#                                     the postgresql log (sent to CloudWatch
#                                     via enabled_cloudwatch_logs_exports).
# rds.force_ssl = 1       — refuse non-TLS connections at the engine. The
#                           Python client sets sslmode=require; this is the
#                           server-side enforcement of the same rule.
# ---------------------------------------------------------------------------

resource "aws_rds_cluster_parameter_group" "this" {
  name        = "${var.name}-pg16"
  family      = "aurora-postgresql16"
  description = "Cluster parameter group for ${var.name} (ADR-019)."

  parameter {
    name  = "log_statement"
    value = "ddl"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }

  tags = local.base_tags
}

# ---------------------------------------------------------------------------
# Break-glass master password.
#
# random_password produces a 32-char password (alphanumeric + symbols
# excluding `'` `"` and `/` so psql + URL-encoded contexts don't choke).
# The secret is created with no rotation configuration — rotation pairs
# with a Secrets Manager CMK (see ADR-019 §Out of scope) and is a separate
# follow-up. App traffic uses IAM auth tokens, not this password.
#
# tfsec:ignore:aws-ssm-secret-use-customer-key — KMS-on-secret is the
# follow-up, deliberately deferred to the next PR per ADR-019.
# ---------------------------------------------------------------------------

resource "random_password" "master" {
  length           = 32
  special          = true
  override_special = "!@#$%^&*()_+-="
}

# tfsec:ignore:aws-ssm-secret-use-customer-key
resource "aws_secretsmanager_secret" "master" {
  name        = "${var.name}/master-credentials"
  description = "Aurora Serverless v2 (${var.name}) break-glass master credentials. NOT used by app traffic; app uses IAM auth tokens. KMS-on-secret deferred to follow-up per ADR-019."

  recovery_window_in_days = 7

  tags = local.base_tags
}

resource "aws_secretsmanager_secret_version" "master" {
  secret_id = aws_secretsmanager_secret.master.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.master.result
    engine   = "postgres"
    host     = aws_rds_cluster.this.endpoint
    port     = aws_rds_cluster.this.port
    dbname   = var.database_name
  })
}

# ---------------------------------------------------------------------------
# Cluster — engine_mode "provisioned" + serverless_v2_scaling_configuration
# is the AWS-blessed combo for Aurora Serverless v2 (the previous v1
# engine_mode = "serverless" is on a deprecation glide path).
#
# storage_encrypted = true with the catalyst_data_key CMK satisfies ADR-016.
# iam_database_authentication_enabled = true is the load-bearing flag for
# the IAM-auth client path from the issue's Gherkin AC.
# ---------------------------------------------------------------------------

resource "aws_rds_cluster" "this" {
  cluster_identifier              = local.cluster_identifier
  engine                          = "aurora-postgresql"
  engine_mode                     = "provisioned"
  engine_version                  = var.engine_version
  database_name                   = var.database_name
  master_username                 = var.master_username
  master_password                 = random_password.master.result
  port                            = 5432
  db_subnet_group_name            = aws_db_subnet_group.this.name
  vpc_security_group_ids          = [aws_security_group.cluster.id]
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.this.name

  # Storage + auth.
  storage_encrypted                   = true
  kms_key_id                          = var.kms_key_arn
  iam_database_authentication_enabled = true

  # CloudWatch logs export for postgresql logs (driven by the parameter
  # group's log_statement / log_min_duration_statement settings).
  enabled_cloudwatch_logs_exports = ["postgresql"]

  # Backup + lifecycle.
  backup_retention_period   = var.backup_retention_days
  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name}-final-${formatdate("YYYYMMDDhhmmss", timestamp())}"

  serverlessv2_scaling_configuration {
    min_capacity = var.min_capacity
    max_capacity = var.max_capacity
  }

  tags = local.base_tags

  lifecycle {
    # final_snapshot_identifier uses timestamp() which would otherwise
    # force a no-op diff on every plan.
    ignore_changes = [final_snapshot_identifier]
  }
}

# ---------------------------------------------------------------------------
# Writer instance (Aurora Serverless v2 still requires at least one
# aws_rds_cluster_instance; "db.serverless" is the marker instance class
# that lets the cluster scale via the serverless_v2_scaling_configuration).
#
# performance_insights_enabled satisfies the issue scope; the KMS key for
# Performance Insights matches the cluster CMK so a single key revocation
# fully blackholes the data plane.
# ---------------------------------------------------------------------------

resource "aws_rds_cluster_instance" "writer" {
  identifier         = "${var.name}-writer-0"
  cluster_identifier = aws_rds_cluster.this.id
  engine             = aws_rds_cluster.this.engine
  engine_version     = aws_rds_cluster.this.engine_version
  instance_class     = "db.serverless"

  db_subnet_group_name = aws_db_subnet_group.this.name
  publicly_accessible  = false

  performance_insights_enabled          = true
  performance_insights_kms_key_id       = var.kms_key_arn
  performance_insights_retention_period = var.performance_insights_retention_period

  tags = local.base_tags
}

# ---------------------------------------------------------------------------
# Bootstrap — Approach A (null_resource + local-exec psql).
#
# We deliberately did NOT pull in the cyrilgdn/postgresql provider here
# (see Decision Log on #229 + ADR-019). The trade-off:
#
#   + Narrower provider footprint (no third-party provider authz dance).
#   + SQL is version-controlled in bootstrap.sql.tftpl.
#   - Requires `psql` on the apply host (CI uses ubuntu-latest which has it).
#   - Cannot drift-detect — if someone hand-edits the role outside the
#     bootstrap, Terraform won't notice. The follow-up to add the
#     postgresql provider is documented in ADR-019.
#
# Trigger is keyed on the cluster ARN so the bootstrap runs once on first
# apply; later cluster modifications don't re-trigger it. The script is
# idempotent (CREATE IF NOT EXISTS / DO blocks) so even a re-trigger
# wouldn't corrupt state.
# ---------------------------------------------------------------------------

resource "null_resource" "bootstrap" {
  triggers = {
    cluster_arn = aws_rds_cluster.this.arn
    secret_arn  = aws_secretsmanager_secret_version.master.arn
    sql_hash = sha256(templatefile("${path.module}/bootstrap.sql.tftpl", {
      database_name = var.database_name
      app_db_user   = var.app_db_user
    }))
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOT
      set -euo pipefail
      SECRET_ARN='${aws_secretsmanager_secret.master.arn}'
      CRED_JSON=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" --query SecretString --output text)
      PGPASSWORD=$(printf '%s' "$CRED_JSON" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["password"])')
      export PGPASSWORD
      psql "host=${aws_rds_cluster.this.endpoint} port=${aws_rds_cluster.this.port} user=${var.master_username} dbname=${var.database_name} sslmode=require" <<'SQL'
${templatefile("${path.module}/bootstrap.sql.tftpl", {
    database_name = var.database_name
    app_db_user   = var.app_db_user
})}
SQL
    EOT
}

depends_on = [aws_rds_cluster_instance.writer]
}
