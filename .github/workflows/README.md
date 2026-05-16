# Catalyst GitHub Actions

This directory holds the CI/CD pipelines that drive infrastructure and service
delivery for the Catalyst monorepo. The runtime topology and IAM choices are
captured in [ADR-006](../../docs/ADR/ADR-006-cicd-pipeline-architecture.md) and
[ADR-009](../../docs/ADR/ADR-009-runtime-strategy.md).

## Workflow inventory

| Workflow | Trigger | Purpose | OIDC role secret |
|---|---|---|---|
| `pr-checks.yml` | `pull_request -> release` | Terraform fmt/validate, TFLint, tfsec, Checkov, Trivy, gitleaks, pytest with `--cov-fail-under=85` | none (read-only) |
| `tf-plan.yml` | `pull_request -> release` (paths `infrastructure/**`) | `terraform init && plan`, sticky PR comment | `AWS_ROLE_PLAN_ARN` |
| `tf-apply.yml` | `push -> release` (paths `infrastructure/**`) | `terraform apply -auto-approve` (env `production`) | `AWS_ROLE_APPLY_ARN` |
| `tf-drift.yml` | cron `0 6 * * *` + dispatch | `plan -detailed-exitcode`, SNS publish + auto-issue on exit code 2 | `AWS_ROLE_PLAN_ARN` |
| `service-cd.yml` | `push -> release` (paths `services/catalyst-api/**`) + dispatch | Builds API image, pushes to ECR, deploys to **lambda** or **ecs** based on `RUNTIME` | `AWS_ROLE_DEPLOY_ARN` |
| `validate-policies.yml` | `pull_request -> release` (paths `infrastructure/policy/opa/**`) | `conftest verify` against the OPA policy bundle | none |
| `ci-smoke.yml` | `pull_request -> release` (paths `.github/**`) + dispatch | Workflow-level smoke: `actionlint`, structural validator, optional STS GetCallerIdentity | optional `AWS_ROLE_PLAN_ARN` |

## OIDC role mapping

Roles are provisioned by `infrastructure/modules/iam`:

* `catalyst-github-plan` -> `AWS_ROLE_PLAN_ARN` (subject `pull_request`)
* `catalyst-github-apply` -> `AWS_ROLE_APPLY_ARN` (subject `ref:refs/heads/release`)
* `catalyst-github-deploy` -> `AWS_ROLE_DEPLOY_ARN` (subject `ref:refs/heads/release`)

Every AWS-touching workflow declares `permissions.id-token: write`, uses
`aws-actions/configure-aws-credentials@v4`, and references the matching
secret. The structural validator at `.github/scripts/validate_workflows.py`
enforces this so a regression fails CI before reaching AWS.

## Runtime selection in `service-cd`

`service-cd.yml` resolves `RUNTIME` from, in order:

1. `inputs.runtime` (workflow_dispatch)
2. `vars.RUNTIME` (repository or environment variable)
3. fallback `lambda`

Both branches always build and push the image to ECR, then run only the
matching deploy step (`if: env.RUNTIME == 'lambda'` or `'ecs'`). The
prerequisite step also asserts that the SSM parameter for the chosen runtime
exists, so a misconfigured target fails fast instead of producing a half-deploy.

## API ingress allowlist variable

`tf-plan.yml`, `tf-apply.yml`, and `tf-drift.yml` read the repository/environment
variable `CATALYST_API_INGRESS_ALLOWLIST` and normalize it into
`TF_VAR_alb_ingress_allowlist` before running Terraform.

Expected format is a JSON array (preferred), for example:

```json
["73.239.59.22", "198.51.100.0/24"]
```

Plain IPv4 entries are normalized to `/32`; CIDRs are kept as-is.

## Local reproducer

```bash
pip install pyyaml pytest
python .github/scripts/validate_workflows.py            # 31 PASS / 0 FAIL
pytest .github/scripts/test_workflow_structure.py -v    # 9 passed
```

`actionlint` runs in CI via `raven-actions/actionlint@v2`; install the binary
locally if you want a pre-push check.
