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

## Out of scope at scaffold stage

- `pr-checks.yml` integration → Phase 2 / #286
- Lambda vendoring → Phase 3 / #287
- Security hardening (IAM narrowing, KMS-CMK encryption everywhere) → #284
- Observability wiring (CloudWatch alarms, dashboards, SNS routing) → #285
- Operator runbook entry in `docs/onboarding/platform.md` → folded into #284/#285

## References

- ADR-023 — Well-Architected IaC Analyzer adoption (Phase 1 binding decision)
- Issue #283 — this scaffold
- Upstream: <https://github.com/aws-samples/well-architected-iac-analyzer>
