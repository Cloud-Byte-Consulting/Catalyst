output "ssm_parameter_arns" {
  description = "Map of SSM parameter ARNs provisioned for this tenant, keyed by 'env/parameter-name'."
  value = merge(
    { for env_name, p in aws_ssm_parameter.landing_zone_account_id : "${env_name}/landing-zone-account-id" => p.arn },
    { for env_name, p in aws_ssm_parameter.compliance_tier : "${env_name}/compliance-tier" => p.arn },
  )
}

output "iam_group_names" {
  description = "Names of the three tenant-scoped IAM groups (owners/administrators/viewers)."
  value       = { for role, g in aws_iam_group.tenant_scoped : role => g.name }
}

output "vpc_ids" {
  description = "Map env name -> VPC id for the per-environment VPCs."
  value       = { for env_name, m in module.network : env_name => m.vpc_id }
}

output "network_firewall_enabled" {
  description = "True when the compliance posture requires AWS Network Firewall (ADR-010)."
  value       = local.firewall_required
}
