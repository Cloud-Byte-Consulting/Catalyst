---
name: github-actions-design
description: >
  GitHub Actions workflow patterns: OIDC role assumption (no static keys),
  reusable workflows, policy-as-code gates (tflint, tfsec, Checkov,
  OPA/Conftest, terraform test), PR plan comments, environment protection
  rules, and matrix strategies. Use when creating or modifying
  .github/workflows/.
---
<!-- Vendored from: platform-catalyst/skills/github-actions-design/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->


## Role

Workflow engineer producing secure, auditable, and maintainable GitHub Actions
pipelines for the Catalyst IDP. Every workflow assumes OIDC federation — no
static AWS credentials exist in this system.

## Instructions

### 1. OIDC role assumption

Use `aws-actions/configure-aws-credentials@<pinned-sha>` with:

```yaml
permissions:
  id-token: write
  contents: read
```

Configure `role-to-assume` from repository variables. Set
`audience: sts.amazonaws.com`. Never store `AWS_ACCESS_KEY_ID` or
`AWS_SECRET_ACCESS_KEY` as repository secrets — they do not exist.

### 2. Reusable workflow pattern for Terraform plan/apply

Define a callable workflow (`.github/workflows/tf-plan-apply.yml`) with inputs:
`working_directory`, `environment`, `terraform_version`. The plan job runs on
every PR push; the apply job runs only after merge to `main` with environment
protection gate. State is stored in `catalyst-tf-state-${acct}` S3 backend
with DynamoDB lock table.

### 3. Policy-as-code gate ordering

Execute gates in strict sequence — failure at any step halts the pipeline:

1. `terraform fmt -check -recursive`
2. `tflint --init && tflint`
3. `tfsec .`
4. `checkov -d . --framework terraform`
5. `conftest test . -p policy/` (OPA/Rego)
6. `terraform test`

Each gate runs as a separate step (not a composite action) so failure is
visible in the Actions UI as a distinct red step.

### 4. PR plan comment

After `terraform plan -out=tfplan`, render human-readable output and post via
`actions/github-script`:

```yaml
- uses: actions/github-script@<pinned-sha>
  with:
    script: |
      const plan = core.getInput('plan_output');
      await github.rest.issues.createComment({
        owner: context.repo.owner,
        repo: context.repo.repo,
        issue_number: context.issue.number,
        body: `### Terraform Plan\n\`\`\`\n${plan}\n\`\`\``
      });
```

Collapse large plans with `<details>` tags to keep PRs readable.

### 5. Environment protection rules

- `staging` — auto-deploy on merge, no approval required.
- `production` — requires 1 reviewer approval, 10-minute wait timer,
  restricted to `main` branch only.

Define environments in Terraform via the `github_repository_environment`
resource in the `github-bootstrap` module.

### 6. Matrix strategy for multi-module testing

Use `matrix.module` derived from changed paths (via `dorny/paths-filter` or
`tj-actions/changed-files`). Run `terraform test` in parallel for each
modified module directory under `infrastructure/modules/`.

### 7. Pipeline as code (CI/CD Design Patterns)

Per Bajpai et al: treat the pipeline definition as a first-class artifact —
version-controlled, reviewed, tested. The reusable workflow is the pipeline
template; calling workflows are thin declarations. Test pyramid in CI: unit
tests (pytest, terraform test) run first and fast; integration tests
(localstack, testcontainers) gate staging; e2e (deployed environment) gate
production.

### 8. Custom GitHub Action for customer Score submissions

The published action (under `.github/actions/catalyst-submit/` or a dedicated
repo) accepts inputs:

- `score_file` — path to the customer's `score.yaml`
- `construct_address` — optional override (defaults to repo-derived address)
- `notify_slack` — optional boolean

The action:
1. Validates Score against the pinned spec (`../spec/` JSON Schema).
2. Calls `catalyst-api` `/submissions` endpoint (OIDC token as bearer).
3. Opens or updates the automation GitHub Issue for state tracking.
4. Posts plan status as a PR check annotation.

## Output

- YAML files under `.github/workflows/` with explicit `permissions:` blocks.
- Composite actions under `.github/actions/` with `action.yml` metadata.
- All secrets referenced via `${{ secrets.* }}` or `${{ vars.* }}` — never
  inline values.

## Guardrails

- Never use `pull_request_target` with checkout of PR HEAD (injection risk).
- Never use `actions/checkout` with `persist-credentials: true` unless
  explicitly needed for push operations.
- Never hardcode AWS account IDs or region in workflow files — source from
  repository variables.
- Never use `continue-on-error: true` on security gates.
- Always pin action versions to full SHA, not mutable tags (supply-chain
  hardening).
