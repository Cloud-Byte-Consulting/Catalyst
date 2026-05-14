# ADR-001 — GitHub Issues + Projects as the durable state machine

**Status**: Accepted · 2026-05-11
**Related**: [`docs/ADR/STATE-MACHINE.md`](ADR/STATE-MACHINE.md), [ADR-002](ADR-002-construct-hierarchy.md), [ADR-003](ADR-003-static-and-ephemeral-environments.md)

## Context

Catalyst is an Internal Developer Platform whose automations (blue/green
deploys, secrets rotation, preview-environment lifecycle, AI PR review,
operational-intelligence findings) all share one shape: **a request comes in,
an agent processes it, the result needs to be auditable and resumable across
restarts.** A prior design treated DynamoDB (and relational catalogs) as the
primary substrate for in-flight automation state. That choice was correct for
"what database do we use" but wrong for "what is the agent's state machine."

In May 2026, Nate B. Jones published *"AI agents are about to route around
every tool that can't pass 5 structural tests"* (`natesnewsletter`,
2026-05-02), arguing that issue trackers — by accident, because they were
built to compensate for human coordination weaknesses — are the cleanest
agent substrate available. He framed five properties:

1. **Persistent state** outside any individual run (an Issue row in a DB).
2. **State machine with defined transitions** (NEW → ASSIGNED → RESOLVED → ...).
3. **Ownership** as a first-class field (the assignee).
4. **Defined verbs** with clear semantics (create, comment, assign, close).
5. **Audit history** logged with timestamp + actor by default.

OpenAI's Symphony shipped Linear as the literal control plane for autonomous
coding agents and reportedly saw 500% more landed PRs on internal teams. The
pattern is not Linear-specific — it is the issue-tracker substrate
generally. **GitHub Issues + GitHub Projects are the same substrate, owned
by GitHub, free, already integrated into the developer workflow.**

For a retail pharmacy and insurance provider specifically, the team's day-to-day is automating things like
blue/green deploys and secrets management to reduce cloud-ops workload. That
work *is* a queue of requests with state, ownership, and audit. The
question "what data store backs Catalyst's automation queue" had a
pre-baked answer hiding in plain sight.

## Decision

**Catalyst's automations use GitHub Issues + a GitHub Project (board) as the
durable state machine. DynamoDB demotes from "primary state" to
"cache/index for fast queries." Aurora Serverless v2 retains its role for
service-catalog and deployment-lineage relational data.**

Concretely:

1. Each automation request — a deploy, a secret rotation, a preview-env
   spin-up, a PR review, an ops-intel finding — has an **Issue** in the
   `catalyst-idp` repo.
2. Issue **labels** encode the state machine. The vocabulary is fixed (see
   `docs/ADR/STATE-MACHINE.md`). Label transitions are validated client-side by
   `catalyst/state_machine.py` and enforced by an OPA/Conftest policy
   running in CI for any direct-label-edit PRs.
3. Issue **assignees** encode current ownership. Bot user
   `catalyst-bot[bot]` owns the issue while it's `state/agent-working`.
   Re-assignment to a human is a transition through `state/blocked-on-human`.
4. Issue **comments** are the audit trail. Every state transition,
   intermediate step, error, and Bedrock-agent finding lands as a comment.
   This is git-observable: `gh issue view <N> --comments`.
5. A **GitHub Project (v2 board)** named "Catalyst Andon" provides a visible
   state machine. Columns: `Pending`, `Agent Working`, `Blocked on Human`,
   `Done`, `Rolled Back`. The board IS the andon — anyone can see the line.
6. **Labels and the Project are managed by Terraform** via the `github`
   provider, so the state machine is reproducible and version-controlled
7. **DynamoDB** holds:
   - Idempotency dedup keys (webhook delivery IDs, TTL 24h).
   - Per-repo daily Bedrock token budgets (DDB conditional updates).
   - A read-through cache of the issue catalog (so `catalyst-api`'s
     `GET /services` doesn't cold-call GitHub for every request).
8. **Aurora SLv2** holds the relational service-catalog and
   deployment-lineage data — joins still belong in SQL.

### What this means for the runtime

- `catalyst-api`'s `POST /deploy` does not orchestrate the deploy. It
  **creates an Issue** with the deploy plan in the body and labels
  `type/deploy`, `state/pending`. It returns the issue URL.
- The webhook handler reacts to the `issues.labeled` event when a human or
  another automation transitions `state/pending → state/agent-working`. It
  enqueues a deploy-orchestration message to SQS.
- The deploy-orchestrator Lambda picks up the SQS message, reads the issue
  body for the plan, runs CodeDeploy, and **comments on the issue** with
  progress. Final state is `state/done` (success) or `state/rolled-back`
  (failed) or `state/blocked-on-human` (refused — needs human decision).

### What this enables

- **Free observability**: the GitHub Project IS the dashboard for in-flight
  automation work. SREs at 2 AM open the board, not a custom UI.
- **Free audit**: every transition, every Bedrock finding, every error has
  a timestamped record in GitHub. CloudTrail-equivalent for free.
- **Free dependency graph**: GitHub's `Closes #N` / `Depends on #M` syntax
  gives us cross-issue dependencies without inventing one.
- **Free permissioning**: GitHub repo permissions ARE the agent's permission
  model. The Catalyst bot's GitHub App scopes define what it can touch.
- **Free human-in-the-loop**: humans interact with Issues every day. There
  is no separate UI to learn. `state/blocked-on-human` is just "needs your
  attention" in the only inbox developers actually read.

## Consequences

### Good

- Honda Construct's **Andon principle** has a literal implementation: the
  board is the andon. The `blocked-on-human` label *is* the cord.
- Honda Construct's **Standardised Work** has a literal implementation: the
  Issue body is the exec plan template; comments are the proving checks.
- The architecture aligns directly with `unattended-agent-architecture.md`
  (the Catalyst codebase's own canonical reference for state-machine-driven
  automation).
- Reduces DynamoDB write traffic substantially (now only cache writes).
- Eliminates a class of bug ("DynamoDB and the UI disagree about state")
  by making the UI and the state store the same thing.
- Trade in interview: this is a memorable architectural choice with a
  clear thesis behind it. Reviewers who haven't read the natesnewsletter
  piece will ask why; reviewers who have will recognize the pattern.

### Trade-offs

- **GitHub API rate limits**: 5,000 req/hour per installation token. We
  cache install tokens (9-min TTL) and batch where possible. At demo
  volumes this is a non-issue; at full scale we'd add per-repo throttling.
  Mitigated.
- **Eventual consistency**: GitHub label changes propagate via webhook
  asynchronously. Catalyst components must treat their local cache as
  eventually consistent and re-read from GitHub on any state-decision
  boundary. We accept this; documented in `docs/ADR/STATE-MACHINE.md` §6.
- **GitHub as a runtime dependency**: if GitHub.com is down, Catalyst's
  automation queue is down. We accept this — at the scale of a national retail pharmacy and insurance provider, GitHub
  Enterprise Server (self-hosted) is an option that preserves the
  architecture. Documented in `RUNBOOK.md` as a Sev1 dependency.
- **Cross-cutting state queries** (e.g., "all in-flight deploys for service
  X across all environments") become "list issues with these labels" calls,
  not SQL JOINs. The DDB cache mitigates latency; complex cross-cuts still
  use Aurora's deployment-lineage table for reporting.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Webhook delivery loss | API Gateway retries; idempotency table; daily reconciliation job that diffs GitHub state vs DDB cache |
| Catalyst bot account compromise | GitHub App with minimum scopes (no `repo`, only `pull_request:write`/`issues:write`); private key rotation; CloudTrail data event on `secretsmanager:GetSecretValue` |
| Label set drift from spec | Terraform-managed labels; CI fails if anyone edits labels manually outside Terraform |
| State-machine bug allows illegal transition | Client-side `assert_legal_transition` in every component; OPA/Conftest policy in CI; runtime alarm `Catalyst-IllegalTransition` |
| IDE agents write to the wrong issue host (GitHub vs Gitea) | Close the gap in [Known gaps: multi-host agent access](#known-gaps-multi-host-agent-access-github-mcp-vs-gitea): configured backend, shared verbs, MCP or adapter |

## Known gaps: multi-host agent access (GitHub MCP vs Gitea)

The **runtime** decision in this ADR is GitHub Issues + Projects (or API-
compatible enterprise hosting). **IDE agents** (Cursor and similar) still
need a **discoverable, authenticated API surface** to read and append the
same durable records humans use.

**Today in this workspace**

- **GitHub:** Agents can use the **GitHub MCP** (and/or `gh`) to list issues,
  read threads, add comments, and correlate with `STATE-MACHINE.md` labels
  when the remote is GitHub or GitHub Enterprise Server.
- **Gitea (and other forges):** There is **no Gitea MCP** wired here and **no
  automation** that maps Catalyst’s issue verbs to Gitea’s Issues API. Agents
  cannot **dynamically** resolve “the issue for this work item” or post
  structured handoff comments against Gitea without ad-hoc URLs or custom
  scripts — a **parity gap** relative to the GitHub path.

**Why it matters**

The five-property substrate (persistence, state machine, ownership, verbs,
audit history) is **host-agnostic**; the *implementation* of those verbs is
not. Until Gitea (or `$FORGE`) is reachable through the same contract, agent
sessions risk **forking the audit trail** (chat-only) or **silently targeting
the wrong remote**.

**Target Kaizen (close the gap)**

1. **Configuration:** Introduce an explicit **issue backend** identity
   (`github` | `gitea` | …), API base URL, and repo slug in workspace or
   service config so Lambdas, CLI, and IDE agents **resolve one canonical
   issue URL space** per deployment.
2. **Verb parity:** Implement the same logical operations as
   [`docs/ADR/STATE-MACHINE.md`](ADR/STATE-MACHINE.md) §4 — **create**,
   **comment**, **assign**, **label**, **close** — against each supported
   backend (GitHub REST/App, Gitea SDK or REST with PAT/scoped token).
3. **Agent surface:** Ship a **Gitea MCP server** (or a thin multi-backend
   “issues MCP” that delegates by config) so agents **call the configured
   backend** instead of assuming GitHub. Prefer MCP over one-off shell
   scripts so tool schemas stay stable across repos.
4. **Ingest path:** For Gitea-hosted repos, add **webhook** (or polling
   fallback) support that normalizes to the same internal events the
   `webhook-handler` already expects, or document a **translator** module
   until native parity exists.

Track as a **`type/kaizen`** Issue when implementation starts; until then,
document the active remote in the repo README or `AGENTS.md` so humans and
agents know which tools are authoritative.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| **DynamoDB-only state machine + custom dashboard** | Reinvents what GitHub already provides for free; loses the "developers already use this UI" benefit; loses git-observable audit; needs a separate auth/permissions stack |
| **Step Functions as the state machine** | Excellent for orchestration but not a substrate for human-in-the-loop / blocked-on-human; the step graph is invisible to the developer; no comment-thread audit |
| **Linear (per the natesnewsletter article)** | Strong choice technically; rejected for this submission because the team uses GitHub and large enterprises in this sector are often GitHub-first. The architectural pattern transfers cleanly if we ever migrate. |
| **Jira** | Same as Linear, but with the additional friction the natesnewsletter article calls out: every Jira deployment is a different maze. The team explicitly mentions GitHub Actions in the recruiter brief. |
| **Custom-built tracker with a Postgres state machine** | Maximum control, maximum cost, zero developer-UX win. NIH-syndrome answer. |

## Why this is the right call now

Three observations from the natesnewsletter piece, applied to this team's
context specifically:

1. *"The translation step is going away. The state machine, the assignee
   field, the audit history, the dependency graph, those are staying."*
   Catalyst's automations need exactly those four things.
2. *"Good UX produces cleaner data."* The team already lives in GitHub
   Issues. State that lives in GitHub Issues will be clean. State that
   lives in a custom dashboard nobody opens will rot.
3. *"The agent doesn't get to do anything the human assignee couldn't have
   done."* The GitHub App permissions model is a first-class permission
   model. The bot user's identity is auditable. The team gets a free,
   existing answer to "what can the agent do."

For the "automate the cloud-ops queue" mandate in this domain, this is the
substrate.

## Implementation pointers

- **State-machine vocabulary**: `docs/ADR/STATE-MACHINE.md`
- **Agent / Cursor execution on Issues** (Gherkin, comment handoff shape for later runs): `docs/issue-execution-gherkin-workflow-2026-05-13.md`
- **Code (state-transition validators)**:
  - `services/catalyst-api/catalyst/state_machine.py`
  - `services/ai-pr-reviewer/src/state_machine.py`
  - `services/webhook-handler/src/state_machine.py`
  - `services/ops-intel/src/state_machine.py`
  - (Duplication is intentional in Phase 1 — each service self-contained.
    A future `catalyst-common` shared package consolidates if/when the
    duplication causes drift.)
- **Terraform (label + Project management)**:
  `infrastructure/modules/composite/github-bootstrap/`
- **Webhook reactor**: `services/webhook-handler/src/router.py`
- **Runbook entry**: `RUNBOOK.md` § "GitHub dependency Sev1"
- **Multi-host gap (Gitea / non-GitHub):** see [Known gaps: multi-host agent access](#known-gaps-multi-host-agent-access-github-mcp-vs-gitea). Planned deliverables: issue-backend config; Gitea MCP (or shared issues MCP); Gitea webhook or translator aligned with `STATE-MACHINE.md` verbs.

## Update cadence

Re-review on architectural delta to the automation surface (new automation
type added, new state added). Quarterly otherwise.

Last reviewed: 2026-05-08.

---

> **Citation**: Jones, Nate B. *"AI agents are about to route around every
> tool that can't pass 5 structural tests."* `natesnewsletter`, 2026-05-02.
> [https://natesnewsletter.substack.com/p/issue-trackers-agent-infrastructure](https://natesnewsletter.substack.com/p/issue-trackers-agent-infrastructure)
