# Unattended Agent Architecture — Implementation Proposal for Catalyst

**Author**: Cursor agent (analysis + proposal; no edits to implementation files)
**Date**: 2026-05-14
**Source doc**: `\\100.115.245.62\media\Workspace\books-rlm\books-rlm\source-documents\unattended-agent-architecture.md` (313 lines)
**Catalyst base read**: ADR-001 through ADR-004, STATE-MACHINE.md, AGENTS.md, challenge-brief.md, docs/research/platform-catalyst-agents-evaluation.md

---

## 1. Summary of the source document

### The pattern in one sentence

*Unattended agent architecture* is a three-layer operating model that removes the human from every place the naive "YOLO-mode" agent setup forces them in — keeping a coding agent running for days at a time, producing 173 merged PRs across 53 hours with most of the work happening without a human at the keyboard.

### The core principle (lines 35–36)

> **Coherence lives on disk, not in the agent's memory.** The repo, the exec plans, the marker files, the pull requests — that's the persistent layer. The agent is the executor.

This single principle — called the **Ralph technique** (attributed to Geoffrey Huntley, lines 170–175) — is the load-bearing idea. Every other component is a consequence of it.

### Three layers, seven components

#### Layer 1 — OS: keep the process alive (lines 48–80)

| Component | What it does |
|---|---|
| **systemd** (Component 1) | Supervisor: start/stop/restart/timer; `journalctl -u <unit>` is the session log. Process survives SSH disconnect. |
| **Linux VM** (Component 2) | Barebones Ubuntu; works *with* the OS, not against it. Windows/macOS require fighting the supervisor model. |
| **worker.sh** (Component 3) | Shell script: git pull → verify clean tree → check marker files → read exec plan → invoke agent CLI → exit. State from disk every session; no context window carryover. |

The OS layer's purpose is to answer: *"Who keeps the loop alive when I step away?"* Answer: Linux and systemd.

#### Layer 2 — Harness: constrain what the agent can do (lines 83–136)

| Component | What it does |
|---|---|
| **Red/green/refactor TDD loop + exec plan** (Component 4) | One thin slice per session. The exec plan (7 fields: milestone, next slice, proving test, lint command, expected red, files in scope, validation evidence) bounds the agent to one testable unit of work. |
| **Harness lock** (Component 5) | **The load-bearing constraint** (line 109). CI rejects any diff touching test runners, lint configs, or CI workflow files unless the PR author satisfies a CODEOWNERS rule. The agent cannot soften its own constraints when problems get hard. |
| **Branch protection + auto-merge** (Component 6) | CI must pass before merge; auto-merge enabled for agent PRs. Wrong and caught in 15 seconds, not three hours later. Makes being wrong cheap. |
| **Isolated VM + secrets vault** (Component 7) | Agent runs on isolated staging VM, not the dev laptop. Secrets via Doppler (or 1Password/Vault) with rotation cadence. Agents will print env vars if they can — never rely on `.env` + `.gitignore`. |

The Harness layer answers: *"What stops the agent from doing something it shouldn't?"* Answer: gates enforced by CI, not by the agent's own judgment.

#### Layer 3 — Persistence: hold the state (lines 139–165)

| Primitive | What it does |
|---|---|
| **Marker files** (`stop`, `blocked`, `done`) | Control plane for the worker loop. Timer fires constantly; markers decide whether anything actually happens. Agent writes `blocked` on detectable upstream failure; human deletes it after fixing. |
| **Git repo as memory** | State lives in branches, exec plan files, marker files, and pull requests. **No information lives only in the prior session's context window.** |
| **Pull requests as unit of progress** | Each thin slice = one PR. |

### Execution model

systemd timer fires → `worker.sh` runs → checks `stop` / `blocked` / `done` → reads `EXEC_PLAN.md` → invokes agent CLI → agent produces one thin slice → commits, opens PR → CI runs → if green, auto-merge fires → `worker.sh` exits → timer fires again.

### Trust model and safety mechanisms

The architecture is *not* based on trusting the agent's judgment. Every safety property is enforced externally:

- **Harness lock** (CODEOWNERS / CI path check): agent cannot weaken its own tests.
- **Branch protection**: agent cannot merge broken code.
- **Marker files**: agent cannot spiral on a blocked dependency — it writes `blocked` and stops.
- **Isolated VM**: agent cannot touch the developer's laptop or production.
- **Secrets rotation cadence**: agent cannot leverage long-lived credentials.

### Observability hooks

- `journalctl -u worker.service` — full session history since boot.
- `blocked` marker file — surface-level signal: something needs a human.
- Pull request list — progress log; each merged PR is a shipped slice.
- `EXEC_PLAN.md` — current position in the milestone plan.

### When this pattern fits (lines 264–279)

**Fits**: work decomposes into thin mergeable slices; proving test is mechanical; codebase has CI; blast radius of any single PR is bounded; staging environment exists.

**Misfits**: fundamentally ambiguous work needing design judgment per slice; codebase with no tests; production access required for every slice; team doesn't trust auto-merge.

---

## 2. Catalyst alignment map

ADR-001 (line 125–126 of that doc) explicitly states: *"The architecture aligns directly with `unattended-agent-architecture.md` (the Catalyst codebase's own canonical reference for state-machine-driven automation)."* That is the strongest possible alignment signal — the Catalyst architecture was deliberately designed around this pattern. The question is what has been built and what is still a gap.

### Component-by-component mapping

#### Layer 1 — OS: keep the process alive

| UAA Component | Catalyst equivalent (existing) | Gap | Effort |
|---|---|---|---|
| **systemd supervisor** | GitHub Actions scheduled workflows + EventBridge triggers. GitHub's webhook delivery model is the "timer that fires." | **Missing: continuous polling worker.** Catalyst uses event-driven (webhook on label change) not timer-driven (fire every N minutes regardless). No equivalent of `worker.sh` that proactively polls for `state/pending` issues and starts an agent session. If webhook delivery fails, work silently stalls until the daily reconciliation job (ADR-001 §consequences). | **Medium** |
| **Linux VM** | Lambda + ECS Fargate for runtime services. No dedicated agent-runner VM. | No isolated Linux VM for the agent coding session specifically. Cursor IDE sessions run on the Windows dev machine. Agent code-writing happens in Cursor, not on an isolated VM. | **Large** (for full isolation; **Small** for demo) |
| **worker.sh** | `services/webhook-handler/src/router.py` is the closest equivalent — it reacts to issue label events and dispatches work to SQS → Lambda. | Missing the *proactive* loop: `worker.sh` polls and acts; Catalyst's webhook handler only reacts. For coding-agent sessions (Cursor doing implementation work), there is no `worker.sh` equivalent that periodically launches the agent. | **Small** (to add a scheduled GHA workflow that polls `state/pending`) |

**Layer 1 summary**: The persistence substrate (GitHub Issues) substitutes for the need for systemd's "memory." But the *keep-alive / restart loop* — the timer that fires regardless of whether a human is at the keyboard — is not yet implemented in Catalyst for coding-agent sessions. For Lambda-based runtime automations, Lambda re-invocation + SQS redrive serves the same role.

#### Layer 2 — Harness: constrain what the agent can do

| UAA Component | Catalyst equivalent (existing) | Gap | Effort |
|---|---|---|---|
| **TDD exec plan** (7-field doc) | **Strong existing equivalent**: Issue body with `## Context`, `## Scope`, `## Acceptance Criteria` (Gherkin). The Gherkin `Feature`/`Scenario` IS the "proving test + expected red." ADR-001 §4.1 mandates this schema. The stable comment headings (`### Decision`, `### Actions taken`, `### Verification`, `### Next`) from `docs/issue-execution-gherkin-workflow-2026-05-13.md` cover milestone + next-slice + validation evidence. | **Missing**: no literal `EXEC_PLAN.md` file with UAA's 7 fields. The "lint command" and "files in scope" fields are not currently required in the Issue body. | **Small** — add an `EXEC_PLAN.md` template and optionally add those fields to the Issue body schema. |
| **Harness lock** | OPA/Conftest policy in CI (`policy/opa/state_machine.rego` per ADR-001 §risk). Terraform manages the GitHub label set. `state_machine.py` validated per-service. | **Critical gap**: no CODEOWNERS rule or CI path-based check that *rejects agent diffs to harness files themselves* (`.github/workflows/`, `tests/`, `infrastructure/modules/composite/github-bootstrap/`). An agent could add `--no-fail-under` to pytest, comment out Gherkin scenarios, or modify CI gates. | **Small** — one `CODEOWNERS` file + one CI workflow path-guard. High-value safety property. |
| **Branch protection + auto-merge** | Not explicitly confirmed as configured on the repo. ADR-001 implies it ("CI must pass before merge") but no Terraform resource for branch protection or auto-merge settings is cited. | **Missing**: branch protection rules and auto-merge config should be Terraform-managed (already using `github` provider for labels). | **Small** — 10–20 lines of Terraform in `github-bootstrap/`. |
| **Isolated environment** | Lambda + ECS Fargate provide isolated runtime. DynamoDB dedup + Bedrock token budget (ADR-004 / Heijunka) cap blast radius. | **Partial**: coding-agent sessions in Cursor run on the dev machine (Windows). The *staging environment* (Vercel preview / ECS preview stacks per ADR-003 `type/preview-env`) is the UAA "staging environment" equivalent. | **Small** for demo; **Large** for a dedicated Linux agent VM. |
| **Secrets vault** | SSM Parameter Store + Secrets Manager (challenge brief §2 requirement). AWS OIDC (no static keys) per ADR-005 draft. | **Partial**: no Doppler-style rotation cadence documented. Challenge brief requires Secrets Manager. ADR-001 §risks mentions private key rotation for the Catalyst GitHub App. | **Small** — document the rotation policy; the vault infrastructure is already required. |

**Layer 2 summary**: The TDD exec plan is 80% implemented (Issue body). The critical missing piece is the **harness lock** — the one component that stops an agent from weakening its own CI gates. Branch protection + auto-merge is likely 1–2 Terraform resources away.

#### Layer 3 — Persistence: hold the state

| UAA Component | Catalyst equivalent (existing) | Gap | Effort |
|---|---|---|---|
| **Marker files** (`stop`, `blocked`, `done`) | **Fully implemented** via GitHub Issues state labels: `state/pending`, `state/agent-working`, `state/blocked-on-human`, `state/done`, `state/rolled-back`, `state/cancelled`. STATE-MACHINE.md is the formal spec. The `state/blocked-on-human` label IS the `blocked` marker; `state/done` IS the `done` marker; no `stop` equivalent (cancelled covers it). | **Minor gap**: UAA's `stop` (manual halt before the next session starts) maps to `state/cancelled` in Catalyst, but the semantics differ slightly — `stop` prevents new starts without terminating in-flight work. A `halt/*` modifier label would be a clean addition. | **Small** |
| **State in the git repo** | **Fully implemented**: Issue bodies (exec plan), labels (state), comments (audit trail), project board (Catalyst Andon — ADR-001 §10), pull requests (progress). The Ralph technique is the explicit design basis of ADR-001. DynamoDB holds only cache; GitHub is the durable record. | None material. RLM state (`state.pkl`) is ephemeral per ADR-004 — correctly aligned with UAA's principle that no information lives only in the prior session's memory. | **None** |
| **PRs as unit of progress** | Referenced in ADR-001 §8 (done-gate requires `pr_merged=true` when `pr_required=true`). `pr_url` logged in completion comment. | **Partial**: "one thin slice = one PR" as a *discipline* is not yet explicitly documented in AGENTS.md or the issue execution workflow. It's the consequence of the architecture but not a named rule. | **Small** — one bullet in AGENTS.md. |

**Layer 3 summary**: This is Catalyst's strongest layer. The GitHub Issues state machine (ADR-001) is a direct, architecturally intentional implementation of UAA's persistence layer. The marker files are labels. The worker state is the issue label + board column. The exec plan is the issue body + handoff comment. This layer is essentially done.

### Gap summary table

| UAA Component | Catalyst status | Effort to close |
|---|---|---|
| systemd timer (keep-alive loop) | Missing for coding-agent sessions | Medium |
| Linux VM (isolation) | Missing (dev machine is Windows) | Large (skip for demo; use GHA runner) |
| worker.sh (proactive poller) | Missing; only reactive webhook handler | Small |
| Exec plan (7-field doc) | 80% present (Issue body + Gherkin) | Small |
| **Harness lock** | **Critical gap** | **Small** |
| Branch protection + auto-merge | Missing explicit Terraform config | Small |
| Secrets vault + rotation | Partially present (SSM/SM required) | Small |
| Marker files | Fully implemented as state labels | None |
| Git-as-memory | Fully implemented (Ralph technique) | None |
| PRs as unit of progress | Implicit; not a named discipline | Small |

---

## 3. Rubric fit

### Which rubric areas does implementing UAA advance?

| Rubric area | Weight | UAA contribution | Classification |
|---|---|---|---|
| **AI-native development workflow** | 20% | UAA *is* the architecture for AI-native development at scale. EXEC_PLAN.md template, harness lock, and the keep-alive loop directly demonstrate "AI as collaborator, not just mentioned" (brief §1). The pattern produces an artifact-rich trail: marker files, exec plans, PRs, audit comments. | **Core rubric** |
| **Automation service** | 30% | The webhook handler + Lambda dispatch chain IS Catalyst's `worker.sh` equivalent. Documenting the connection — and adding the proactive polling worker — demonstrates that the automation service is designed for autonomous operation, not just one-shot triggers. | **Core rubric** |
| **CI/CD and operational maturity** | 15% | Harness lock (CODEOWNERS + CI path-guard) + branch protection + auto-merge + `blocked` marker → `state/blocked-on-human` transition are textbook CI/CD maturity signals. The `journalctl`-equivalent is GitHub Issue comments + CloudWatch logs from Lambda sessions. | **Core rubric** |
| **Communication and documentation** | 10% | The exec plan template, the marker-file convention, and ADR-006 (if written) are documentation deliverables that tell a clear design story in the review session. | **Core rubric** |
| **Infrastructure design and Terraform quality** | 25% | Indirect: branch protection + auto-merge rules as Terraform adds a small number of resources that demonstrate Terraform-managed GitHub configuration. | **Supporting** |

**Rubric verdict**: UAA implementation touches **four of five rubric areas** directly. Three of those four are at the "core rubric" level. This is not a "digging deeper / optional" exercise — it is the operational model for the entire AI-native workflow area (20%) and directly supports the Automation Service area (30%). Together those two areas are **50% of the total score**.

### Which milestones does it map to?

Using the challenge brief milestone structure (Milestones #1–#5 = rubric areas, #6–#11 = Digging Deeper options):

| Milestone | Mapping |
|---|---|
| **Milestone #3 — AI-native development workflow** | Primary home for EXEC_PLAN.md template, harness lock documentation, keep-alive worker design. |
| **Milestone #4 — CI/CD and operational maturity** | Branch protection + auto-merge Terraform, CODEOWNERS harness lock CI gate, blocked-marker → notification pattern. |
| **Milestone #1 — Automation Service** | The webhook handler / Lambda dispatch already implements the worker loop; documenting that connection explicitly maps to UAA. |
| **Milestone #6 — Digging Deeper Option 1** (more complex Terraform) | Branch protection + auto-merge config via `github` Terraform provider is a small but genuine Terraform addition. |

### Core rubric or optional?

**Core rubric**. The AI-native development workflow area (20%) explicitly requires: agent configuration in the repo, at least one open PR showing AI-assisted process, and an interview-ready answer about what worked. UAA provides the *architecture* behind all three of those deliverables. Without it, the workflow is undocumented and the interview answer is thin.

---

## 4. Implementation options (3 tiers)

### Tier 1 — Minimal (low effort, high rubric value)

**Objective**: Demonstrate the unattended agent pattern concretely enough to score the AI-native workflow area and support the CI/CD maturity narrative, without building new infrastructure.

**Concrete deliverables** (all in one branch, e.g., `rc/unattended-agent-pattern`):

1. **`docs/exec-plan-template.md`** — The UAA 7-field EXEC_PLAN.md template adapted for Catalyst:
   - `milestone:` — links to GitHub milestone
   - `next_slice:` — one-line description of this session's work
   - `proving_test:` — the Gherkin scenario that must go green
   - `lint_command:` — exact shell command to run
   - `expected_red:` — what the failing test output looks like before implementation
   - `files_in_scope:` — explicit list; agent must not touch files outside this list
   - `validation_evidence:` — what the agent posts to the issue as proof
   Note: for Catalyst, the exec plan lives *inside the GitHub Issue body* (per ADR-001), not as a separate file. The template is a reference doc that agents and humans use when structuring Issue bodies.

2. **`.github/CODEOWNERS`** — Harness lock:
   ```
   # Harness files — only human maintainers may modify
   .github/workflows/                @Cloud-Byte-Consulting/maintainers
   infrastructure/modules/composite/github-bootstrap/  @Cloud-Byte-Consulting/maintainers
   services/*/tests/                 @Cloud-Byte-Consulting/maintainers
   policy/                           @Cloud-Byte-Consulting/maintainers
   ```
   This is the single highest-value safety primitive from UAA (Component 5, line 109: *"load-bearing constraint"*).

3. **GitHub Actions workflow — `scheduled-agent-poller.yml`** — a `worker.sh` equivalent as a GHA scheduled workflow:
   - Fires every 15 minutes (cron schedule, UAA lines 241–243 recommends 5–15 minutes).
   - Queries GitHub Issues API for issues with `state/pending` label.
   - For each pending issue: posts a notification comment and optionally triggers a Catalyst dispatch via `workflow_dispatch` to the deploy/review/ops-intel Lambda.
   - Checks for `state/blocked-on-human` issues older than 2 hours → posts a reminder.
   - This is the "systemd timer" equivalent for Catalyst (UAA Layer 1, Component 1).

4. **AGENTS.md addition** — document the "one thin slice = one PR" discipline, the exec-plan template reference, and the marker-file mapping:
   ```
   ## Unattended agent discipline
   - Each agent session completes ONE thin slice: the smallest deliverable that turns the Gherkin scenario green.
   - The slice produces ONE PR. PR = proving artifact.
   - Marker files = state labels: `state/blocked-on-human` is `blocked`; `state/done` is `done`.
   - Agent MUST NOT modify harness files (`.github/workflows/`, `tests/`, `policy/`) — CODEOWNERS enforces this.
   ```

5. **`docs/ADR/ADR-006-unattended-agent-pattern.md`** — ADR documenting the adoption of UAA in Catalyst, mapping the three layers to Catalyst primitives, and recording the harness-lock and exec-plan decisions.

**Effort estimate**: 2–3 focused agent sessions. Branch: `rc/unattended-agent-pattern`.
**Rubric impact**: AI-native (20%) — strong direct evidence; CI/CD (15%) — harness lock is a named safety control.

---

### Tier 2 — Full in-repo implementation

**Objective**: UAA as a fully-specified Catalyst sub-system. Every layer is implemented, documented, and Terraform-managed. The agent can run autonomously on all automation types.

**Components beyond Tier 1**:

1. **Branch protection + auto-merge — Terraform** (`infrastructure/modules/composite/github-bootstrap/`):
   ```hcl
   resource "github_branch_protection" "release" {
     repository_id = github_repository.catalyst.node_id
     pattern       = "release"
     required_status_checks { strict = true; contexts = ["ci/test", "ci/lint", "ci/policy"] }
     required_pull_request_reviews { required_approving_review_count = 0 }  # CI is the gate, not reviewers
     enforce_admins = false
   }

   resource "github_repository" "catalyst" {
     # ...
     auto_init                   = false
     allow_auto_merge            = true  # enables auto-merge for agent PRs
     delete_branch_on_merge      = true
   }
   ```
   This completes UAA Component 6 (lines 116–122).

2. **CI path-guard workflow** (complement to CODEOWNERS) — a separate CI check that `git diff --name-only origin/release...HEAD` produces no paths matching `^\.github/workflows/` or `^policy/` or `^services/.*/tests/` unless the PR has a `harness-change-approved` label set by a human. Belt-and-suspenders with CODEOWNERS. Implements UAA Component 5 (line 113: *"CI rejects diffs to harness files"*).

3. **Issue-body exec-plan schema enforcement** — add a GitHub Actions check that validates new issues matching `type/*` labels have:
   - `## Acceptance Criteria` with a fenced `gherkin` block (already required per ADR-001 §4.1)
   - `files_in_scope:` field in `## Scope` (new requirement — makes the exec plan complete per UAA 7-field spec)
   This makes the issue body a machine-readable exec plan.

4. **`blocked` marker → notification pipeline**:
   - Webhook handler already tracks `state/blocked-on-human` transitions (ADR-001).
   - Add: when an issue transitions to `state/blocked-on-human`, post to an SNS topic → email/Slack notification.
   - This is the Catalyst equivalent of UAA's "laptop pings" (line 181) after hitting a `blocked` state.
   - Implement as a Lambda extension of the existing webhook-handler service.

5. **`state/done` gate automation**:
   - The done-gate (ADR-001 §8, STATE-MACHINE.md §8) already requires `tests_passed`, `docs_updated`, `pr_merged`.
   - Add an automated check: a Lambda triggered by `issues.labeled` with `state/done` that verifies the PR in `pr_url` is actually merged before accepting the transition. Reject and comment if not.
   - Implements UAA's "CI gates" (Component 6) at the issue lifecycle level.

6. **New ADRs needed**:
   - **ADR-006** (Tier 1 deliverable, promoted to full spec): Unattended agent pattern adoption.
   - **ADR-007** (optional): Secrets rotation cadence and vault policy for agent credentials.

7. **Issues to open** (type/kaizen, using default construct-address labels per STATE-MACHINE.md §2.2.1):
   - "Implement CODEOWNERS harness lock and CI path-guard"
   - "Add Terraform branch protection + auto-merge config for release branch"
   - "Implement blocked-marker SNS notification pipeline in webhook-handler"
   - "Add done-gate PR verification Lambda"
   - "Write ADR-006: Unattended agent pattern in Catalyst"

**Effort estimate**: 4–6 agent sessions across 2 branches. Builds on Tier 1; can be phased.
**Rubric impact**: Tier 1 impact + Automation Service (30%) — demonstrates autonomous operation of the core service; Infrastructure & Terraform (25%) — branch protection as Terraform.

---

### Tier 3 — Production-grade (optional / digging deeper)

**Objective**: Run Catalyst's agent sessions unattended at scale with full observability and blast-radius controls. Mostly beyond the challenge scope but maps to Digging Deeper Option 4 (operational intelligence) and Option 1 (complex Terraform).

> Flag: this tier is **out of challenge scope** for the core submission. Implement elements selectively as "Digging Deeper" signals.

**Additional AWS infrastructure**:

1. **EventBridge Scheduler as the systemd timer** — replace the GHA cron with an EventBridge Scheduler rule that fires a Lambda every 5 minutes to poll `state/pending` issues and dispatch agent sessions. More reliable than GHA scheduled workflows (which GitHub throttles under load).

2. **Dedicated ECS task as the agent runner** — instead of spawning Lambda per issue, run a long-lived ECS Fargate task per agent session. The task mounts the repo, runs the agent CLI (Claude Code or Cursor), commits, pushes, opens PRs, then exits. The ECS task = `worker.sh` + `systemd` in one. Task definition is Terraform-managed; scaling is ECS auto-scaling policy.

3. **Doppler / AWS Secrets Manager rotation** — agent credentials (GitHub App private key, Bedrock API key) rotate on a 30-day cadence with an EventBridge Scheduler trigger. The rotation event posts an SNS notification so the agent session does NOT retry with the expired credential — it writes `state/blocked-on-human` and stops. This is the exact worked example in UAA (lines 181–208).

4. **CloudWatch alarms on agent behaviour**:
   - `Catalyst-BlockedDuration` — alarm when an issue stays in `state/blocked-on-human` > 4 hours.
   - `Catalyst-SessionDuration` — alarm when a single agent session runs > 30 minutes (infinite loop / cost runaway).
   - `Catalyst-HarnessEditAttempt` — alarm on CI path-guard check failures (agent tried to edit harness).
   - All three alarms → SNS → email/PagerDuty. This is the `journalctl` equivalent at the infrastructure level.

5. **Bedrock token budget enforcement at the session level** — extend the existing per-repo daily Bedrock token budget (DynamoDB conditional updates, ADR-004 / Heijunka) to a per-issue-session cap. If a single session exceeds N tokens, the agent writes `state/blocked-on-human` with a `budget-exhausted` modifier label (already defined in STATE-MACHINE.md §2.6) and stops.

6. **VPC isolation for the agent runner** — ECS task runs in a private subnet with no internet egress except via NAT (to GitHub API, Bedrock, Secrets Manager). Prevents the agent from reaching arbitrary internet endpoints. The isolated VM requirement from UAA Component 7 (line 127) maps to this.

**Terraform additions**: ECS task definition, EventBridge Scheduler rule, CloudWatch alarms with SNS, Secrets Manager rotation Lambda, VPC/NAT for agent runner subnet. Estimated 8–12 new Terraform modules, all candidates for Digging Deeper Option 1.

**Effort estimate**: 10–15 agent sessions; significant AWS infra cost at demo scale (negligible — ECS Fargate on-demand, EventBridge free tier, Secrets Manager pennies). Production scale is a different story.

---

## 5. Gaps and risks

### Top risks

| Risk | Severity | Detail | Mitigation |
|---|---|---|---|
| **No harness lock = agent can weaken CI** | Critical | Without CODEOWNERS + CI path-guard, an agent that hits a failing test can comment out the assertion, add `--no-fail-under`, or delete the workflow step. This is the classic failure mode UAA Component 5 (line 111) was designed to prevent. | Implement CODEOWNERS and the CI path-guard in Tier 1. First deliverable, before anything else. |
| **GHA scheduled workflows are unreliable as the keep-alive loop** | High | GitHub throttles scheduled workflows during high-load periods; they can slip 30–60 minutes. For a challenge demo, this is fine. For production, EventBridge Scheduler (Tier 3) is more reliable. | Document the limitation explicitly in ADR-006. Use EventBridge for Tier 3. |
| **Auto-merge trust requires test quality** | High | If the test suite has low coverage, green CI does not mean the PR is safe to merge autonomously. The harness lock loses meaning if the harness tests nothing. | Track coverage with `--cov-fail-under=85` gate (already referenced in AGENTS.md for Python CLIs). Block auto-merge if coverage drops below threshold. |
| **Secrets in Cursor sessions on Windows dev machine** | Medium | The UAA isolated VM requirement (Component 7, lines 126–135) is partially violated when agents run in Cursor on the Windows dev machine. GitHub tokens, AWS OIDC credentials, and Bedrock keys are in scope for exposure. | Use `gh auth login` + AWS SSO (`aws sso login`) — credentials in the keyring, not in the agent's environment. Document in AGENTS.md. |
| **Context window / session boundary** | Medium | UAA's worker exits after each slice, forcing fresh state read. Cursor agent sessions can run long, accumulating context drift. Long-running sessions risk "context rot" where early decisions are forgotten. | Enforce the one-slice discipline in AGENTS.md. Encourage short sessions that terminate after one Gherkin scenario turns green. |
| **Webhook delivery loss breaks the reactive loop** | Medium | ADR-001 acknowledges this risk and mitigates with a daily reconciliation job. But between reconciliation runs, a missed webhook means a slice sits stuck in `state/pending` with no agent picking it up. | The GHA scheduled poller (Tier 1 deliverable #3) directly addresses this by proactively scanning for stuck issues. |

### Cross-reference with open questions from `docs/research/platform-catalyst-agents-evaluation.md`

The agents evaluation (§7 Open questions remaining) surfaces several questions that UAA implementation directly informs:

- **Q4 — Agent import phasing and ECS vs Lambda for `automation-architect`**: The UAA Layer 1 decision (ECS Fargate task as the agent runner vs. Lambda for short invocations) is exactly the decision Q4 raises. Recommendation: Lambda for the poller and dispatcher (stateless, event-driven); ECS Fargate for the agent *execution* session (longer-running, needs a shell). This matches UAA Component 3 (`worker.sh` is a shell process) and UAA Component 7 (isolated environment with real services).

- **Q5 — Bedrock model binding**: The agent sessions that implement slices will consume Bedrock tokens. ADR-006 (Unattended Agent Pattern) should cite the model selection policy, or a companion ADR-007 should nail it down before the agent sessions run autonomously. Without a model pin, the daily token budget (DDB conditional update) cannot be set accurately.

- **Q6 — ADR numbering drift**: Now resolved — canonical numbers are ADR-001 through ADR-004, with ADR-005 in the `rc/aws-agentic-platform-engineering` branch. ADR-006 is the next open slot for the unattended agent pattern ADR.

- **The harness lock** (Section 5 risk #1 above) is not raised as an open question in the agents evaluation — it should be. The evaluation recommends importing `cicd-operator` and `checkov-expert` agents, both of which assume a robust harness gate exists. Until CODEOWNERS is in place, importing those agents without the lock gives the agents a false sense of safety.

### Decisions that must be made before implementation

1. **Which branch hosts this work?** — Recommendation: `rc/unattended-agent-pattern`, cut from `release` after PR #20 (`rc/aws-agentic-platform-engineering`) merges (per the agents evaluation's branch coordination decision §1).

2. **Does auto-merge apply to the `release` branch or only feature branches?** — UAA enables auto-merge for agent PRs (Component 6). In Catalyst, `release` is the integration branch and `main`/`prod` (or equivalent) is the protected trunk. Confirm whether agent PRs targeting `release` should auto-merge (yes, with CI gate) or whether human review is required.

3. **What is the CODEOWNERS team?** — `@Cloud-Byte-Consulting/maintainers` is a placeholder. In a solo challenge submission, this is just the author's GitHub handle. For the submission, it demonstrates the pattern even if there's only one team member.

4. **Harness lock scope** — which directories are "harness files"? Minimum recommended: `.github/workflows/`, `policy/`, `services/*/tests/`, `infrastructure/modules/composite/github-bootstrap/`. The exec plan template itself (`docs/exec-plan-template.md`) should also be locked — agents shouldn't be able to relax the template.

---

## 6. Recommended next action

### Tier to target: **Tier 1 (Minimal)**, with Tier 2's branch protection Terraform folded in.

Tier 1 delivers the maximum rubric-per-effort ratio. The five deliverables (exec-plan template, CODEOWNERS, scheduled poller workflow, AGENTS.md update, ADR-006) are all documentation and configuration — no new AWS infrastructure required, no new Lambda code. Together they demonstrate:

- A named, architecturally grounded AI-native workflow (20% rubric) ✓
- A harness lock safety control (CI/CD maturity, 15% rubric) ✓
- Proactive agent keep-alive (Automation Service operational story, 30% rubric) ✓
- An ADR with clear design rationale (Communication, 10% rubric) ✓

The Terraform branch protection addition (Tier 2, item 1) is 10–20 HCL lines and should be folded into Tier 1 because it directly supports the auto-merge gate story.

### Branch

`rc/unattended-agent-pattern` — cut from `release` *after* PR #20 lands (per agents evaluation §1 branch coordination decision).

### Issues to open (type/kaizen, state/pending)

Open these in order, each with Gherkin acceptance criteria per ADR-001:

1. **"Implement CODEOWNERS harness lock + CI path-guard"** — Milestone #4 (CI/CD), priority: HIGH (safety-first).
2. **"Write ADR-006: Unattended Agent Pattern in Catalyst"** — Milestone #3 (AI-native), references this proposal doc.
3. **"Add exec-plan template and update Issue body schema to include files_in_scope"** — Milestone #3 (AI-native).
4. **"Add Terraform branch protection + auto-merge for release branch"** — Milestone #6 (Digging Deeper Option 1).
5. **"Add GHA scheduled poller workflow for state/pending issues"** — Milestone #1 (Automation Service).

All five carry construct-address labels `tenant/catalyst`, `env/shared`, `lz/shared`, `project/platform`, `app/kaizen` per STATE-MACHINE.md §2.2.1.

### ADR to write first

**ADR-006 — Unattended Agent Pattern in Catalyst**

Structure:
- **Context**: cite UAA source doc (lines 35–36, 170–175) and ADR-001 line 125–126 ("aligns directly with...").
- **Decision**: Catalyst adopts UAA's three-layer model. Layer 3 (persistence) is complete via ADR-001. Layer 2 (harness) adds CODEOWNERS + branch protection. Layer 1 (OS) is approximated by GHA scheduled workflow; Tier 3 escalates to EventBridge + ECS.
- **Consequences**: Harness lock is a net-new safety control. Auto-merge changes the merge workflow. The exec plan template is a new required field in Issue bodies.
- **Alternatives**: Naive YOLO-mode agent (rejected — human back in loop); AWS Step Functions as the orchestrator (rejected — no human-in-the-loop substrate; already rejected for ADR-001); daily batch instead of 15-min timer (rejected — too coarse for real-time operational response).

### Single most important next action

**Implement `.github/CODEOWNERS`** (the harness lock) in the next agent session on `rc/unattended-agent-pattern`. This is the one component that makes everything else trustworthy. Without it, every other layer of the unattended architecture is a suggestion rather than an enforcement. It is 5–10 lines of configuration, takes one session, and unblocks the auto-merge gate story.

---

## Appendix A — UAA source doc section references

| Section | Lines | Key quote |
|---|---|---|
| Core principle (Ralph technique) | 35–36 | "Coherence lives on disk, not in the agent's memory." |
| Layer 1 — systemd | 50–62 | "The process **survives your SSH disconnect**. That's the whole point." |
| Layer 2 — harness lock | 109–113 | "This is the load-bearing constraint… The harness is locked." |
| Layer 2 — gates | 118–122 | "Wrong and caught at CI in 15 seconds… the cost of being wrong is bounded by the gate." |
| Layer 3 — marker files | 144–151 | "The systemd timer can fire as often as it wants. **The markers decide whether anything actually happens.**" |
| Worked example (blocked recovery) | 181–208 | 5-minute recovery after expired token; no quota burn, no drift, no data loss. |
| Composition with other patterns | 285–290 | Explicitly cites RLM / recursive-LM pattern and work-graph control plane (= Catalyst's GitHub Issues). |
| Fit conditions | 264–279 | Misfits: ambiguous work, no tests, production access required for every slice. |

---

## Appendix B — Catalyst ADR cross-reference

| Catalyst ADR | UAA component it implements | Status |
|---|---|---|
| **ADR-001** — GitHub Issues state machine | Layer 3 (persistence) — marker files, git-as-memory, PRs as progress units | Complete |
| **ADR-002** — Construct hierarchy | Context for exec plan routing (`<tenant>/<env>/<lz>/<project>/<app>` in every issue) | Complete |
| **ADR-003** — Static + ephemeral environments | Staging environment for agent work (`dev` / `stage`; never auto-promote to `prod`) | Complete |
| **ADR-004** — RLM for long-context tasks | Exec plan reading for large diffs / plans; maps to UAA "exec plan read at startup" | Complete |
| **ADR-005** (planned) — AWS agentic platform | Secrets (SSM/SM, OIDC) — partial Layer 2 (isolated env + secrets vault) | In-flight (PR #20) |
| **ADR-006** (proposed) — Unattended agent pattern | The synthesis ADR that maps all three layers to Catalyst primitives | **To be written** |

---

*This is a read-only analysis and proposal document. No git commits, PRs, or GitHub issue mutations were performed. The single file written is this proposal at `docs/research/unattended-agent-architecture-proposal.md`.*
