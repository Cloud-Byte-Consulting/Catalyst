# Worklog — RLM Cursor agent compatibility layer

**Issue**: [#5 — feat: RLM Cursor agent compatibility layer](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/5)
**Parent**: [#3 — Implementing Recursive Language Models for long running tasks](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/3)
**Branch**: `rc/rlm-cursor-compat`
**Date**: 2026-05-14
**Author**: Cursor agent (orchestrated)

---

## Summary

Extended the RLM (Recursive Language Model) toolkit to work natively with Cursor IDE
agents, in addition to the existing Claude Code support. The `rlm_repl.py` REPL script
is shared unchanged between both platforms. All changes are additive — no existing
Claude Code files were modified.

## Deliverables

### 1. `.cursor/rules/rlm-workflow.mdc` — Cursor rule file

- Documents the ~50k character trigger threshold
- Maps the RLM architecture to Cursor primitives: Shell tool for REPL commands, Task
  tool (`subagent_type="generalPurpose"`) for parallel chunk analysis
- Includes step-by-step orchestration procedure (init → scout → chunk → subagent loop
  → collect → synthesise → post → clean up)
- Maps all four canonical usage patterns (PR review, ops-intel, Terraform plan, feature
  implementation) to Cursor-specific commands
- References MCP alternative for tool-native access
- Documents all guardrails (no raw chunk pasting, depth-1 subagents only, REPL state
  is ephemeral, confidence field semantics)

### 2. `.cursor/skills/rlm/rlm_mcp_server.py` — MCP server wrapper

- Lightweight JSON-RPC 2.0 stdio server (pure Python stdlib, no external dependencies)
- Imports `rlm_repl.py` directly (shared module, not forked)
- Exposes 8 MCP tools: `rlm_init`, `rlm_status`, `rlm_peek`, `rlm_grep`, `rlm_chunk`,
  `rlm_exec`, `rlm_reset`, `rlm_export_buffers`
- Each tool delegates to the existing REPL functions
- Shares the same state pickle at `.claude/rlm_state/state.pkl`

### 3. `.cursor/mcp.json` — MCP server registration

- Registers the `rlm-repl` server with `python .cursor/skills/rlm/rlm_mcp_server.py`
  as the command

### 4. `docs/rlm-integration-guide.md` — Cursor agent usage section

- Added "Cursor agent usage" section with:
  - Quick-start shell commands for Cursor
  - MCP tool mapping table (MCP tool ↔ Shell equivalent)
  - Platform mapping table (Claude Code primitive ↔ Cursor equivalent)
  - Pattern equivalents for all four patterns in Cursor context
  - PowerShell variant for codebase concatenation (Pattern 4)
  - 9-step orchestration checklist

### 5. `docs/ADR/ADR-004-rlm-for-long-context-agent-tasks.md` — Cursor compat subsection

- Added "Cursor IDE compatibility layer (2026-05-14)" subsection under Implementation
  findings, documenting:
  - What was added (table of new files and purposes)
  - Platform mapping table (RLM concept → Claude Code → Cursor)
  - Three deviations from Claude Code (no model selection for subagents, no `/rlm`
    command, MCP wrapper is optional)
  - Validation results

### 6. `AGENTS.md` — Updated RLM trigger rule

- Updated the operating rule to explicitly note it applies to both Claude Code and
  Cursor agents
- Added Cursor-specific paths (`.cursor/rules/rlm-workflow.mdc`, MCP server, Task
  subagents)

### 7. Issue management

- Created [issue #5](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/5) with
  Context/Scope/Gherkin AC, labels, and link to parent #3
- Added to [project board #3](https://github.com/orgs/Cloud-Byte-Consulting/projects/3),
  status set to "In progress"

## Decisions

### MCP server approach

**Decision**: Implement an MCP server that imports `rlm_repl.py` as a Python module
rather than forking it as a subprocess.

**Rationale**: Direct import shares the same state pickle without serialisation
overhead, avoids process management complexity, and keeps the MCP server dependency-free
(pure stdlib). The trade-off is that the MCP server must be run from the repo root
(it does `os.chdir(REPO_ROOT)` on startup).

### Rule file vs skill directory

**Decision**: Use `.cursor/rules/rlm-workflow.mdc` as the primary Cursor guidance file,
not a `.cursor/skills/` SKILL.md.

**Rationale**: Cursor rules with `alwaysApply: false` and a `description` field activate
contextually when the agent encounters matching conditions. This is more natural than a
skill directory for a workflow that should fire based on artifact size, not explicit user
invocation. The MCP server lives under `.cursor/skills/rlm/` for organisational clarity.

### Task subagent model selection

**Decision**: Accept that Cursor Task subagents use the workspace default model rather
than Haiku-specific targeting.

**Rationale**: Cursor's Task tool does not expose a model selector for cost-tier routing.
The context-window savings (structured JSON vs raw artifact) are the primary RLM benefit
and apply regardless of subagent model. Cost optimisation via Haiku remains a Claude
Code-specific advantage, documented in ADR-004 as a deviation.

## Validation

| Check | Result |
|---|---|
| `python -m py_compile .cursor/skills/rlm/rlm_mcp_server.py` | Exit 0 |
| `python -m py_compile .claude/skills/rlm/scripts/rlm_repl.py` | Exit 0 |
| `.cursor/rules/rlm-workflow.mdc` exists | True |
| `.cursor/mcp.json` exists and references `rlm-repl` | True |
| `AGENTS.md` contains "both Claude Code and Cursor" | True |
| `docs/rlm-integration-guide.md` contains "Cursor agent usage" | True |
| ADR-004 contains "Cursor IDE compatibility layer" | True |
| `.claude/skills/rlm/SKILL.md` unmodified | True |
| `.claude/agents/rlm-subcall.md` unmodified | True |
| `.claude/skills/rlm/scripts/rlm_repl.py` unmodified | True |

## Limitations and follow-ups

1. **No model-tier routing in Cursor**: Cursor Task subagents cannot be targeted to
   Haiku for cost savings. The RLM cost model in ADR-004 is based on Haiku subcalls;
   actual Cursor costs will depend on the workspace default model.

2. **MCP server not integration-tested end-to-end**: The server compiles and the
   tool schemas are valid, but a live MCP session test requires a Cursor workspace with
   MCP enabled. Validation is deferred to first real usage.

3. **PowerShell-specific commands**: The Cursor rule and integration guide include
   PowerShell syntax (e.g., `Get-ChildItem`) for Windows environments. Bash equivalents
   exist in the original Claude Code patterns. Consider adding cross-platform notes
   if the team works across OSes.

4. **Task subagent prompt standardisation**: The chunk analysis prompt in the Cursor
   rule duplicates the `rlm-subcall.md` schema. If the schema evolves, both locations
   need updating. A future kaizen could extract the shared schema to a reusable file.

## Done-gate accounting

| Field | Value |
|---|---|
| `tests_passed` | true — all `py_compile` and content checks pass |
| `docs_updated` | true — integration guide, ADR-004, AGENTS.md, worklog all updated |
| `pr_required` | true |
| `pr_merged` | pending — PR to be opened |
| `pr_url` | pending |

## References

- Issue [#5](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/5)
- Parent [#3](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/3)
- [ADR-004](../ADR/ADR-004-rlm-for-long-context-agent-tasks.md)
- [RLM integration guide](../rlm-integration-guide.md)
- [Handoff template](../rlm-issue-handoff-template.md)
- Branch: `rc/rlm-cursor-compat`
