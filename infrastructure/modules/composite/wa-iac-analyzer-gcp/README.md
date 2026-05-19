# wa-iac-analyzer-gcp — DEFERRED placeholder

**Status**: **DEFERRED** per the [#291](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/291) spike ([PR #295](https://github.com/Cloud-Byte-Consulting/Catalyst/pull/295)). This directory is a naming-slot reservation only — no Terraform, no deployable surface.

Closes the Phase 1 scaffold work tracked under [#292](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/292) by recording the deferral explicitly rather than shipping an unowned greenfield module.

## Why not now

1. **Zero GCP footprint** — `infrastructure/` has no GCP provider, no `lz/gcp-*` landing zone, and no GCP workload to analyze. Standing up a WA-equivalent analyzer ahead of any GCP IaC inverts ADR-005's dependency arrow ("don't ship golden paths for substrates you don't operate").
2. **No upstream parallel** — the AWS track binds ADR-023 to `aws-samples/well-architected-iac-analyzer`, a Google-supported reference implementation. The #291 spike's key finding is that **no Google-published equivalent exists today**. A GCP analyzer is therefore a **greenfield build** (~3 weeks for the Gemini-on-Vertex + Architecture Framework RAG candidate, or ~1 week for the raw-Gemini MVP), not a fork.
3. **Cost floor** — Vertex AI minimums + RAG index storage are ~$80–200/mo for zero analyzed plans. Premature to spend before there is anything to analyze.

## Trigger to revisit

Revive this module when **the first `lz/gcp-*` issue lands carrying a real Terraform root** in `infrastructure/gcp/` (or equivalent). That is the earliest point a WA-equivalent analyzer has any IaC payload to evaluate.

Until then, the slot stays empty.

## Naming slot reserved

Per ADR-023's Cloud-prefixed naming convention (mirroring `var.enable_wa_aws_iac_analyzer`), the reserved flag is:

```hcl
# RESERVED — do NOT declare in any Terraform root until this module is revived.
variable "enable_wa_gcp_iac_analyzer" {
  type        = bool
  default     = false
  description = "Enable GCP Well-Architected (Architecture Framework) IaC analyzer. DEFERRED — see infrastructure/modules/composite/wa-iac-analyzer-gcp/README.md."
}
```

This variable is **reserved by documentation only**. Declaring it as a live unused variable would trip `tflint` `terraform_unused_declarations` (per the #277 pattern). When the slot fills, a follow-up ADR will accept the build/buy decision and the variable will be declared in the analyzer module's `variables.tf`.

## Implementation path when revived

1. **Defensive interim (single-digit hours)** — when the first GCP Terraform root lands, gate it with the Checkov GCP pack as a workflow step. This gives a security-pillar floor without committing to the full analyzer.
2. **WA-equivalent build (greenfield)** — implement candidate 2.1 from the spike (Google Cloud Architecture Framework markdown ingested into Vertex AI Search + Gemini-on-Vertex for RAG-grounded narrative analysis) or the lighter candidate 2.4 (raw Gemini with framework excerpts embedded in the system prompt). Either path is greenfield engineering — no upstream to fork.
3. **Authoring ADR** — draft ADR-02x to formally accept the build/buy decision against the then-current GCP landing-zone topology before any Terraform lands here.

## Auth model — Workload Identity Federation (WIF) only

When GCP CI is added, **GitHub → GCP authentication is via Workload Identity Federation exclusively** (per the #291 spike §5 and the issue's Gherkin AC). Long-lived service-account JSON keys are prohibited — parity with Catalyst's AWS OIDC-only posture per CLAUDE.md and ADR-005.

Minimum WIF shape (forecast, codified later in a `wif-github` module):

- Pool per GitHub organization (`Cloud-Byte-Consulting`) in a `lz/gcp-shared-services` project
- OIDC provider issuer `https://token.actions.githubusercontent.com/`
- Attribute condition: `assertion.repository_owner == 'Cloud-Byte-Consulting'`
- Workflow uses `google-github-actions/auth@v2` with `id-token: write`

## References

- Spike doc: [`docs/spike/gcp-wa-iac-analyzer-spike.md`](https://github.com/Cloud-Byte-Consulting/Catalyst/blob/spike-gcp-wa-iac-analyzer-291/docs/spike/gcp-wa-iac-analyzer-spike.md) (currently on PR #295's branch — will land in `release` when #295 merges)
- Spike PR: [#295](https://github.com/Cloud-Byte-Consulting/Catalyst/pull/295)
- Tracking issue: [#291](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/291) (spike) · [#292](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/292) (this scaffold)
- ADR-023 — AWS Well-Architected IaC Analyzer adoption (AWS-track binding; defines the naming convention this slot extends)
- Azure-track parallel: [#288](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/288) spike · [#289](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/289) scaffold (`wa-iac-analyzer-azure`)
