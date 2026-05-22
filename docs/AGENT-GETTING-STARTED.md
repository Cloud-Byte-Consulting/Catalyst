# Agent getting started

Unified onboarding for coding agents working in Catalyst across **Cursor**, **Claude Code**, and **Gemini CLI**. For AWS platform onboarding (accounts, Terraform, deploy), use the audience tracks in [`docs/onboarding/`](./onboarding/README.md) instead.

## 1. Clone and bootstrap

**Hybrid forge ([ADR-021](./ADR/ADR-021-migration-github-to-gitea.md)):** canonical git is on **Gitea**; GitHub is a read mirror + issue host. See [`docs/gitea/`](./gitea/README.md) for URLs, remotes, and Tailscale access.

```bash
# Preferred: clone from Gitea (Tailscale Serve URL or operator-provided endpoint)
git clone <gitea-clone-url>
cd Catalyst
git remote add github https://github.com/Cloud-Byte-Consulting/Catalyst.git  # mirror reference
git checkout release
python platform/bootstrap.py
python platform/bootstrap.py --check   # verify tool trees match canonical paths
```

GitHub-only clone (read/mirror; issues and AWS CI still use GitHub):

```bash
git clone https://github.com/Cloud-Byte-Consulting/Catalyst.git
```

**What bootstrap does** ([ADR-024](./ADR/ADR-024-unified-agent-config-and-issue-indexing.md)):

- Wires `.cursor/skills/`, `.claude/skills/`, and `.gemini/skills/` to canonical `skills/`
- Wires `.cursor/agents/`, `.claude/agents/`, and `.gemini/agents/` to canonical `agents/`
- Generates MCP client configs from `platform/mcp.servers.json`
- Uses symlinks on macOS/Linux; copies on Windows or with `--copy`

Re-run bootstrap after `git pull` when `skills/` or `agents/` change. See [`platform/README.md`](../platform/README.md) for the platform directory map.

## 2. Pick your IDE

| IDE | Entry file | MCP config | Notes |
|---|---|---|---|
| **Cursor** | [`AGENTS.md`](../AGENTS.md) | `.cursor/mcp.json` (generated) | Cursor-only rules in `.cursor/rules/*.mdc`; hooks in `.cursor/hooks/` |
| **Claude Code** | [`CLAUDE.md`](../CLAUDE.md) + [`AGENTS.md`](../AGENTS.md) | `.mcp.json` (generated) | Thin Claude adapters under `.claude/agents/` from `platform/personas.meta.yaml` |
| **Gemini CLI** | [`GEMINI.md`](../GEMINI.md) + [`AGENTS.md`](../AGENTS.md) | `.gemini/settings.json` (generated) | Same canonical skills/agents as Cursor and Claude |

Per-tool details, runbooks for adding skills/personas/MCP servers, and Cursor-rule analogues: [`docs/multi-tool-config.md`](./multi-tool-config.md).

## 3. Operating contract (`AGENTS.md`)

[`AGENTS.md`](../AGENTS.md) is the shared execution contract for all tools:

- GitHub Issues as durable state machine ([ADR-001](./ADR/ADR-001-github-issues-as-state-machine.md))
- Gherkin acceptance criteria and structured issue comments ([issue-execution workflow](./issue-execution-gherkin-workflow-2026-05-13.md))
- Pre-PR peer review and PR-open contract (`Closes #N` + Catalyst Progress project)
- RLM workflow for artifacts over ~50k characters ([ADR-004](./ADR/ADR-004-rlm-for-long-context-agent-tasks.md))
- AWS work via GitHub OIDC only ([ADR-005](./ADR/ADR-005-aws-agentic-platform-engineering.md))

Read `AGENTS.md` before executing tracked work.

## 4. Issue context and persona routing

When working from a GitHub issue or free-form task:

1. **Export issue context** — `skills/catalyst-issue-context/`:
   ```bash
   python3 scripts/catalyst-issue-context.py --issue <N>
   python3 scripts/catalyst-issue-context.py --kind iac --state agent-working
   python3 scripts/catalyst-ask.py "Terraform module fails Checkov"
   ```
   Registry: `registry/catalyst-domains.yaml`.

2. **Route to the right persona** — `skills/catalyst-agent-routing/`:
   - Read the routing table in `skills/catalyst-agent-routing/SKILL.md`
   - Load the matching file from `agents/<name>.md` before composing answers
   - For cross-cutting work, chain personas (architect → terraform → security/CI)

3. **Follow state-machine labels** — legal transitions and label vocabulary: [`docs/ADR/STATE-MACHINE.md`](./ADR/STATE-MACHINE.md).

## 5. Typical session flow

```text
Pick issue (#N) or task
  → catalyst-issue-context.py (labels, Gherkin AC, handoff comments)
  → catalyst-agent-routing (pick agents/<persona>.md)
  → Implement against Gherkin AC
  → Pre-PR peer review (AGENTS.md gate)
  → gh pr create with Closes #N + project assignment
  → Structured handoff comment on the issue
```

## Related

- [ADR-024 — Unified agent config and issue indexing](./ADR/ADR-024-unified-agent-config-and-issue-indexing.md)
- [ADR-022 — Canonical skills/agents layout](./ADR/ADR-022-multi-tool-skill-layout.md) (delivery superseded by bootstrap; paths unchanged)
- [Multi-tool config](./multi-tool-config.md)
- [AI workflow narrative](./ai-workflow-narrative.md) — evidence of the AGENTS.md contract in practice
