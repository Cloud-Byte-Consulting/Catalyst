# Checkov reference — paths and docs

## Local clone (optional)

After `git clone … local/research/checkov`:

| Topic | Path under `local/research/checkov/` |
|-------|--------------------------------------|
| Quick start | `docs/1.Welcome/Quick Start.md` |
| Terraform plan | `docs/7.Scan Examples/Terraform Plan Scanning.md` |
| Dockerfile | `docs/7.Scan Examples/Dockerfile.md` |
| SCA (packages / images) | `docs/7.Scan Examples/Sca.md` |
| Suppressions | `docs/2.Basics/Suppressing and Skipping Policies.md` |
| Custom Python policies | `docs/3.Custom Policies/Overview.md` (and `checkov/` package layout) |

## Catalyst repo

| Artifact | Path |
|----------|------|
| Checkov config | `.checkov.yaml` (repo root) |
| Custom checks | `infrastructure/policies/checkov/*.py` |
| OPA (sibling gate) | `infrastructure/policies/opa/terraform.rego` |
| DevSecOps ladder | `.cursor/skills/devsecops-integration/SKILL.md` |

## Docker image for CI

```bash
docker pull bridgecrew/checkov
docker run --rm -v "$PWD:/work" -w /work bridgecrew/checkov \
  --directory infrastructure --framework terraform --compact
```

Remove `-t` when piping to files to avoid control characters in SARIF/JUnit.
