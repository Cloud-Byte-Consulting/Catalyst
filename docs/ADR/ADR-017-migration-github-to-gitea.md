# ADR-017 — Migration from GitHub to self-hosted Gitea

**Status**: Proposed (placeholder) · 2026-05-18

> **Placeholder — design sessions required before Accepted.** GitHub remains the **current source of truth** for Catalyst code, issues, Projects v2, and CI/CD. This ADR records a **future migration track**, not an in-flight cutover.

**Related**: [ADR-001](ADR-001-github-issues-as-state-machine.md) · [ADR-006](ADR-006-cicd-pipeline-architecture.md) · [ADR-011](ADR-011-catalyst-agentic-workflow.md) · [ADR-013](ADR-013-guided-milestone-orchestration.md) · [ADR-016](ADR-016-catalyst-homelab-deployment.md) · [`docs/worklog/2026-05-13-migration-to-github.md`](../worklog/2026-05-13-migration-to-github.md)

---

## Context

Catalyst **migrated from self-hosted Gitea to GitHub** in May 2026 because Gitea’s project-board column automation was blocked (404 on column-move API) while GitHub Projects v2 and GraphQL met the issue-as-state-machine requirements ([`docs/worklog/2026-05-13-migration-to-github.md`](../worklog/2026-05-13-migration-to-github.md)). The prior Gitea instance lived on homelab infrastructure (TrueNAS SCALE; remote preserved as `gitea-origin`).

The platform owner now wants a **documented option** to host the canonical repo (or a mirror with eventual cutover) on a **Gitea homelab** instance again — often **co-located** with homelab runtime ([ADR-016](ADR-016-catalyst-homelab-deployment.md)).

This ADR captures **migration as a future workstream**, summarises phased work from planning conversations, and lists what breaks vs what ports — without committing to cutover date or full design.

---

## Decision

**TBD (placeholder).** Documented intent:

- A **return path to Gitea** (or dual-host hybrid) is a recognised future track, **subordinate** to current GitHub canonical status until Accepted.
- Migration will be executed in **phased workstreams** (below); no phase is authorised by this placeholder alone.
- Any cutover must re-validate [ADR-001](ADR-001-github-issues-as-state-machine.md) state-machine automation on the target forge or accept manual/board gaps.

---

## Migration workstreams (planning summary)

| Phase | Focus | Notes |
|---|---|---|
| **Phase 1 — Git mirror** | Push/mirror `release` (and tags) to Gitea; `origin` strategy TBD (GitHub canonical vs Gitea) | `gitea-origin` remote already exists from prior migration |
| **Phase 2 — Issues & labels** | Export/import or recreate issues; label taxonomy; cross-reference numbering | Prior migration embedded Gitea metadata in comment headers — pattern may reverse |
| **Phase 3 — CI/CD re-platform** | Replace or duplicate GitHub Actions; **rewrite AWS OIDC trust** (`sub`, `aud`, repo slug) for Gitea-hosted workflows | [ADR-006](ADR-006-cicd-pipeline-architecture.md) assumes `github.com` JWT subjects today |
| **Phase 4 — Agent tooling** | `gh` → `tea` / Gitea API; project board equivalent; MCP or adapter per ADR-001 multi-host gap | [ADR-011](ADR-011-catalyst-agentic-workflow.md), [ADR-013](ADR-013-guided-milestone-orchestration.md) |
| **Phase 5 — Cutover** | Flip canonical remote, archive GitHub or mirror-only, update docs/onboarding | Requires rollback runbook |

Dependencies: Phase 3–5 are blocked on forge + runner topology; homelab Gitea often shares network with [ADR-016](ADR-016-catalyst-homelab-deployment.md) Phase 0–1.

---

## What breaks (GitHub-specific)

| Capability | Impact on Gitea track |
|---|---|
| **GitHub Copilot / Bugbot** | Not available on Gitea; agent assistance relies on Cursor/local models |
| **GitHub Projects v2 (GraphQL)** | No drop-in; need Gitea Projects, external board, or issue-label-only workflow |
| **GitHub Actions OIDC → AWS** | Trust policies must list Gitea issuer, repo, ref subjects — new roles or duplicated trusts |
| **Secret scanning / GitHub Advanced Security** | Not ported; homelab policy TBD |
| **GitHub MCP / `gh` automation** | Agents lose default tooling unless Gitea MCP or REST adapter ships (see ADR-001 § Known gaps) |
| **Issue/PR integrations** | Branch protection, required checks, merge queues — map to Gitea equivalents |

---

## What ports (low friction)

| Asset | Notes |
|---|---|
| **Git history** | Already migrated GitHub ← Gitea once; reverse is mechanical with mirror |
| **`.cursor/` agents, rules, skills** | Repo-local; work on any host if API endpoints configured |
| **Terraform / application code** | Forge-agnostic; CI secrets and OIDC are not |
| **ADR and docs** | Update URLs and “canonical forge” statements on cutover |

---

## Alternatives considered

| Alternative | When it fits |
|---|---|
| **Stay on GitHub (status quo)** | Simplest; keeps Copilot, Projects v2, OIDC as documented |
| **Mirror-only Gitea** | Read replica / backup; GitHub remains canonical — low risk |
| **Hybrid** | Issues on GitHub, git on Gitea (or vice versa) — high agent confusion; needs strict ADR-001 backend config |
| **Full cutover to Gitea** | Owner homelab sovereignty; pays migration tax in Phases 2–5 |

No alternative is selected in this placeholder.

---

## Consequences

- **Positive:** Sovereignty, co-location with homelab API ([ADR-016](ADR-016-catalyst-homelab-deployment.md)), no GitHub org dependency for air-gapped labs.
- **Positive:** Reuses prior operational knowledge (TrueNAS Gitea URL, `gitea-origin` remote).
- **Cost:** Rebuild CI/CD and IAM trust; re-test entire [ADR-006](ADR-006-cicd-pipeline-architecture.md) matrix.
- **Cost:** Agent and milestone flows ([ADR-013](ADR-013-guided-milestone-orchestration.md)) need re-validation or scope reduction on Gitea.
- **Risk:** Reintroducing the **project board 404** class of failures — must be spike-tested before Phase 5.

---

## Related

- [ADR-001](ADR-001-github-issues-as-state-machine.md) — GitHub-centric today; Gitea multi-host gap documented
- [ADR-006](ADR-006-cicd-pipeline-architecture.md) — OIDC workflows
- [ADR-011](ADR-011-catalyst-agentic-workflow.md) — six-gate agent contract
- [ADR-013](ADR-013-guided-milestone-orchestration.md) — Andon / Projects dependency
- [ADR-016](ADR-016-catalyst-homelab-deployment.md) — homelab co-deployment
- [`docs/worklog/2026-05-13-migration-to-github.md`](../worklog/2026-05-13-migration-to-github.md) — prior Gitea → GitHub migration log
