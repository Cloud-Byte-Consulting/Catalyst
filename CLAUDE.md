# CLAUDE.md

Catalyst execution guardrails:

- Treat `AGENTS.md` as the operating contract for issue execution and verification gates.
- Follow ADR-006 through ADR-010 for CI/CD, golden paths, RBAC, runtime, and egress controls.
- Use GitHub OIDC roles for all AWS automation; never use long-lived AWS keys.
- Keep issue and PR artifacts in Context/Scope/Gherkin shape.
- **Docs / diagrams currency** — before every `gh pr create` (and before pushing any scope-expanding commit), ask explicitly: *"does this change need new or updated documentation (`README.md`, `DECISIONS.md`, `docs/ADR/`, `docs/onboarding/`, `docs/demo-script.md`, `docs/ai-workflow-narrative.md`) or diagrams (`diagrams/`, `.drawio` assets, inline mermaid in `docs/`)?"* Record the yes/no answer in the PR body or Decision Log; silence is a refusal trigger per the AGENTS.md PR-open contract. The canonical workflow + decision rubric live in `skills/pr-open-contract/SKILL.md`. The default position is "no change required" — but reach it deliberately, not by omission.

Registered MCP servers:

1. GitHub MCP server
2. AWS MCP server
3. Context7 MCP server
4. Sequential Thinking MCP server
