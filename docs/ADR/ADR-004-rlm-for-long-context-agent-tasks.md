# ADR-004 — Recursive Language Model (RLM) pattern for long-context agent tasks

**Status**: Proposed · 2026-05-13

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

## Related

- [ADR-001 — GitHub Issues as durable state machine](ADR-001-github-issues-as-state-machine.md)
- [STATE-MACHINE.md](STATE-MACHINE.md) — label vocabulary, audit comment conventions
- [docs/rlm-integration-guide.md](../rlm-integration-guide.md) — practical usage patterns
- [docs/issue-execution-gherkin-workflow-2026-05-13.md](../issue-execution-gherkin-workflow-2026-05-13.md) — agent handoff comment format
- Source: `https://github.com/BittahCriminal/claude_code_RLM`
- Paper: Zhang, Kraska, Khattab — *Recursive Language Models* (arXiv:2512.24601, MIT CSAIL)

**Last reviewed**: 2026-05-13
