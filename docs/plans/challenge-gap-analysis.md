# Challenge Gap Analysis — Catalyst vs. Senior Platform Engineer Brief

**Branch**: `plan/challenge-gap-analysis` (cut from `release` @ `42f170d`)
**Sources**:
- [`docs/references/Senior-Platform-Engineer-Project.pdf`](../references/Senior-Platform-Engineer-Project.pdf) — canonical brief
- [`docs/references/challenge-brief.md`](../references/challenge-brief.md) — extract
- [GitHub Project #3 "Catalyst Andon"](https://github.com/orgs/Cloud-Byte-Consulting/projects/3/views/1) — 22 items, statuses captured 2026-05-14

**Purpose**: identify the deliverable gap between the challenge brief and what is actually
shipped on `release` today, so a focused build plan can close it before submission. This is
a planning artefact only — no service code is produced here.

**Last reviewed**: 2026-05-14

---

## 1. Executive summary

Catalyst's `release` branch contains an exceptionally complete **AI-native workflow
substrate** (5 ADRs, 13 Cursor agents, ~40 skills, 4 MCP servers, multiple plans) but
**none of the rubric's three largest deliverables exist as code yet**: no Terraform, no
service, no CI/CD pipeline, no diagrams, no Dockerfile, no application binary, no open PR.

Estimated rubric coverage today (best-case interpretation):

| Rubric area | Weight | Coverage | Notes |
|---|---:|---:|---|
| Automation service | 30% | **~0%** | No service code, no Dockerfile, no API surface, no AWS deployment |
| Infrastructure / Terraform | 25% | **~0%** | No `.tf` files; no `infrastructure/` directory; no modules; no Terraform tests |
| AI-native dev workflow | 20% | **~85%** | Vast scaffolding done; **missing**: ≥1 open PR demonstrating AI-assisted iteration (brief calls this out explicitly) |
| CI/CD & operational maturity | 15% | **~0%** | No `.github/workflows/` directory exists; no pipeline; no observability target wired |
| Communication / docs | 10% | **~70%** | Strong ADRs + plans; **missing**: `diagrams/` directory with draw.io artifact (mandatory), deploy README (current README describes principles not deploy steps), live deployment evidence |

**Implied current score: ~22–25 / 100.** The work to date is concentrated in the
lowest-weight rubric area (AI workflow, 20%) and the second-lowest (documentation, 10%);
the three highest-weight areas (Automation 30%, Terraform 25%, CI/CD 15% — **70% of the
grade**) are essentially un-started in code.

The good news: the agent scaffolding that already exists is *exactly* what is needed to
generate the missing deliverables quickly. Each backlog issue (#7–#18) targets a real gap;
the gaps that **do not yet have issues** are listed in §5.

---

## 2. Rubric-by-rubric gap detail

### 2.1 Automation service — 30%

**Brief requires** (PDF p.3):
- Service on ECS Fargate or Lambda supporting a common platform / developer workflow
- Containerized (Dockerfile) OR Lambda-packaged
- Exposed via load balancer, REST API Gateway, OR CloudFront
- Input validation + robust error handling
- Observability: structured logging, CloudWatch alarms with SNS for key metrics, dashboard
- Persists important data to S3, DynamoDB, OR RDS Aurora PostgreSQL
- **Accessible during the technical interview to demonstrate functionality** (i.e. deployed live)

**Exists on release**:
- `.cursor/agents/automation-architect.md` — persona describing how to build
- `.cursor/skills/fastapi-control-plane/SKILL.md` — pattern guidance
- `.cursor/skills/lambda-service-patterns/SKILL.md` — pattern guidance
- Issue [#18 — Create the catalyst api](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/18): "Built on FastAPI in a container; will need a self-hosted container registry"

**Missing**:
1. The service itself (no Python/TS/Go source code in repo)
2. `Dockerfile`
3. API contract / OpenAPI spec
4. Container registry decision (ECR — self-hosted is **not** required for the brief; default ECR is simpler)
5. Persistence layer choice + schema (issue #18 says FastAPI but doesn't decide S3 vs DynamoDB vs Aurora)
6. Structured logging library + format decision
7. CloudWatch alarms + SNS topic definitions
8. Health check endpoint
9. Input-validation framework (Pydantic if FastAPI)
10. Deployed running URL the interviewer can hit

**Issue alignment**: #18 covers the API existence but does not yet enumerate ① the
service's *purpose* (the brief gives four examples: self-service provisioning API,
GitHub webhook handler, multi-service health-check aggregator, developer portal backend
— Catalyst needs to pick one and commit), ② the persistence layer, ③ observability
specifics. **Issue #18 needs to be expanded or split** before work starts.

**Recommendation**: build the service around the work Catalyst has *already done*. The
strongest tie-in is a **GitHub Issues state-machine control plane** — a FastAPI service
on ECS Fargate exposing the verbs from `STATE-MACHINE.md` §4 (create, comment, assign,
label, close) via REST, persisting transitions to DynamoDB (the ADR-001 cache layer),
emitting CloudWatch metrics + alarms to SNS, fronted by an ALB. This makes the service
*be* the platform-as-a-product the agent scaffolding was designed to operate.

### 2.2 Infrastructure / Terraform — 25%

**Brief requires** (PDF p.3):
- All workloads deployed via Terraform
- Reusable modules as needed
- **Terraform Tests in one or more modules** verifying required configuration
- CI/CD pipeline for deploying Terraform
- Least-privilege IAM, **no wildcard policies**
- Secrets via SSM Parameter Store or Secrets Manager — **no hardcoded secrets**

**Exists on release**:
- `.cursor/agents/terraform-engineer.md` — persona
- `.cursor/agents/aws-platform-engineer.md` — persona
- `.cursor/skills/terraform-module-design/SKILL.md`
- `.cursor/skills/terraform-native-tests/SKILL.md`
- `.cursor/skills/iam-policy-craft/SKILL.md`
- `.cursor/skills/encryption-patterns/SKILL.md`
- `.cursor/skills/aws-platform-engineering/templates/*.tf.tmpl` — 8 Terraform templates (ECS Fargate, ECR scan-on-push, OIDC, base image policy, Bedrock, etc.)
- `.cursor/skills/checkov-cloud-image-static-analysis/SKILL.md`
- Issue [#7 — Implementing IaC Best practices](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/7) (backlog)

**Missing**:
1. The `infrastructure/` directory itself (no `.tf` files committed)
2. Backend configuration (S3 + DynamoDB lock table for Terraform state)
3. Module structure decision (the brief and ADR-002 imply: `infrastructure/modules/<name>/` plus a `live/<env>/` root for stage roots)
4. KMS keys (CMK) — required by **Option 1** which is the most natural fit to claim
5. VPC + networking module
6. ECR repository module (or use of pre-built)
7. ECS cluster + service module
8. ALB + listener module
9. DynamoDB table module
10. Aurora Serverless v2 module (if persistence choice = Aurora)
11. IAM roles with **scoped** policies (the templates exist but no live policies)
12. SSM parameter / Secrets Manager module
13. Terraform `tests/` blocks (`run` blocks with `command = plan`/`apply`, assertions)
14. Provider lock file + version pinning
15. `terraform fmt` + `terraform validate` baseline

**Issue alignment**: #7 exists but is empty. Issues #12 (Checkov) and #13 (OPA) cover IaC
policy gates but not the IaC itself. **Issue #7 needs full content** (Context, Scope,
Acceptance Criteria in Gherkin) before work starts. Issue #14 (AWS SCPs) addresses
Organization-level guardrails — relevant but not on the critical path for the rubric;
land it after the core IaC.

### 2.3 AI-native development workflow — 20%

**Brief requires** (PDF p.3):
- AI tools as a **core** part of development
- AI agent config in repo (`CLAUDE.md`, custom instructions, MCP configs, or equivalent)
- **At least one open PR** showing AI-assisted process (commits, conversation, iteration)
- Interview discussion: what worked, course-corrections, improvements

**Exists on release** — substantial:
- `AGENTS.md` (workspace memory + operating rules)
- `.cursor/agents/` × 13 personas (advocate, architect, aws-platform-engineer, automation-architect, checkov-expert, cicd-operator, opa-expert, platform-engineering-architect, score-expert, security-hardener, terraform-engineer, ai-reviewer-architect, skeptic)
- `.cursor/skills/` × ~40 skills (RLM, GitHub state machine, Terraform module design, IAM policy craft, AI observability, etc.)
- `.cursor/rules/` × 5 rules (aws-platform-engineering, catalyst-agents, github-secret-scanning, intent-judge, rlm-workflow)
- `.cursor/mcp.json` + 4 MCP servers (RLM REPL, AWS-PE wrapper, Bedrock binding, intent-judge shim)
- `.claude/skills/rlm/` + `.claude/agents/rlm-subcall.md` (Claude Code parity)
- 5 ADRs covering issues-as-state-machine, construct hierarchy, environments, RLM, AWS agentic platform engineering
- Worklog directory pattern with structured handoff comments

**Missing**:
1. **At least one open PR** — `gh pr list --state open` returns `[]`. The brief is explicit. This is a **3-line fix** (open a draft PR with a small AI-assisted change) but it is mandatory.
2. **A live AI-assisted iteration story to talk through in interview** — the merged PRs (#2, #4, #6, #20, #22, #24, #26, #28, #30, #31) are excellent evidence on paper; an open PR with active conversation and course-correction is the part the brief asks for specifically.
3. **`CLAUDE.md` at repo root** — the brief gives this as the canonical example. Catalyst uses `AGENTS.md` instead, which is acceptable, but a brief `CLAUDE.md` pointing to `AGENTS.md` and listing the 4 MCP servers would mirror the brief's vocabulary and reduce friction for reviewers using Claude Code.

**Issue alignment**: Issues #10 (ADMIN agentic workflow) and #11 (Consumer agentic workflow)
sit in this rubric area but are backlog. They are **valuable** but not strictly required —
the rubric grades AI as a development collaborator, not the existence of consumer
plug-ins. Suggest scoping #10 / #11 to "design only" for the submission window and
implementing post-submission if time allows.

### 2.4 CI/CD & operational maturity — 15%

**Brief requires** (PDF p.4):
- Pipeline design (Terraform via CI/CD; bonus for app via CI/CD)
- Observability (already counted in §2.1 for the service)
- Deployment strategy explicit

**Exists on release**:
- `.cursor/skills/github-actions-design/SKILL.md`
- `.cursor/skills/aws-platform-engineering/templates/github-actions-oidc.yml.tmpl`
- `.cursor/skills/aws-platform-engineering/templates/container-scan-trivy.yml.tmpl`
- `.cursor/skills/aws-platform-engineering/templates/container-scan-scout.yml.tmpl`
- `.cursor/skills/aws-platform-engineering/templates/dependabot-container.yml.tmpl`
- `.cursor/skills/cicd-operator.md` (wait — this is an agent file under agents/, but the pattern guidance for pipelines is there)
- `.cursor/skills/deployment-strategies/SKILL.md`
- `.cursor/rules/github-secret-scanning.mdc` (gate)
- Issue [#17 — Implement the github action for platform api](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/17) (backlog, empty)

**Missing**:
1. `.github/workflows/` directory does not exist
2. `tf-plan.yml` workflow (README references it; doesn't exist)
3. `tf-apply.yml` workflow (README references it; doesn't exist)
4. `ci.yml` workflow for the service (build + test + image push)
5. `cd.yml` workflow for the service (deploy via ECS service update / Lambda alias shift)
6. `pr-checks.yml` (lint, sec scan, Terraform fmt/validate, Checkov, OPA/Conftest)
7. **GitHub OIDC IAM role** (Terraform module + provisioned trust policy)
8. `dependabot.yml` (one template exists — needs adoption)
9. PR template + Issue templates at `.github/` (README claims `.github/PULL_REQUEST_TEMPLATE.md` exists; it doesn't)
10. Deployment strategy decision: rolling vs blue/green for ECS, or alias-shift for Lambda — pick one + document
11. `CHANGELOG.md` or release-tagging strategy
12. Branch protection rules (cannot live in repo files but can be declared via Terraform with the GitHub provider)

**Issue alignment**: #17 covers the platform-api GitHub Action but is empty. Need
companion issues for the Terraform pipeline (not yet created) and the PR-checks
workflow (not yet created). See §5.

### 2.5 Communication & documentation — 10%

**Brief requires** (PDF p.4):
- README with **deploy steps** + explanation of what was built
- Design rationale (1–2 paragraphs) on a key decision + alternatives — in README or `DECISIONS.md`
- Technical diagram via **draw.io** (or similar) committed under `diagrams/` (image AND/OR `.xml`)

**Exists on release**:
- 5 ADRs (ADR-001 through ADR-005) — far exceeds "1–2 paragraph rationale"
- Multiple plans + research docs
- Worklog entries
- README (5 KB) describing principles and references

**Missing**:
1. **`diagrams/` directory** — does not exist. Brief is explicit: must contain image and/or `.xml`. Mandatory.
2. **README deploy steps** — current README describes principles + agent surface; no `# Deploy` section with the actual commands a reviewer runs to deploy the stack
3. **Architecture diagram** — at minimum: the IDP control-plane data flow (GitHub → ECS service → DynamoDB → CloudWatch → SNS → Slack). Recommend a second diagram for Option 5 (HA secure infra OR GitOps workflow) if claiming Option 5.
4. **Live deployment evidence** — screenshots, URL, or a one-shot demo script (the brief calls this out for the interview)
5. **`README` claims that don't yet match reality**: lines 16–25 reference workflow files, modules, services, and templates that don't exist on disk. This is a **credibility risk for the reviewer** — fix by either building them or rewording as "designed shape, to be implemented in issue #N."

**Issue alignment**: Issue [#9 — Create Threat Model Assessment](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/9) is the only doc issue and is empty. Threat model is bonus, not mandatory. **A separate issue for the diagrams + deploy README is missing.** See §5.

---

## 3. "Digging deeper" — which optional(s) to claim

Brief requires **at least one** optional. Catalyst's existing scaffolding aligns naturally
with three of the six options. Recommendation: claim **Option 1 + Option 2 + Option 4**
explicitly, hint at Option 5 if the diagram is good enough. Detailed fit assessment:

| Option | Required to add on top of core | Catalyst pull strength | Recommend |
|---|---|---:|---|
| **1. Complex Terraform** — modules everywhere, CMK encryption at rest, in-transit encryption, logging, **serverless RDS queried by app**, autoscaling, automated IaC checks in CI | If serving Aurora Serverless v2 + KMS module + checkov/tfsec in CI on top of the core Terraform | **High** — already have Checkov + OPA + encryption-patterns skills | **Yes** |
| **2. AI Maturity** — **Bedrock in containerized service**, safe AI usage, multiple AI tasks together, AI for PR reviews + sample PR with bad code | Wire Bedrock into the FastAPI service; ship one workflow that uses the AI reviewer trio (advocate/architect/skeptic) and posts a verdict to an example PR with deliberate flaws | **High** — already have Bedrock MCP, AI reviewer architect, three review personas, intent-judge shim | **Yes** |
| **3. Dev skills** — own app, IAM-auth to Postgres, health checks | Stronger app + IAM-auth-to-Aurora | **Medium** — overlaps with Option 1; only add if Aurora is the persistence choice | Defer (subsumed by 1) |
| **4. Operational Intelligence** — Python or Go tool aggregating ops data (GHA history, S3 audit, IAM role usage, CW log ingestion, resource inventory) | A second CLI/Lambda/script that pulls + reports | **Medium-High** — fits the "ops-intel" persona already in design (ADR-005 references it) | **Yes — small** — one Python module hitting S3 encryption audit + GHA workflow history makes a strong showing |
| **5. Detailed diagrams** — HA / production GitOps | One more polished diagram | **Low effort** — if Option 1's serverless Aurora + autoscaling is shipped, the diagram showing it is essentially Option 5 | **Yes — free** |
| **6. Something else cool** | — | — | Decline (no time premium) |

**Net recommendation**: Options **1, 2, 4, 5**. Build Options 1 + 2 + 4 as features of the
same service; Option 5 falls out of the diagram you must produce anyway.

---

## 4. Project-board issue alignment

Mapping each backlog issue to which gap it closes:

| # | Title | Status | Rubric area | Gap closes | Action |
|---|---|---|---|---|---|
| 1 | EA CLI MCP server | Done | AI workflow | Issue-driven workflow | ✓ |
| 3 | RLM for long running tasks | Done | AI workflow | Long-context handling | ✓ |
| 5 | RLM Cursor compat | Done | AI workflow | Multi-host parity | ✓ |
| 7 | **Implementing IaC Best practices** | **Backlog — empty** | Infrastructure 25% | The entire Terraform deliverable | **Expand body** (Context/Scope/Gherkin AC) → split into ≥3 sub-issues (network + ECS + persistence) |
| 8 | **Develop AWS Application stack** | **Backlog — empty** | Automation 30% | The deployed service stack | **Expand body**; clarify if this is the same as #18 or an umbrella |
| 9 | Threat Model Assessment | Backlog — empty | Docs 10% | Bonus — not required | Optional; expand if time permits |
| 10 | ADMIN agentic workflow framework | Backlog | AI workflow | Bonus | Optional; design-only for submission |
| 11 | Consumer agentic workflow framework | Backlog | AI workflow | Bonus | Optional; design-only for submission |
| 12 | Implementing Checkov | Backlog — empty | Infrastructure 25% | IaC policy gate | **Expand body**; depends on #7 |
| 13 | Implementing Open Policy Agent | Backlog — empty | Infrastructure 25% | IaC policy gate | **Expand body**; depends on #7 |
| 14 | Implementing AWS SCPs | Backlog | Infrastructure (bonus) | Org-level guardrails | Defer — out of rubric scope |
| 15 | **Develop user interaction points** (CLI + Action YAML) | Backlog | Automation 30% / CI/CD 15% | User surface | **Expand**; depends on #18 |
| 16 | Implement the client CLI | Backlog — empty | Automation 30% | CLI surface | **Expand**; could double as Option 4 ops-intel tool |
| 17 | Implement the GitHub Action for platform API | Backlog — empty | CI/CD 15% | The Action surface | **Expand**; depends on #18 |
| 18 | **Create the catalyst API** (FastAPI in container) | Backlog | Automation 30% | The core service | **Expand**: pick purpose + persistence + observability spec |
| 19, 21, 23, 25, 27, 29, 32 | Various platform-catalyst imports + secret scanning + judge shim | Done | AI workflow | Scaffolding | ✓ |

### What's wrong with the current issue set

1. Six backlog issues have **empty bodies** (no Context, no Scope, no Gherkin AC) — that
   violates Catalyst's own state-machine rules (`STATE-MACHINE.md` §5: issue body must
   have Context + Scope + Gherkin AC). They will fail the `gherkin-validator` agent the
   moment one picks them up.
2. **No issue covers the `diagrams/` directory** (mandatory deliverable).
3. **No issue covers the README deploy-steps rewrite** (mandatory deliverable).
4. **No issue covers opening a PR for AI-assisted iteration evidence** (mandatory deliverable).
5. **No issue covers the GitHub OIDC IAM role provisioning** (required by every workflow).
6. **No issue covers the Terraform backend bootstrap** (S3 state bucket + DynamoDB lock table — chicken-and-egg requires a manual / Click-Ops bootstrap or a separate small Terraform root).
7. **No issue covers the Bedrock-in-service work** (Option 2's claim depends on this).
8. **No issue covers the Operational Intelligence tool** (Option 4's claim depends on this).

---

## 5. Missing issues — proposed new issue list

Issue numbers will be auto-assigned by GitHub. Listing in build order. Each entry shows
the rubric area, dependencies, and the proposed labels (matching the `STATE-MACHINE.md`
vocabulary already in use on the board).

| Proposed title | Rubric / weight | Type | Depends on | Labels |
|---|---|---|---|---|
| **A. Bootstrap Terraform backend** (S3 state bucket + DynamoDB lock + KMS CMK) | Infra 25% | `type/deploy` + `kind/bootstrap` | none | `tenant/catalyst, env/dev, lz/shared, project/platform, app/idp-platform, type/deploy, state/pending` |
| **B. Provision GitHub OIDC trust for AWS** (IAM identity provider + role + scoped policy) | CI/CD 15% | `type/deploy` | A | `… type/deploy, kind/security` |
| **C. VPC + networking module** (subnets, NAT, route tables, endpoints) | Infra 25% | `type/deploy` | A | `… type/deploy` |
| **D. ECR repository module + scan-on-push** | Infra 25% | `type/deploy` | A | `… type/deploy` |
| **E. ECS Fargate cluster + ALB module** | Infra 25% | `type/deploy` | C, D | `… type/deploy` |
| **F. DynamoDB table module** (control-plane state cache) | Infra 25% | `type/deploy` | A | `… type/deploy` |
| **G. Aurora Serverless v2 module + IAM auth** (Option 1 + Option 3 fit) | Infra (bonus) | `type/deploy` | C | `… type/deploy, kind/option-1` |
| **H. Terraform Tests for every module** (`tests/*.tftest.hcl` with `run` blocks + assertions) | Infra 25% | `type/test` | C, D, E, F, G | `… type/test` |
| **I. Catalyst FastAPI service skeleton** (Dockerfile + Pydantic models + health endpoint + structured logging) | Auto 30% | `type/feat` | none (parallel to A) | `… type/feat` — expand existing #18 |
| **J. Service: GitHub-Issues control-plane endpoints** (create / comment / transition / close — wraps `STATE-MACHINE.md` verbs) | Auto 30% | `type/feat` | I | `… type/feat` |
| **K. Service: persistence layer to DynamoDB** (issue cache, dedup, audit) | Auto 30% | `type/feat` | F, I | `… type/feat` |
| **L. Service: Bedrock AI reviewer endpoint** (calls advocate/architect/skeptic, returns verdict) — **Option 2 anchor** | Auto 30% / AI 20% | `type/feat` | I | `… type/feat, kind/option-2` |
| **M. Service: observability** (CloudWatch log groups, alarms, SNS topic, dashboard) | Auto 30% / CI/CD 15% | `type/feat` | I | `… type/feat` |
| **N. Service: input validation + error handling sweep** (verify Pydantic schemas, retry/backoff, structured error responses) | Auto 30% | `type/feat` | J, K | `… type/feat` |
| **O. CI workflow: `pr-checks.yml`** (terraform fmt/validate, tflint, Checkov, OPA/Conftest, Trivy, secret scan, pytest --cov-fail-under=85) | CI/CD 15% | `type/feat` | B, H | `… type/feat` — closes #12, #13 partially |
| **P. CI workflow: `tf-plan.yml`** (plan on PR, post output as comment) | CI/CD 15% | `type/feat` | B, H | `… type/feat` |
| **Q. CD workflow: `tf-apply.yml`** (apply on merge to release, manual approval for prod) | CI/CD 15% | `type/feat` | B, P | `… type/feat` |
| **R. CD workflow: `service-cd.yml`** (build image, push ECR, update ECS service / Lambda alias shift) | CI/CD 15% | `type/feat` | B, E, I | `… type/feat` |
| **S. Ops-Intel CLI** (Python, knack-based — S3 encryption audit + GHA workflow run history) — **Option 4 anchor** | Auto 30% (bonus) | `type/feat` | none | `… type/feat, kind/option-4` — covers #16 partially |
| **T. `diagrams/` directory + architecture diagram (.drawio + .png)** (control-plane data flow; second diagram for HA topology — Option 5) | Docs 10% | `type/docs` | I, E | `… type/docs` |
| **U. README rewrite: deploy steps + design rationale + reality alignment** | Docs 10% | `type/docs` | A–R landing | `… type/docs` |
| **V. Open a "demo PR" with deliberate bad code** to showcase AI reviewer + leave open for interview — **mandatory per brief** | AI 20% / Option 2 fit | `type/feat` + `kind/demo` | L | `… type/feat, kind/demo` |
| **W. Backfill the empty backlog issues** (#7, #8, #9, #12, #13, #15, #16, #17) with proper Context / Scope / Gherkin AC, OR close them and let A–V supersede | AI 20% | `type/chore` | none | `… type/chore` |

23 proposed issues. Several **subsume or supersede** existing backlog entries:

- A, C, D, E, F, G, H → close or absorb **#7** (IaC best practices)
- I, J, K, L, M, N → expand and absorb **#18** (catalyst API) and **#8** (AWS application stack)
- O, P, Q, R → expand and absorb **#17** (GitHub Action for platform API)
- O → closes **#12** (Checkov) and **#13** (OPA) as steps within
- S → absorbs **#16** (client CLI) and adds Option 4 framing
- T, U → close docs gap not covered by any existing issue
- V → fills the **single most important missing piece** (mandatory per brief)
- W → cleanup pass on the empty issue bodies

---

## 6. Proposed build sequence — 4 waves

Each wave is sized for one focused day of agent-led work plus human review. Order assumes
the platform is built as it deploys itself (Catalyst's agent scaffolding generates the
Terraform via the `terraform-engineer` + `aws-platform-engineer` personas, the service
via `automation-architect`, the workflows via `cicd-operator`, etc.).

### Wave 1 — Bootstrap & visibility (issues A, B, T-stub, U-stub, V-stub, W)
**Goal**: turn ON OIDC, prove the AWS account works, open the mandatory demo PR with a
placeholder so the AI-workflow gate is satisfied immediately, and align README with
reality so a reviewer landing today doesn't see promised-but-missing files.
**Acceptance**: AWS account reachable from GitHub Actions via OIDC; S3 + DDB backend
exists; README has accurate "what exists vs. planned" framing; `diagrams/` exists with
at least a stub; one open PR linked.

### Wave 2 — Infrastructure (issues C, D, E, F, H, O, P, Q)
**Goal**: Terraform modules cover the full stack the service will sit on. Tests pass.
Plan/apply pipelines green. Checkov + OPA + Trivy gates in `pr-checks.yml`.
**Acceptance**: `terraform test` passes across all modules; `tf-plan.yml` runs on every
PR; `tf-apply.yml` runs on merge to release with manual approval for prod; OPA blocks
wildcards; Checkov blocks public S3 + unencrypted resources.

### Wave 3 — Service (issues I, J, K, L, M, N, R)
**Goal**: FastAPI service shipped to ECS Fargate behind ALB. Health check green. Bedrock
endpoint live. Observability wired. CD pipeline updates the service on every release-branch
merge. **Issue #18 is the umbrella for this wave.**
**Acceptance**: Service URL responds 200 on `/health`; `POST /issues` round-trips through
DynamoDB; `POST /review/{pr}` calls Bedrock and returns a verdict; CloudWatch alarms exist
for 5xx rate, p99 latency, ECS task count; SNS topic publishes to a test endpoint.

### Wave 4 — Bonus + polish (issues G, S, T, U, V, plus docs/diagrams sweep)
**Goal**: Land Option 1 (Aurora Serverless v2 + IAM auth), Option 4 (ops-intel CLI), and
polish docs + diagrams to interview-ready. Fill the demo PR with a deliberate flaw, let
the AI reviewer comment on it, leave it open.
**Acceptance**: Aurora Serverless v2 exists, app reads from it; ops-intel CLI produces a
report on S3 encryption posture across the account; two diagrams committed under
`diagrams/` (`.drawio` + `.png`); README has a deploy section a stranger can follow; the
demo PR has an active AI conversation thread visible to reviewers.

---

## 7. Acceptance gate per rubric area

Define done before starting. These translate directly to Gherkin `Scenario:` blocks for
each issue per Catalyst's `STATE-MACHINE.md` requirements.

### Automation service (30%) — done when
- `curl https://<alb-url>/health` returns `200 OK`
- `POST /issues` round-trips through DynamoDB (write + read)
- `POST /review/{pr_number}` returns a Bedrock-backed verdict
- Service emits structured JSON logs visible in CloudWatch Logs Insights
- At least 2 CloudWatch alarms tied to SNS
- A live URL is recorded in the README and the closing issue comment

### Infrastructure / Terraform (25%) — done when
- `terraform fmt -check` passes
- `terraform validate` passes
- `terraform test` runs and **at least 3 modules** have `*.tftest.hcl` with `run` blocks asserting required configuration
- `checkov -d infrastructure/` returns zero HIGH/CRITICAL
- `conftest test infrastructure/ --policy infrastructure/policy/opa/` returns zero failures
- No wildcards in IAM policies (`rg '"Action":\s*"\*"' infrastructure/` returns empty)
- No hardcoded secrets (`gitleaks detect` returns clean)

### AI-native dev workflow (20%) — done when
- `gh pr list --state open` returns ≥ 1 PR
- The open PR has ≥ 1 AI-authored review comment AND ≥ 1 commit responding to it
- `AGENTS.md` + `CLAUDE.md` both present at repo root (CLAUDE.md a 10-line pointer is fine)
- `.cursor/mcp.json` registers ≥ 3 MCP servers (already true)
- Interview talking-points doc exists at `docs/ai-workflow-narrative.md` covering: what worked, course-corrections, improvements

### CI/CD & operational maturity (15%) — done when
- `.github/workflows/` contains at minimum: `pr-checks.yml`, `tf-plan.yml`, `tf-apply.yml`, `service-cd.yml`
- All workflows use **OIDC** to AWS (no long-lived keys; `rg 'AWS_ACCESS_KEY' .github/` returns empty)
- Branch protection on `release` requires green checks
- A merge to `release` triggers a deploy that updates the live URL within ≤ 10 minutes

### Communication & documentation (10%) — done when
- `diagrams/` directory exists with at least one `.drawio` AND one `.png`
- README has a `## Deploy` section with copy-pasteable commands a stranger can run
- README's "principles" table either matches reality file-for-file OR clearly labels aspirational items
- 5 ADRs remain valid (no contradictions with what was actually built)
- `git log` reads cleanly (conventional commits, no `fix typo`-style noise on `release`)

---

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AWS account hit by quotas / billing surprise | Medium | High | Bootstrap with smallest viable footprint; tag everything `Catalyst-Owner=demo`; cost-explorer alarm at $20/day |
| Bedrock model unavailable in chosen region | Medium | Medium | Pre-flight check; default region `us-east-1` where all Anthropic models are available |
| Aurora Serverless v2 cold start blows interview timing | Medium | Medium | Pre-warm before interview; or fall back to DynamoDB-only (Option 1 then loses some teeth) |
| README claims drift again as wave 3 changes scope | High | Low | Wave 1's task U-stub explicitly aligns README with reality before any new feature lands |
| Empty backlog issues picked up by agents and fail `gherkin-validator` | High | Low | Wave 1's task W backfills them before any agent picks them up |
| Open demo PR forgotten before submission | Medium | High | Wave 1 opens a stub PR immediately; refined in Wave 4 |
| Reviewer can't reach the deployed service | Medium | High | Add `terraform output service_url` to README deploy section; record screenshot fallback |

---

## 9. Decision matrix — what NOT to do

To keep scope honest, these are intentionally out-of-scope for the submission window:

| Excluded | Why |
|---|---|
| Multi-account landing zones (AFT / Control Tower) | The construct hierarchy (ADR-002) accommodates this conceptually; building real OUs adds days for zero rubric points |
| Issue #14 (AWS SCPs) | Same reason — bonus for an enterprise scenario the reviewer is not graded against |
| Backstage / Port portal | ADR-005 explicitly excludes this from the current phase |
| Replacing GitHub Issues as state machine | ADR-001 is authoritative |
| Service mesh (App Mesh / Istio) | Catalyst is one service, not many |
| EKS | Brief explicitly names ECS Fargate or Lambda; no EKS premium for the grade |
| Vector DB / RAG stack | ADR-004 explicitly rejects in favour of RLM for in-session work |
| Custom dashboard UI for the andon | ADR-001: GitHub Projects board IS the andon |

---

## 10. Single-page summary

**Where we are**: ~22–25 / 100 on the rubric, concentrated in the lowest-weight areas.

**What's missing**: the 70 points of the grade — service, Terraform, CI/CD — exist as
*persona definitions and templates* but not as code or deployed infrastructure. Plus four
mandatory items the brief calls out specifically: an open PR, a `diagrams/` directory, a
deploy README, and at least one digging-deeper option.

**The shortest credible path to a strong submission** (4 waves, ~4 focused days):

1. Bootstrap account + OIDC + open the mandatory demo PR + align README with reality
2. Land Terraform modules with tests + CI/CD pipeline for IaC
3. Build the FastAPI service with Bedrock endpoint + observability + CD pipeline
4. Add Aurora Serverless v2 (Option 1), the ops-intel CLI (Option 4), polished diagrams (Option 5), and fill the demo PR with deliberate flaws for the AI reviewer to catch (Option 2)

**Why this works**: every wave uses the agent scaffolding Catalyst has already built —
`terraform-engineer` writes the modules, `automation-architect` writes the service,
`cicd-operator` writes the workflows, `ai-reviewer-architect` reviews the demo PR, the
RLM scaffold reads any large artifact, the intent-judge shim gates the deploys. The
substrate is done. The artefacts are not.

---

## Related

- [`docs/references/Senior-Platform-Engineer-Project.pdf`](../references/Senior-Platform-Engineer-Project.pdf)
- [`docs/references/challenge-brief.md`](../references/challenge-brief.md)
- [`docs/ADR/ADR-001-github-issues-as-state-machine.md`](../ADR/ADR-001-github-issues-as-state-machine.md)
- [`docs/ADR/ADR-002-construct-hierarchy.md`](../ADR/ADR-002-construct-hierarchy.md)
- [`docs/ADR/ADR-005-aws-agentic-platform-engineering.md`](../ADR/ADR-005-aws-agentic-platform-engineering.md)
- [`docs/plans/aws-agentic-platform-engineering-plan.md`](aws-agentic-platform-engineering-plan.md)
- [`docs/plans/platform-catalyst-import-plan.md`](platform-catalyst-import-plan.md)
- [GitHub Project #3 — Catalyst Andon](https://github.com/orgs/Cloud-Byte-Consulting/projects/3/views/1)
