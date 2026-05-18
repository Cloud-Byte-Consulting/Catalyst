output "protected_branch_pattern" {
  description = "Branch pattern that this module protects."
  value       = var.protected_branch
}

output "branch_protection_id" {
  description = "Node ID of the github_branch_protection resource (useful for downstream auditing)."
  value       = github_branch_protection.this.id
}

output "repository_full_name" {
  description = "owner/repo string the rule applies to (built from the input variables)."
  value       = "${var.repository_owner}/${var.repository_name}"
}
