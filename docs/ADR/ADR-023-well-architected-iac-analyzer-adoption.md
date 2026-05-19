# ADR-023 — Adopt the AWS Well-Architected IaC Analyzer (deferred Phase 1 deployment)

**Status**: Accepted · 2026-05-19
**Related**: ADR-005 (AWS Agentic Platform Engineering), ADR-008 (RBAC), ADR-009 (Runtime strategy — ECS Fargate option), ADR-010 (Egress controls), ADR-022 (Multi-tool skill layout — `skills/bedrock-binding/` home)
**Upstream**: https://github.com/aws-samples/well-architected-iac-analyzer (MIT-0)

---

## Context

The brief's "Digging deeper" axis weights Option 1 (advanced Terraform tooling), Option 2 (Bedrock in containerized service), and the AI-native-workflow rubric (20%). Catalyst already ships Terraform-quality automation (`tflint` + `tfsec` + `checkov` + `conftest`/OPA in `.github/workflows/pr-checks.yml`) and an internal Bedrock binding (`skills/bedrock-binding/bedrock_mcp_server.py`). The gap is a *Well-Architected-pillar-aware* layer that turns an opinionated framework score into per-PR feedback — none of the existing IaC linters reason about WA pillars.

`aws-samples/well-architected-iac-analyzer` is an AWS-maintained generative-AI application that closes exactly that gap:

| Property | Value |
|---|---|
| What it does | Analyzes Terraform / CloudFormation / CDK / architecture diagrams against AWS Well-Architected pillars + custom lenses |
| Engine | Amazon Bedrock (Claude models) + AWS Well-Architected Tool API + S3 Vectors for embeddings |
| Deployment shape | Containerized React frontend + Node.js/Python backend on ECS Fargate behind an ALB; Cognito/OIDC ingress; DynamoDB metadata; CloudFormation/CDK installer |
| License | **MIT-0** (no attribution required; commercial + private use permitted; modify + redistribute permitted) |
| Standalone vs hosted | Hosted-only — depends on AWS services; must run in an AWS account |
| Extension points | Custom Lenses, an Analyzer Assistant chatbot API, CSV export, document-upload plugins, localization framework |

The architectural primitives the analyzer requires — ECS Fargate, ALB, Bedrock, Cognito/OIDC, DynamoDB — are already first-class in Catalyst. The integration question is not *can it run* but *what integration shape carries the most value for the demo-readiness window and the longer Catalyst arc*.

## Decision

**Accept adoption of the well-architected-iac-analyzer behind a default-off feature flag.** Execute in three phases, each gated by a separate issue + PR.

### Feature flag — the contract for every phase

| Property | Value |
|---|---|
| Variable | `var.enable_wa_aws_iac_analyzer` |
| Type | `bool` |
| Default | `false` — the deployment surface is **off** on every account out of the box |
| Toggle point | Deployment time only (set via `TF_VAR_enable_wa_aws_iac_analyzer=true` in the workflow env, or via tfvars). No runtime toggle, no console knob, no CLI flag |
| Scope of the flag | Wraps the entire WA-Analyzer composite via `count = var.enable_wa_aws_iac_analyzer ? 1 : 0`. When false: zero resources plan, zero AWS spend, zero IAM footprint, zero ALB DNS entries |
| Flip-on prerequisites | Phase 1's readiness checklist (below) must be satisfied — Bedrock + S3 Vectors regional availability, IAM scope review, Cognito decision, cost-model entry, observability wiring |
| Rollback | Flip the flag to `false`, run `terraform apply`. The composite's `count = 0` causes Terraform to destroy all WA-Analyzer resources in a single graph reconciliation |

Rationale for default-off:
- Demo accounts inherit zero analyzer surface area — no idle ECS/ALB/Bedrock cost during the demo prep window
- Production accounts opt-in deliberately after Phase 1 readiness is met — no silent activation
- The flag is itself a documented operator action, recorded in the deployment runbook; flipping it on becomes the canonical Phase 1 commit moment
- Default-off mirrors the existing Catalyst pattern: `enable_ecs_runtime` (#62), `enable_ecs_autoscaling` (#230), `enable_aurora_serverless` (#229), `enable_network_firewall` (ADR-010) — every opt-in capability ships off-by-default and is enabled via TF_VAR_* at apply time

### Cloud-prefixed naming for the post-demo multi-cloud arc

The variable name carries the cloud explicitly (`wa_aws_*`, not just `wa_*`) because Catalyst's post-demo direction is multi-cloud: GCP and Azure tracks will land their own Well-Architected-equivalent analyzers (GCP Architecture Framework, Azure Well-Architected Framework) behind sibling flags. The shape is fixed now so the future flags drop in cleanly without a rename:

| Future flag | Cloud | Status |
|---|---|---|
| `var.enable_wa_aws_iac_analyzer` | AWS | This ADR — accepted, default false |
| `var.enable_wa_gcp_iac_analyzer` | GCP | Future ADR when the GCP track opens |
| `var.enable_wa_azure_iac_analyzer` | Azure | Future ADR when the Azure track opens |

Same convention applies to the CI-side variable: `WA_AWS_ANALYZER_PR_COMMENTS_ENABLED` (the AWS one shipped here); `WA_GCP_*` / `WA_AZURE_*` slots reserved for the future tracks. The `WA_` (Well-Architected) namespace is the umbrella; the `_<CLOUD>_` segment is the per-provider scope.

### Phase 1 (post-demo) — Deploy upstream as-is behind the flag

- New Terraform composite at `infrastructure/modules/composite/wa-iac-analyzer/` instantiated by `module "wa_aws_iac_analyzer"` in `infrastructure/main.tf` with `count = var.enable_wa_aws_iac_analyzer ? 1 : 0`
- Composite either (a) wraps the upstream CloudFormation/CDK installer as a child resource, or (b) re-expresses the deployment in Terraform-native modules using the existing `modules/ecs-alb`, `modules/observability`, `modules/security-groups` primitives — discovery decides
- IAM narrowing: the upstream installer uses AWS-managed PowerUserAccess-style policies; the Catalyst deployment must scope to least-privilege per ADR-008 / ADR-009
- Observability: alarms + dashboard wired into the existing `modules/observability` SNS topic (#63 pattern)
- The flag's default stays `false` post-Phase-1 — flipping to `true` is a per-account operator decision, not a global Catalyst convention

### Phase 2 — Wire into `pr-checks.yml` (also feature-flagged)

- Job that runs `terraform plan -out=tfplan` (already happens in CI) and POSTs the plan to the analyzer's API
- Parse the CSV/JSON response into a GitHub PR comment formatted like the existing `pr-review-triage` summary
- Surfaces WA-pillar scores per PR — turns the analyzer from a "manual web app" into a "PR-aware reviewer"
- **CI-side flag**: a separate repo variable `WA_AWS_ANALYZER_PR_COMMENTS_ENABLED` (string `"true"`/`"false"`, default `"false"`) gates the PR-comment behavior. Even when Phase 1's infrastructure flag is on, the PR comment job stays opt-in to avoid surprising contributors during the Phase 1 stabilization window. Cloud prefix encoded per §Cloud-prefixed naming above

### Phase 3 (optional, longer arc) — Vendor the analyzer logic

- If Phase 1's standing-stateful-service ops cost proves too high relative to value
- Vendor the analyzer's pillar-evaluation logic into a Catalyst-native Lambda invoked per-PR
- Drops the ECS task + ALB idle cost in favor of per-PR Bedrock invocation cost only
- Inherits the same `var.enable_wa_aws_iac_analyzer` flag — vendored or standing, the operator sees one toggle

**This ADR does not authorize Phase 1.** It documents the *adoption decision*. Phase 1 deployment requires a separate issue + Decision Log + PR per the `pr-open-contract` skill (AGENTS.md gate 5).

## Why this design

| Lens | Verdict |
|---|---|
| **License fit** | MIT-0 — strictly permissive; no attribution burden; clean modify + redistribute rights. Lowest possible friction for both as-is deploy (Phase 1) and vendoring (Phase 3). |
| **Architectural fit** | ECS Fargate + ALB + Bedrock matches the Catalyst stack. The analyzer drops onto Catalyst's existing runtime primitives without new platform requirements. |
| **Brief alignment** | Hits Option 1 (advanced Terraform tooling), Option 2 (Bedrock containerized service), and the AI-native-workflow rubric — three rubric surfaces for one adoption. |
| **Operational tail** | Phase 1 adds a stateful service. Real ops cost. Phase 2 amortizes the value across every PR. Phase 3 (if pursued) eliminates the idle baseline. |
| **Cost** | Idle Phase 1: ECS task ≥$25/mo + ALB ~$16/mo + S3 Vectors + DynamoDB baseline. Bedrock per-call $0.003-$0.015 per analysis. ~$50-100/mo idle + per-PR variable. Material; manageable. **Deferred to post-demo precisely because** the demo-window cost budget is tight. |
| **Security posture** | Cognito/OIDC ingress aligns with ADR-008 RBAC; the analyzer ingress will live behind the same allowlist (`var.alb_ingress_allowlist`) as the catalyst-api. Vector storage isolated per-deployment. The upstream's IAM policies need Catalyst-specific narrowing in Phase 1. |

## Consequences

### Positive

- Catalyst gains a Well-Architected-pillar reasoning layer it does not have today
- Three rubric surfaces (OPT1 / OPT2 / AI-native) advanced by a single decision
- Phase 2 turns every PR into a WA-scored event without forcing operators to remember to run the tool
- MIT-0 means future Catalyst-specific extensions (custom lenses for Catalyst conventions, multi-tenant scoping) are unrestricted

### Negative

- Adds a third stateful service to the operator's runbook (alongside catalyst-api and the future Aurora cluster); raises operational complexity
- Bedrock cost is variable per PR; Phase 2 wiring should include a per-PR rate-limit so a runaway re-push does not generate runaway invoice
- Cognito introduces an identity-provider dependency Catalyst does not currently carry — Phase 1 must decide whether to wire to Catalyst SSO or stand up a dedicated user pool
- Standing CloudFormation/CDK deploy vs Terraform-native re-expression is a real fork; Phase 1 discovery must reach a deliberate verdict

### Risk register (tracked into Phase 1's issue)

- **Bedrock model deprecation** — upstream pins to specific Claude versions; needs a model-pinning policy aligned with ADR-005 §AI model lifecycle
- **S3 Vectors regional availability** — confirm us-east-1 / us-west-2 support before Phase 1 starts
- **CloudFormation drift** if Phase 1 wraps the upstream installer — Catalyst's terraform-state model (ADR-015) is the source of truth; mixing CFN drift in is a known anti-pattern

## Alternatives considered

| Option | Verdict |
|---|---|
| **Reject** the adoption | No — the brief weights three options the analyzer hits; rejecting forfeits ~25% of the rubric surface |
| **Adopt and deploy immediately (pre-demo)** | No — adds AWS cost + a stateful service in the demo-prep window; the analyzer is not a demo-required capability |
| **Vendor immediately** (skip Phase 1; build Phase 3 directly) | No — premature; Phase 1's standing-deploy is the cheapest way to validate that the analyzer's WA-pillar output is useful for Catalyst's PR shape. Phase 3 follows from Phase 1 evidence |
| **Adopt only the API contract** (don't deploy the upstream; build a Catalyst-native equivalent) | No — duplicates AWS-maintained work; MIT-0 license makes this unnecessary |
| **Status `Proposed` only** (defer the decision itself) | No — the analyst question is a one-shot decision with a clear verdict; sitting at Proposed for weeks costs time without benefit. Accepted + deferred deployment is the right separation |

## Phase 1 readiness checklist (for the issue that authorizes Phase 1)

The flag stays `false` until **every** item below is signed off in the Phase 1 issue's Decision Log. The flag is the contract surface that decides "are we ready" — flipping it to `true` is the binary outcome of this checklist passing.

- [ ] Confirm Bedrock + S3 Vectors regional availability for the target Catalyst account
- [ ] Decide CloudFormation-wrap vs Terraform-native expression (discovery output: ADR-NN if material divergence)
- [ ] IAM scope review against ADR-008 / ADR-009 — narrow to least-privilege; document any exceptions
- [ ] Cognito identity provider decision (federate to Catalyst SSO vs stand up a dedicated user pool)
- [ ] Cost-model entry in `docs/cost-model.md` for the standing-deploy baseline
- [ ] Alarms wired to the `modules/observability` SNS topic (#63 pattern)
- [ ] Document the per-account flip procedure in `docs/onboarding/platform.md` (operator runbook)
- [ ] Smoke-test the flip-off path: confirm `terraform apply` with the flag flipped back to `false` cleanly destroys every WA-Analyzer resource

## References

- Upstream: https://github.com/aws-samples/well-architected-iac-analyzer
- License: MIT-0 (https://github.com/aws/mit-0)
- AWS Well-Architected Framework: https://aws.amazon.com/architecture/well-architected/
- AWS Well-Architected Tool API: https://docs.aws.amazon.com/wellarchitected/
- Brief options the adoption hits: Option 1 (Advanced Terraform tooling), Option 2 (Bedrock containerized service), AI-native workflow rubric
- Catalyst existing surfaces that overlap: `modules/ecs-alb`, `modules/observability`, `modules/security-groups`, `skills/bedrock-binding`, `.github/workflows/pr-checks.yml`
