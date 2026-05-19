# `infrastructure/modules/github`

Terraform module that codifies GitHub branch protection on Catalyst's `release` branch using the `integrations/github` provider's `github_branch_protection` resource. Tracks [#72](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/72) and supports [ADR-006](../../../docs/ADR/ADR-006-cicd-pipeline-architecture.md).

## Purpose

`release` is the GitOps target for the Catalyst Terraform pipeline (plan/apply/drift) and the Catalyst service-CD pipeline. Merging there should not be possible until:

- a human has approved the PR (≥ 1 review, stale reviews dismissed on push),
- the canonical CI status checks are all green,
- the branch is up-to-date with `release`,
- and the rule cannot be bypassed by repository admins.

This module wraps a single `github_branch_protection` resource that encodes those guarantees.

## Provider

The module declares the required-providers entry but **does NOT** declare a `provider "github" {}` block. The caller's root module owns the provider config and is responsible for supplying credentials. The recommended pattern is:

```hcl
terraform {
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

provider "github" {
  owner = "Cloud-Byte-Consulting"
  # GITHUB_TOKEN env var is read automatically; do not hard-code tokens.
}

module "branch_protection" {
  source           = "../modules/github"
  repository_name  = "Catalyst"
  repository_owner = "Cloud-Byte-Consulting"
}
```

## Authentication

`GITHUB_TOKEN` is supplied **at apply time** by the operator via environment variable; no credentials are committed to the repo and CI does NOT apply this resource. The token must be either:

- a **fine-grained PAT** scoped to `Cloud-Byte-Consulting/Catalyst` with `Administration: Read and write` (required for branch-protection management) and `Metadata: Read-only` (implicit), or
- a **GitHub App** installation token with the same `Administration: write` permission.

Classic PATs (`repo` scope) also work but are not recommended; prefer fine-grained tokens.

## Variables

| Name | Type | Default | Description |
|---|---|---|---|
| `repository_name` | `string` | — (required) | Name of the GitHub repository (e.g. `Catalyst`). |
| `repository_owner` | `string` | — (required) | Owning org/user (e.g. `Cloud-Byte-Consulting`). Used for outputs and documentation; the provider itself reads the owner from its own config. |
| `protected_branch` | `string` | `"release"` | Branch pattern to protect. |
| `required_status_checks` | `list(string)` | `["test-summary"]` (see below) | CI contexts that must pass before merge. |
| `required_approving_review_count` | `number` | `1` | Minimum approving reviews on a PR. |

### Default `required_status_checks`

```
test-summary
```

Post-[#208](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/208) the default is a **single context**: `test-summary`. This is a fan-in aggregator job in `.github/workflows/pr-checks.yml` that:

- `needs:` every conditional component-test job (`python-tests`, `cli-tests`, `terraform-quality`, `cursor-config`, `workflow-structure`, `conftest`, `bootstrap-script-tests`, `actionlint`, `e2e-tests`),
- runs `if: always()` so it executes even when upstreams skipped,
- treats `skipped` upstream jobs as pass (the path-filter intentionally excluded that component for the PR),
- fails when any upstream reports `failure` or `cancelled`.

Pinning the required set to this single aggregator is what allows a doc-only PR (where every component test skips) to still merge — the previous 8-context green set blocked that case. See [`.claude/skills/test-coverage-discipline/SKILL.md`](../../../.claude/skills/test-coverage-discipline/SKILL.md) for the full changed-path → CI-job map and the three full-suite escape hatches, and [ADR-006 §"Path-filtered component tests"](../../../docs/ADR/ADR-006-cicd-pipeline-architecture.md) for the architectural rationale.

## Outputs

| Name | Description |
|---|---|
| `protected_branch_pattern` | The branch pattern this rule protects. |
| `branch_protection_id` | Node ID of the underlying `github_branch_protection` resource. |
| `repository_full_name` | `owner/repo` string built from the input variables. |

## Behaviour locked in by `main.tf`

- `enforce_admins = true` — no admin bypass.
- `allows_force_pushes = false`, `allows_deletions = false`.
- `required_status_checks.strict = true` — branch must be up-to-date with the base before merge.
- `required_pull_request_reviews.dismiss_stale_reviews = true`.
- `required_pull_request_reviews.require_code_owner_reviews = false` — Catalyst has no `CODEOWNERS` file today.
- `required_linear_history` is **not** set; squash-merge is the working convention and a linear-history requirement would block merge commits unnecessarily.

## Operator workflow

This module is consumed from `infrastructure/branch-protection/`, a small operator-facing root that lives outside the catalyst-product composite and is **not** applied by CI. See that root's README for the apply commands.

## Related

- [#72](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/72) — tracking issue
- [ADR-006](../../../docs/ADR/ADR-006-cicd-pipeline-architecture.md) — CI/CD pipeline architecture
- [ADR-015](../../../docs/ADR/ADR-015-terraform-state-partitioning.md) — Terraform state partitioning (`catalyst/branch-protection.tfstate` lives at the L1 sibling level)
