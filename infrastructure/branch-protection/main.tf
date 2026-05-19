# Operator-facing root that applies the branch-protection module.
#
# This root is intentionally separate from `infrastructure/` so:
#   - The CI plan/apply pipeline does NOT touch it (no GITHUB_TOKEN in CI).
#   - The state key lives at its own L1 sibling per ADR-015
#     (`catalyst/branch-protection.tfstate`).
#
# Apply once per repo, then re-apply whenever the protection contract changes:
#
#     cd infrastructure/branch-protection
#     export GITHUB_TOKEN=...
#     terraform init -backend-config="bucket=<state-bucket-from-bootstrap>"
#     terraform apply
#
# The GITHUB_TOKEN must have `Administration: write` on the target repository
# (fine-grained PAT or GitHub App installation token). See README.md.

provider "github" {
  owner = var.repository_owner
  # GITHUB_TOKEN is read from the environment.
}

module "branch_protection" {
  source = "../modules/github"

  repository_name  = var.repository_name
  repository_owner = var.repository_owner
  protected_branch = var.protected_branch
}

output "protected_branch_pattern" {
  description = "Branch pattern that this root has protected."
  value       = module.branch_protection.protected_branch_pattern
}

output "repository_full_name" {
  description = "owner/repo string the rule applies to."
  value       = module.branch_protection.repository_full_name
}
