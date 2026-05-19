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
    the protected branch. The default is the canonical Catalyst green set
    confirmed from recent merged PRs against `release`:

      - python-tests
      - cli-tests
      - Analyze (python)      # CodeQL job display name
      - terraform-quality
      - Terraform              # plan job from terraform.yml
      - cursor-config
      - conftest
      - workflow-structure

    `actionlint` is intentionally excluded — it is advisory today (post-#198)
    and will be added once #200 flips it to `fail-on-error: true`.
  EOT
  default = [
    "python-tests",
    "cli-tests",
    "Analyze (python)",
    "terraform-quality",
    "Terraform",
    "cursor-config",
    "conftest",
    "workflow-structure",
  ]
}

variable "required_approving_review_count" {
  type        = number
  description = "Number of approving PR reviews required before merge. Catalyst's working agreement is at least one human approval."
  default     = 1
}
