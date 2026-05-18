# `infrastructure/branch-protection`

Operator-facing Terraform root that applies the [`infrastructure/modules/github`](../modules/github/) module to lock down the `release` branch of `Cloud-Byte-Consulting/Catalyst` per [#72](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/72) and [ADR-006](../../docs/ADR/ADR-006-cicd-pipeline-architecture.md).

## Why a separate root?

- **CI does not apply this.** Branch protection is a repo-admin concern, and CI never holds a `GITHUB_TOKEN` with `Administration: write`. Keeping this root out of `infrastructure/` means the catalyst-product composite stays free of GitHub credentials.
- **Separate state file.** Per [ADR-015](../../docs/ADR/ADR-015-terraform-state-partitioning.md), L1 platform-wide concerns get sibling state keys. This root writes to `catalyst/branch-protection.tfstate` next to `catalyst/platform.tfstate`.
- **Blast-radius isolation.** A bad plan in the main infra root cannot accidentally rewrite the repo's protection rule, and vice versa.

## One-time apply

Requires:

- AWS credentials with read/write on the bootstrap-managed Terraform state bucket (the same bucket the main infra root uses).
- A GitHub token with `Administration: write` on `Cloud-Byte-Consulting/Catalyst` (fine-grained PAT or GitHub App installation token).

```bash
cd infrastructure/branch-protection

# 1. Auth (no credentials are committed).
export GITHUB_TOKEN=<your fine-grained PAT or GH App token>
# AWS_PROFILE / AWS_ACCESS_KEY_ID etc. must already let you read+write the state bucket.

# 2. Init against the same state bucket the main infra root uses.
terraform init \
  -backend-config="bucket=<state-bucket-from-bootstrap>"

# 3. Plan + apply.
terraform plan
terraform apply
```

Re-run `terraform apply` any time the protection contract changes (new required CI checks, review count, etc.). The module's defaults already encode the canonical Catalyst working agreement, so most callers only need to invoke it.

## What this provisions

A single `github_branch_protection` resource on the `release` branch that requires:

- ≥ 1 approving PR review (stale reviews dismissed on push).
- All canonical CI status checks green: `python-tests`, `cli-tests`, `Analyze (python)`, `terraform-quality`, `Terraform`, `cursor-config`, `conftest`, `workflow-structure`.
- Branch up-to-date with `release` before merge.
- `enforce_admins = true` — no admin bypass.
- No force pushes, no branch deletion.

`actionlint` is excluded from required checks until [#200](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/200) flips it to `fail-on-error: true`. `CODEOWNERS` review is not required because Catalyst has no `CODEOWNERS` file today.

## State layout

```
s3://<bootstrap-bucket>/
  catalyst/platform.tfstate           # infrastructure/  (catalyst-product composite)
  catalyst/branch-protection.tfstate  # this root
```

## Out of scope

- Repository-wide settings (description, default branch, merge-button toggles) — separate kaizen if wanted.
- `CODEOWNERS` file — separate concern.
- The catalyst-product composite — distinct root, distinct state.

## Related

- [`../modules/github/README.md`](../modules/github/README.md) — module reference.
- [#72](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/72) — tracking issue.
- [ADR-006](../../docs/ADR/ADR-006-cicd-pipeline-architecture.md) — CI/CD pipeline architecture and the gate's purpose.
- [ADR-015](../../docs/ADR/ADR-015-terraform-state-partitioning.md) — Terraform state partitioning.
