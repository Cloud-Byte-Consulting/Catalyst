# Catalyst

Catalyst is an Internal Developer Platform control plane for AWS. This repository contains deployable infrastructure modules, a FastAPI control-plane service, CI/CD workflows, and interface artifacts (CLI + GitHub Action).

## Repository layout

- `infrastructure/`: Terraform modules and tests for backend, network, IAM, runtime, and security controls.
- `services/catalyst-api/`: FastAPI service implementing Tier 1/Tier 2 golden paths plus product catalog and inventory endpoints.
- `clients/catalyst-cli/`: Knack-based CLI for invoking Catalyst API endpoints.
- `.github/workflows/`: CI/CD pipelines for quality checks, plan/apply, runtime deploy, drift detection, and policy validation.
- `docs/ADR/`: Accepted architectural decisions.
- `docs/ai-workflow-narrative.md`: Evidence of the AGENTS.md operating contract — PRs cited, decision logs, peer-review trail.
- `diagrams/`: Architecture diagrams (mermaid sources, rendered inline by GitHub) — see [Architecture](#architecture) below.

## Deploy

Catalyst splits provisioning into two tiers; the GitHub Actions pipeline is the
single source of truth for everything outside the one-time bootstrap. See
[`.github/workflows/README.md`](./.github/workflows/README.md) for the full
table.

| Tier | Owns | How |
|---|---|---|
| Bootstrap (one-time) | IAM bootstrap-admin role, GitHub OIDC provider, `catalyst-github-{plan,apply,deploy}` roles, RBAC IAM groups, Terraform state S3 bucket, Terraform DynamoDB lock table, Catalyst API data S3 bucket | `scripts/bootstrap-aws-account.sh` |
| Pipeline (ongoing) | VPC + subnets + NAT + endpoints, security groups (incl. ALB allowlist), ECR, ECS cluster + ALB + target group, Lambda runtime, DynamoDB platform-state table, optional Network Firewall | `terraform.yml` (PR plan + release apply, single consolidated workflow) → `tf-drift.yml` (daily) |
| Service deploy | Catalyst API container image build/push + runtime update | `service-cd.yml` |

1. Once per account, run the bootstrap script (or trigger
   `bootstrap-smoke.yml` with `run_aws_validation: true, allow_live_changes: true`).
   **New operator? Start here: [`docs/operator-bootstrap.md`](./docs/operator-bootstrap.md)** —
   what to gather (AWS auth choice, account-id, admin principal ARN, region), where to get
   each value, and the full post-run secret/variable setup with verification commands.
2. Configure the `Catalyst` GitHub Actions environment with the variables and
   secrets listed in [`.github/workflows/README.md`](./.github/workflows/README.md)
   (the operator runbook in the previous step walks through this).
3. Open a PR touching `infrastructure/**`; the `Terraform` job in `terraform.yml`
   runs `plan` automatically and sticky-comments the rendered plan.
4. Merge to `release`; the same `terraform.yml` workflow runs `apply` against
   the bootstrap-managed apply role. `tf-drift.yml` runs nightly.

For local sanity checks (no AWS calls):

```bash
terraform -chdir=infrastructure init -backend=false
terraform -chdir=infrastructure fmt -recursive -check
terraform -chdir=infrastructure validate
terraform -chdir=infrastructure test
```

Run API locally:

```bash
pip install -r services/catalyst-api/requirements.txt
uvicorn catalyst.main:app --app-dir services/catalyst-api --reload
```

Run tests:

```bash
pip install -r services/catalyst-api/requirements-dev.txt
pytest services/catalyst-api/tests --cov=services/catalyst-api/catalyst --cov-branch --cov-fail-under=85
```

## Architecture

Three diagrams cover the system at different cuts. All are committed as markdown with mermaid sources; GitHub renders them inline.

- **[`diagrams/control-plane.md`](./diagrams/control-plane.md)** — request path (caller → ALB → Lambda → DynamoDB/SSM/STS), provisioning tiers (bootstrap vs pipeline), and the phase-ordering sequence enforced by `terraform.yml` + `service-cd.yml`.
- **[`diagrams/ha.md`](./diagrams/ha.md)** — multi-AZ ECS topology with Aurora Serverless v2, NAT redundancy, and the failure-mode coverage table. This is the scale-out variant of ADR-009; the demo runs Lambda.
- **[`diagrams/gitops.md`](./diagrams/gitops.md)** — PR → plan comment → review → apply → deploy → andon flow, OIDC role separation per pipeline phase, and the andon-signal pattern where drift becomes a `state/pending` issue.

See also [ADR-001 through ADR-010](./docs/ADR/) for the design decisions these diagrams encode.

## Runtime configuration

Resolution order per setting: explicit env var → SSM parameter (`CATALYST_*_PARAMETER`) → Secrets Manager secret (`CATALYST_*_SECRET`) → built-in default.

| Setting | Env var | Default | Notes |
|---|---|---|---|
| Repository backend | `CATALYST_REPOSITORY` | `memory` | Set to `dynamodb` in production. |
| DynamoDB table name | `CATALYST_DYNAMODB_TABLE` or `CATALYST_DYNAMODB_TABLE_PARAMETER` | resolved from SSM in prod | Module: `infrastructure/modules/dynamodb`. |
| Auth mode | `CATALYST_AUTH_MODE` | `headers` | `sigv4` enforces presigned-STS verification + `iam:ListGroupsForUser`. |
| Group cache TTL | `CATALYST_GROUP_CACHE_TTL` | `300` (seconds) | Per-process IAM group cache. |
| Runtime secrets | `CATALYST_RUNTIME_SECRET_<KEY>_SECRET` | unset | Names a Secrets Manager secret for `<KEY>`. |
| API ingress allowlist (pipeline var) | `CATALYST_API_INGRESS_ALLOWLIST` | `["73.239.59.22"]` | JSON array; plain IPv4 entries are normalized to `/32` and passed to Terraform as `TF_VAR_alb_ingress_allowlist`. |

## Runtime strategy

`service-cd.yml` supports runtime selection via `RUNTIME=lambda|ecs` (default `lambda`), aligned with ADR-009.

## RBAC scoped group format

Scoped RBAC groups use `catalyst-{tenant}--{project}--{role}` to avoid tenant/project
parsing ambiguity. Migration notes and backward-compatibility behavior are documented in
`docs/migrations/2026-05-15-rbac-scoped-group-delimiter.md`.

## Demo cost management

The Catalyst demo environment auto-destructs nightly at 22:00 UTC Mon–Fri via `teardown-scheduled.yml`. All Terraform-managed resources (VPC, NAT, ECS, Lambda, ALB, ECR, DynamoDB) are destroyed; bootstrap resources (IAM, OIDC provider, S3 state, DynamoDB lock) are preserved.

To rebuild after teardown or to trigger teardown on demand, see **[`docs/teardown.md`](./docs/teardown.md)**.

## Decision records

Use `DECISIONS.md` as a pointer to canonical ADRs in `docs/ADR/`.
