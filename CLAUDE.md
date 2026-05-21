# CLAUDE.md

Catalyst execution guardrails:

- Treat `AGENTS.md` as the operating contract for issue execution and verification gates.
- Follow ADR-006 through ADR-010 for CI/CD, golden paths, RBAC, runtime, and egress controls.
- Use GitHub OIDC roles for all AWS automation; never use long-lived AWS keys.
- Keep issue and PR artifacts in Context/Scope/Gherkin shape.

**Getting started:** [`docs/AGENT-GETTING-STARTED.md`](docs/AGENT-GETTING-STARTED.md) · **Per-tool config:** [`docs/multi-tool-config.md`](docs/multi-tool-config.md)

Registered MCP servers:

1. GitHub MCP server
2. AWS MCP server
3. Context7 MCP server
4. Sequential Thinking MCP server

After clone or when `skills/` / `agents/` change, run `python platform/bootstrap.py` to wire `skills/` and `.claude/agents/` to canonical paths (ADR-024). Use `python platform/bootstrap.py --check` to verify.
