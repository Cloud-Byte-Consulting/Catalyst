# `modules/composite/wa-iac-analyzer`

ADR-023 Phase 1 composite for the AWS [Well-Architected IaC Analyzer](https://github.com/aws-samples/well-architected-iac-analyzer).

> **Status: SCAFFOLD.** This module currently owns zero resources. The
> `var.enable_wa_aws_iac_analyzer` feature flag at the root stack defaults to
> `false`; `terraform plan` on default vars produces NO analyzer resources.
> See ADR-023 §Phase 1 + tracking issue #283.

## Why this module exists at scaffold stage

Issue #283 ships the **flag + the module surface** ahead of Phase 1
implementation so downstream wiring (operator runbooks, observability hooks
from #285, security hardening from #284) can target a stable address. The
implementation PR will replace the empty resource graph with the chosen
deploy approach (see "Discovery" below).

## Discovery: CFN-wrap vs Terraform-native

Per ADR-023 §Phase 1, the implementer must record the deploy-approach
decision **here** before adding real resources. The trade-off:

| Option | Pros | Cons |
| --- | --- | --- |
| **CFN-wrap** — `aws_cloudformation_stack` wrapping the upstream aws-samples deploy template | Lowest divergence from upstream; upstream updates are pull-through; minimal Terraform code | Drift detection opaque to Terraform; ADR-002 construct-address tagging cannot be enforced uniformly; cross-stack outputs are stringly-typed |
| **Terraform-native port** — re-author the ECS Fargate + ALB + Cognito + DynamoDB + S3 Vectors + Bedrock IAM topology in Terraform on top of existing `modules/{network,security-groups,ecs-alb,kms}` | Inherits ADR-005 (supply chain), ADR-008 (RBAC), ADR-009 (runtime), ADR-016 (CMK) controls for free; first-class drift detection; uniform tagging | Higher up-front cost; upstream-template updates require manual port |

### Decision (Phase 1 implementer fills in)

- **Date:** _to be filled in by Phase 1 implementer_
- **Choice:** _CFN-wrap_ OR _Terraform-native_
- **Rationale:** _one paragraph_
- **Rollback:** _one paragraph — what `terraform destroy` (or equivalent) does, and how to confirm the analyzer ALB / Cognito pool / DynamoDB tables are gone_

## Inputs (at scaffold stage)

| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `name_prefix` | `string` | `catalyst-wa-analyzer` | Lowercase + digits + hyphen |
| `vpc_id` | `string` | `""` | Required once Phase 1 lands |
| `subnet_ids` | `list(string)` | `[]` | ECS task subnets |
| `public_subnet_ids` | `list(string)` | `[]` | ALB subnets |
| `bedrock_model_id` | `string` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Mirrors upstream default |
| `tags` | `map(string)` | `{}` | Merged on top of `catalyst:component` + `catalyst:adr` |

## Outputs (at scaffold stage)

All outputs are `null` except `component_tag`, which always returns
`wa-iac-analyzer`. The shapes are fixed so downstream consumers can wire
against them ahead of the Phase 1 implementation PR.

## Feature flag

The root stack wires `var.enable_wa_aws_iac_analyzer` (default `false`)
through `count = var.enable_wa_aws_iac_analyzer ? 1 : 0` on the module
instantiation in `infrastructure/main.tf`. Set
`TF_VAR_enable_wa_aws_iac_analyzer=true` (or override in tfvars) to flip the
module on once Phase 1 implementation lands.

## Zero-impact contract

`terraform plan` on default vars MUST show **zero** analyzer resources. Verify:

```bash
cd infrastructure
terraform plan -out=tfplan
terraform show -json tfplan \
  | jq '.resource_changes[] | select(.address | startswith("module.wa_aws_iac_analyzer"))'
# expected: empty output
```

## Security contract

Tracking issue: **#284** (stacked on #283). This section is the binding
contract the Phase 1 implementation PR will conform to. Reviewers: challenge
the *scope envelope* below, not the resource-attachment plumbing (which
moves with Phase 1).

### IAM least-privilege envelope

Codified as `aws_iam_policy_document` data sources in [`iam.tf`](./iam.tf).
Both documents are `count = 0` at scaffold stage — they are *contracts*, not
roles. The Phase 1 implementer drops in `aws_iam_role` + `aws_iam_role_policy`
that reference these documents (see the implementer-hook block at the bottom
of `iam.tf`).

| Resource | Actions allowed | Resource scope | Rejected at review if |
| --- | --- | --- | --- |
| Bedrock | `InvokeModel`, `InvokeModelWithResponseStream` | `var.bedrock_model_arns` (must be non-empty for the statement to exist) | Adds `bedrock:*`, `ListFoundationModels`, or any wildcard ARN |
| DynamoDB | `GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `Query`, `BatchGet/WriteItem` | `arn:aws:dynamodb:*:<account>:table/<name_prefix>-analyses[/index/*]` | Adds `CreateTable` / `DeleteTable` / `dynamodb:*` |
| S3 (vectors) | `GetObject`, `PutObject`, `DeleteObject` | `arn:aws:s3:::<name_prefix>-vectors-*/*` | Adds `s3:*` or removes the `s3:prefix` condition on `ListBucket` |
| S3 (vectors) | `ListBucket` (scoped via `s3:prefix` to `analyses/*`, `embeddings/*`) | `arn:aws:s3:::<name_prefix>-vectors-*` | Drops the `s3:prefix` condition |
| CloudWatch Logs | `CreateLogStream`, `PutLogEvents` | `arn:aws:logs:*:<account>:log-group:/aws/ecs/<name_prefix>:log-stream:*` | Adds `CreateLogGroup` to the task role (Terraform owns the group) |

**Trust policy.** Only `ecs-tasks.amazonaws.com` may assume the role, and a
confused-deputy guard restricts assumption to ECS tasks in *this* account
(`aws:SourceAccount` condition). NO Lambda, NO EC2 instance profile, NO
cross-account assume.

**Acceptance gate (#284 Scenario 1).** The matrix above contains zero
`Action="*"` and zero `Resource="*"` cells. Any Phase 1 PR that broadens
either fails this contract.

### Cognito group → API permission mapping

Codified as `locals` in [`cognito.tf`](./cognito.tf). Group names follow the
ADR-008 2-segment global form (`catalyst-{role}`), with `wa-analyzer` as the
role-namespace stand-in:

| Cognito group (`var.name_prefix`-`{suffix}`) | UI routes | API actions |
| --- | --- | --- |
| `catalyst-wa-analyzer-readers` | `GET /analyses`, `GET /analyses/:id` | read-only |
| `catalyst-wa-analyzer-admins` | reader routes + `POST /analyses`, `DELETE /analyses/:id` | read + write |
| _no group_ | 401/403 (per #284 Scenario 2) | none |

**User-pool shape contract** (declared inline in `cognito.tf` `locals`,
to be instantiated by Phase 1):

- `mfa_configuration = "ON"` — workforce MFA mandatory per ADR-008
- `advanced_security_mode = "ENFORCED"` — threat protection on
- `admin_create_user_only = true` — no self-signup
- `deletion_protection = "ACTIVE"`
- Minimal attribute schema: `email`, `given_name`, `family_name`, `custom:scope`
- ALB listener action: `authenticate-cognito` with `OnUnauthenticatedRequest = deny` (NOT `authenticate` — anonymous requests must get 401, not a redirect loop)

### Federation decision (Phase 1 implementer fills in)

The composite supports two paths via `var.cognito_user_pool_existing_id`:

| `cognito_user_pool_existing_id` | Behaviour | When to choose |
| --- | --- | --- |
| Non-empty | **Federate** the analyzer against an existing Catalyst SSO user pool. The analyzer creates groups inside the existing pool but does not own the pool. | The operator already runs Catalyst SSO. *Default preference.* |
| Empty (default) | **Dedicated pool** — Phase 1 stands up a fresh `aws_cognito_user_pool` per the `cognito.tf` shape contract. | First-deployment-in-account scenarios where no SSO pool exists yet. *Fallback only.* |

The Phase 1 implementation PR must record the decision in its PR body and,
once chosen, the `Decision (Phase 1 implementer fills in)` row in the
"Discovery" section above. Federation is preferred because it inherits any
existing identity-provider plumbing (SAML / OIDC) and consolidates user
administration.

### Security-relevant inputs (added in #284)

| Name | Type | Default | Why this default |
| --- | --- | --- | --- |
| `bedrock_model_arns` | `list(string)` | `[]` | Empty default = NO Bedrock access. Forces explicit operator approval per ARN. |
| `cognito_user_pool_existing_id` | `string` | `""` | Empty default biases toward the "stand-up-fresh-pool" path; override to federate. |
| `allow_unauthenticated_read` | `bool` | `false` | `false` is the only posture compatible with #284 Scenario 2 on internet-facing ALBs. |

### References

- ADR-008 — Catalyst API RBAC via AWS IAM Groups (group-name convention)
- ADR-010 — egress controls + least-privilege bar
- ADR-023 — Well-Architected IaC Analyzer adoption, Phase 1 security plan
- Issue #284 — this PR
- Issue #283 / PR #296 — the composite scaffold this builds on

## Out of scope at scaffold stage

- `pr-checks.yml` integration → Phase 2 / #286
- Lambda vendoring → Phase 3 / #287
- IAM least-priv + Cognito/RBAC shape → **delivered in #284 (this PR), see §"Security contract" above**
- KMS-CMK encryption everywhere → still deferred, folded into Phase 1 implementation
- Observability wiring (CloudWatch alarms, dashboards, SNS routing) → #285
- Operator runbook entry in `docs/onboarding/platform.md` → folded into #284/#285

## References

- ADR-023 — Well-Architected IaC Analyzer adoption (Phase 1 binding decision)
- Issue #283 — this scaffold
- Upstream: <https://github.com/aws-samples/well-architected-iac-analyzer>
