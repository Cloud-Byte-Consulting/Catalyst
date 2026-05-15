# Catalyst

Catalyst is an Internal Developer Platform control plane for AWS. This repository contains deployable infrastructure modules, a FastAPI control-plane service, CI/CD workflows, and interface artifacts (CLI + GitHub Action).

## Repository layout

- `infrastructure/`: Terraform modules and tests for backend, network, IAM, runtime, and security controls.
- `services/catalyst-api/`: FastAPI service implementing Tier 1/Tier 2 golden paths plus product catalog and inventory endpoints.
- `clients/catalyst-cli/`: Knack-based CLI for invoking Catalyst API endpoints.
- `.github/workflows/`: CI/CD pipelines for quality checks, plan/apply, runtime deploy, drift detection, and policy validation.
- `docs/ADR/`: Accepted architectural decisions.
- `diagrams/`: Architecture source and rendered artifacts.

## Deploy

1. Configure AWS auth through GitHub OIDC roles (`catalyst-github-plan`, `catalyst-github-apply`, `catalyst-github-deploy`).
2. Bootstrap backend and validate Terraform:

```bash
terraform -chdir=infrastructure init -backend=false
terraform -chdir=infrastructure fmt -recursive
terraform -chdir=infrastructure validate
```

3. Apply the stack:

```bash
terraform -chdir=infrastructure apply
```

4. Run API locally:

```bash
pip install -r services/catalyst-api/requirements.txt
uvicorn catalyst.main:app --app-dir services/catalyst-api --reload
```

5. Run tests:

```bash
pytest services/catalyst-api/tests --cov=services/catalyst-api/catalyst --cov-branch --cov-fail-under=85
```

## Runtime strategy

`service-cd.yml` supports runtime selection via `RUNTIME=lambda|ecs` (default `lambda`), aligned with ADR-009.

## RBAC scoped group format

Scoped RBAC groups use `catalyst-{tenant}--{project}--{role}` to avoid tenant/project
parsing ambiguity. Migration notes and backward-compatibility behavior are documented in
`docs/migrations/2026-05-15-rbac-scoped-group-delimiter.md`.

## Decision records

Use `DECISIONS.md` as a pointer to canonical ADRs in `docs/ADR/`.
