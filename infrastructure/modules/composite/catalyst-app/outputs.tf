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
