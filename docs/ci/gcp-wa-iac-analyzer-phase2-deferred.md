# GCP Well-Architected IaC Analyzer — Phase 2 (Deferred)

**Status:** Deferred
**Issue:** [#293](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/293)
**Spike:** [#291](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/291) — PR [#295](https://github.com/Cloud-Byte-Consulting/Catalyst/pull/295) (verdict: **DEFER**)
**Sibling docs:** AWS counterpart [#286](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/286), GCP composite README [#298](https://github.com/Cloud-Byte-Consulting/Catalyst/pull/298)
**ADR:** ADR-023 Phase 2 (GCP variant) — *ADR file not yet committed in this worktree; tracked separately*

---

## 1. Decision

Phase 2 of the Well-Architected IaC Analyzer CI integration (issue #293) targeted a GCP-flavored
`pr-checks.yml` job mirroring the AWS job introduced in #286. The spike (#291 / PR #295) returned a
**DEFER** verdict. This PR records the deferral and pre-bakes the future activation contract so
that re-opening this work is a small, well-scoped change rather than a fresh design exercise.

**No CI workflow changes ship in this PR.** `.github/workflows/pr-checks.yml` is untouched.

## 2. Rationale (why deferred)

The spike (`docs/spike/gcp-wa-iac-analyzer-spike.md`, landing via PR #295) concluded:

1. **No direct GCP upstream parallel.** AWS provides
   [`aws-samples/well-architected-iac-analyzer`](https://github.com/aws-samples/well-architected-iac-analyzer),
   which couples to the AWS Well-Architected Tool API. GCP has the
   *Architecture Framework* as guidance documentation but **no equivalent first-party analyzer service or
   maintained reference implementation** that ingests Terraform/IaC and produces pillar-scored output.
2. **Building a Catalyst-native analyzer would expand scope beyond ADR-023.** ADR-023 is scoped to
   wiring an existing analyzer into CI, not to authoring a new one. A native GCP analyzer would
   require: (a) codifying the GCP Architecture Framework into machine-checkable rules, (b) building
   a scoring engine, (c) ongoing rule maintenance — each a separate ADR-level decision.
3. **Third-party options are immature.** No third-party SaaS or OSS tool surveyed during the spike
   provided pillar-mapped output comparable to the AWS analyzer at the cost/maintenance profile
   ADR-023 assumes.

Given the demo timeline and the absence of a drop-in parallel, the WA IaC Analyzer remains
**AWS-only** for now. The reservation contract below makes re-activation cheap.

## 3. Reserved path filters (for future activation)

When a GCP analyzer parity service is identified, the future `pr-checks.yml` GCP job MUST trigger
on these path filters (mirroring the AWS job's discrimination strategy):

```yaml
paths:
  - 'infrastructure/gcp/**'
  - '**/*.tf'  # filtered downstream by GCP provider block detection
```

Provider-block detection (downstream filter) MUST identify Terraform files whose `provider` /
`required_providers` declarations reference `google` or `google-beta` before invoking the analyzer.
This avoids spurious runs on AWS-only Terraform.

## 4. Gating contract (for future activation)

The future GCP analyzer job MUST be gated by a repository variable:

| Variable                     | Type            | Required state to run | Meaning                                            |
|------------------------------|-----------------|-----------------------|----------------------------------------------------|
| `GCP_WA_ANALYZER_ENDPOINT`   | repo variable   | set AND non-empty     | URL of the GCP WA analyzer service to POST IaC to. |

Gating logic (pseudocode for the future job's `if:` expression):

```
if: ${{ vars.GCP_WA_ANALYZER_ENDPOINT != '' }}
```

When unset/empty, the job is a no-op (skipped at the workflow level). This matches the AWS job's
posture in #286 and keeps fork PRs / un-provisioned environments green.

## 5. Issue #293 Gherkin → deferred mapping

| Gherkin scenario (from #293)                                                  | Status      | Notes                                                                 |
|-------------------------------------------------------------------------------|-------------|-----------------------------------------------------------------------|
| GIVEN a PR touching `infrastructure/gcp/**` WHEN CI runs THEN GCP WA job runs | DEFERRED    | No analyzer service to call. Path filter reserved (Section 3).        |
| GIVEN a PR with no GCP IaC WHEN CI runs THEN GCP WA job is skipped            | DEFERRED    | Skip-when-unset gating contract reserved (Section 4).                 |
| GIVEN `GCP_WA_ANALYZER_ENDPOINT` unset WHEN CI runs THEN job is a no-op       | DEFERRED    | Gating variable name reserved; no workflow uses it yet.               |
| GIVEN analyzer returns pillar scores WHEN parsed THEN PR comment is posted    | DEFERRED    | No analyzer → no payload schema → no comment renderer.                |
| GIVEN analyzer fails WHEN CI runs THEN job fails closed (not silently green)  | DEFERRED    | Failure-mode design deferred until an analyzer exists.                |

## 6. Re-open trigger

Re-open this work by filing a **new issue** that references this deferral when **any** of the
following becomes true:

- GCP publishes (or a credible third party releases) a maintained Architecture Framework analyzer
  service that ingests Terraform/IaC and emits pillar-scored output.
- Catalyst scope expands to include authoring a native GCP analyzer (would require a new ADR).
- An internal Catalyst Bedrock-backed analyzer is approved to cover GCP pillar checks (would
  require an ADR extending ADR-023).

The new issue MUST link back to:
- This document (`docs/ci/gcp-wa-iac-analyzer-phase2-deferred.md`)
- Spike #291 / PR #295
- ADR-023 (once committed)

## 7. What this PR is and is not

- **Is:** A documentation-only deferral record. Closes #293 by recording "not implemented and why".
- **Is not:** A workflow change. `.github/workflows/pr-checks.yml` is unmodified.
- **Is not:** A GCP infrastructure addition. No modules under `infrastructure/gcp/**` are added.

---

*Generated as part of the ADR-023 Phase 2 deferral. Review-only; not intended to merge for the demo.*
