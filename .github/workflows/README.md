# Catalyst GitHub Actions

This directory holds the CI/CD pipelines that drive infrastructure and service
delivery for the Catalyst monorepo. The runtime topology and IAM choices are
captured in [ADR-006](../../docs/ADR/ADR-006-cicd-pipeline-architecture.md) and
[ADR-009](../../docs/ADR/ADR-009-runtime-strategy.md).

## Division of responsibility: bootstrap vs Terraform pipeline

Catalyst is split into two ownership tiers. Everything outside the bootstrap
tier MUST be managed by Terraform through the GitHub Actions pipeline.

| Tier | What it owns | How it is provisioned |
|---|---|---|
| Bootstrap (one-time) | IAM bootstrap-admin role, GitHub OIDC provider, `catalyst-github-{plan,apply,deploy}` roles, RBAC IAM groups, Terraform state S3 bucket, Terraform DynamoDB lock table, Catalyst API data S3 bucket | `scripts/bootstrap-aws-account.sh` (or `.ps1`), validated by `bootstrap-smoke.yml`. Runs once per account. |
| Terraform pipeline (ongoing) | VPC + subnets + NAT + gateway endpoints, security groups (incl. ALB ingress allowlist), ECR, ECS cluster + ALB + target group, Lambda runtime, DynamoDB platform-state table, optional Network Firewall | `terraform.yml` (consolidated PR plan + release apply), `tf-drift.yml` nightly. Root config at `infrastructure/`. |
| Service deploy | Container image build, push to ECR, point Lambda image / ECS service at the new tag | `service-cd.yml` on `release` (`services/catalyst-api/**`). |

Adding net-new AWS resources for the Catalyst platform means a Terraform PR
that the pipeline plans and applies — never a one-off script or console click.

## Workflow inventory

| Workflow | Trigger | Purpose | OIDC role secret |
|---|---|---|---|
| `pr-checks.yml` | `pull_request -> release` | Terraform fmt/validate, TFLint, tfsec, Checkov, Trivy, gitleaks, pytest with `--cov-fail-under=85` | none (read-only) |
| `terraform.yml` | `pull_request -> release` and `push -> release` (paths `infrastructure/**`) + dispatch | Consolidated HashiCorp-style pipeline: `terraform init` (S3 backend + DynamoDB lock), `fmt -check`, `plan -lock=false` (sticky PR comment) on PRs, `apply -auto-approve` on release push | `AWS_ROLE_PLAN_ARN` for PR runs, `AWS_ROLE_APPLY_ARN` for release push (selected via `role-to-assume` expression on `github.event_name`) |
| `tf-drift.yml` | cron `0 6 * * *` + dispatch | `plan -detailed-exitcode -lock=false`, SNS publish + auto-issue on exit code 2 | `AWS_ROLE_PLAN_ARN` |
| `service-cd.yml` | `push -> release` (paths `services/catalyst-api/**`) + dispatch | Builds API image, pushes to ECR, deploys to **lambda** or **ecs** based on `RUNTIME` | `AWS_ROLE_DEPLOY_ARN` |
| `bootstrap-smoke.yml` | `pull_request -> release` (paths `scripts/bootstrap-aws-account.*`) + dispatch | Bash/PowerShell syntax + pytest smoke; optional live AWS validation | `BOOTSTRAP_AWS_VALIDATION_ROLE_ARN` |
| `validate-policies.yml` | `pull_request -> release` (paths `infrastructure/policy/opa/**`) | `conftest verify` against the OPA policy bundle | none |
| `ci-smoke.yml` | `pull_request -> release` (paths `.github/**`) + dispatch | Workflow-level smoke: `actionlint`, structural validator, optional STS GetCallerIdentity | optional `AWS_ROLE_PLAN_ARN` |

## OIDC role mapping

Roles are provisioned by `scripts/bootstrap-aws-account.sh`:

* `catalyst-github-plan` → `AWS_ROLE_PLAN_ARN` (subject `pull_request`, `ReadOnlyAccess`)
* `catalyst-github-apply` → `AWS_ROLE_APPLY_ARN` (subject `ref:refs/heads/release`, `PowerUserAccess` + scoped inline `CatalystApplyIAMScoped` for `iam:*` against `catalyst-*` roles/policies, see ADR-008)
* `catalyst-github-deploy` → `AWS_ROLE_DEPLOY_ARN` (subject `ref:refs/heads/release`, `PowerUserAccess`)

Every AWS-touching workflow declares `permissions.id-token: write`, uses
`aws-actions/configure-aws-credentials@v4`, and references the matching
secret. The structural validator at `.github/scripts/validate_workflows.py`
enforces this so a regression fails CI before reaching AWS.

> Note on plan role and state locking: the plan role's `ReadOnlyAccess` policy
> cannot write to the DynamoDB lock table. `terraform.yml` (PR runs) and
> `tf-drift.yml` therefore pass `-lock=false`, which is safe because both
> commands are read-only. `terraform.yml` on `push -> release` (apply path)
> holds the lock normally with the apply role.

## Environment + variables

> The tf-* workflows intentionally do NOT bind to a GitHub Actions environment.
> The bootstrap-provisioned `catalyst-github-{plan,apply,deploy}` roles trust
> the JWT subjects `repo:OWNER/REPO:pull_request` and
> `repo:OWNER/REPO:ref:refs/heads/release`. Adding an `environment:` binding
> mutates the JWT `sub` to include `:environment:<name>` and breaks the
> AssumeRoleWithWebIdentity call. To gate tf-apply behind a manual environment
> approval (e.g. `production`), first update the bootstrap-managed role trust
> policies to accept the env-scoped subject, then re-add `environment:` here.

The following Actions variables MUST be set at repository scope (or, once the
trust policies are extended, on the bound environment):

| Variable | Purpose |
|---|---|
| `BOOTSTRAP_AWS_ACCOUNT_ID` | Account hosting Catalyst. Used to compute the backend bucket name. |
| `BOOTSTRAP_AWS_REGION` | Region for all Catalyst resources (also the backend region). |
| `BOOTSTRAP_GITHUB_REPOSITORY` | Repo allowed to assume the OIDC roles. |
| `BOOTSTRAP_ADMIN_PRINCIPAL_ARN` | IAM principal allowed to assume the bootstrap admin role. |
| `BOOTSTRAP_CATALYST_PREFIX` | Optional. Defaults to `catalyst`. Resource prefix used by bootstrap + Terraform. |
| `CATALYST_API_INGRESS_ALLOWLIST` | JSON array of IPv4 CIDRs (or bare IPs) allowed to reach the public ALB on 443. Flows into `TF_VAR_alb_ingress_allowlist` in `terraform.yml` and `tf-drift.yml`. |

The following secrets MUST be set at repository scope:

| Secret | Purpose |
|---|---|
| `AWS_ROLE_PLAN_ARN` | ARN of `catalyst-github-plan` role. |
| `AWS_ROLE_APPLY_ARN` | ARN of `catalyst-github-apply` role. |
| `AWS_ROLE_DEPLOY_ARN` | ARN of `catalyst-github-deploy` role. |
| `DRIFT_SNS_TOPIC_ARN` | Optional. Topic notified by `tf-drift.yml` on drift. |

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

`terraform.yml` and `tf-drift.yml` read the environment variable
`CATALYST_API_INGRESS_ALLOWLIST` and normalize it into
`TF_VAR_alb_ingress_allowlist` before running Terraform. The root config in
`infrastructure/main.tf` passes the value to `modules/security-groups` which
attaches the corresponding `aws_vpc_security_group_ingress_rule` resources to
the public ALB.

Expected format is a JSON array (preferred), for example:

```json
["73.239.59.22", "198.51.100.0/24"]
```

Plain IPv4 entries are normalized to `/32`; CIDRs are kept as-is.

## Local reproducer

```bash
pip install pyyaml pytest
python .github/scripts/validate_workflows.py            # structural validator
pytest .github/scripts/test_workflow_structure.py -v
```

```bash
# Quick Terraform validation (no AWS calls)
export AWS_ACCESS_KEY_ID=AKIATESTTESTTESTTEST
export AWS_SECRET_ACCESS_KEY=TESTTESTTESTTESTTESTTESTTESTTESTTESTTEST
export AWS_REGION=us-east-1
terraform -chdir=infrastructure init -backend=false
terraform -chdir=infrastructure fmt -recursive -check
terraform -chdir=infrastructure validate
terraform -chdir=infrastructure test
```

`actionlint` runs in CI via `raven-actions/actionlint@v2`; install the binary
locally if you want a pre-push check.
