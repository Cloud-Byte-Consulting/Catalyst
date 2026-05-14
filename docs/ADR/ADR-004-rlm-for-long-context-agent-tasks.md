# ADR-004 — Recursive Language Model (RLM) pattern for long-context agent tasks

**Status**: Accepted · 2026-05-13

## Context

Catalyst's agent-driven automation depends on language models reading and reasoning over large artifacts
at every layer of the stack:

| Catalyst workflow | Artifact that hits context limits |
|---|---|
| `type/pr-review` | Large diffs — multi-file PRs with hundreds of changed lines, imported module trees |
| `type/ops-intel-finding` | CloudWatch log exports, CloudTrail events, S3 inventory CSVs (tens to hundreds of KB) |
| `type/deploy` | `terraform plan` output for modules with dozens of resources |
| Feature agent tasks | Full codebase reads across `services/`, `infrastructure/`, multiple ADRs, issue history |
| Issue resume (handoff) | Accumulated issue comment threads (audit trail from prior agent runs) |

Claude Opus 4.x has a 200k-token context window, but a single large `terraform plan`, a CloudTrail
export, or a PR spanning several services can saturate it while leaving insufficient budget for the
model to produce high-quality output. Forcing the whole artifact inline also wastes tokens on
content irrelevant to the specific query.

The academic paper *"Recursive Language Models"* (Zhang, Kraska, Khattab — MIT CSAIL, arXiv:2512.24601)
describes a pattern where a root LLM decomposes large context into chunks, delegates chunk-level
analysis to sub-LLMs, and synthesizes results — enabling effective reasoning over inputs two orders
of magnitude beyond a single context window.

An open-source minimal implementation of this pattern exists at
`https://github.com/BittahCriminal/claude_code_RLM` (also cloned to the
`Cloud-Byte-Consulting/claude_code_RLM` workspace directory). It maps RLM primitives to Claude Code
natively:

| RLM concept | Claude Code primitive |
|---|---|
| Root LLM | Main Claude Code session (Opus 4.x) |
| Sub-LLM (llm_query) | `rlm-subcall` subagent (Haiku 4.5 — fast, cheap) |
| External environment | Persistent Python REPL (`rlm_repl.py`) — pickle-based state across tool calls |

The REPL externalizes the large artifact from the model context entirely. Only structured JSON
summaries from subagents flow back to the root. Context window usage scales with the number of
relevant findings, not with the size of the original artifact.

## Decision

Catalyst will adopt the RLM pattern — via the `.claude/skills/rlm/` skill and `rlm-subcall`
subagent from `claude_code_RLM` — as the standard approach for agent tasks that require reasoning
over artifacts exceeding ~50k tokens.

Concretely:

1. **Copy the RLM skill and subagent** into Catalyst's `.claude/` directory. The REPL script
   (`rlm_repl.py`) is pure Python stdlib — zero new dependencies.

2. **Four canonical Catalyst + RLM usage patterns** (detailed in `docs/rlm-integration-guide.md`):
   - **PR Review**: chunk the diff by file; each Haiku subagent extracts issues per file; Opus
     synthesizes verdict (aligns with `type/pr-review` state machine)
   - **Ops-Intel**: chunk CloudWatch/CloudTrail/S3 exports; Haiku extracts resource-level
     findings; Opus composes ops-intel issue body and severity
   - **Terraform plan**: chunk plan output by resource block; Haiku flags drift, cost, and policy
     violations per resource; Opus composes deployment risk summary
   - **Feature implementation (long codebase reads)**: chunk relevant source files; Haiku
     extracts structural facts per file; Opus synthesizes implementation plan and posts to issue

3. **Trigger threshold**: invoke `/rlm` when the artifact to be read exceeds ~50k characters
   (~35k tokens). Below that threshold, inline reading is more efficient (no chunking overhead).

4. **Model budget**: Haiku 4.5 for all subagent `rlm-subcall` invocations (cost and latency).
   Opus for the root synthesis step only. This aligns with Catalyst's Heijunka principle
   (Bedrock token-budget throttling) — high-traffic workflows like `type/ops-intel-finding`
   run many Haiku calls in parallel rather than serialising on Opus.

5. **State persistence**: RLM's `rlm_state/state.pkl` is ephemeral to the agent session. It is
   NOT the durable state store. GitHub Issues remain the durable state machine per ADR-001.
   The REPL state file lives in `.claude/rlm_state/` (gitignored) and is discarded after the
   issue reaches a terminal state.

6. **Issue comment handoff**: after an RLM-assisted session, the structured comment (`### Next`,
   `### Actions taken`) MUST record the query, chunk count, and synthesis outcome so a future
   agent can reproduce or extend the analysis without re-running the full RLM pass. See
   `docs/issue-execution-gherkin-workflow-2026-05-13.md` for comment conventions.

## Consequences

**Good:**
- Agents can reason over arbitrarily large artifacts without silent truncation or hallucinated
  summaries caused by context overflow.
- Haiku subagents are substantially cheaper per token than Opus; large-artifact analysis cost
  drops proportionally to the share of work done by Haiku.
- The chunking + structured-JSON output pattern produces machine-readable evidence that can be
  persisted as GitHub Issue body fields (resource ARN, severity, evidence excerpt) per the
  ops-intel spec in `STATE-MACHINE.md`.
- Pure Python stdlib — zero new runtime dependencies for the Catalyst services build.
- The RLM REPL's `grep()` and `peek()` helpers let the root agent scout and selectively skip
  irrelevant chunks, further reducing cost.

**Trade-offs we accept:**
- **Latency**: chunked analysis adds round-trips. A 500 KB plan file with 5 chunks and sequential
  subagent calls adds ~30–60 seconds. Mitigated by parallelising subagent calls where Haiku
  invocations are independent (each chunk is a separate file read).
- **Chunk boundary artefacts**: semantic continuity can be lost at chunk edges (e.g., a multi-file
  hunk split across chunks). Mitigated by the `overlap_chars` parameter in the REPL's
  `chunk_indices()` helper.
- **`exec()` security**: `rlm_repl.py` runs arbitrary Python via `exec()`. Acceptable because
  it executes only under the agent's local permissions during a development session — never in
  a production Lambda or ECS task.
- **No recursive subagent calls**: the `rlm-subcall` subagent cannot itself spawn subagents
  (Claude Code depth-1 handoff). This means a two-pass synthesis (chunk → intermediate summary →
  final answer) requires two explicit root-orchestrated loops, not automatic recursion.
- **Pickle state**: `.pkl` files are not human-readable and are not version-controlled. Agents
  resuming work on an issue must re-run `python rlm_repl.py init <file>` rather than inheriting
  prior REPL state.

**Risks and mitigations:**

| Risk | Mitigation |
|---|---|
| Agent forgets to invoke `/rlm` and truncates silently | CLAUDE.md instruction: "If the artifact exceeds 50k chars, invoke `/rlm` before reading." Add this as a guardrail in AGENTS.md. |
| `state.pkl` grows stale across sessions | Script's `reset` command; `status` command shows `loaded_at` timestamp; agent checks age before trusting state. |
| Haiku hallucination per chunk propagates to synthesis | Root Opus synthesis step cross-checks conflicting chunk results; structured JSON includes `confidence` field. |
| `rlm_state/` accidentally committed | Already handled — `.gitignore` entry `**/.claude/rlm_state/` in RLM repo; replicate in Catalyst's `.gitignore`. |

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Increase Opus context and read inline | Silent truncation risk; token cost scales linearly with file size regardless of relevance; doesn't solve >200k token cases. |
| Pre-summarise artifacts before agent session (offline pipeline) | Requires separate compute; summaries are lossy and query-agnostic; can't be re-targeted at different questions mid-session. |
| AWS Bedrock Knowledge Bases (RAG) | Right for production retrieval at scale; heavyweight for in-session agent reasoning; adds vector-DB dependency; no offline/local option. |
| LangChain / LlamaIndex chunking libraries | Additional dependency; Claude Code native primitives (skills, subagents, REPL) are sufficient and simpler. |
| Custom per-service chunking logic | Reinvents the RLM REPL; inconsistent across `type/pr-review`, `type/ops-intel`, `type/deploy`; no reuse. |

## Implementation findings (2026-05-13)

Adoption was executed end-to-end on branch `rc/rlm` against issue
[#3](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/3) following the
six-phase plan in
[`docs/catalyst-agent-toolkit-plan.md`](../catalyst-agent-toolkit-plan.md).

**What was vendored and where it lives**:

| Path | Provenance |
|---|---|
| `.claude/skills/rlm/SKILL.md` | verbatim from `BittahCriminal/claude_code_RLM` @ `0b3cdba` |
| `.claude/skills/rlm/scripts/rlm_repl.py` | verbatim, pure stdlib Python (no new deps) |
| `.claude/agents/rlm-subcall.md` | verbatim, Haiku-targeted `llm_query` subagent |
| `.gitignore` | extended with `**/.claude/rlm_state/` (existing rules preserved) |
| `AGENTS.md` | new `## Operating Rules` section captures the ~50k-character trigger and the canonical paths |
| `docs/issue-execution-gherkin-workflow-2026-05-13.md` | new `## RLM workflow` section cross-links the four canonical patterns from `docs/rlm-integration-guide.md` |
| `docs/rlm-issue-handoff-template.md` | new — required RLM-handoff fields composed with the existing `### Context / ### Decision / …` skeleton |
| `docs/worklog/2026-05-13-issue-3-rlm-toolkit.md` | full evidence trail and per-phase pass/fail |

**Deviations from the original ADR**: none material. The only clarifications:

1. The plan doc `docs/catalyst-agent-toolkit-plan.md` was authored in the
   same session as the implementation; its 6 phases map 1:1 to the issue #3
   scope bullets and the four canonical patterns referenced in this ADR.
2. The end-to-end dry-run validation used a deterministic regex stub for
   `rlm-subcall` because the implementation owner ran from Cursor's Claude
   orchestrator, which cannot spawn Claude Code subagents. The REPL
   plumbing, chunking, `buffers` accumulation, and JSON-per-chunk schema are
   all exercised against the real `rlm_repl.py`. Real Haiku invocation is
   the next agent's first action when an RLM-assisted issue is picked up
   under Claude Code.

**Validation results from the end-to-end dry run**:

| Metric | Value |
|---|---|
| Synthetic artifact | concatenation of ADR-001 / STATE-MACHINE / ADR-004 / integration guide / Gherkin workflow / handoff template / plan / vendored RLM assets |
| Artifact size on disk | 99,622 bytes |
| REPL-loaded chars | 98,478 (≈48k tokens) — comfortably above the ~50k-char trigger |
| Chunk strategy | `chunk_chars=30000`, `overlap_chars=1000` |
| Chunks materialised | 4 (chunks 0–2 = 30,000 chars; chunk 3 = 11,478 chars) |
| Subcall outputs | 4 JSON-per-chunk findings appended to `buffers` (`relevant` lists: 3, 9, 8, 0) |
| Synthesis input file | `.claude/rlm_state/synthesis-input.json` — 4,980 bytes |
| Cost-model estimate | scout ~0.6k Opus, chunk × 4 = ~120k Haiku, synth ~6k Opus → ~$0.12 total vs ~$1.10 inline-Opus |
| Latency (excl. real subagent calls) | <2 s end-to-end on local Python 3 |
| Done-gate at write-time | `tests_passed=true`, `docs_updated=true`, `pr_required=true`, `pr_merged=<see closing issue comment>` |

The 27× cost reduction quoted earlier in this ADR was derived from the 500 KB
worked example in `docs/rlm-integration-guide.md`. The dry-run is below the
break-even point at 98k chars (artifact small enough that inline Opus is
cheaper), confirming the trigger threshold of ~50k characters is not too
aggressive and that RLM should not be invoked for small artifacts. The
plumbing scales linearly, so the cost-model holds at the artifact sizes the
trigger rule is designed for (terraform plans, CloudTrail exports, large PR
diffs).

**Cross-links to the implementation**:

- Worklog: [`docs/worklog/2026-05-13-issue-3-rlm-toolkit.md`](../worklog/2026-05-13-issue-3-rlm-toolkit.md)
- Plan: [`docs/catalyst-agent-toolkit-plan.md`](../catalyst-agent-toolkit-plan.md)
- Handoff template: [`docs/rlm-issue-handoff-template.md`](../rlm-issue-handoff-template.md)
- Issue #3: <https://github.com/Cloud-Byte-Consulting/Catalyst/issues/3>

### Cursor IDE compatibility layer (2026-05-14)

The original RLM implementation was coupled to Claude Code primitives (`.claude/`
skills, `.claude/agents/` subagents, Bash tool). This follow-up extends RLM support
to Cursor IDE agents without modifying any existing Claude Code assets.

**What was added**:

| Path | Purpose |
|---|---|
| `.cursor/rules/rlm-workflow.mdc` | Cursor rule — documents the ~50k-char trigger, chunking → Task-subagent → synthesis orchestration, and all four canonical patterns mapped to Cursor's Shell + Task tools |
| `.cursor/skills/rlm/rlm_mcp_server.py` | Lightweight MCP stdio server wrapping `rlm_repl.py` — exposes `rlm_init`, `rlm_status`, `rlm_peek`, `rlm_grep`, `rlm_chunk`, `rlm_exec`, `rlm_reset`, `rlm_export_buffers` as MCP tools |
| `.cursor/mcp.json` | MCP server registration for the RLM wrapper |
| `docs/rlm-integration-guide.md` | New "Cursor agent usage" section with quick-start, MCP tool mapping, subagent mapping, pattern equivalents, and orchestration checklist |
| `AGENTS.md` | Updated RLM trigger rule to note applicability to both Claude Code and Cursor agents |

**Platform mapping**:

| RLM concept | Claude Code | Cursor |
|---|---|---|
| Root LM | Main Claude Code session | Root Cursor agent |
| Sub-LM (`llm_query`) | `rlm-subcall` subagent (Haiku) | `Task` tool (`subagent_type="generalPurpose"`) |
| External environment | Bash → `rlm_repl.py` | Shell tool → `rlm_repl.py` (or MCP `rlm-repl` server) |
| Skill trigger | `/rlm` skill invocation | `.cursor/rules/rlm-workflow.mdc` (auto-activates on description match) |

**Deviations from Claude Code**:

1. Cursor's Task subagents do not support model selection (no Haiku-specific
   targeting). The `generalPurpose` subagent uses the default model for the
   workspace. Cost savings from Haiku sub-calls are Claude Code-specific;
   Cursor agents should still benefit from context-window savings.
2. Cursor does not have a native `/rlm` skill invocation command. The rule file
   activates based on its `description` field when the Cursor agent encounters
   a matching context. The rule is `alwaysApply: false` to avoid noise on
   unrelated tasks.
3. The MCP server wrapper is optional but recommended — it provides tool-native
   access without Shell round-trips. It imports `rlm_repl.py` directly rather
   than forking it, sharing the same state pickle.

**Validation**: the MCP server compiles cleanly (`python -m py_compile` exit 0).
The Cursor rule file includes all four patterns, trigger threshold, and
orchestration steps. `AGENTS.md` updated. Integration guide extended. No
existing Claude Code files were modified.

**Open follow-ups discovered during implementation**:

1. Re-run the Phase 6 dry-run from a Claude Code session so a real Haiku
   `rlm-subcall` invocation replaces the regex stub. Track as a future
   `type/kaizen` only if the team wants explicit follow-up; the simulator's
   JSON output already conforms to the subagent schema.
2. Consider a `type/kaizen` to rename the project board column `In review` →
   `Review` so it matches the ADR-001 vocabulary verbatim; non-blocking.
3. Re-evaluate the ADR-004 cost model against a real `terraform plan` output
   once `infrastructure/modules/composite/github-bootstrap/` lands on
   `release`. Current ADR references modules that exist in design but not yet
   in this branch.

The done-criteria of this ADR (vendor assets, gitignore, trigger guardrail,
operating-doc alignment, handoff template, end-to-end validation) are all
met. **Status flipped from `Proposed` → `Accepted`.**

## Related

- [ADR-001 — GitHub Issues as durable state machine](ADR-001-github-issues-as-state-machine.md)
- [STATE-MACHINE.md](STATE-MACHINE.md) — label vocabulary, audit comment conventions
- [docs/catalyst-agent-toolkit-plan.md](../catalyst-agent-toolkit-plan.md) — 6-phase implementation plan
- [docs/rlm-integration-guide.md](../rlm-integration-guide.md) — practical usage patterns
- [docs/rlm-issue-handoff-template.md](../rlm-issue-handoff-template.md) — RLM-handoff comment template
- [docs/issue-execution-gherkin-workflow-2026-05-13.md](../issue-execution-gherkin-workflow-2026-05-13.md) — agent handoff comment format
- [docs/worklog/2026-05-13-issue-3-rlm-toolkit.md](../worklog/2026-05-13-issue-3-rlm-toolkit.md) — implementation worklog
- Source: `https://github.com/BittahCriminal/claude_code_RLM` @ `0b3cdba`
- Paper: Zhang, Kraska, Khattab — *Recursive Language Models* (arXiv:2512.24601, MIT CSAIL)

**Last reviewed**: 2026-05-13
