# Catalyst

Catalyst is an Internal Developer Platform control plane for AWS. This repository contains deployable infrastructure modules, a FastAPI control-plane service, CI/CD workflows, and interface artifacts (CLI + GitHub Action).

## Get started

Onboarding into Catalyst is **three audience-sliced tracks** ([ADR-012](./docs/ADR/ADR-012-onboarding-experience.md)). Pick the one that matches your role:

| Track | Audience | Runbook | Outcome |
|---|---|---|---|
| **A — Platform** | Cloud / platform engineering | [`docs/onboarding/platform.md`](./docs/onboarding/platform.md) | Fresh AWS account ready for GitOps; Catalyst API reachable from allowlisted networks |
| **B — Organization** | Team / lab leaders (Owners) | [`docs/onboarding/organization.md`](./docs/onboarding/organization.md) | Tenant hierarchy registered (OUs, landing zones, environments) |
| **C — Application** | Application teams (Administrators) | [`docs/onboarding/application.md`](./docs/onboarding/application.md) | App onboarded onto an existing tenant via `POST /services/onboard` |

The index at [`docs/onboarding/README.md`](./docs/onboarding/README.md) explains the cross-track sequencing.

## Agent IDE setup

For **coding agents** (Cursor, Claude Code, Gemini CLI) — not AWS platform operators:

1. Clone the repo and run `python platform/bootstrap.py` ([ADR-024](./docs/ADR/ADR-024-unified-agent-config-and-issue-indexing.md)).
2. Follow [`docs/AGENT-GETTING-STARTED.md`](./docs/AGENT-GETTING-STARTED.md) — bootstrap → pick IDE → [`AGENTS.md`](./AGENTS.md) workflow → issue context + persona routing.
3. Per-tool config details: [`docs/multi-tool-config.md`](./docs/multi-tool-config.md).

- **Self-deploy** via `catalyst products deploy catalyst-api --construct <addr>` — exercise the platform's own product-deploy contract on Catalyst itself ([`docs/products.md`](./docs/products.md), CAT-3 / [#103](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/103)).

## Repository layout

- `infrastructure/`: Terraform modules and tests for backend, network, IAM, runtime, and security controls.
- `services/catalyst-api/`: FastAPI service implementing Tier 1/Tier 2 golden paths plus product catalog and inventory endpoints.
- `clients/catalyst-cli/`: Knack-based CLI for invoking Catalyst API endpoints.
- `.github/workflows/`: CI/CD pipelines for quality checks, plan/apply, runtime deploy, drift detection, and policy validation.
- `docs/ADR/`: Accepted architectural decisions.
- `docs/onboarding/`: Audience-sliced onboarding runbooks (platform / organisation / application) per [ADR-012](./docs/ADR/ADR-012-onboarding-experience.md).
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

Recently shipped (release):

- **KMS module + CMK at rest** for DynamoDB, ECR, and CloudWatch log groups — closes the AWS-managed-key gaps from [ADR-016 §CMK strategy](./docs/ADR/ADR-016-cmk-key-strategy.md) (#228 / #234).
- **ECS Fargate task definition + execution/task roles** wired alongside the Lambda runtime per the runtime switch in [ADR-009](./docs/ADR/ADR-009-runtime-strategy.md) (#62 / #232).
- **ECS app autoscaling** — CPU + `ALBRequestCountPerTarget` target tracking on the Fargate service (#235).
- **Aurora Serverless v2 + IAM-auth Postgres** with `GET /deployment-history` endpoint backed by Aurora reads — see [ADR-019](./docs/ADR/ADR-019-aurora-serverless-iam-auth.md) (#229 / #234).

1. Once per account, run the bootstrap script (or trigger
   `bootstrap-smoke.yml` with `run_aws_validation: true, allow_live_changes: true`).
   **New operator? Start here: [`docs/onboarding/`](./docs/onboarding/)** — the three onboarding tracks (platform / organisation / application) per [ADR-012](./docs/ADR/ADR-012-onboarding-experience.md). For the day-0 step-by-step, [`docs/operator-bootstrap.md`](./docs/operator-bootstrap.md) is the canonical sequence (linked from `docs/onboarding/platform.md`).
2. Configure the `Catalyst` GitHub Actions environment with the variables and
   secrets listed in [`.github/workflows/README.md`](./.github/workflows/README.md)
   (the operator runbook in the previous step walks through this).
3. Open a PR touching `infrastructure/**`; the `Terraform` job in `terraform.yml`
   runs `plan` automatically and sticky-comments the rendered plan.
4. Merge to `release`; the same `terraform.yml` workflow runs `apply` against
   the bootstrap-managed apply role. `tf-drift.yml` runs nightly.

Once the stack is up, run the [smoke-test runbook](./docs/smoke-tests.md) to verify Lambda + ALB are healthy. For the interview-panel walkthrough, see the [6-minute demo script](./docs/demo-script.md).

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
# Copy .env.example to .env and fill in values (see services/catalyst-api/.env.example)
cp services/catalyst-api/.env.example services/catalyst-api/.env
# Edit .env with your local configuration
uvicorn catalyst.main:app --app-dir services/catalyst-api --reload
```

Run tests:

```bash
# API service (gate: 93.83% coverage)
pip install -r services/catalyst-api/requirements-dev.txt
pytest services/catalyst-api/tests --cov=services/catalyst-api/catalyst --cov-branch --cov-fail-under=93.83

# CLI client (gate: 80% coverage; live tests opt-in via -m live)
pip install -r clients/catalyst-cli/requirements-dev.txt
pytest clients/catalyst-cli/tests -m 'not live' --cov=catalyst_cli --cov-branch --cov-fail-under=80
```

CLI live-stack smoke (opt-in, runs against a deployed Catalyst ALB):

```bash
export CATALYST_API_ENDPOINT="http://catalyst-alb-XXXX.us-east-1.elb.amazonaws.com"
pytest -m live clients/catalyst-cli/tests -v
```

See [`docs/smoke-tests.md`](./docs/smoke-tests.md) for the full smoke-test runbook (curl + pytest paths).

## Architecture

Seven diagrams cover the system at different cuts — three Mermaid (render inline in GitHub) and four Draw.io (open in any Draw.io editor). See **[`diagrams/README.md`](./diagrams/README.md)** for the full index, audience descriptions, and authoring conventions.

GitHub-inline (Mermaid):

- **[`diagrams/control-plane.md`](./diagrams/control-plane.md)** — request path (caller → ALB → Lambda → DynamoDB/SSM/STS), provisioning tiers (bootstrap vs pipeline), and the phase-ordering sequence enforced by `terraform.yml` + `service-cd.yml`.
- **[`diagrams/ha.md`](./diagrams/ha.md)** — multi-AZ ECS topology with Aurora Serverless v2, NAT redundancy, and the failure-mode coverage table. This is the scale-out variant of ADR-009; the demo runs Lambda.
- **[`diagrams/gitops.md`](./diagrams/gitops.md)** — PR → plan comment → review → apply → deploy → andon flow, OIDC role separation per pipeline phase, and the andon-signal pattern where drift becomes a `state/pending` issue.

Draw.io (open in your IDE plugin or app.diagrams.net):

- **[`diagrams/network-layer.drawio`](./diagrams/network-layer.drawio)** — VPC + subnets + NAT (one per AZ) + IGW + VPC endpoints (implemented vs ADR-010 target) + 3 security groups + ALB ingress allowlist. Audience: cloud / network engineer.
- **[`diagrams/application-layer.drawio`](./diagrams/application-layer.drawio)** — request path + persistence + SigV4 RBAC + runtime swap to ECS Fargate. Audience: service developer.
- **[`diagrams/agentic-workflow.drawio`](./diagrams/agentic-workflow.drawio)** — six AGENTS.md gates, Issues state machine, peer-review sub-agent fork, OIDC role separation per phase, drift andon flow. Audience: interview panel + future agents.
- **[`diagrams/cicd-pipeline.drawio`](./diagrams/cicd-pipeline.drawio)** — all nine GitHub Actions workflows mapped to triggers, quality + security gates (tfsec, Checkov, Trivy, gitleaks, OPA conftest, SARIF + SBOM), OIDC roles per phase, and outcomes. Audience: DevOps / platform engineer.

See also [ADR-001 through ADR-011](./docs/ADR/) for the design decisions these diagrams encode. The Catalyst agentic-workflow operating contract is captured in [ADR-011](./docs/ADR/ADR-011-catalyst-agentic-workflow.md) (citing [`AGENTS.md`](./AGENTS.md) as the source of truth). Authoring conventions for new diagrams live in [`.claude/skills/draw-aws-diagrams/SKILL.md`](./.claude/skills/draw-aws-diagrams/SKILL.md).

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
