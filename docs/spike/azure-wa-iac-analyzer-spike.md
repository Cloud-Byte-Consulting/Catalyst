# Spike — Azure parity for ADR-023 (Well-Architected IaC analysis)

**Status**: Spike — research only · 2026-05-19
**Issue**: [#288](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/288)
**Branch**: `spike-azure-wa-iac-analyzer-288`
**Verdict**: **DEFER** — revisit only when an Azure footprint lands in `infrastructure/`.
**Naming reservation**: `var.enable_wa_azure_iac_analyzer` (per ADR-023 §Cloud-prefixed naming).

## 1. Context

ADR-023 (in-flight via issue [#281](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/281))
binds the AWS track of Catalyst to
[`aws-samples/well-architected-iac-analyzer`](https://github.com/aws-samples/well-architected-iac-analyzer)
as a deferred Phase 1 deployment. The upstream analyzes Terraform / CloudFormation /
CDK against the AWS Well-Architected pillars using Amazon Bedrock (Claude),
ECS Fargate + ALB, DynamoDB, S3 Vectors, and Cognito. The license is MIT-0.

Catalyst's lineage doc — ADR-005 (AWS Agentic Platform Engineering) — explicitly
maps the Microsoft GBB *Agentic Platform Engineering* pattern (Azure-native:
AKS, Bicep, Workload Identity Federation, Azure OpenAI, AKS-MCP, Microsoft
Foundry) **into** AWS-prescriptive equivalents. The lineage is one-way: Catalyst
took the Azure pattern and AWS-ified it. ADR-023 follows the same direction —
the AWS-native verdict is committed; Azure parity is a separate, open question.

This spike answers: **what does an Azure equivalent of ADR-023 look like, and
should Catalyst build, buy, or defer it?**

Key constraints framing the answer:

- **No Azure infrastructure exists in `infrastructure/` today.** Every Terraform
  composite, module, and landing-zone primitive in Catalyst targets AWS.
- The pharmacy/insurance enterprise context (per the issue Gherkin AC) makes
  **data residency** and **Entra ID** auth non-negotiable for any production
  Azure adoption.
- Catalyst's IaC is Terraform-first today. Any Azure analyzer must handle
  Terraform-with-`azurerm`/`azapi` providers **and** Bicep, because Microsoft
  prescriptive content frequently ships in Bicep.
- ADR-023's Phase 2 plan (POST `terraform plan` to an analyzer, parse JSON/CSV
  into a PR comment) is the integration shape we'd need to mirror for Azure.

## 2. Survey

Four candidate paths considered.

### 2.1 Microsoft Well-Architected Review automation surface

Microsoft ships the WAF assessment through:

- The **Azure Well-Architected Review** experience in the Azure portal
  (questionnaire-driven, not API-first).
- **Azure Advisor** recommendations (per-subscription, post-deploy, runtime
  signal — *not* an IaC pre-deploy analyzer).
- The **Azure Proactive Resiliency Library (APRL)** — a curated set of
  recommendations published as YAML/Markdown, queryable via Azure Resource
  Graph (ARG) KQL queries the APRL ships.
- **Azure Review Checklists** (`Azure/review-checklists` on GitHub) — Excel/JSON
  collateral that codifies the WAF checklist; integrates with ARG via the
  community-maintained `azqr` CLI.
- **`azqr`** (Azure Quick Review) — the closest first-party-adjacent tool to
  what ADR-023 ships on AWS: scans a subscription, emits Excel + JSON + Markdown
  WAF scoring. But it operates against **deployed resources via ARG**, not IaC.

The gap is explicit: Microsoft's WAF automation is **runtime-state-driven**,
not IaC-driven. There is no official Microsoft equivalent of the AWS analyzer's
"feed me a Terraform plan, get back WAF scoring" loop.

### 2.2 Azure OpenAI + Azure Resource Graph + Policy as analysis primitives

The DIY Azure-native build. Concrete shape:

- **Azure OpenAI** (GPT-4o / o-series) replaces Bedrock as the LLM that scores
  IaC text against WAF pillars.
- **Azure Resource Graph (ARG)** as the runtime-state oracle for "what would
  this look like post-deploy" enrichment.
- **Azure Policy** + **PSRule for Azure** (`Azure/PSRule.Rules.Azure`) as the
  deterministic rule engine, with the LLM layered on top for synthesis.
- **Bicep CLI + `bicep build`** to normalize Bicep to ARM JSON before analysis;
  `terraform plan -out=tfplan && terraform show -json tfplan` for Terraform.
- **Container Apps** or **Azure Functions Flex** as the runtime, fronted by
  **Application Gateway** + **Entra ID** for auth.
- **Cosmos DB (serverless)** for metadata, **AI Search** for embeddings.

Build effort is real (estimate: 6–10 engineer-weeks for a credible MVP) but
every component is well-documented Azure-prescriptive territory.

### 2.3 Self-host / fork the AWS WA IaC Analyzer with Azure substitutions

The "vendor it and swap" path. Substitution map:

| AWS upstream | Azure substitution |
| --- | --- |
| Amazon Bedrock | Azure OpenAI (Claude via Azure AI Foundry Models, or GPT-4o) |
| ECS Fargate + ALB | Container Apps + Application Gateway |
| DynamoDB | Cosmos DB for NoSQL (serverless) |
| S3 Vectors | Azure AI Search vector index |
| Cognito | Entra ID (External ID for B2C-style flows) |
| CloudFormation/CDK deploy | Terraform composite + `azapi` provider |
| WAF pillar prompts | **Reusable** — pillars map 1:1 (Cost, Reliability, Security, Performance, Operational Excellence; Sustainability differs minorly) |

The MIT-0 license makes this legally clean. The **engineering reality** is that
the upstream's prompt templates, ingestion pipelines, and PR-comment formatter
*are* the IP — the runtime substrate is replaceable but tedious to swap
end-to-end. The codebase mixes TypeScript (frontend), Python (backend),
CloudFormation, and CDK; an Azure fork must replace CloudFormation/CDK with
Terraform/Bicep deploy modules and re-test every prompt against Azure-flavored
plans (the WAF questions overlap, but the **resource shapes** the LLM reasons
over are different — an `aws_lambda_function` is not an `azurerm_linux_function_app`).

Rough effort: 8–14 engineer-weeks, including IAM/RBAC re-modeling for Entra ID
and a Bicep ingestion path the upstream does not provide.

### 2.4 Third-party scanners (Checkov + Bicep, tfsec, PSRule, etc.)

The "good enough for today" path. Components:

- **Checkov** — already integrated in `pr-checks.yml` for Terraform; supports
  Bicep and ARM out of the box; ships Azure-specific policy packs aligned with
  CIS Azure and (partially) WAF.
- **PSRule for Azure** — Microsoft-maintained rules engine for Bicep/ARM with
  explicit WAF tagging on every rule. Runs as a GitHub Action.
- **`tfsec`** (now folded into Trivy) — Terraform-only, Azure provider
  coverage is solid for security pillar; weaker for cost/operational.
- **`azqr`** — runtime-state WAF scoring post-deploy; complementary, not a
  replacement for pre-deploy IaC analysis.
- **Aqua / Snyk IaC / Bridgecrew** (commercial) — adjacent. Buy decision lives
  outside this spike.

This stack covers ~60–70% of the WAF surface deterministically, with zero LLM
cost and zero new infrastructure. It misses the *narrative synthesis* the AWS
analyzer is prized for ("here is a paragraph explaining how your plan fails
the reliability pillar's redundancy posture") — that's the LLM gap.

## 3. Comparison matrix

| Candidate | Build effort | Ops cost (idle/mo) | AI capability | Bicep + Terraform | Entra ID | Data residency |
| --- | --- | --- | --- | --- | --- | --- |
| **2.1** MS WAF automation (Advisor + `azqr` + APRL) | Low (1–2 wks integration) | $0 (runtime tools only) | None (deterministic) | Partial — runtime-only, not IaC | Native | Native (subscription-region scoped) |
| **2.2** Azure OpenAI + ARG + Policy (DIY) | High (6–10 wks) | $80–$150 (Container Apps + Cosmos serverless + AI Search basic + AppGW) + per-call OpenAI | Strong (Azure OpenAI in-tenant) | Yes — Bicep via `bicep build`, TF via plan-json | Native | Configurable (Azure OpenAI regional + data-residency commitments) |
| **2.3** Fork AWS analyzer to Azure | Very high (8–14 wks) | $80–$150 idle (matches 2.2) | Strong (prompts inherited) | Yes after Bicep ingestion port | Requires re-modeling Cognito → Entra ID | Configurable |
| **2.4** Third-party scanners (Checkov + PSRule + Trivy) | Very low (~1 wk) | $0 (CI-only) | None — deterministic rules | Yes — strongest of all options on coverage breadth | N/A (CI runs in GitHub OIDC → no Azure auth needed for static analysis) | N/A (no data leaves CI runner) |

Reading the matrix: **2.4 is the cheapest, fastest, most coverage-broad option
and ships zero Azure infrastructure.** It also lacks the headline AI synthesis
that makes ADR-023 distinctive. **2.2 and 2.3 are the only AI-capable options**
and they cost the same to run; the difference is build path (greenfield vs
fork). **2.1 is a runtime-state companion to any of the above**, not a
standalone answer.

## 4. Recommendation

**DEFER.** Revisit when **all** of the following conditions hold:

1. At least one Azure workload exists under `infrastructure/composite/` or
   `infrastructure/landing-zone/` with non-trivial Bicep or `azurerm`
   resources (i.e. there is *something to analyze*).
2. ADR-023 Phase 1 (AWS WA IaC Analyzer deployment) has shipped and produced
   at least 30 days of PR-comment telemetry — so we have a baseline for what
   "good" looks like before paying to clone it.
3. A pharmacy/insurance customer or internal product has a binding Azure
   delivery requirement that the third-party scanner stack (option 2.4)
   cannot satisfy on its own.

**Rationale.** Catalyst has zero Azure footprint today. Building option 2.2
or 2.3 means standing up Container Apps + Cosmos + AI Search + App Gateway +
an Entra ID tenant configuration **before there is any Azure IaC to point
the analyzer at**. That inverts the dependency arrow and burns 6–14
engineer-weeks on a tool with no users. The honest engineering call is to
**adopt option 2.4 (Checkov + PSRule for Azure) as a CI-only scaffold the
day the first Azure IaC lands**, and revisit the AI-synthesis layer when
ADR-023's AWS Phase 1 has produced enough telemetry to justify an Azure
clone.

**Cost/ops estimate when deferral is lifted** (planning number only):

- **Tier-1 (option 2.4) adoption when first Azure IaC lands**: ~1 engineer-week
  to add Checkov Azure packs + PSRule for Azure to `pr-checks.yml`. $0 ops.
- **Tier-2 (option 2.2 DIY Azure-native)**: 6–10 engineer-weeks; $80–$150/mo
  idle + Azure OpenAI per-call (estimate $0.005–$0.02 per PR analysis with
  GPT-4o); requires Entra ID app registration, data-residency policy decision,
  Container Apps environment in the relevant Azure region.
- **Tier-3 (option 2.3 fork)** is **not recommended** as the entry path — only
  consider if Tier-2's prompt-engineering loop proves more expensive than
  inheriting the AWS upstream's prompt library.

## 5. Naming reservation

Per ADR-023 §Cloud-prefixed naming, the Azure track reserves:

```hcl
variable "enable_wa_azure_iac_analyzer" {
  type        = bool
  default     = false
  description = "Enable the Azure parity stack for ADR-023 (Well-Architected IaC analysis). Currently DEFERRED per docs/spike/azure-wa-iac-analyzer-spike.md."
}
```

This slot is **declared, not implemented** by this spike. The corresponding
AWS slot is `var.enable_wa_aws_iac_analyzer` (per ADR-023 in-flight on #281).

Construct-address labels for future Azure work, aligned with Catalyst's
existing label scheme:

- `lz/azure-shared` — Azure shared-services landing zone
- `lz/azure-workload-*` — per-workload Azure landing zones
- `app/wa-azure-iac-analyzer` — application label if Tier-2/Tier-3 is pursued

## 6. Open questions for the user

Items this spike cannot settle alone:

1. **Data residency policy.** Which Azure regions are permissible for
   pharmacy/insurance customer data? Azure OpenAI regional availability
   (especially for the o-series and Claude-via-Foundry-Models) varies sharply
   from AWS Bedrock's regional footprint. This needs a customer-facing
   policy answer before any Tier-2 work begins.
2. **Entra ID federation choice.** Workload Identity Federation from GitHub
   Actions to Entra ID (the Azure mirror of Catalyst's AWS OIDC pattern in
   ADR-005) — confirm tenant ownership and whether Catalyst operates inside
   the Cloud Byte Consulting tenant or stands up a dedicated platform tenant.
3. **Bicep vs Terraform first.** If/when Azure IaC lands, which is the
   primary surface? PSRule for Azure scores Bicep with native rule fidelity;
   Checkov treats Bicep as a translated artifact. The answer reshapes
   option 2.4's tooling order.
4. **Claude via Azure AI Foundry vs GPT-4o.** Azure AI Foundry now hosts
   Claude models in select regions; if a future Tier-2 build wants prompt
   parity with the AWS analyzer (which uses Claude), this dictates region
   selection and pricing.
5. **Do we want WAF-pillar scoring in PRs at all for Azure?** ADR-023
   commits to it for AWS because the analyzer ships ready-made. The
   cost/benefit of clone-and-deploy must be re-justified for Azure
   independently, *after* Phase 1 telemetry exists.

## 7. References

External:

- AWS Samples upstream: <https://github.com/aws-samples/well-architected-iac-analyzer>
- Azure Quick Review (`azqr`): <https://github.com/Azure/azqr>
- Azure Review Checklists: <https://github.com/Azure/review-checklists>
- PSRule for Azure: <https://azure.github.io/PSRule.Rules.Azure/>
- Azure Proactive Resiliency Library: <https://azure.github.io/Azure-Proactive-Resiliency-Library-v2/>
- Azure Well-Architected Framework (official): <https://learn.microsoft.com/azure/well-architected/>
- Azure OpenAI data, privacy, and residency: <https://learn.microsoft.com/azure/ai-services/openai/how-to/data-residency>
- Microsoft GBB Agentic Platform Engineering (lineage source): <https://github.com/microsoftgbb/agentic-platform-engineering>

Catalyst internal:

- ADR-005 — AWS Agentic Platform Engineering (lineage doc) — `docs/ADR/ADR-005-aws-agentic-platform-engineering.md`
- ADR-023 (in-flight, issue #281) — `docs/ADR/ADR-023-well-architected-iac-analyzer-adoption.md` (pending)
- ADR-009 — Runtime strategy (ECS Fargate / Lambda) — `docs/ADR/ADR-009-*.md`
- ADR-022 — Multi-tool skill layout — `docs/ADR/ADR-022-multi-tool-skill-layout.md`
- Existing PR checks — `.github/workflows/pr-checks.yml`
- Issue #288 — this spike's home

---

**End of spike.** No infrastructure changes, no ADR edits, no CI changes
in this PR. The verdict (DEFER) is the deliverable; the closing comment on
issue #288 records it on the state machine per the Gherkin AC.
