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

## Observability

Phase 1 observability **contract** (#285, stacked on #283). The composite
declares the log group, three alarms, and one dashboard up-front so the
Phase 1 implementer wires them automatically when the ECS / ALB / DynamoDB
resources land. Everything inherits the root `count = 0` gate — at default
vars `terraform plan` shows zero observability resources.

### CloudWatch log group

- **Name:** `/aws/ecs/${var.name_prefix}` (default `/aws/ecs/catalyst-wa-analyzer`)
- **Retention:** `var.log_retention_days` (default `30` per ADR-015 §Log retention)
- **Encryption:** When `var.log_group_kms_key_arn` is set, the group is
  CMK-encrypted via the ADR-016 artifact-key pattern; otherwise the AWS-owned
  CloudWatch Logs key is used so the scaffold remains zero-impact before the
  CMK lands.

### Alarms (three)

| Alarm | Metric | Threshold | Evaluation | Rationale |
| --- | --- | --- | --- | --- |
| `${name_prefix}-5xx-rate` | `AWS/ApplicationELB:HTTPCode_Target_5XX_Count` (Sum, 60s) | `> 5` | 3 of 3 | Sustained backend errors from the ECS Fargate tasks once Phase 1 provisions the ALB. |
| `${name_prefix}-bedrock-throttling` | `AWS/Bedrock:InvocationThrottles` (Sum, 60s, ModelId dimension) | `> 0` | 5 of 5 | Heavy Bedrock consumer; throttling means review requests are silently failing. |
| `${name_prefix}-task-restarts` | `ECS/ContainerInsights:DesiredTaskCount - RunningTaskCount` (Average, 300s) | `> 1` | 2 of 2 | ECS crash loops surfaced before user reports. |

Thresholds were chosen to match the SVC-9 module's posture (#63): noisy
enough to catch real degradation, conservative enough to skip transient
single-event blips. Tune via tfvars once Phase 1 baselines exist.

### Dashboard

One `aws_cloudwatch_dashboard` named `${name_prefix}-operator` with four
panels:

1. **Top-left** — ALB request count + target-5xx (per minute)
2. **Top-right** — Bedrock invocation latency p50 / p99 for `${bedrock_model_id}`
3. **Middle-left** — DynamoDB consumed RCU / WCU on `${dynamodb_table_name}`
4. **Middle-right** — ECS running vs desired task count

A trailing text widget summarises the three alarms + the SNS wiring. The
dashboard JSON IS the visualization — no separate diagram needed.

### SNS wiring (shared `catalyst-alerts` topic from #63)

The composite accepts `var.sns_topic_arn` (default `""`). When empty, each
alarm declares `alarm_actions = []`: the alarm is observable in the
console but does **not** page. The root stack will wire the shared
`catalyst-alerts` topic produced by `modules/observability` (#63) into this
composite once Phase 1 lands. This mirrors the #235 ECS-autoscaling
topic-ARN-via-variable pattern and respects the ADR-014 operator-alert
fan-out posture.

### References

- ADR-014 — operator-alert posture (shared SNS topic, no per-team pagers in
  the module)
- ADR-015 — log retention (30 days default)
- ADR-016 — artifact key / CMK encryption pattern
- Issue #63 + `infrastructure/modules/observability` — the SVC-9 alarm +
  dashboard pattern this composite reuses
- Issue #235 — the ECS-autoscaling `sns_topic_arn`-via-variable pattern

## Out of scope at scaffold stage

- `pr-checks.yml` integration → Phase 2 / #286
- Lambda vendoring → Phase 3 / #287
- Security hardening (IAM narrowing, KMS-CMK encryption everywhere) → #284
- PagerDuty / Slack subscribers on the SNS topic — out-of-band per #63
- Operator runbook entry in `docs/onboarding/platform.md` → folded into #284

## References

- ADR-023 — Well-Architected IaC Analyzer adoption (Phase 1 binding decision)
- Issue #283 — this scaffold
- Upstream: <https://github.com/aws-samples/well-architected-iac-analyzer>
