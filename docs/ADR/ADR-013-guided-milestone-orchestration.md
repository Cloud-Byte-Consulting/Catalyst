# ADR-013 — Guided milestone orchestration from templates

**Status**: Proposed · 2026-05-18

## Context

Catalyst delivers platform and application work through a durable GitHub Issues
state machine ([ADR-001](ADR-001-github-issues-as-state-machine.md)), golden-path
API contracts ([ADR-007](ADR-007-catalyst-api-golden-paths.md)), and a six-gate
agentic operating contract ([ADR-011](ADR-011-catalyst-agentic-workflow.md)).
Operators and agents already know *how* to comment, transition labels, and open
PRs — but starting a **multi-issue milestone** (new module, product surface, or
API improvement) still requires manual assembly: picking labels, drafting Gherkin,
sequencing architecture review before implementation, and preserving decisions
across sessions.

The Senior Platform Engineer challenge brief ([`docs/references/challenge-brief.md`](../references/challenge-brief.md))
grades **AI-native development workflow** (20% rubric weight) on whether AI is a
*core collaborator* with agent configuration in-repo and evidence of assisted
iteration — not merely on the existence of static prompts. Milestone templates
plus guided orchestration make that collaboration **repeatable** for net-new
modules, products, and API improvements rather than ad-hoc per chat session.

Gap analysis ([`docs/plans/challenge-gap-analysis.md`](../plans/challenge-gap-analysis.md))
maps related backlog items (#10 ADMIN agentic workflow, #11 Consumer agentic
workflow) as **optional** for submission; this ADR does not replace those issues
but defines the **canonical delivery spine** any future workflow framework must
implement. It is complementary to onboarding tracks ([ADR-012](ADR-012-onboarding-experience.md)):
onboarding wires *accounts and constructs*; milestone orchestration wires
*feature delivery episodes*.

## Decision

Adopt **guided milestone orchestration**: a version-controlled **milestone
template** instantiates a parent GitHub Issue (and optional child issues) on the
Catalyst Andon project; a Cursor/Claude agent session then walks the operator
through the **existing Catalyst delivery phases** below, carrying context forward
in issue comments, decision logs, and ADRs. Human approval gates are explicit;
automation never skips them.

### Milestone templates

Templates live under `docs/milestones/templates/` (to be populated per template).
Each template defines:

| Field | Purpose |
|---|---|
| `template_id` | Stable slug (e.g. `new-api-endpoint`, `new-service-module`) |
| `title_pattern` | Issue title with `{construct_address}` / `{feature}` placeholders |
| `labels` | Initial `type/*`, `state/pending`, tenant/env/project labels per [STATE-MACHINE.md](STATE-MACHINE.md) |
| `body_sections` | Pre-filled `## Context`, `## Scope`, fenced `gherkin` AC skeleton |
| `child_issues` | Optional checklist of follow-on issues (IaC, service, docs) |
| `golden_path_hint` | When applicable, pointer to ADR-007 endpoint(s) |
| `approval_gates` | Which phases require `state/blocked-on-human` before continuing |

Instantiation MAY be CLI-driven (`catalyst milestone create --template …`) or
documented manual copy; v1 prioritises **documented template + agent guidance**
over new control-plane code.

### Orchestration phases (mapped to Catalyst process)

Phases are **sequential gates**. Each phase ends with a structured issue comment
(per `docs/issue-execution-gherkin-workflow-2026-05-13.md`) and, where material,
an `### Agent Decision Log` entry ([ADR-011](ADR-011-catalyst-agentic-workflow.md)
gate 1). Board status follows ADR-001: `todo` → `in-progress` → `review` → `done`.

| Phase | Catalyst process step | Primary outputs | Human gate |
|---|---|---|---|
| **0 — Template bootstrap** | Milestone / epic issue creation | Parent issue + children on Andon; labels `state/pending` | Confirm template choice + scope |
| **1 — Architecture review** | Design / ADR alignment before code | Decision log; ADR draft or explicit "no ADR needed"; ADR-002 construct address validated | **Required** before issue fan-out |
| **2 — Issue creation** | Break work into trackable issues | Child issues with Context/Scope/Gherkin; dependencies via `Depends on #N` | Review issue set |
| **3 — Intent validation** | Pre-implementation scope check | `intent-judge` MCP `validate_intent` (`.cursor/rules/intent-judge.mdc`); ACCEPT/REJECT on tracking issue | REJECT → revise scope or escalate human |
| **4 — Implementation** | Agent execution per child issue | Commits; `state/agent-working`; model decision logs at material choices | `state/blocked-on-human` on scope/security surprises |
| **5 — Validation** | Tests, policy, coverage | pytest `--cov-fail-under=85`; `terraform fmt/validate/test`; Checkov/OPA where IaC touched | CI green on PR |
| **6 — Pre-PR peer review** | ADR-011 gate 5 | Sub-agent review on tracking issue; ACCEPT/REJECT table | All ACCEPT resolved |
| **7 — Security review** | Secret scan + hardening | GitHub MCP `secret_protection` / `run_secret_scanning` (`.cursor/rules/github-secret-scanning.mdc`); Trivy/SBOM if container touched | Scan clean or documented exception |
| **8 — PR creation** | Open linked PR | PR body: Context, Scope, Gherkin AC, Agent Decision Log, peer-review disposition, Verification | Human merge (not agent-merge) |

**Terminal success**: parent issue records `pr_url`, `pr_merged=true`, children
`state/done` where applicable, parent transitions to `state/done`.

### Context carry-forward

Orchestration MUST preserve:

1. **Decision log chain** — model, rationale, alternatives on the parent issue;
   child issues reference parent `#N` in `### Context`.
2. **ADR corpus** — accepted ADRs in `docs/ADR/` are load-bearing; contradictions
   require a new ADR or PR scope change (ADR-011).
3. **Issue bodies** — Context/Scope/Gherkin remain source of truth for AC;
   agents do not re-derive scope from chat memory alone.
4. **RLM handoffs** — artifacts >50k chars use ADR-004 scaffold with
   `docs/rlm-issue-handoff-template.md` fields on the tracking issue.
5. **Intent signals** — `intent-judge` validation results posted before phase 4.

### Intent judging (deliverable classes)

Before phase 4, the orchestrating agent classifies user intent against template
`deliverable_class`:

| Class | Examples | Typical golden path / issues |
|---|---|---|
| `module` | New Terraform module, shared library | `type/deploy` + `type/test` children; ADR if new construct pattern |
| `product` | New service surface, multi-issue epic | Parent `type/feat`; Track C onboard if new app ([ADR-012](ADR-012-onboarding-experience.md)) |
| `api_improvement` | New/changed Catalyst API route | ADR-007 contract check; RBAC matrix ADR-008 |

Misclassified intent MUST transition to `state/blocked-on-human` with a proposed
re-scope comment — not silent replanning.

## Consequences

- **Repeatable AI-native delivery** — reviewers see the same phase spine on every
  milestone; interview narrative aligns with challenge brief §1 (AI as collaborator).
- **Audit trail by construction** — parent + child issues reconstruct architecture →
  merge without replaying IDE sessions (ADR-001, ADR-011).
- **Template drift risk** — templates must be updated when STATE-MACHINE vocabulary
  or ADR-007 contracts change; owners: platform engineering + `adr-writer` skill.
- **Not a replacement for CI** — phases 5–7 still depend on `.github/workflows/`
  (ADR-006); orchestration coordinates gates, does not bypass them.
- **v1 is process + docs** — no mandatory new microservice; optional future
  `POST /milestones` on catalyst-api is out of scope until automation service
  rubric delivery (#18) lands.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Chat-only orchestration (no templates) | Context does not survive session restarts; violates ADR-001 audit model. |
| Backstage / Port developer portal wizard | ADR-005 and gap analysis §9 exclude portal for current phase. |
| Single mega-issue per milestone | Loses parallel child work, obscures done gates, breaks Andon visibility. |
| Skip intent-judge (trust prompt) | Heuristic gate is cheap; catches scope creep before expensive implementation. |
| Agent auto-merge PRs | Human merge preserves challenge/interview review story and branch protection. |
| New `phase/*` labels per orchestration step | ADR-001 and issue-execution doc use **project board columns** for workflow status; duplicate label vocabulary rejected. |

## Compliance

- All instantiated issues MUST include `## Context`, `## Scope`, and fenced
  `gherkin` acceptance criteria per [STATE-MACHINE.md](STATE-MACHINE.md) and
  ADR-001 §Decision point 5.
- Orchestrating agents MUST follow [ADR-011](ADR-011-catalyst-agentic-workflow.md):
  model decision logging, RLM at ~50k chars, OIDC-only AWS, container security gate,
  mandatory pre-PR peer review, GitHub MCP secret scanning before `pr_merged`.
- Construct addresses and RBAC MUST validate per [ADR-002](ADR-002-construct-hierarchy.md)
  and [ADR-008](ADR-008-catalyst-api-rbac.md) before Tier 2 golden-path calls.
- Significant milestones SHOULD use `type/feat` or `type/chore` parent issues;
  platform-only milestones MAY use `type/onboarding` when aligned with ADR-012.
- Template changes that alter gate order REQUIRE an ADR amendment or superseding ADR.

## Related

- [ADR-001](ADR-001-github-issues-as-state-machine.md) — Issues + Projects as state machine
- [ADR-007](ADR-007-catalyst-api-golden-paths.md) — Golden path API contracts
- [ADR-011](ADR-011-catalyst-agentic-workflow.md) — Six-gate agentic workflow
- [ADR-012](ADR-012-onboarding-experience.md) — Platform/org/app onboarding tracks
- [STATE-MACHINE.md](STATE-MACHINE.md) — Label and transition vocabulary
- [`docs/references/challenge-brief.md`](../references/challenge-brief.md) — Rubric (AI-native 20%)
- [`docs/plans/challenge-gap-analysis.md`](../plans/challenge-gap-analysis.md) — Issues #10, #11, #18
- [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](../issue-execution-gherkin-workflow-2026-05-13.md) — Comment shape
- `.cursor/rules/intent-judge.mdc` — Intent validation rule
- `.cursor/rules/github-secret-scanning.mdc` — Secret scanning gate
- `AGENTS.md` — Operating contract (gates 1–6)
