# Multi-tool config — Claude Code and Cursor

This doc is the operating map for Catalyst's two-tool config surface. It explains where each kind of agent-facing artifact lives, which tool consumes it, and how the canonical-source refactor (ADR-022) keeps both tools in sync without dual-maintenance.

## Quick map

| Surface | Canonical source | Claude Code path | Cursor path | Sync mechanism |
|---|---|---|---|---|
| Skills | `skills/<name>/SKILL.md` (+ scripts/, templates/, *_mcp_server.py) | `.claude/skills/<name>/SKILL.md` | `.cursor/skills/<name>/SKILL.md` | `scripts/sync_tool_skills.py` auto-generates stubs; CI checks |
| Personas | `agents/<name>.md` | `.claude/agents/<name>.md` (hand-authored adapter with Claude frontmatter) | `.cursor/agents/<name>.md` (auto-generated stub) | `scripts/build_claude_agent_adapters.py` (one-shot for Claude side); `scripts/sync_tool_skills.py` regenerates Cursor side |
| Routing skills | `skills/<name>/` | `.claude/skills/<name>/SKILL.md` stub | `.cursor/skills/<name>/SKILL.md` stub | Same as Skills |
| MCP servers | `skills/<name>/<name>_mcp_server.py` | `.mcp.json` (generated) | `.cursor/mcp.json` (generated) | Edit `platform/mcp.servers.json`; `platform/bootstrap.py` emits per-tool JSON |
| Operating contract | `AGENTS.md`, `CLAUDE.md` | Both | Both | Already shared; no sync needed |
| Cursor-only rules | `.cursor/rules/*.mdc` | (no equivalent — see below) | Cursor reads natively | Documented by intent here, not duplicated |
| Cursor-only hooks | `.cursor/hooks/` | (no equivalent — see below) | Cursor reads natively | Documented by intent here, not duplicated |

## Cursor rules → Claude Code analogues

Five `.cursor/rules/*.mdc` files remain after the ADR-022 refactor (`catalyst-agents.mdc` was migrated to `skills/catalyst-agent-routing/`). Each one is mapped here by intent.

| `.cursor/rules/*.mdc` | Intent | Claude Code analogue | Notes |
|---|---|---|---|
| `aws-platform-engineering.mdc` | Auto-activate the AWS Platform Engineer persona + matching skill + AWS-flavoured prompts when work touches AWS services, Terraform, OIDC, Bedrock, ECS/EKS/Lambda, VPC/ALB, landing zones | Read the `aws-platform-engineering` skill (auto-discovered by Claude Code) or invoke the `aws-platform-engineer` subagent via Task | No 1:1 rule equivalent. Claude Code discovers skills by frontmatter `description`. Persona is dispatched explicitly via Task, not auto-activated. |
| `github-secret-scanning.mdc` | PreToolUse-style gate: before commits, pushes, file writes touching credential paths, invoke GitHub MCP `secret_protection` toolset | Use a `PreToolUse` hook in `.claude/settings.json` matching `Bash` + `git commit`/`git push` patterns, calling the same MCP tool. **Not implemented in this refactor** — documented for follow-up. | The MCP server is already registered in `.mcp.json` as `catalyst-github-secret-scanning`. Tooling exists; only the trigger needs porting. |
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

# 2. Regenerate per-tool stubs
python scripts/sync_tool_skills.py

# 3. Verify CI will be happy
python scripts/sync_tool_skills.py --check  # exits 0

# 4. Stage and commit canonical + both stubs
git add skills/my-new-skill/ .claude/skills/my-new-skill/ .cursor/skills/my-new-skill/
git commit -m "feat(skill): add my-new-skill (#issue-number)"
```

## Adding a new persona (runbook)

```bash
# 1. Author canonical persona body
$EDITOR agents/my-new-persona.md

# 2. Add an entry to the PERSONAS dict in scripts/build_claude_agent_adapters.py
#    (description, model, tools)

# 3. Rebuild the Claude adapter
python scripts/build_claude_agent_adapters.py

# 4. Regenerate the Cursor stub
python scripts/sync_tool_skills.py

# 5. Stage and commit
git add agents/ .claude/agents/ .cursor/agents/ scripts/build_claude_agent_adapters.py
git commit -m "feat(agent): add my-new-persona (#issue-number)"
```

## CI guard

`.github/workflows/multi-tool-sync.yml` runs on every PR to `release` and fails if:

- A canonical skill is missing its `.claude/skills/<name>/SKILL.md` or `.cursor/skills/<name>/SKILL.md` stub
- A canonical persona is missing its `.claude/agents/<name>.md` adapter
- Any stub content has drifted from its canonical source (delegates to `scripts/sync_tool_skills.py --check`)

## Adding an MCP server (runbook)

```bash
# 1. Add or extend the server script under skills/<name>/
# 2. Register in the canonical manifest (Cursor-only HTTP servers: add name to cursorOnly)
$EDITOR platform/mcp.servers.json

# 3. Regenerate client configs
python platform/bootstrap.py

# 4. Verify
python platform/bootstrap.py --check
```

The `catalyst-github-secret-scanning` HTTP server stays Cursor-only (`cursorOnly` in the manifest) so `${env:GITHUB_MCP_PAT}` is not required in Claude/Gemini configs.

## Related

- ADR-022 — Canonical `skills/` and `agents/` layout
- ADR-024 — Unified agent config, bootstrap, and `platform/mcp.servers.json`
- ADR-011 — Catalyst agentic workflow (the operating contract that this layout serves)
