# tftest for the github branch-protection module.
#
# Lives inside the module directory (`infrastructure/modules/github/tests/`)
# rather than the centralised `infrastructure/tests/` directory because the
# main infrastructure root only declares the `aws` provider in
# `required_providers`. Mixing a `github` provider into that root just for
# this test would pollute it, so the module owns its own test harness.
#
# Run with:
#     terraform -chdir=infrastructure/modules/github test
#
# Provider strategy: the test stays fully offline. The `github` provider is
# configured with a placeholder token and is never asked to authenticate
# because `command = plan` walks the graph without an actual API call for
# `github_branch_protection`. The assertions read back the *input* shape we
# drive into the resource, which is what this module owns.
#
# If a future provider release insists on a live API check at plan time, fall
# back to a plan-only smoke test (drop the assertions; keep `command = plan`)
# — that loses the resource-shape gate but keeps compile-time validation.

provider "github" {
  token = "test-token-not-real"
  owner = "Cloud-Byte-Consulting"
}

run "branch_protection_module_plans" {
  command = plan

  variables {
    repository_name  = "Catalyst"
    repository_owner = "Cloud-Byte-Consulting"
  }

  assert {
    condition     = github_branch_protection.this.pattern == "release"
    error_message = "default protected branch must be `release` per ADR-006"
  }

  assert {
    condition     = github_branch_protection.this.enforce_admins == true
    error_message = "enforce_admins must be true — no admin bypass"
  }

  assert {
    condition     = github_branch_protection.this.allows_force_pushes == false
    error_message = "force pushes must be blocked on the protected branch"
  }

  assert {
    condition     = github_branch_protection.this.allows_deletions == false
    error_message = "the protected branch must not be deletable"
  }

  # Post-#208: the required-status set is a single fan-in `test-summary`
  # aggregator. The 8-context green set is no longer enforced at the
  # branch-protection layer — `test-summary` itself `needs:` every component
  # job and fans their results into one signal. See ADR-006
  # §"Path-filtered component tests".
  assert {
    condition     = length(github_branch_protection.this.required_status_checks[0].contexts) == 1
    error_message = "default required_status_checks must be a single context (`test-summary`) post-#208"
  }

  assert {
    condition     = github_branch_protection.this.required_status_checks[0].contexts == toset(["test-summary"])
    error_message = "default required_status_checks must be exactly [\"test-summary\"] post-#208"
  }

  assert {
    condition     = github_branch_protection.this.required_status_checks[0].strict == true
    error_message = "required_status_checks.strict must be true (branch must be up-to-date)"
  }

  assert {
    condition     = github_branch_protection.this.required_pull_request_reviews[0].required_approving_review_count == 1
    error_message = "Catalyst requires at least one approving PR review by default"
  }

  assert {
    condition     = github_branch_protection.this.required_pull_request_reviews[0].dismiss_stale_reviews == true
    error_message = "stale reviews must be dismissed when new commits land"
  }

  assert {
    condition     = contains(github_branch_protection.this.required_status_checks[0].contexts, "test-summary")
    error_message = "required_status_checks must include the test-summary aggregator context"
  }

  assert {
    condition     = !contains(github_branch_protection.this.required_status_checks[0].contexts, "python-tests")
    error_message = "python-tests is no longer a direct required context post-#208 (it fans into test-summary instead)"
  }
}
