# Branch protection on the GitOps release branch.
#
# Provider note: this module does NOT declare a `provider "github" {}` block.
# The caller's root module is responsible for declaring the provider and
# supplying credentials (typically via the `GITHUB_TOKEN` environment variable
# at apply time). The module consumes whichever provider config is in scope.
# This keeps secrets out of the repo and lets the operator vary auth strategy
# (fine-grained PAT vs. GitHub App) without forking the module.

resource "github_branch_protection" "this" {
  repository_id = var.repository_name
  pattern       = var.protected_branch

  enforce_admins      = true
  allows_force_pushes = false
  allows_deletions    = false

  required_status_checks {
    strict   = true
    contexts = var.required_status_checks
  }

  required_pull_request_reviews {
    required_approving_review_count = var.required_approving_review_count
    dismiss_stale_reviews           = true
    require_code_owner_reviews      = false
  }
}
