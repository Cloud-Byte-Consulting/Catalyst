output "vpc_id" {
  value       = module.network.vpc_id
  description = "VPC the Catalyst platform runs in."
}

output "alb_dns_name" {
  value       = module.ecs_alb.alb_dns_name
  description = "Public DNS of the Catalyst API ALB."
}

output "alb_target_group_arn" {
  value       = module.ecs_alb.target_group_arn
  description = "ALB target group used by both Lambda and ECS runtime variants."
}

output "ecs_cluster_arn" {
  value       = module.ecs_alb.cluster_arn
  description = "ECS cluster ARN (used by service-cd when RUNTIME=ecs)."
}

output "lambda_function_arn" {
  value       = module.lambda_service.function_arn
  description = "Lambda function ARN (used by service-cd when RUNTIME=lambda)."
}

output "ecr_repository_url" {
  value       = module.ecr.repository_url
  description = "ECR repository the Catalyst API image is pushed to."
}

output "platform_state_table" {
  value       = module.dynamodb.table_name
  description = "DynamoDB table the runtime uses for control-plane state."
}

output "network_firewall_enabled" {
  value       = var.enable_network_firewall
  description = "Whether the optional egress firewall is provisioned."
}
