variable "repository_name" {
  type        = string
  description = "Name of the GitHub repository the protection rule applies to (e.g. \"Catalyst\")."
}

variable "repository_owner" {
  type        = string
  description = "GitHub owner (org or user) that owns the repository (e.g. \"Cloud-Byte-Consulting\"). Surfaced as a variable for documentation / output use; the provider itself resolves the owner from its own provider config."
}

variable "protected_branch" {
  type        = string
  description = "Branch pattern to protect. Catalyst protects `release` because that is the GitOps target per ADR-006."
  default     = "release"
}

variable "required_status_checks" {
  type        = list(string)
  description = <<-EOT
    Required CI status-check contexts that must pass before a PR can merge into
    the protected branch. The default is a single context: `test-summary`.

    `test-summary` is a fan-in aggregator job in `.github/workflows/pr-checks.yml`
    (added by #208) that `needs:` every conditional component-test job
    (python-tests, cli-tests, terraform-quality, cursor-config,
    workflow-structure, conftest, bootstrap-script-tests, actionlint,
    e2e-tests) and runs `if: always()`. It treats `skipped` upstream jobs as
    pass (the path-filter intentionally excluded that component for the PR)
    and fails when any upstream reports `failure` or `cancelled`.

    Pinning the required-status set to this single aggregator is what allows
    a doc-only PR (where every component test skips) to still merge — the
    previous canonical 8-context green set blocked that case. See ADR-006
    §"Path-filtered component tests" and #208 for the full rationale.

    Override only when a future workflow surface needs an out-of-band
    required check that doesn't fan into `test-summary`.
  EOT
  default = [
    "test-summary",
  ]
}

variable "required_approving_review_count" {
  type        = number
  description = "Number of approving PR reviews required before merge. Catalyst's working agreement is at least one human approval."
  default     = 1
}
