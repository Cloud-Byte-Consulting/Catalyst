# Spike — GCP parity for ADR-023 (Well-Architected IaC Analysis)

**Status**: Spike · 2026-05-19
**Issue**: [#291](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/291)
**Verdict**: **Defer** (until first GCP landing zone exists)
**Related**: ADR-005 (AWS agentic platform engineering lineage), ADR-023 (AWS Well-Architected IaC Analyzer adoption — AWS-track), `#288` (Azure parity spike, independent track)

---

## 1. Context

ADR-023 binds Catalyst's Well-Architected IaC analysis capability to AWS-native
substrate: Bedrock (LLM), AWS Well-Architected Tool (framework lenses), and the
AWS-published `wa-iac-analyzer` reference implementation. That binding is correct
for AWS — but it is **not portable**. Catalyst's long-term multi-cloud direction
(`lz/gcp-*` landing zones reserved under the labelling taxonomy, future
`infrastructure/gcp/` Terraform root) means we need a deliberate answer for the
GCP equivalent **before** any GCP code lands, not after.

This spike answers one question: *when (and how) does Catalyst stand up a GCP
parity surface for ADR-023's analysis capability?* It is a research artefact
only — no Terraform, no workflows, no ADR mutations.

Catalyst's GCP footprint today: **zero**. There is no `infrastructure/gcp/`,
no `lz/gcp-*` issue has been opened beyond #291 itself, and no workload has a
GCP target. The premise of "parity" is therefore forward-looking: we are
deciding the shape of the slot, not filling it.

## 2. Survey

Four candidate stacks could fill the GCP-parity slot. Each is evaluated as a
*system* — LLM substrate + framework grounding + IaC ingestion + auth glue.

### 2.1 Google Cloud Architecture Framework + Gemini-on-Vertex (build, GCP-native)

The Google Cloud Architecture Framework (formerly "Google Cloud Well-Architected
Framework") publishes six pillars: Operational Excellence; Security, Privacy &
Compliance; Reliability; Cost Optimization; Performance Optimization;
Sustainability. This is structurally parallel to AWS WA's six pillars and would
serve as the grounding corpus for a Gemini-on-Vertex analyzer.

- **LLM**: Gemini 1.5/2.x via Vertex AI (`us-central1`, `europe-west*` regions
  available — data-residency parity with Bedrock is achievable).
- **Framework grounding**: Architecture Framework pillar docs (markdown ingest
  via Vertex AI Search or RAG-on-Vertex).
- **IaC ingestion**: Terraform `.tf` plain-text + `terraform plan -out` JSON.
- **Effort**: Mirror of the AWS `wa-iac-analyzer` shape — significant. No
  Google-published reference implementation equivalent exists today.

### 2.2 Google Cloud Recommender APIs + Config Validator (buy, post-deploy)

Google's Active Assist / Recommender API produces optimization insights across
IAM, cost, performance, and security categories. Config Validator (part of the
broader Forseti / Policy Controller lineage, now folded into Anthos Config
Management and `gcloud` policy tooling) validates GCP resource configurations
against constraints.

- **Critical limitation**: Recommender operates on *deployed* resources, not
  Terraform plans. Confirmed by GCP docs: "Active Assist focuses on analyzing
  existing Google Cloud resources." No `terraform plan` ingestion.
- **Config Validator** can be wired pre-apply via `gcloud beta terraform
  vet` (formerly `terraform-validator`) — but it produces constraint-violation
  output, not WA-framework-grounded narrative analysis. It is a policy-as-code
  tool, not a WA analyzer.
- **Effort**: Low integration cost, but it does **not deliver the ADR-023
  capability** — only the policy-gate adjacency.

### 2.3 Third-party IaC scanners with GCP providers (buy, defensive)

Checkov, tfsec (now Trivy IaC), and Terrascan all ship GCP rule packs covering
~300+ misconfigurations (public buckets, unencrypted disks, over-broad IAM
bindings, etc.).

- **Coverage**: Strong on the Security pillar. Weak-to-absent on Reliability,
  Cost, Performance, Sustainability pillars.
- **AI capability**: None natively — these are static rule engines. Some
  vendors (Wiz, Snyk) layer LLM remediation suggestions, but those are
  commercial and outside Catalyst's open-source posture.
- **Effort**: Trivial to wire (a single workflow step). Already partially
  precedented on the AWS track.

### 2.4 Gemini-on-Vertex as raw LLM substrate (build, minimal scaffold)

The lightest "build" path: a single Cloud Run service that takes a `.tf`
payload, passes it to Gemini with a system prompt seeded from the Architecture
Framework markdown, returns structured findings. No Vertex AI Search index, no
agent framework — just Converse-style invocation.

- **Effort**: Days, not weeks. Mirror of `bedrock-binding` skill but with
  `google-genai` SDK.
- **Quality**: Lower than 2.1 (no retrieval grounding) but adequate as MVP.
- **Risk**: Hallucinated pillar references; mitigated by prompt-embedded
  framework excerpts.

## 3. Comparison Matrix

| Candidate | Build effort | Ops cost (monthly) | AI capability | TF + DM coverage | WIF compat | Data residency |
|---|---|---|---|---|---|---|
| 2.1 GCP Arch Framework + Gemini + RAG | High (~3-4 wks) | $80-200 (Vertex AI + storage) | Strong — RAG-grounded narrative | Terraform yes; DM legacy, low priority; KCC viable | Native | EU/US/APAC regions available |
| 2.2 Recommender API + Config Validator | Low (~3 days) | $0 (Recommender free tier) + minor compute | None (rule output only) | Post-deploy only, no TF plan | Native | Per-resource region pinning |
| 2.3 Checkov / Trivy / Terrascan | Trivial (~1 day) | $0 (OSS) | None | Terraform yes; DM partial | Native (runs in GH runner) | N/A — local execution |
| 2.4 Gemini raw + system prompt | Low (~1 wk) | $30-80 (Vertex AI calls) | Moderate — ungrounded LLM | Terraform yes; DM via raw text | Native | Vertex regional endpoints |

Notes:
- *Deployment Manager (DM)* is in maintenance mode and Catalyst will not adopt
  it; Terraform is the only supported GCP IaC surface per the issue's Gherkin
  AC ("Terraform path is primary"). KCC (Config Connector) is a Kubernetes-
  native alternative that emits GCP resources — orthogonal to this spike.
- *Workload Identity Federation* is the only acceptable GitHub→GCP auth pattern
  per the Gherkin AC. All four candidates are WIF-compatible.

## 4. Recommendation — **DEFER**

**Verdict: Defer.** Catalyst has zero GCP footprint today. Building a
GCP-parity WA IaC analyzer ahead of a single deployed GCP workload would create
an unowned, untested, and unmaintained code path — the same anti-pattern
ADR-005 warns against ("don't ship golden paths for substrates you don't
operate"). The right trigger to revive this spike is the first
`lz/gcp-foundation` issue landing on the project board with an actual GCP
project ID and a Terraform root to analyze.

**Cost/ops estimate when revived** (forecast, not commitment):
- One-time engineering: ~3 weeks (candidate 2.1) or ~1 week (candidate 2.4 MVP)
- Steady-state ops: $30-200/mo Vertex AI + ~$10 storage
- Maintenance burden: one renovate cadence (Gemini model version pinning) +
  pillar-doc refresh every ~6 months

**Defensive interim**: when the first GCP Terraform lands, gate it with
candidate 2.3 (Checkov GCP pack) as a workflow step. That is single-digit
hours of work and gives a security-pillar floor without committing to the
larger analyzer. This is the same posture the AWS track held before ADR-023.

**Why not "build" today**: no GCP workload to analyze, no operator on-call,
no production traffic. Vertex AI minimums + RAG index storage would be
$80-200/mo for zero analyzed plans.

**Why not "buy" candidate 2.2 today**: it doesn't deliver ADR-023's capability
(post-deploy only) and would mis-set the slot's expectations.

## 5. Auth model — Workload Identity Federation

WIF is the only acceptable GitHub→GCP authentication pattern. Long-lived
service-account JSON keys are prohibited (parity with Catalyst's AWS OIDC-only
posture per CLAUDE.md and ADR-005).

**Required federation shape** (forecast, for when the slot fills):

- **Pool**: one per GitHub organization (`Cloud-Byte-Consulting`). Created in
  a `lz/gcp-shared-services` project, not in workload projects.
- **Provider**: OIDC provider with Issuer URL
  `https://token.actions.githubusercontent.com/`.
- **Attribute mapping** (minimum):
  - `google.subject = assertion.sub`
  - `attribute.repository = assertion.repository`
  - `attribute.repository_owner = assertion.repository_owner`
  - `attribute.ref = assertion.ref`
- **Attribute condition** (CEL):
  `assertion.repository_owner == 'Cloud-Byte-Consulting'`
  — extended to `assertion.ref == 'refs/heads/release'` for deploy-class roles.
- **Numeric IDs**: bind via numeric `*_id` fields per Google's guidance to
  defeat typosquatting against repository names.
- **Workflow permissions**: `id-token: write` + `contents: read`.
- **Action**: `google-github-actions/auth@v2` for credential exchange.

A future ADR (not this spike) will codify the Terraform module shape for the
pool/provider pair under `infrastructure/gcp/modules/wif-github/`.

## 6. Naming reservation

Per ADR-023's *Cloud-prefixed naming* convention (the AWS slot is
`var.enable_wa_aws_iac_analyzer`), the reserved GCP slot is:

```hcl
variable "enable_wa_gcp_iac_analyzer" {
  type        = bool
  default     = false
  description = "Enable GCP Well-Architected (Architecture Framework) IaC analyzer. Deferred — see docs/spike/gcp-wa-iac-analyzer-spike.md."
}
```

This variable is **reserved, not declared**. It must not appear in any
Terraform root until the spike is revived and a follow-up ADR (ADR-02x) accepts
the build/buy decision against an actual GCP landing zone.

## 7. Open questions

1. **Data residency policy** — Catalyst has no codified data-residency stance
   for analyzed IaC payloads. Vertex AI offers regional endpoints, but the
   pillar-doc RAG index storage region is a separate decision. To be settled
   when ADR-02x is drafted.
2. **Multi-region pinning** — should the analyzer service run in
   `us-central1` (cost-optimal) or follow the workload's region? Defer to
   landing-zone topology.
3. **Pillar-doc refresh cadence** — Google publishes Architecture Framework
   updates without changelogs. RAG re-index cadence is unsettled.
4. **KCC vs Terraform priority** — if Catalyst adopts Config Connector for
   any GCP workload, the analyzer must ingest KCC YAML in addition to `.tf`.
   Not in scope until KCC adoption is decided.
5. **Cross-cloud unification** — should the AWS and GCP analyzers share a
   common findings schema (e.g., SARIF, OSCAL)? Worth deciding before either
   matures, but blocked on AWS-track stabilization first.
6. **Gemini model pinning** — `gemini-1.5-pro` vs `gemini-2.x` vs future
   models. Renovate-style auto-pin policy needed.

## 8. References

1. Google Cloud Architecture Framework —
   <https://cloud.google.com/architecture/framework>
2. Workload Identity Federation with deployment pipelines —
   <https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines>
3. `google-github-actions/auth` —
   <https://github.com/google-github-actions/auth>
4. Google Cloud Recommender API overview —
   <https://cloud.google.com/recommender/docs/overview>
5. `gcloud beta terraform vet` (Config Validator successor) —
   <https://cloud.google.com/docs/terraform/policy-validation>
6. Vertex AI Gemini pricing & regions —
   <https://cloud.google.com/vertex-ai/generative-ai/pricing>
7. Checkov GCP coverage —
   <https://www.checkov.io/5.Policy%20Index/gcp.html>
8. AWS Well-Architected IaC Analyzer reference (AWS-track precedent for the
   ADR-023 shape this spike mirrors for GCP) —
   <https://github.com/aws-samples/well-architected-iac-analyzer>
