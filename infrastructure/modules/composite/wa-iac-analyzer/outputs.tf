# ---------------------------------------------------------------------------
# wa-iac-analyzer — outputs (ADR-023 Phase 1 scaffold).
#
# All outputs are null at scaffold time. Their shapes are fixed here so
# downstream consumers (operator runbooks, the platform catalog) can wire
# against the module ahead of the Phase 1 implementation PR without a
# breaking-change cycle.
# ---------------------------------------------------------------------------

output "alb_dns_name" {
  description = "DNS name of the ALB fronting the analyzer UI. Null at scaffold stage; populated when Phase 1 implementation lands."
  value       = null
}

output "cognito_user_pool_arn" {
  description = "ARN of the Cognito user pool gating the analyzer UI. Null at scaffold stage."
  value       = null
}

output "ecs_service_name" {
  description = "Name of the ECS Fargate service running the analyzer. Null at scaffold stage."
  value       = null
}

output "component_tag" {
  description = "The catalyst:component tag value applied to every analyzer resource once Phase 1 implementation lands. Available at scaffold stage as a structural contract."
  value       = local.component_tags["catalyst:component"]
}
