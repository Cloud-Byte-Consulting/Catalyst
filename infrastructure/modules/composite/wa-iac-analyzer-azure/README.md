# wa-iac-analyzer-azure — DEFERRED placeholder

## Status

**DEFERRED** per the [#288 Azure parity spike](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/288)
(verdict landed in [PR #294](https://github.com/Cloud-Byte-Consulting/Catalyst/pull/294)).

This directory holds **no Terraform code**. It exists to:

1. Reserve the composite-module address `infrastructure/modules/composite/wa-iac-analyzer-azure/`
   alongside the AWS-track sibling for ADR-023.
2. Record the deferred posture for future operators.
3. Cross-reference the spike that produced the verdict.

There is no `main.tf`, no `variables.tf`, no `outputs.tf` in this directory by
design — the [#277](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/277)
pattern says do not ship unused Terraform that fails `tflint`.

## Trigger to revisit

Revisit this placeholder when **all** of the following conditions hold (lifted
from the spike's §4 Recommendation):

1. At least one Azure workload exists under `infrastructure/composite/` or
   `infrastructure/landing-zone/` with non-trivial Bicep or `azurerm`
   resources — i.e. there is something to analyze.
2. ADR-023 Phase 1 (the AWS Well-Architected IaC Analyzer deployment) has
   shipped and produced at least 30 days of PR-comment telemetry, so we have
   a baseline for what "good" looks like before paying to clone it.
3. A pharmacy / insurance customer or internal product has a binding Azure
   delivery requirement that the third-party scanner stack (Tier-1 below)
   cannot satisfy on its own.

The operational signal that condition 1 is approaching is the first
`lz/azure-*` labeled issue landing in this repo.

## Naming slot reserved

Per ADR-023 §Cloud-prefixed naming, the binding flag for the Azure parity
stack is:

```hcl
variable "enable_wa_azure_iac_analyzer" {
  type        = bool
  default     = false
  description = "Enable the Azure parity stack for ADR-023 (Well-Architected IaC analysis). Currently DEFERRED per docs/spike/azure-wa-iac-analyzer-spike.md."
}
```

This variable is **declared in this README only**. It is not added to
`infrastructure/variables.tf` until there is a consumer — declaring an unused
variable would trip `tflint`'s `terraform_unused_declarations` rule.

The corresponding AWS slot is `var.enable_wa_iac_analyzer` (ADR-023).

Future construct-address labels (also reserved by the spike):

- `lz/azure-shared` — Azure shared-services landing zone
- `lz/azure-workload-*` — per-workload Azure landing zones
- `app/wa-azure-iac-analyzer` — application label if Tier-2 / Tier-3 is pursued

## Implementation path when revived — Tier-1 entry

Per the spike's §4 cost/ops estimate, the entry path when the revival trigger
fires is **Tier-1, option 2.4** from the spike:

- **Effort**: ~1 engineer-week
- **Ops cost**: $0 (CI-only, no Azure infrastructure stood up)
- **Tooling**: add Checkov Azure policy packs and
  [PSRule for Azure](https://azure.github.io/PSRule.Rules.Azure/) to
  `.github/workflows/pr-checks.yml`, gated behind the
  `var.enable_wa_azure_iac_analyzer` flag
- **Coverage**: ~60–70% of the WAF surface deterministically, with no
  data leaving the GitHub Actions runner

Tier-2 (Azure-native DIY: Azure OpenAI + ARG + Container Apps + Cosmos +
AI Search) and Tier-3 (fork the AWS analyzer) remain options for later if
Tier-1 proves insufficient — see the spike for the full comparison matrix
and ~6–14 engineer-week estimates.

## Why not now

The spike's verbatim rationale: Catalyst has zero Azure footprint today.
Building a Tier-2 or Tier-3 stack means standing up Container Apps + Cosmos
DB + AI Search + Application Gateway + an Entra ID tenant configuration
**before there is any Azure IaC to point the analyzer at**. That inverts
the dependency arrow and burns 6–14 engineer-weeks on a tool with no users.

## Spike-doc cross-reference

The full survey, comparison matrix, recommendation, and open questions
live in `docs/spike/azure-wa-iac-analyzer-spike.md` on the
[`spike-azure-wa-iac-analyzer-288`](https://github.com/Cloud-Byte-Consulting/Catalyst/tree/spike-azure-wa-iac-analyzer-288/docs/spike/azure-wa-iac-analyzer-spike.md)
branch (PR #294). Once that PR merges, the canonical path is
`docs/spike/azure-wa-iac-analyzer-spike.md` on `release`.

## Related ADRs and issues

- ADR-023 — Well-Architected IaC Analyzer adoption (AWS track in-flight via [#281](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/281))
- ADR-005 — AWS Agentic Platform Engineering (Azure→AWS lineage doc)
- [#288](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/288) — Azure parity spike (verdict: DEFER)
- [#289](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/289) — this placeholder
- [PR #294](https://github.com/Cloud-Byte-Consulting/Catalyst/pull/294) — spike PR
