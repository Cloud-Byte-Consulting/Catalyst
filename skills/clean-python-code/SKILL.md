---
name: clean-python-code
description: >-
  Maintainable Python for Catalyst: tooling discipline, idiomatic patterns,
  separation of concerns, SOLID boundaries, thin decorators, pragmatic use of
  advanced features, async-safe iteration, test-driven refactoring, and
  layering so routers/handlers stay thin. Use when writing or reviewing Python in
  services/, refactoring for clarity, or grounding style reviews in explicit
  criteria.
---
<!-- Vendored from: platform-catalyst/skills/clean-python-code/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Clean Python (maintainability)

## Role

You apply **maintainable Python** discipline consistent with Catalyst's `AGENTS.md` (ruff, mypy --strict, async-first, structlog, httpx). This skill adds **structure and review criteria** for readability and testability; it does not relax security, typing, or IAM rules.

## Topic map (Catalyst use)

| Area | Apply in Catalyst |
|------|---------------------|
| Tooling and docs | ruff + mypy --strict; docstrings on **public** APIs only per `AGENTS.md`. |
| Idiomatic Python | Context managers for resources; idiomatic iteration; async-first I/O. |
| Design traits | Narrow signatures; contracts via pydantic; prefer composition over deep inheritance for domain rules. |
| SOLID | Single-purpose modules; inject dependencies (`Depends`, factories for AWS clients); stable abstractions at boundaries. |
| Decorators | Cross-cutting concerns (logging, tracing, retries) stay thin and testable—Powertools patterns for Lambda. |
| Descriptors | Rare in app code; default to pydantic fields instead of custom descriptors unless there is a clear win. |
| Generators and async | Stream large collections; async generators where appropriate; never block the event loop. |
| Tests and refactor | Tests enable refactor; design for testability at I/O seams—pair with `@python-cli-and-testing`. |
| Patterns | Prefer clarity over ceremony; use patterns when they reduce coupling, not for their own sake. |
| Layering | Domain/application vs infrastructure: keep FastAPI routers and Lambda handlers thin; core logic testable without I/O. |

## Instructions

1. **Names reveal intent** — functions and modules do what their names say; avoid opaque abbreviations.
2. **Small surfaces** — public API minimal; helpers private (`_`); one-line summaries on public callables per `AGENTS.md`.
3. **Fail with useful signals** — structured errors (`detail`, `code`, `trace_id`); log context, never secrets.
4. **Dependency direction** — infrastructure depends on application ports, not the reverse; aligns with ports/adapters in `@python-cli-and-testing` / hexagonal patterns.
5. **Refactor behind tests** — behavior change + tests in the same PR when possible.

## Output

- For **reviews**: checklist on readability, separation of concerns, contracts, and testability.
- For **new code**: propose module boundaries and dependencies before line-level edits.
- Prefer **repo** sources of truth (`AGENTS.md`, `docs/research/platform-catalyst-agents-evaluation.md`) over generic style advice when they conflict.

## Guardrails

- Do not weaken type safety or security gates to chase shorter code.
