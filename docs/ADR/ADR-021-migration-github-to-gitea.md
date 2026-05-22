# ADR-021 — Hybrid forge: Gitea primary git, GitHub mirror + issue host

**Status**: Accepted · 2026-05-21

**Related**: [ADR-001](ADR-001-github-issues-as-state-machine.md) · [ADR-006](ADR-006-cicd-pipeline-architecture.md) · [ADR-011](ADR-011-catalyst-agentic-workflow.md) · [ADR-013](ADR-013-guided-milestone-orchestration.md) · [ADR-020](ADR-020-catalyst-homelab-deployment.md) · [`docs/gitea/`](../gitea/README.md) · [`docs/worklog/2026-05-13-migration-to-github.md`](../worklog/2026-05-13-migration-to-github.md)

---

## Context

Catalyst **migrated from self-hosted Gitea to GitHub** in May 2026 because Gitea’s project-board column automation was blocked (404 on column-move API) while GitHub Projects v2 and GraphQL met the issue-as-state-machine requirements ([`docs/worklog/2026-05-13-migration-to-github.md`](../worklog/2026-05-13-migration-to-github.md)). The prior Gitea instance lived on **TrueNAS SCALE** (legacy LAN `http://100.115.245.62:30008`, org slug typo `Cloud-Byte-Consultling`; MagicDNS hostname `truenas-scale-1` per worklog). Hybrid cutover re-establishes **Gitea on the same TrueNAS host** with **Tailscale already co-installed**: Gitea as a SCALE app (NodePort, e.g. `30008`), tailnet HTTPS via **Tailscale Serve on the NAS** (no sidecar), NodePort not exposed to WAN — see [`docs/gitea/tailscale-exposure.md`](../gitea/tailscale-exposure.md).

The platform owner now accepts a **hybrid forge model**: canonical git on homelab Gitea, GitHub as a **read mirror** for visibility and **permanent issue/Projects host**. This preserves [ADR-001](ADR-001-github-issues-as-state-machine.md) automation without reintroducing Gitea project-board gaps.

Operator runbooks: [`docs/gitea/README.md`](../gitea/README.md) · mirror · workflows · Tailscale exposure.

---

## Decision

**Accepted hybrid architecture:**

| Surface | Host | Notes |
|---|---|---|
| **Git (canonical)** | **Gitea** (homelab) | Developers clone, branch, and push to Gitea |
| **Git (mirror)** | **GitHub** (`Cloud-Byte-Consulting/Catalyst`) | Read-only mirror of `release` branch + tags; updated from Gitea |
| **Issues, Projects v2, agent `gh` / GitHub MCP** | **GitHub** | Permanent; Phase 2 issue migration **not planned** |
| **CI/CD — non-AWS** | **Gitea Actions** | Port per [`docs/gitea/workflow-migration.md`](../gitea/workflow-migration.md) |
| **CI/CD — AWS OIDC** | **GitHub Actions** (on mirror) | Until Gitea OIDC trust is designed and IAM roles updated ([ADR-006](ADR-006-cicd-pipeline-architecture.md)) |
| **Gitea reachability** | **TrueNAS SCALE** + **Tailscale Serve** on same host (tailnet-only) | Gitea Apps chart (NodePort → `127.0.0.1`); Serve → MagicDNS HTTPS; no WAN port-forward; see [`docs/gitea/`](../gitea/README.md) |

**Git remote naming (canonical for new clones):**

| Remote | Target | Purpose |
|---|---|---|
| `origin` | Gitea repo URL | Day-to-day fetch/push |
| `github` | `https://github.com/Cloud-Byte-Consulting/Catalyst.git` | Mirror push target (operators/automation only) |

Legacy clones from the May 2026 GitHub-canonical period may still have `gitea-origin` pointing at the old Gitea URL — rename or re-clone per [`docs/gitea/mirror-setup.md`](../gitea/mirror-setup.md).

**Issue references stay GitHub-native:** use `Closes #N`, `Fixes #243`, etc. in commit messages and PR bodies even when branches live on Gitea.

---

## Migration workstreams (revised)

| Phase | Focus | Status |
|---|---|---|
| **Phase 1 — Git mirror (reversed)** | Push from **Gitea → GitHub**; mirror `release` + tags; configure remotes (`origin` = Gitea, `github` = mirror) | **In progress** — tracked [#246](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/246) |
| **Phase 2 — Issues & labels** | Export/import or recreate on Gitea | **Deferred / not planned** — GitHub remains permanent issue host per owner decision |
| **Phase 3 — CI/CD re-platform (split)** | Non-AWS workflows → Gitea Actions; AWS/OIDC workflows (`terraform`, `tf-drift`, `service-cd`, `teardown*`, optional OIDC in `bootstrap-smoke` / `ci-smoke`) **stay on GitHub** until Gitea JWT issuer + `sub`/`aud` trust designed | **Partial** — Phase 1b ports “migrate now” tier; OIDC blocked |
| **Phase 4 — Agent tooling** | `gh` → `tea` for issues | **Out of scope** — issues stay on GitHub; `gh` / GitHub MCP unchanged |
| **Phase 5 — Full cutover / archive GitHub** | Flip all surfaces to Gitea-only | **Deferred indefinitely** — hybrid is the steady state for git+CI split |

Dependencies: Phase 3 AWS half blocked on IAM OIDC redesign; homelab Gitea co-locates with [ADR-020](ADR-020-catalyst-homelab-deployment.md) Phase 0–1 on **TrueNAS SCALE** (Gitea + Tailscale apps, persistent volume for repo data, push mirror to GitHub). GitOps webhooks → Flux tracked separately ([#243](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/243)); webhook URLs must use Gitea `ROOT_URL` on MagicDNS after Serve is configured.

---

## What breaks (GitHub-specific) — mitigated by hybrid

| Capability | Hybrid mitigation |
|---|---|
| **GitHub Projects v2 (GraphQL)** | Unchanged — issues stay on GitHub |
| **GitHub MCP / `gh` automation** | Unchanged for issues/PRs on GitHub mirror |
| **GitHub Actions OIDC → AWS** | AWS workflows run on GitHub mirror until Gitea trust exists |
| **GitHub Copilot / Bugbot** | Available on GitHub mirror PRs; Gitea-native PRs use Cursor/local models |
| **Secret scanning / GHAS** | Runs on GitHub mirror; Gitea-side policy TBD |

---

## What ports (low friction)

| Asset | Notes |
|---|---|
| **Git history** | Already migrated Gitea → GitHub once; reverse mirror is mechanical |
| **`.cursor/` agents, rules, skills** | Repo-local; work on any host if API endpoints configured |
| **Non-AWS CI** | `pr-checks`, `validate-policies`, `multi-tool-sync`, `full-suite`, bootstrap script job — see workflow matrix |
| **Terraform / application code** | Forge-agnostic; OIDC secrets and trust policies are not |

---

## Alternatives considered

| Alternative | Outcome |
|---|---|
| **Stay on GitHub (status quo)** | Rejected for git — owner wants homelab sovereignty for canonical repo |
| **Mirror-only Gitea (GitHub canonical)** | Superseded — Gitea is now git canonical |
| **Full cutover to Gitea** | Rejected for issues — Gitea project board 404 class remains; GitHub Projects v2 retained |
| **Hybrid (accepted)** | Git + non-AWS CI on Gitea; issues + AWS CI on GitHub mirror |

---

## Consequences

- **Positive:** Homelab git sovereignty; co-location with homelab API ([ADR-020](ADR-020-catalyst-homelab-deployment.md)); GitHub issue automation unchanged.
- **Positive:** AWS CI continues on proven GitHub OIDC path until Gitea trust is designed.
- **Cost:** Dual-host mental model — developers must know `origin` vs `github`; agents must not open issues on Gitea.
- **Cost:** Mirror lag between Gitea push and GitHub AWS workflow trigger — monitor mirror health.
- **Risk:** Stale GitHub mirror blocks AWS deploys — alert on mirror failures.

---

## Related

- [`docs/gitea/`](../gitea/README.md) — operator docs (mirror, workflows, Tailscale)
- [ADR-001](ADR-001-github-issues-as-state-machine.md) — GitHub issue host; Gitea issue backend deferred
- [ADR-006](ADR-006-cicd-pipeline-architecture.md) — OIDC workflows on GitHub mirror
- [ADR-020](ADR-020-catalyst-homelab-deployment.md) — homelab co-deployment
- [`docs/worklog/2026-05-13-migration-to-github.md`](../worklog/2026-05-13-migration-to-github.md) — prior Gitea → GitHub migration log
- [#246](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/246) — Gitea deploy + mirror execution
- [#243](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/243) — Flux bootstrap / GitOps webhooks
