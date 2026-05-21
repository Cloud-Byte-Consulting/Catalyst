# Platform agent wiring

One-page map for ADR-024 bootstrap and MCP manifest. Full onboarding: [`docs/AGENT-GETTING-STARTED.md`](../docs/AGENT-GETTING-STARTED.md).

## `bootstrap.py`

Wires canonical `skills/` and `agents/` into per-tool trees and emits MCP client configs.

```bash
python platform/bootstrap.py          # wire after clone or canonical changes
python platform/bootstrap.py --check  # verify (CI uses this; exit 1 on drift)
python platform/bootstrap.py --copy   # force copy mode (Windows / no symlinks)
```

- **Unix**: symlinks from `.cursor/`, `.claude/`, `.gemini/` into canonical paths
- **Windows / `--copy`**: recursive copies with the same layout
- **Never overwrites**: `.claude/agents/rlm-subcall.md` (Claude-only subagent)

## `mcp.servers.json`

Single MCP registry for all tools. Edit here; bootstrap generates:

| Tool | Output |
|---|---|
| Cursor | `.cursor/mcp.json` |
| Claude Code | `.mcp.json` |
| Gemini CLI | `.gemini/settings.json` (MCP section) |

HTTP-only servers (e.g. GitHub secret scanning) can be marked `cursorOnly` so Claude/Gemini configs stay lean.

## `personas.meta.yaml`

Optional Claude dispatch overlay (`model`, `tools`, `description`) for thin `.claude/agents/` adapters. Canonical persona bodies live in `agents/<name>.md`.

## Related

- [ADR-024](../docs/ADR/ADR-024-unified-agent-config-and-issue-indexing.md)
- [Multi-tool config](../docs/multi-tool-config.md)
