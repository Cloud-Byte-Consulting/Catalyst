# Gitea Actions workflows

Workflows for the hybrid forge model ([ADR-021](../../docs/ADR/ADR-021-migration-github-to-gitea.md)).

**Migration matrix:** [`docs/gitea/workflow-migration.md`](../../docs/gitea/workflow-migration.md)

## Status

| Workflow | Status |
|---|---|
| `validate-policies.yaml` | Ported ([#338](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/338)) |
| `multi-tool-sync.yaml` | Ported |
| `pr-checks.yaml` | Ported |
| `full-suite.yaml` | Ported |
| `bootstrap-smoke.yaml` | Ported (script jobs only; AWS validation on GitHub) |

AWS OIDC workflows remain in [`.github/workflows/`](../../.github/workflows/) and run on the GitHub mirror.

## Prerequisites

- Gitea Actions enabled on the homelab instance
- Registered runner (`ubuntu-latest` or equivalent)
- Tailnet access to Gitea — see [`docs/gitea/tailscale-exposure.md`](../../docs/gitea/tailscale-exposure.md)
- Operator cutover: [`docs/gitea/operator-cutover-checklist.md`](../../docs/gitea/operator-cutover-checklist.md)

## Local validation

```bash
pip install pyyaml pytest
python .github/scripts/validate_workflows.py
pytest .github/scripts/test_workflow_structure.py -v
```

Extending the structural validator to scan `.gitea/workflows/` is a follow-up if needed.
