output "ecr_uri" {
  description = "ECR repository URL for the application's container images. Format: {account}.dkr.ecr.{region}.amazonaws.com/{tenant}-{project}-{app}."
  value       = aws_ecr_repository.app.repository_url
}

output "execution_role_arn" {
  description = "ARN of the Lambda exec role (or ECS task role for service_type=batch) provisioned for this application."
  value       = aws_iam_role.exec.arn
}

output "log_group_name" {
  description = "CloudWatch log group name for the application. Conforms to /aws/catalyst/{tenant}/{env}/{project}/{app}."
  value       = aws_cloudwatch_log_group.app.name
}

output "alb_listener_rule_arn" {
  description = "ARN of the ALB listener rule routing this app's path prefix. Null when service_type != 'web-service' or when no listener was supplied."
  value       = local.is_web_service && length(aws_lb_listener_rule.app) > 0 ? aws_lb_listener_rule.app[0].arn : null
}

output "catalog_record_key" {
  description = "Composite key (pk + '|' + sk) of the catalog row written for this app in the platform-state DynamoDB table."
  value       = "${local.catalog_record_key}|${local.catalog_record_sk}"
}

output "construct_address" {
  description = "Canonical construct address (tenant/env/lz/project/app) computed from the inputs. Useful for downstream consumers."
  value       = local.construct_address
}

# ---------------------------------------------------------------------------
# SVC-8 (#62) — ADR-009 ECS alternate-runtime outputs.
#
# Null when enable_ecs_runtime = false (the Lambda-default path). Wired
# here so downstream consumers (CD pipeline, runbooks, observability) can
# discover the task definition + role ARNs without round-tripping through
# SSM.
# ---------------------------------------------------------------------------

output "ecs_task_definition_arn" {
  description = "ARN of the catalyst-api Fargate task definition. Null when enable_ecs_runtime = false."
  value       = try(module.ecs_runtime[0].task_definition_arn, null)
}

output "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution role (image pull + log write + secrets read). Null when enable_ecs_runtime = false."
  value       = try(module.ecs_runtime[0].ecs_execution_role_arn, null)
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role (DynamoDB + SSM + CloudWatch metrics). Null when enable_ecs_runtime = false."
  value       = try(module.ecs_runtime[0].ecs_task_role_arn, null)
}

# ---------------------------------------------------------------------------
# Aurora Serverless v2 outputs (ADR-019 / issue #229).
#
# All null when `var.enable_aurora_serverless = false` so existing
# consumers (that don't read these fields) remain unaffected. The
# count-gated module emits a 1-element list; we unwrap via try() so the
# outputs degrade cleanly when the module is disabled.
# ---------------------------------------------------------------------------

output "aurora_cluster_arn" {
  description = "ARN of the Aurora Serverless v2 cluster, or null when `enable_aurora_serverless = false`."
  value       = try(module.aurora[0].cluster_arn, null)
}

output "aurora_cluster_endpoint" {
  description = "Writer endpoint hostname for the Aurora cluster, or null when disabled. Apps target this via psycopg + RDS IAM auth tokens."
  value       = try(module.aurora[0].cluster_endpoint, null)
}

output "aurora_cluster_reader_endpoint" {
  description = "Reader endpoint hostname for the Aurora cluster, or null when disabled."
  value       = try(module.aurora[0].cluster_reader_endpoint, null)
}

output "aurora_cluster_resource_id" {
  description = "Stable Aurora cluster resource id (`cluster-XXXX...`) used in the `rds-db:connect` IAM policy ARN. Null when disabled."
  value       = try(module.aurora[0].cluster_resource_id, null)
}

output "aurora_database_name" {
  description = "Aurora initial database name. Null when disabled."
  value       = try(module.aurora[0].database_name, null)
}

output "aurora_app_db_user" {
  description = "PostgreSQL role mapped to IAM auth (`catalyst_app` by default). Null when disabled."
  value       = try(module.aurora[0].app_db_user, null)
}

output "aurora_secret_arn" {
  description = "ARN of the break-glass master credentials in Secrets Manager. NOT used by app traffic. Null when disabled."
  value       = try(module.aurora[0].secret_arn, null)
}

output "aurora_security_group_id" {
  description = "ID of the Aurora cluster security group. Null when disabled."
  value       = try(module.aurora[0].security_group_id, null)
}
