# Multi-tool config — Cursor, Claude Code, and Gemini CLI

Operating map for Catalyst agent config. Canonical content lives under `skills/` and `agents/`; per-tool trees are **wired by bootstrap** (ADR-024), replacing ADR-022 committed stub copies in phased sub-issues.

## Bootstrap (ADR-024)

After clone or when canonical `skills/` / `agents/` change:

```bash
python platform/bootstrap.py          # symlink on Unix, copy on Windows
python platform/bootstrap.py --check  # verify tool trees match canonical
python platform/bootstrap.py --copy   # force copy mode (Windows / no symlinks)
```

**Dual mode until A-4**: CI may still enforce committed ADR-022 stubs via `scripts/sync_tool_skills.py --check`. Locally, bootstrap is the editor source of truth. `.gitignore` lists generated tool trees; committed stubs are removed in ADR-024 A-4.

## Quick map

| Surface | Canonical source | Claude Code path | Cursor / Gemini path | Sync mechanism |
|---|---|---|---|---|
| Skills | `skills/<name>/SKILL.md` (+ scripts/, templates/, *_mcp_server.py) | `skills/<name>/` | `skills/<name>/`, `.gemini/skills/<name>/` | `platform/bootstrap.py`; CI `--check` after A-4 |
| Personas | `agents/<name>.md` | `.claude/agents/<name>.md` (thin adapter from `platform/personas.meta.yaml`) | `.cursor/agents/<name>.md`, `.gemini/agents/<name>.md` | `platform/bootstrap.py`; Claude dispatch in `personas.meta.yaml` |
| Routing skills | `skills/<name>/` | `skills/<name>/` | `skills/<name>/`, `.gemini/skills/<name>/` | Same as Skills |
| MCP servers | `skills/<name>/<name>_mcp_server.py` | `.mcp.json` (generated) | `.cursor/mcp.json` (generated) | Edit `platform/mcp.servers.json`; bootstrap emits per-tool JSON |
| Operating contract | `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` | Both | Both | Already shared; no sync needed |
| Cursor-only rules | `.cursor/rules/*.mdc` | (no equivalent — see below) | Cursor reads natively | Documented by intent here, not duplicated |
| Cursor-only hooks | `.cursor/hooks/` | (no equivalent — see below) | Cursor reads natively | Documented by intent here, not duplicated |

## Cursor rules → Claude Code analogues

Five `.cursor/rules/*.mdc` files remain after the ADR-022 refactor (`catalyst-agents.mdc` was migrated to `skills/catalyst-agent-routing/`). Each one is mapped here by intent.

| `.cursor/rules/*.mdc` | Intent | Claude Code analogue | Notes |
|---|---|---|---|
| `aws-platform-engineering.mdc` | Auto-activate the AWS Platform Engineer persona + matching skill + AWS-flavoured prompts when work touches AWS services, Terraform, OIDC, Bedrock, ECS/EKS/Lambda, VPC/ALB, landing zones | Read the `aws-platform-engineering` skill (auto-discovered by Claude Code) or invoke the `aws-platform-engineer` subagent via Task | No 1:1 rule equivalent. Claude Code discovers skills by frontmatter `description`. Persona is dispatched explicitly via Task, not auto-activated. |
| `github-secret-scanning.mdc` | PreToolUse-style gate: before commits, pushes, file writes touching credential paths, invoke GitHub MCP `secret_protection` toolset | Use a `PreToolUse` hook in `.claude/settings.json` matching `Bash` + `git commit`/`git push` patterns, calling the same MCP tool. **Not implemented in this refactor** — documented for follow-up. | Registered in `.cursor/mcp.json` only via `platform/mcp.servers.json` `cursorOnly`. |
| `intent-judge.mdc` | PreToolUse-style allow/deny/clarify gate for high-risk tool calls (writes, deletes, deploys, IAM/policy edits, secret ops, broad-scope automation) | Use a `PreToolUse` hook in `.claude/settings.json` calling the `intent-judge` MCP server's `validate_intent` tool. **Not implemented in this refactor.** | The MCP server is registered in `.mcp.json`. The `intent-judge-shim` skill explains the protocol. Trigger logic is what needs porting. |
| `model-decision-logging.mdc` | Always-apply rule: log model selection rationale in GitHub issue decision comments | Covered by `CLAUDE.md` execution guardrails + `AGENTS.md` decision-log gate. No hook needed; this is human-discipline territory. | Already enforced via PR template + ADR-011 gate-5. |
| `rlm-workflow.mdc` | Activate the RLM workflow when an artifact exceeds ~50k characters | The `rlm` skill itself (canonical: `skills/rlm/SKILL.md`) carries the trigger description in its frontmatter. Claude Code's skill discovery surfaces it on the same signal. | Functional parity achieved via the skill's auto-discovery; no rule file needed. |

## Cursor hooks → Claude Code analogues

`.cursor/hooks/` and its `state/` directory hold Cursor-specific filesystem hooks. They are intentionally **not mirrored** into `.claude/hooks/`.

| `.cursor/hooks/` purpose | Claude Code analogue | Notes |
|---|---|---|
| Cursor IDE event hooks (file save, session start, etc.) | `hooks` block in `.claude/settings.json` (PreToolUse, PostToolUse, Stop, etc.) | Implementation surface is fundamentally different — Cursor invokes shell scripts on filesystem events; Claude Code invokes shell commands on tool-call events. Mechanical port would mis-time. |

If/when a Cursor hook's *intent* needs Claude-side coverage, add an entry to `.claude/settings.json` under `hooks` and update this table — do not blindly copy the script.

## Adding a new skill (runbook)

```bash
# 1. Author canonical content
mkdir -p skills/my-new-skill/
$EDITOR skills/my-new-skill/SKILL.md   # author SKILL.md with frontmatter

# 2. Wire per-tool trees
python platform/bootstrap.py

# 3. Verify locally
python platform/bootstrap.py --check  # exits 0

# 4. Stage and commit canonical only (after A-4); until then also run sync if CI still checks stubs
git add skills/my-new-skill/
git commit -m "feat(skill): add my-new-skill (#issue-number)"
```

## Adding a new persona (runbook)

```bash
# 1. Author canonical persona body
$EDITOR agents/my-new-persona.md

# 2. Add Claude dispatch metadata in platform/personas.meta.yaml (model, tools, description)

# 3. Wire per-tool trees and thin Claude adapters
python platform/bootstrap.py

# 4. Verify
python platform/bootstrap.py --check

# 5. Stage and commit canonical + personas.meta.yaml (+ thin .claude adapter until A-4)
git add agents/my-new-persona.md platform/personas.meta.yaml .claude/agents/my-new-persona.md
git commit -m "feat(agent): add my-new-persona (#issue-number)"
```

## Adding an MCP server (runbook)

```bash
# 1. Add or extend the server script under skills/<name>/
# 2. Register in platform/mcp.servers.json (HTTP/Cursor-only: add name to cursorOnly)
$EDITOR platform/mcp.servers.json

# 3. Regenerate client configs
python platform/bootstrap.py

# 4. Verify
python platform/bootstrap.py --check
```

The `catalyst-github-secret-scanning` HTTP server stays Cursor-only (`cursorOnly` in the manifest) so `${env:GITHUB_MCP_PAT}` is not required in Claude/Gemini configs.

## CI guard

Until ADR-024 A-4 lands, `.github/workflows/multi-tool-sync.yml` still runs `scripts/sync_tool_skills.py --check` against committed stubs.

After A-4, CI runs `python platform/bootstrap.py --check` only; PRs touch `skills/` and `agents/` canonical paths.

## Related

- ADR-022 — Canonical `skills/` and `agents/` layout (stub delivery superseded by ADR-024 bootstrap)
- ADR-024 — Unified agent config and bootstrap-wired tool trees
- Issue #255 — the one-time refactor that produced this layout
- ADR-011 — Catalyst agentic workflow (the operating contract that this layout serves)
