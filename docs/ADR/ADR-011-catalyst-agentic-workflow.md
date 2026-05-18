# ADR-011 — Adopt a multi-gate agentic workflow contract for Catalyst delivery

**Status**: Accepted · 2026-05-18
**Related**: [ADR-001](ADR-001-github-issues-as-state-machine.md), [ADR-004](ADR-004-rlm-for-long-context-agent-tasks.md), [ADR-005](ADR-005-aws-agentic-platform-engineering.md), [ADR-006](ADR-006-cicd-pipeline-architecture.md), [STATE-MACHINE.md](STATE-MACHINE.md), [`AGENTS.md`](../../AGENTS.md), [`docs/ai-workflow-narrative.md`](../ai-workflow-narrative.md), [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](../issue-execution-gherkin-workflow-2026-05-13.md)

## Context

Catalyst is an AWS-native Internal Developer Platform delivered entirely by
AI agents (Claude Code, Cursor) working against GitHub Issues. The bar we
set for this delivery model from the outset:

- **Audit-grade trail** — Any merged PR must be reconstructable from
  comments alone. A reviewer in 2030 should be able to ask "why was this
  decision made?" and find the answer on the tracking issue, including
  which model produced it, what alternatives were weighed, and what
  rationale prevailed.
- **Architectural discipline** — Accepted ADRs in `docs/ADR/` are
  load-bearing, not aspirational. A PR that contradicts an ADR must
  surface that contradiction and either override the ADR (with a new ADR)
  or change the PR. The contract makes this surfacing automatic.
- **Production-grade security defaults** — OIDC-only AWS access, container
  security gates, secret scanning, RBAC via IAM groups — applied uniformly,
  not on a per-PR judgment call.
- **Confidence-calibrated output** — Long artifacts (50k+ char diffs,
  terraform plans, CloudWatch exports) are read with explicit chunk-level
  confidence tracking via the RLM scaffold (ADR-004) rather than
  whole-context summarization that silently omits the surprising part.

Meeting that bar requires more than ADRs. ADRs encode *what we decided*;
they do not constrain agent behavior *while a session is in flight*. The
contract closes that gap: it makes the gates a precondition for opening a
PR, so the discipline travels with every session rather than depending on
post-hoc review to catch lapses.

The Microsoft GBB Agentic Platform Engineering pattern (ADR-005) describes
how an *engineering platform* can be agent-driven; this ADR describes how
the **delivery process for Catalyst itself** is agent-driven. They are
complementary: ADR-005 is the platform we build for users; ADR-011 is the
contract we follow while building it.

## Decision

Adopt the six-gate operating contract codified in `AGENTS.md` as the
mandatory workflow for any agent contributing to Catalyst. The gates are
load-bearing on the audit trail — without them the codebase cannot be
demonstrated as "AI-produced under discipline" rather than "AI-produced and
hoping it's right":

1. **Model decision logging** — Before implementation and at every material
   architecture/security/scope decision, post `### Agent Decision Log` on
   the tracking issue (model selected, fallback known, rationale, next).
2. **RLM trigger at ~50k chars** — Long artifacts (diffs, terraform plans,
   CloudWatch exports, codebase reads >10 files) route through the recursive
   language model scaffold (ADR-004) before inline reading.
3. **AWS OIDC only** — No long-lived AWS keys in any agent path. GitHub
   OIDC roles only (ADR-006). Enforced by `validate_workflows.py` in CI.
4. **Container security gate** — Trivy HIGH/CRITICAL severity gate, SPDX
   2.3 + CycloneDX 1.5 SBOMs, SARIF upload to code scanning, on every PR
   that touches a Dockerfile or container image.
5. **Pre-PR peer review (mandatory)** — Before `gh pr create`, spawn a
   peer-review sub-agent (`Agent` tool, general-purpose). Sub-agent reviews:
   AC compliance, ADR compliance, security, coverage, naming. Every
   suggestion is recorded on the tracking issue with ACCEPT/REJECT + a
   one-line rationale. All ACCEPT items must be resolved before the PR
   opens; REJECT items are documented in the PR body.
6. **GitHub MCP secret scanning** — `secret_protection` toolset invoked on
   any PR adding files or credentials before the `pr_merged=true` done gate.

The contract is enforced by:

- `validate_workflows.py` — structural CI check that every AWS-touching
  workflow has `permissions.id-token: write` and references the matching
  OIDC role secret. Regression fails the build before reaching AWS.
- `docs/issue-execution-gherkin-workflow-2026-05-13.md` — issue comment
  shape (Context / Decision / Rationale / Alternatives / Actions /
  Verification / Risks / Next) and Gherkin AC format.
- `docs/rlm-issue-handoff-template.md` — required fields when a session
  involved RLM (analysis query, chunk count, synthesis decision, low-
  confidence callouts).
- The Cursor plugin assets under `.cursor/agents/`, `.cursor/rules/`,
  `.cursor/skills/` make the contract IDE-resident for any agent that
  opens the repo in Cursor.

## Consequences

- **PR bodies are structured artifacts by design.** Context, Scope, Gherkin
  AC, Agent Decision Log, Pre-PR Peer Review with disposition table,
  Alternatives Considered, Verification. Reviewer time per PR is higher
  than for a bare diff — and reviewer surprise approaches zero.
- **Every merged PR is a defensible artifact in a panel/audit setting.**
  The trail from "issue opened" to "code merged" is reconstructable from
  comments alone. `docs/ai-workflow-narrative.md` cites PRs #147, #140,
  #115, and #105 as worked examples of the contract in action.
- **Peer-review sub-agents raise the diagnostic floor.** The sub-agent runs
  in 1–3 minutes, has full repo access, and produces a written verdict on
  the tracking issue. PR #147 is the canonical example: the triage agent
  posted an initial hypothesis (`paths:` filter); the peer-review sub-agent
  ran actionlint locally and returned a higher-confidence diagnosis
  (`secrets.*` in step-level `if:`). The contract turned a plausible
  guess into a verified root cause *before* the PR opened.
- **Agents stop at architectural surprises rather than power through.**
  PR #115 is the worked example: mid-implementation, the agent discovered
  that binding a workflow to a GitHub Environment mutates the OIDC JWT
  `sub` claim and breaks bootstrap-managed role trust. It posted a
  decision log, surfaced the scope change to the operator, and waited
  for approval before re-scoping to a single consolidated `terraform.yml`.
  This stop-and-surface behavior is a designed feature of the contract,
  not an exception path.
- **The contract requires a capable agent host.** Sessions need sub-agent
  spawn, MCP server access, and structured comment posting. A bare LLM
  call cannot satisfy gate 5 (peer review) or gate 6 (secret scanning);
  such sessions must produce a hand-off comment for an agent session that
  can. This is explicit and documented, not implicit.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Loose contract — "agents follow ADRs, no other gates" | ADRs encode *what we decided*; they cannot constrain *how* an in-flight session reaches its decision. Without the in-session gates, the audit trail is post-hoc and incomplete — the trail must be created *as the work happens* to be defensible. |
| Hard gate via CI only — no in-session contract | CI catches regressions after a PR is opened. The contract has to be *in the session* so the agent self-corrects before `gh pr create`, when the cost of revision is lowest and the reasoning is still in context. |
| Single peer-review *human* per PR — no sub-agent | A human reviewer is still expected at merge time; the sub-agent is the *pre-PR* gate, not a replacement. The sub-agent's value is producing a written verdict on the tracking issue in seconds, so the human reviewer arrives at the PR already informed. |
| Adopt the Microsoft Azure pattern (ADR-005) verbatim | ADR-005 is about the *engineering platform we build*. This ADR is about *how we build Catalyst itself*. They operate at different layers; both are needed. |
| Centralize gates in a single "agent runner" script | A wrapper script makes the rules opaque to the agent — gates become a pass/fail black box rather than rules the agent understands. Distributing the contract across `AGENTS.md`, `.cursor/rules/`, and Claude Code agent files keeps the gates in the agent's reasoning context, so it can apply them with judgment rather than just trip on them. |

## Related

- `AGENTS.md` — operating contract, source of truth for the six gates.
- `CLAUDE.md` — four-rule guardrail layered on top of AGENTS.md for Claude
  Code sessions specifically.
- `docs/ai-workflow-narrative.md` — evidence catalog with PR citations.
- `docs/issue-execution-gherkin-workflow-2026-05-13.md` — issue/comment
  shape required by gate 1.
- `docs/rlm-issue-handoff-template.md` — required fields when gate 2 fires.
- `.cursor/agents/aws-platform-engineer.md`,
  `.cursor/agents/security-hardener.md` — agent personas that own
  specific gates (security-hardener owns gate 6).
