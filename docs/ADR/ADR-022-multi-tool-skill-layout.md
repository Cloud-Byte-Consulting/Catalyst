# ADR-022 — Unify Claude Code and Cursor skills/agents under a canonical-source layout

**Status**: Accepted · 2026-05-19

## Context

Catalyst maintained two parallel tool-config trees that drifted as the project grew. Before this ADR, the asymmetry was:

| Surface | Claude Code | Cursor |
|---|---|---|
| Skills | 4 (`draw-aws-diagrams`, `pr-review-triage`, `rlm`, `test-coverage-discipline`) | 35 (adr-writer, ai-observability, ... 33 more) |
| Agents | 1 (`rlm-subcall`) | 10 personas |
| Rules | none — uses `CLAUDE.md` | 6 `.mdc` rules |
| Hooks | none configured | `.cursor/hooks/` |
| MCP servers | `.mcp.json` | `.cursor/mcp.json` (already mirrored per PR #176) |
| Operating contract | `CLAUDE.md` + `AGENTS.md` | `AGENTS.md` (already shared) |

Anything an agent discovered via the Cursor surface was invisible to a Claude Code session, and vice versa. New skills authored on one side silently missed the other. The MCP mirror already proved that some surfaces can be unified cleanly.

The user surfaced the gap directly: "cursor and claude are not sharing the same skills, hooks, agents etc... it can be a single issue with a one time refactor". Issue [#255](https://github.com/Cloud-Byte-Consulting/coding/issues/255) tracks the refactor.

## Decision

We will keep a single canonical source for every skill, agent, and routable rule, and let each IDE-specific tree contain only thin pointers to that canonical content.

```
skills/<name>/SKILL.md         -- canonical skill content
skills/<name>/scripts/         -- optional supporting files
skills/<name>/templates/       -- optional supporting files
skills/<name>/<name>_mcp_server.py  -- optional MCP server source

agents/<name>.md               -- canonical persona content (10 personas)

.claude/skills/<name>/SKILL.md -- AUTO-GENERATED stub copy of the canonical
.cursor/skills/<name>/SKILL.md -- AUTO-GENERATED stub copy of the canonical
.cursor/agents/<name>.md       -- AUTO-GENERATED stub copy of the canonical
.claude/agents/<name>.md       -- HAND-AUTHORED adapter that adds Claude
                                  subagent frontmatter (name, description,
                                  model, tools) above the canonical body
```

Each `.claude/skills/<name>/SKILL.md` and `.cursor/skills/<name>/SKILL.md` and `.cursor/agents/<name>.md` carries this header so the source of truth is obvious:

```
<!-- AUTO-GENERATED from skills/<name>/SKILL.md — do not edit here.
     Run scripts/sync_tool_skills.py to regenerate. -->
```

A new GitHub Actions workflow `.github/workflows/multi-tool-sync.yml` enforces drift-zero on every PR.

## Implementation choices

### Stub files, not symlinks

We considered symlinks (each tool stub being a symlink to the canonical), which would be free of any "sync" concept. We probed the worktree:

- `git config --get core.symlinks` returned `false`
- Attempting `ln -s` inside `.claude/skills/_probe/` on Windows MSYS git did not produce a symlink — the target was written as a regular file in-place

We therefore use **stub files** with the auto-generated header above. `scripts/sync_tool_skills.py` regenerates every stub from canonical content. `scripts/sync_tool_skills.py --check` exits non-zero if any stub diverges; the CI workflow runs that check on every PR against `release`.

### Claude agent adapters are not auto-generated

Cursor personas are pure prose system-prompts; the tool reads the whole file. A Claude Code subagent registered for the Task tool needs explicit frontmatter (`name`, `description`, `model`, `tools`) so the dispatcher can pick a model and restrict tool access. Auto-generating that frontmatter from prose is fragile.

We hand-authored the 10 adapter files once via `scripts/build_claude_agent_adapters.py`, recording model + tools per persona in a `PERSONAS` dict in that script. Architect/security personas → `opus`; operator/expert personas → `sonnet`; default tools are `[Read, Grep, Glob]` (read-only) with `Bash`/`Edit` added only where the persona's work obviously requires them (`terraform-engineer`, `aws-platform-engineer`, `cicd-operator`, etc.).

The CI workflow only checks that each canonical persona has a corresponding Claude adapter file; it does not regenerate adapter bodies.

### MCP-server reference paths

Four skills ship an MCP server: `rlm`, `aws-platform-engineering`, `bedrock-binding`, `intent-judge-shim`. The server source files moved with the rest of the skill content into `skills/<name>/`. Both `.mcp.json` (Claude Code) and `.cursor/mcp.json` (Cursor) were updated to reference `skills/<name>/<name>_mcp_server.py` instead of the old `.cursor/skills/<name>/<name>_mcp_server.py`.

### Cursor rules — migrate by intent, not by code

Of the six `.cursor/rules/*.mdc` files, only `catalyst-agents.mdc` is genuinely a routing skill (a topic-to-persona lookup table) — it became `skills/catalyst-agent-routing/SKILL.md`. The remaining five (`aws-platform-engineering`, `github-secret-scanning`, `intent-judge`, `model-decision-logging`, `rlm-workflow`) are Cursor-specific platform behaviors (auto-activation patterns, PreToolUse-equivalent gates) and stay where they are. `docs/multi-tool-config.md` maps each one to its Claude Code analogue by intent (CLAUDE.md prose, a hook, a skill, or "no equivalent").

### Cursor hooks stay untouched

`.cursor/hooks/` is left alone. We do not attempt to mirror them under `.claude/hooks/` in this refactor — the implementation surfaces are too different to mechanically port, and the user direction explicitly scoped this kaizen to skills/agents.

## Consequences

- Single source of truth for 39 skills + 10 personas; future authors edit `skills/<name>/SKILL.md` once.
- New skills follow a 1-step runbook: drop the canonical into `skills/<name>/`, run `python scripts/sync_tool_skills.py`, commit all three paths.
- CI catches the drift case where someone hand-edits a stub or forgets to regenerate — the workflow fails with a named-file diff.
- Stub files duplicate canonical bytes on disk (~3x storage for the SKILL.md surface). Acceptable: total <500 KB and the redundancy is what makes tool discovery work without symlinks.
- Claude adapter bodies can drift from the canonical persona text if someone edits `agents/<name>.md` and forgets to re-run `scripts/build_claude_agent_adapters.py`. The CI workflow flags missing files but not stale bodies; that's a follow-up tightening.
- MCP-server clients must be restarted after this change because the script paths moved.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Symlinks from `.claude/`/`.cursor/` into `skills/` | Windows MSYS git probe showed `core.symlinks=false` and `ln -s` did not produce a symlink. Would break for any contributor on Windows. |
| Author canonical inside `.cursor/skills/` and stub from `.claude/skills/` | Implies Cursor is the source of truth. Locks Catalyst to the Cursor convention forever and makes the canonical location surprising. |
| Auto-generate Claude adapter frontmatter from persona prose | Brittle. Model and tools choice is a deliberate per-persona judgement (architect → opus + read-only, operator → sonnet + Bash). Encoding it once in a script's `PERSONAS` dict is clearer. |
| Mirror `.cursor/hooks/` into `.claude/hooks/` | Implementation surfaces differ — Cursor hooks are filesystem-scripts, Claude hooks are JSON config in `.claude/settings.json`. Mechanical port would produce wrong semantics. Documented by intent in `docs/multi-tool-config.md` instead. |
| Migrate all 6 `.cursor/rules/*.mdc` into `skills/` | Only `catalyst-agents.mdc` is content-portable. The other five encode Cursor-platform behaviors (auto-activation, PreToolUse) with no 1:1 Claude analogue. Forcing them into the skills tree would mislead future readers. |

## Related

- Issue [#255](https://github.com/Cloud-Byte-Consulting/coding/issues/255) — kaizen tracking
- PR #176 (commit `21c1551`) — the `.mcp.json` ↔ `.cursor/mcp.json` mirror that was the proof point
- `docs/multi-tool-config.md` — the by-intent mapping for the 5 remaining Cursor rules + hooks
- `scripts/sync_tool_skills.py` — stub regenerator + drift checker
- `scripts/build_claude_agent_adapters.py` — one-shot Claude adapter generator
- `.github/workflows/multi-tool-sync.yml` — CI drift guard
- ADR-011 (catalyst agentic workflow) — operating contract this refactor supports
