# AI-native workflow narrative

This document is the answer to *"prove this codebase was actually produced by AI agents following a disciplined contract."* The contract is `AGENTS.md`. The state machine is GitHub Issues with `state/*` labels. The audit trail is comments on those issues. The evidence is concrete: every artifact below cites the PR or comment that produced it.

## The contract

`AGENTS.md` (the operating contract) plus `CLAUDE.md` (the 4-rule guardrail) constrain every agent that touches this repo:

1. **Model decision logging** — Before implementation, post `### Agent Decision Log` on the tracking issue (model selected, fallback known, rationale, next).
2. **RLM trigger** — If an artifact exceeds ~50k characters, invoke the recursive language model workflow before reading inline.
3. **AWS OIDC** — No long-lived AWS credentials. GitHub OIDC roles only (ADR-006).
4. **Container security gate** — Trivy/Docker Scout HIGH/CRITICAL gate + SPDX 2.3 + CycloneDX 1.5 SBOMs + SARIF upload.
5. **Pre-PR peer review** — Before `gh pr create`, spawn a peer-review sub-agent. Record every suggestion with ACCEPT or REJECT + rationale on the tracking issue.
6. **GitHub MCP secret scanning** — Invoke on any PR adding files or credentials.

Every PR in this repo that touches code carries the trail of these gates being honored — or explicitly waived with rationale.

## Evidence catalogue

### PR #147 — ci-smoke parse failure (Phase D of the demo-readiness plan)

The chronic failure pattern was: `ci-smoke.yml` registered with the *file path* as its workflow name and fired on `push` events despite declaring `on: pull_request` only. The diagnosis flow:

1. **Triage agent** (Claude Code, Opus 4.7): pulled the workflow file, read the failed run metadata, noted GitHub's parse-failure signature, hypothesized `paths:` filter or bare `on:` keyword.
2. **Peer-review sub-agent** (general-purpose, AGENTS.md gate): spawned with explicit "do NOT modify files, diagnose only" prompt. Ran `actionlint` via Docker against the workflow tree. Returned HIGH confidence on the actual root cause: **`secrets.*` in step-level `if:` is disallowed by GitHub Actions and causes registration-time parse failure**.
3. **Triage agent**: applied the minimum diff (3 added lines, 0 removed — hoist secret to job `env:`, reference via `env.*`). Recorded the peer-review verdict verbatim in the PR body with a suggestion-disposition table.
4. **PR body** included: Context, Decision, Scope, Gherkin AC, Agent Decision Log, Pre-PR Peer Review, Secret Scanning gate, Alternatives Considered.

Every box on the contract was checked. The PR is a single-file, ~5-line fix.

### PR #140 — teardown ECR + IAM fix (Phase A precursor)

> "The `terraform destroy` failed on `iam:ListInstanceProfilesForRole`. The fix adds the permission to `emit_apply_iam_scoped_policy` in `scripts/bootstrap-aws-account.sh`. Re-run bootstrap after merge."

The PR body explicitly documents an operator action required *after* merge — the bootstrap script is the source of truth for the live IAM policy, and a code change doesn't refresh the policy automatically. The agent recorded the operator handoff in the PR description rather than burying it in a comment, so the next person picking up the merged PR has the runbook in their face.

This is the AGENTS.md "operator handoff" pattern: agents don't pretend to have AWS credentials when they don't. They produce a *script* the operator runs.

### PR #115 — consolidated terraform pipeline

The original design had two workflows (`tf-plan.yml` + `tf-apply.yml`) with a GitHub Environment approval gate on apply. The implementing agent discovered mid-flight that binding to an Environment mutates the OIDC JWT `sub` claim, breaking the bootstrap-managed role trust. The agent **stopped, posted a decision log, consulted the operator**, and re-scoped to a single consolidated `terraform.yml` matching the HashiCorp starter template. The approval gate is deferred and tracked.

This is the "agent stops at architectural decisions" pattern. The decision wasn't to power through — it was to surface the surprise and let a human approve the scope change.

### PR #105 — DynamoDB repo + SigV4 RBAC + SSM/Secrets config (workstream A)

A single PR landed: the DynamoDB repository layer, SigV4 verification of API requests, and runtime configuration resolution (env → SSM → Secrets Manager). The peer-review sub-agent flagged that the configuration resolver should fail-fast on missing required keys; the implementing agent accepted that, refactored, and re-ran tests. The trail is in the PR comment history.

The wider observation: **AI-produced code that's been through a peer-review gate looks like code that's been through a senior reviewer's gate.** Small functions, narrow responsibilities, no speculative abstractions, explicit error handling at boundaries (and trust at internal seams). That's not coincidence — it's the contract.

### Issue #124 → #130 — scope split mid-flight

The original CICD-11 issue conflated *unblocking* scheduled drift detection with *hardening* the OIDC role. The agent recognized this mid-implementation (peer-review surfaced it), posted a `### Scope shift discovered before implementation` comment splitting the work, and filed #130 (CICD-11a — minimum unblock) as a sibling. #130 merged the same day. #124 (CICD-11b — hardening) was deferred and ultimately closed as redundant when the minimum unblock proved sufficient for the current state.

This is the "the spec is wrong, the agent says so" pattern. Agents do not bend code to match a wrong spec. They surface the inconsistency.

## Issue tracking conventions

Every issue follows Context + Scope (In/Out) + Gherkin Acceptance Criteria. State machine labels:

- `state/pending` → created, not yet picked up
- `state/agent-working` → claimed, work in progress
- `phase/review` → PR open, awaiting review
- `state/done` → merged
- `state/blocked-on-human` → agent refused, needs human decision
- `state/rolled-back` → failed and reverted

Other taxonomies in active use: `tenant/*`, `env/*`, `lz/*`, `project/*`, `app/*`, `type/*`, `kind/*`, plus the demo-window `phase/A-*` through `phase/F-*` for time-bound execution.

## What this isn't

This is **not** "Claude wrote the code, ship it." Every PR that touched production code was reviewed by:
- A peer-review sub-agent (different process, different context window)
- A human operator (the user) who decided on merge

The peer-review sub-agent's verdict is included verbatim in PR bodies with a suggestion-disposition table — ACCEPT decisions are resolved, REJECT decisions are explained. That table is the artifact, not the diff.

## Reading order for an interview panel

If you want to walk this codebase as evidence:

1. **`AGENTS.md`** — the contract itself
2. **`CLAUDE.md`** — the 4-rule guardrail at repo root
3. **`docs/ADR/ADR-001-github-issues-as-state-machine.md`** — why issues, not Jira
4. **`docs/ADR/STATE-MACHINE.md`** — the label vocabulary
5. **Issue #136** — a real closed kaizen showing Context → Gherkin → Done
6. **PR #147** — the demo PR with the full AGENTS.md trail in its body
7. **PR #140** — the operator-handoff pattern
8. **Issue #124 → #130** — the scope-split pattern

That sequence demonstrates: the contract exists, the state machine is real, an agent followed both end-to-end, and stopped at human decisions.

## What worked (legacy notes from earlier stub)

- Issue-driven execution with Context/Scope/Gherkin acceptance criteria produced reviewable outputs.
- ADR alignment (006-010) provided clear constraints for runtime, RBAC, and egress design.
- Continuous verification gates (`terraform validate`, `pytest --cov-fail-under=85`) reduced integration drift.

## Where AI was course-corrected

- Shifted RBAC enforcement to application-layer checks to match ALB front-door architecture.
- Added explicit runtime branching (`RUNTIME=lambda|ecs`) in deployment workflow.
- Added resource visibility filtering for tenant/project-scoped support groups.

## How to improve

- Add automated issue comment checks to enforce decision-log section headings.
- Add snapshot tests for workflow YAML and issue templates.
- Add synthetic load tests to compare Lambda vs ECS runtime behavior before switching defaults.
