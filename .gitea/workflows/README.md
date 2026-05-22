# Gitea Actions workflows

Workflows for the hybrid forge model ([ADR-021](../../docs/ADR/ADR-021-migration-github-to-gitea.md)) are ported here incrementally.

**Migration matrix:** [`docs/gitea/workflow-migration.md`](../../docs/gitea/workflow-migration.md)

## Status

| Workflow | Status |
|---|---|
| `validate-policies.yml` | Not yet ported |
| `multi-tool-sync.yml` | Not yet ported |
| `pr-checks.yml` | Not yet ported |
| `full-suite.yml` | Not yet ported |
| `bootstrap-smoke.yml` (non-AWS jobs) | Not yet ported |

AWS OIDC workflows remain in [`.github/workflows/`](../../.github/workflows/) and run on the GitHub mirror.

## Prerequisites

- Gitea Actions enabled on the homelab instance
- Registered runner (`ubuntu-latest` or equivalent)
- Tailnet access to Gitea — see [`docs/gitea/tailscale-exposure.md`](../../docs/gitea/tailscale-exposure.md)
