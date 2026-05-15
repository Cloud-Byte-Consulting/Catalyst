# Issue Creation Plan — Catalyst Submission

**Branch**: `plan/challenge-gap-analysis`
**Companion**: [`challenge-gap-analysis.md`](challenge-gap-analysis.md)
**Last reviewed**: 2026-05-14

This plan enumerates every issue that should exist on
[Project #3 — Catalyst Andon](https://github.com/orgs/Cloud-Byte-Consulting/projects/3/views/1)
to close the gap identified in the companion doc.

## Parent ↔ Sub-issue convention

Per the user's instruction: **the issue waiting on the deliverable is the parent;
the prerequisite is the sub-issue.** This lets each umbrella parent track the
percentage-complete of every prerequisite needed to ship it.

GitHub sub-issues are 1-parent only. Where one prerequisite serves two umbrellas
(e.g. ECS cluster is needed by both the IaC discipline AND the service deploy), the
issue is parented under its **closest direct consumer** and the other umbrella links
to it via `Depends on #N` in the body.

## Milestone vocabulary (verified against `gh api`)

| # | Milestone (verbatim) |
|---|---|
| 1 | Automation Service |
| 2 | Infrastructure Design and Terraform Quality |
| 3 | AI-native Development workflow |
| 4 | CI/CD and operational Maturity |
| 5 | Communication and Documentation |
| 6 | [Option 1] optional — Advanced/complete Terraform (modules, CMK, encryption, autoscaling, IaC checks) |
| 7 | [Option 2] optional — AWS Bedrock in containerized service(s) |
| 8 | [Option 3] optional — Dev skills: IAM auth to Postgres, health checks |
| 9 | [Option 4] optional — Operational intelligence tool (Python or Go) |
| 10 | [Option 5] optional — Production-ready or HA architecture diagrams |
| 11 | [Option 6] optional — Extended scope (combination or variation) |

---

## 1. Existing issue disposition

| # | Title | Action | New parent | Rationale |
|---|---|---|---|---|
| 7 | Implementing IaC Best practices | **Keep as umbrella + backfill body** | TOP-LEVEL (Infra) | Natural parent for IaC sub-issues |
| 8 | Develop AWS Application stack | **Close as superseded** | n/a | Redundant — #7 covers infra, #18 covers app |
| 9 | Create Threat Model Assessment | **Reparent** | DOC-0 (new umbrella) | Docs surface; deferred low priority |
| 10 | [ADMIN] establish policies and framework for agentic workflow | **Keep top-level, design-only** | TOP-LEVEL (AI-native) | Bonus; defer implementation |
| 11 | [Consumer] Establish policies and framework for agentic workflow | **Keep top-level, design-only** | TOP-LEVEL (AI-native) | Bonus; defer implementation |
| 12 | Implementing Checkov | **Reparent + backfill body** | #7 | IaC policy gate sub-issue |
| 13 | Implementing Open Policy Agent | **Reparent + backfill body** | #7 | IaC policy gate sub-issue |
| 14 | Implementing AWS SCPs | **Keep top-level, deferred** | TOP-LEVEL (Infra) | Out of rubric scope; nice-to-have |
| 15 | Develop user interaction points | **Reparent + backfill body** | #18 | Client surface for the API |
| 16 | Implement the client CLI | **Reparent + backfill body** | #15 | Sub-deliverable of #15 |
| 17 | Implement the github action for platform api | **Reparent + backfill body** | CICD-0 (new umbrella) | Action surface ships from CI/CD pipelines |
| 18 | Create the catalyst api | **Keep as umbrella + expand body** | TOP-LEVEL (Automation) | Natural parent for service sub-issues |

---

## 2. New umbrella issues to create (7)

Each umbrella is the "deliverable we want to ship" — its sub-issues are everything
that has to land before it can close.

| Tag | Title | Milestone |
|---|---|---|
| **IAC-0** | (use existing #7) | Infrastructure Design and Terraform Quality |
| **SVC-0** | (use existing #18) | Automation Service |
| **CICD-0** | Land `.github/workflows/` with OIDC-based pipelines (PR gates + plan/apply + service CD) | CI/CD and operational Maturity |
| **DOC-0** | Interview-ready documentation, diagrams, and deploy story | Communication and Documentation |
| **AI-0** | AI-native workflow evidence: open PR, narrative, root-level `CLAUDE.md`, backfilled issue bodies | AI-native Development workflow |
| **OPT1-0** | Option 1 claim: CMK + encryption-in-transit + logging + serverless RDS + autoscaling + IaC checks | [Option 1] |
| **OPT2-0** | Option 2 claim: Bedrock in containerized service + multi-agent AI tasks + AI PR review demo | [Option 2] |
| **OPT4-0** | Option 4 claim: Operational Intelligence CLI (Python) aggregating GHA/S3/IAM data | [Option 4] |
| **OPT5-0** | Option 5 claim: HA + GitOps architecture diagrams | [Option 5] |

(Option 3 and Option 6 deferred — see §5 of the gap analysis.)

---

## 3. New sub-issues by umbrella

### 3.1 Under **#7 IaC Best practices** — Infrastructure milestone

| Tag | Title | Depends on |
|---|---|---|
| **TF-1** | Bootstrap Terraform backend (S3 state bucket + DynamoDB lock table + KMS CMK) | — (must run first, one-shot) |
| **TF-2** | Network module: VPC + subnets + NAT + route tables + VPC endpoints | TF-1 |
| **TF-3** | ECR repository module + scan-on-push + lifecycle policy | TF-1 |
| **TF-4** | ECS Fargate cluster + ALB + listener module | TF-2 |
| **TF-5** | DynamoDB table module (control-plane state cache + idempotency dedup) | TF-1 |
| **TF-6** | Secrets module — SSM Parameter Store + Secrets Manager patterns | TF-1 |
| **TF-7** | IAM module — least-privilege role/policy patterns (no wildcards) | TF-1 |
| **TF-8** | Terraform Tests baseline (`tests/*.tftest.hcl` with `run` blocks + assertions) across at least 3 modules | TF-2, TF-3, TF-4 |
| **TF-9** | `terraform fmt` + `validate` + `tflint` + `tfsec` configuration baseline | TF-1 |
| **#12** | Implementing Checkov *(existing — reparent + backfill)* | TF-1, TF-9 |
| **#13** | Implementing Open Policy Agent *(existing — reparent + backfill)* | TF-1, TF-9 |

### 3.2 Under **#18 Catalyst API** — Automation Service milestone

| Tag | Title | Depends on |
|---|---|---|
| **SVC-1** | FastAPI service skeleton + Dockerfile + Pydantic models + `/health` endpoint + uvicorn/gunicorn entry | — |
| **SVC-2** | GitHub Issues state-machine endpoints (POST `/issues`, POST `/issues/{n}/transition`, POST `/issues/{n}/comment`) wrapping STATE-MACHINE verbs | SVC-1 |
| **SVC-3** | Persistence layer — DynamoDB writes for issue cache + audit trail + idempotency dedup | SVC-2, TF-5 |
| **SVC-4** | Service observability — structured JSON logging + custom CloudWatch metrics + correlation IDs | SVC-1 |
| **SVC-5** | Input validation + error handling sweep — Pydantic schemas + retry/backoff + structured error responses + 4xx vs 5xx discipline | SVC-2, SVC-3 |
| **SVC-6** | ECS task definition + service IAM execution role + task role (least-privilege) | SVC-1, TF-4, TF-7 |
| **SVC-7** | CloudWatch alarms + SNS topic + dashboard for 5xx rate, p99 latency, ECS task count, DLQ depth | SVC-4, SVC-6 |
| **#15** | Develop user interaction points (CLI + Action YAML) *(existing — reparent + backfill)* | SVC-2 |
| **#16** | Implement the client CLI *(existing — reparent under #15 + backfill)* | #15 |

### 3.3 Under **CICD-0** — CI/CD and operational Maturity milestone

| Tag | Title | Depends on |
|---|---|---|
| **CICD-1** | Provision GitHub OIDC trust to AWS — IAM identity provider + plan-role + apply-role with scoped trust conditions on branch/ref | TF-1, TF-7 |
| **CICD-2** | `.github/workflows/pr-checks.yml` — terraform fmt/validate, tflint, tfsec, Checkov, OPA/Conftest, Trivy, gitleaks, pytest `--cov-fail-under=85` | CICD-1, TF-8, TF-9, #12, #13 |
| **CICD-3** | `.github/workflows/tf-plan.yml` — `terraform plan` on PR with sticky comment | CICD-1 |
| **CICD-4** | `.github/workflows/tf-apply.yml` — `terraform apply` on merge to `release` with manual approval gate for prod | CICD-1, CICD-3 |
| **CICD-5** | `.github/workflows/service-cd.yml` — build image → push ECR → register task definition → update ECS service | CICD-1, SVC-1, TF-3, TF-4 |
| **CICD-6** | `.github/dependabot.yml` adoption (template already in `.cursor/skills/aws-platform-engineering/templates/`) | — |
| **CICD-7** | `.github/PULL_REQUEST_TEMPLATE.md` + `.github/ISSUE_TEMPLATE/*.yml` (default + bug + feat + kaizen forms aligned to Catalyst state machine) | — |
| **CICD-8** | Branch protection on `release` via Terraform `github_branch_protection` resource (requires green checks, requires PR review) | CICD-2, CICD-3, CICD-4 |
| **#17** | Implement the github action for platform api *(existing — reparent + backfill)* | SVC-2 |

### 3.4 Under **DOC-0** — Communication and Documentation milestone

| Tag | Title | Depends on |
|---|---|---|
| **DOC-1** | Create `diagrams/` directory + control-plane architecture diagram (`.drawio` + exported `.png`) **MANDATORY per brief** | — (can start day 1) |
| **DOC-2** | README rewrite — add `## Deploy` section with copy-pasteable commands a stranger can follow | CICD-4 landed (or earlier with placeholder) |
| **DOC-3** | README reality alignment — remove or clearly label every claim about files that don't yet exist on disk | — (can start day 1) |
| **DOC-4** | `DECISIONS.md` consolidation pointer to existing ADRs (brief lists DECISIONS.md as acceptable alternative) | — |
| **#9** | Create Threat Model Assessment *(existing — reparent + backfill)* | SVC-2 (subject of model) |

### 3.5 Under **AI-0** — AI-native Development workflow milestone

| Tag | Title | Depends on |
|---|---|---|
| **AI-1** | Add `CLAUDE.md` at repo root pointing to `AGENTS.md` + listing the 4 registered MCP servers + the agent persona index | — |
| **AI-2** | `docs/ai-workflow-narrative.md` — interview talking points: what worked, where AI was course-corrected, how the workflow would be improved | — |
| **AI-3** | Backfill empty issue bodies (#7, #9, #12, #13, #15, #16, #17, #18) with proper Context / Scope / Gherkin Acceptance Criteria — required to satisfy Catalyst's own `gherkin-validator` rule | — |
| **AI-4** | **Open the mandatory demo PR** — small AI-assisted change committed to a feature branch, PR opened against `release`, left open through interview **MANDATORY per brief** | SVC-4 (Bedrock endpoint) for the review-side demo; can open with placeholder earlier |

### 3.6 Under **OPT1-0** — Option 1 milestone (Advanced Terraform)

| Tag | Title | Depends on |
|---|---|---|
| **OPT1-1** | KMS CMK module — customer-managed keys for every encryption-at-rest service (S3, DDB, EBS, RDS, ECR, CW Logs, SNS) | TF-1 |
| **OPT1-2** | ACM + TLS module — certificates for ALB; enforce HTTPS-only (encryption in transit) | TF-4 |
| **OPT1-3** | CloudWatch log group module — log everything; retention + encryption with CMK | OPT1-1 |
| **OPT1-4** | ECS autoscaling — target tracking on CPU + memory; scale-in protection during deploy | SVC-6, TF-4 |
| **OPT1-5** | Aurora Serverless v2 module + IAM authentication (also satisfies Option 3) | TF-2, OPT1-1 |
| **OPT1-6** | App reads from Aurora — wire SVC-3 (or new endpoint) to query Aurora SLv2 via IAM auth | OPT1-5, SVC-3 |

### 3.7 Under **OPT2-0** — Option 2 milestone (Bedrock + AI)

| Tag | Title | Depends on |
|---|---|---|
| **OPT2-1** | Bedrock AI reviewer endpoint — FastAPI route `POST /review/{pr_number}` that calls Bedrock Converse using the existing `.cursor/skills/bedrock-binding/` patterns | SVC-1 |
| **OPT2-2** | Multi-agent orchestration in service — service runs advocate + architect + skeptic personas in parallel; synthesizer agent merges verdicts | OPT2-1 |
| **OPT2-3** | Safe AI usage demonstration — prompt-injection defense (intent-judge shim), output validation (`ai-output-validation` skill), token-budget throttling | OPT2-2 |
| **OPT2-4** | Sample bad-code PR for AI reviewer — open a PR with deliberate flaws (SQL injection placeholder, wildcards in IAM, unencrypted bucket); AI reviewer posts a verdict comment | OPT2-2, AI-4 |

### 3.8 Under **OPT4-0** — Option 4 milestone (Operational Intelligence)

| Tag | Title | Depends on |
|---|---|---|
| **OPT4-1** | Python CLI skeleton — knack framework + pytest + `--cov-fail-under=85` (use existing `.cursor/skills/python-cli-and-testing/` patterns) | — |
| **OPT4-2** | `catalyst-ops audit-s3-encryption` — list S3 buckets, report SSE-KMS / SSE-S3 / unencrypted + public-access-block status | OPT4-1 |
| **OPT4-3** | `catalyst-ops gha-history` — fetch GitHub Actions workflow run history for a repo, summarise success/failure rate + p50/p99 duration | OPT4-1 |
| **OPT4-4** | `catalyst-ops iam-role-usage` — for each role, when was it last used (via `iam:GenerateServiceLastAccessedDetails`); flag stale roles | OPT4-1 |
| **OPT4-5** | Report output to S3 + summary to stdout — pluggable sink so the CLI can dump JSON to S3 for archival | OPT4-1, TF-1 |

### 3.9 Under **OPT5-0** — Option 5 milestone (HA / GitOps diagrams)

| Tag | Title | Depends on |
|---|---|---|
| **OPT5-1** | HA architecture diagram (`.drawio` + `.png`) — multi-AZ ECS + Aurora SLv2 + autoscaling + ALB + NAT redundancy | DOC-1 (base diagrams folder) |
| **OPT5-2** | GitOps workflow diagram — PR → plan comment → review → apply → deploy → andon signal → either done or rollback | DOC-1 |

---

## 4. Dependency graph (critical path)

```
TF-1 (backend) ───┬─► TF-2 (VPC) ───┬─► TF-4 (ECS+ALB) ─┬─► SVC-6 (taskdef) ─┐
                  ├─► TF-3 (ECR) ─────────────────────► CICD-5 (service-cd) │
                  ├─► TF-5 (DDB) ──────► SVC-3 (persist) ─┐                  │
                  ├─► TF-6 (Secrets)                       │                  │
                  ├─► TF-7 (IAM) ──┬─► CICD-1 (OIDC) ─┬─► CICD-2 (PR checks) │
                  │                │                   ├─► CICD-3 (tf-plan)  │
                  │                │                   └─► CICD-4 (tf-apply) │
                  └─► OPT1-1 (KMS)─┴─► OPT1-2/3/5 ...                        │
                                                                              │
SVC-1 (FastAPI) ──┬─► SVC-2 (endpoints) ──► SVC-3 (DDB)                       │
                  ├─► SVC-4 (observability) ──► SVC-7 (alarms)                │
                  └─► SVC-5 (validation+error) ◄─────────┘                    │
                                                                              │
                                                                       (deploy lands)
                                                                              │
                                                                              ▼
                                       OPT2-1 (Bedrock route) ──► OPT2-2/3/4
                                                              ──► AI-4 (open demo PR)
```

**Top of critical path = TF-1.** Nothing downstream works without the Terraform backend.

**Independent (can start day 1, in parallel)**:
- DOC-1 (diagrams folder + first diagram)
- DOC-3 (README reality alignment)
- AI-1 (CLAUDE.md)
- AI-2 (workflow narrative — can be drafted from the worklogs/ADRs that already exist)
- AI-3 (backfill empty issue bodies)
- CICD-6 (dependabot adoption)
- CICD-7 (PR template + issue templates)
- OPT4-1 (Python CLI skeleton)

---

## 5. Final issue inventory

**To create new**: 7 umbrella issues + 47 sub-issues = **54 new issues**
**Existing to reparent + backfill**: 8 (#7, #9, #12, #13, #15, #16, #17, #18)
**Existing to close**: 1 (#8 — superseded by #7 + #18)
**Existing to leave top-level**: 3 (#10, #11, #14)

**Net board state after creation**:
- 22 existing items remain (with re-parenting applied to 8 of them)
- 54 new items created
- 1 item closed
- = **75 items** on the board (~7 umbrellas + ~68 leaf deliverables)

If 54 new issues feels heavy, the highest-ROI subset to create first is the
24 issues **inside the critical path**:

```
TF-1, TF-2, TF-3, TF-4, TF-5, TF-7, TF-8, TF-9
SVC-1, SVC-2, SVC-3, SVC-4, SVC-5, SVC-6, SVC-7
CICD-0, CICD-1, CICD-2, CICD-3, CICD-4, CICD-5
DOC-0, DOC-1, DOC-2
AI-0, AI-1, AI-4
```

Plus the 5 optional-milestone umbrellas (OPT1-0, OPT2-0, OPT4-0, OPT5-0) so the
optional-claim tracking exists even if leaf issues are filled in later.

---

## 6. Default labels for every new issue

Per `STATE-MACHINE.md` §2, every Catalyst-managed issue carries all five construct
anchors plus state and type. Defaults for all new issues below unless otherwise noted:

```
tenant/catalyst
env/shared
lz/shared
project/platform
app/idp-platform   (or app/kaizen for AI-0 family; app/ops-intel for OPT4 family)
state/pending
type/deploy        (for TF-*, OPT1-*; the rest see table)
```

Per-family type label:

| Family | `type/*` label | `kind/*` modifier (optional) |
|---|---|---|
| TF-* | `type/deploy` | `kind/iac` |
| SVC-*, OPT2-* | `type/feat` | `kind/service` |
| CICD-* | `type/feat` | `kind/cicd` |
| DOC-*, OPT5-* | `type/docs` | — |
| AI-* | `type/chore` / `type/feat` | `kind/ai-workflow` |
| OPT1-*, OPT4-* | `type/feat` | `kind/option-N` |

Umbrellas (TOP-LEVEL parents) also carry `kind/umbrella`.

---

## 7. Recommended creation order

Create in this order so sub-issue parent references resolve cleanly:

1. **Umbrellas first** (CICD-0, DOC-0, AI-0, OPT1-0, OPT2-0, OPT4-0, OPT5-0)
2. **Reparent existing issues** (#9 → DOC-0; #12 → #7; #13 → #7; #15 → #18; #16 → #15; #17 → CICD-0)
3. **Backfill empty bodies** in existing kept issues (#7, #9, #12, #13, #15, #16, #17, #18) with Context/Scope/Gherkin AC
4. **Close** #8 with a comment pointing to #7 + #18 as the supersession
5. **Create TF-* leaf issues** under #7 (TF-1 first; the rest can be created in any order since parent is the same)
6. **Create SVC-* leaf issues** under #18
7. **Create CICD-* leaf issues** under CICD-0
8. **Create DOC-* leaf issues** under DOC-0
9. **Create AI-* leaf issues** under AI-0
10. **Create OPT1-*, OPT2-*, OPT4-*, OPT5-* leaf issues** under their umbrellas

GitHub sub-issue API: `gh api -X POST repos/Cloud-Byte-Consulting/Catalyst/issues/{parent}/sub_issues -f sub_issue_id={child_node_id}` — the child must be created first, then linked. The CLI also accepts `gh issue create ... --label ... --milestone ...` for the initial create.

---

## 8. Single-question gate before creation begins

Before opening 54 new issues, confirm one decision: **persistence layer for the service**.

- **DynamoDB only** → SVC-3 wires to DDB. OPT1-5/6 (Aurora SLv2) becomes Option 1 work only; Option 3 (IAM auth to Postgres) is declined.
- **DynamoDB + Aurora SLv2** → SVC-3 wires to DDB for state cache; OPT1-5/6 builds Aurora for app data. Option 1 + Option 3 both claimed. This is the recommended path because it gets two optional milestones from one piece of work, and Aurora SLv2 with IAM auth is the strongest single technical demonstration in the brief's optional list.

If we go DDB+Aurora, no issue list changes — just SVC-3 lands DDB plumbing and OPT1-6 lands Aurora plumbing.

---

## Related

- [`docs/plans/challenge-gap-analysis.md`](challenge-gap-analysis.md) — the gap analysis these issues close
- [`docs/ADR/STATE-MACHINE.md`](../ADR/STATE-MACHINE.md) — label vocabulary
- [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](../issue-execution-gherkin-workflow-2026-05-13.md) — issue body shape + Gherkin AC requirements
- [Project #3 — Catalyst Andon](https://github.com/orgs/Cloud-Byte-Consulting/projects/3/views/1)
