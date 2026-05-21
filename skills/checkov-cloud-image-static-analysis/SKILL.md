---
name: checkov-cloud-image-static-analysis
description: >-
  Designs Checkov-based static analysis for Terraform/OpenTofu IaC and
  Dockerfile/container hardening in Catalyst. Covers directory and plan scans,
  framework flags, SARIF/CI gates, custom Python checks, suppressions, and how
  Checkov SCA for images relates to Prisma Cloud. Use when configuring Checkov,
  writing `.checkov.yaml`, extending `infrastructure/policies/checkov/`, or
  pairing IaC + Dockerfile + image CVE strategy with Trivy/Grype.
---

<!-- Vendored from: platform-catalyst/skills/checkov-cloud-image-static-analysis/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Checkov — cloud IaC and container static analysis (Catalyst)

## Upstream source (local clone)

Clone [bridgecrewio/checkov](https://github.com/bridgecrewio/checkov) next to skills for deep reference (gitignored):

```bash
git clone --depth 1 https://github.com/bridgecrewio/checkov local/research/checkov
```

Use that tree for policy class names, runner behavior, and doc paths under `docs/`. Official docs: [checkov.io](https://www.checkov.io/1.Welcome/What%20is%20Checkov.html).

## Role in Catalyst

- **Cloud / IaC:** Terraform under `infrastructure/` — graph-aware checks, optional **plan JSON** scan for effective configuration.
- **Image build static analysis:** **Dockerfile** policies (`CKV_DOCKER_*`) — non-root, no `:latest`, healthcheck, dangerous `EXPOSE`, etc. Aligns with `AGENTS.md` / `@container-hardening`.
- **Image CVEs (runtime packages in layers):** Checkov’s **SCA** path for packages/images is documented around Prisma Cloud API keys. For **keyless CI**, keep **Trivy/Grype** (see `@devsecops-integration`) as the primary image CVE gate; use Checkov Dockerfile + IaC where it does not need a vendor token.

## Commands (design defaults)

**Terraform / OpenTofu (HCL on disk)**

```bash
checkov --directory infrastructure --framework terraform \
  --download-external-modules false \
  --compact
```

**Terraform plan (JSON)**

```bash
terraform -chdir=infrastructure/environments/dev plan -out=tfplan
terraform -chdir=infrastructure/environments/dev show -json tfplan | jq '.' > tfplan.json
checkov --file tfplan.json \
  --repo-root-for-plan-enrichment "$(pwd)/infrastructure"
```

Plan-only findings often report line `0` without `jq` or enrichment; prefer `jq` + `--repo-root-for-plan-enrichment` for PR-friendly output.

**Dockerfile only**

```bash
checkov --directory services --framework dockerfile --compact
```

**CI outputs**

- `--output sarif` — upload to GitHub Code Scanning or similar.
- `--output cli` + `--compact` — short human logs in Actions.

**Gradual adoption**

- `--soft-fail` — report failures without non-zero exit (use sparingly; prefer baselines).
- `--create-baseline .checkov.baseline` / `--baseline .checkov.baseline` — suppress known backlog without inline `skip` sprawl.

**Scope control**

- `--check CKV_AWS_123,CKV_AWS_456` — allow list.
- `--skip-check CKV_AWS_*` — deny patterns (avoid blanket skips that hide new checks).

## Custom policies (repo)

Catalyst already ships Python custom checks under `infrastructure/policies/checkov/` (e.g. wildcard IAM, explicit S3 encryption). When adding checks:

- Follow Checkov’s **BaseCheck** / resource-type pattern from upstream `checkov/terraform/checks/`.
- Add **Checkov + native `.tftest.hcl`** coverage where the rule maps to module outputs (see `@terraform-native-tests`).

## Suppressions

Prefer **fix the code** (`AGENTS.md`). When a finding is accepted:

- Inline comment suppressions per [Suppressing and Skipping Policies](https://github.com/bridgecrewio/checkov/blob/main/docs/2.Basics/Suppressing%20and%20Skipping%20Policies.md) — tie each to an ADR or ticket id in the comment body.

## `.checkov.yaml` (repo root)

Keep one canonical config: frameworks list, skip paths (`**/samples/**`, `**/.terraform/**`), severity or check include/exclude, external-modules download policy. Pin Checkov **version** in CI (pip or Docker `bridgecrew/checkov:<tag>`) so rules do not drift silently.

## Pairing with other gates

| Concern | Checkov | Complement |
|--------|---------|------------|
| Terraform misconfig | ✅ primary in ladder | OPA/Conftest (`infrastructure/policies/opa/`), `terraform test` |
| Dockerfile hygiene | ✅ `dockerfile` framework | `@container-hardening` |
| Image CVE / OS packages | Partial (SCA often needs Prisma) | Trivy, Grype in CI |

## Further reading

- [reference.md](reference.md) — links into the local clone and Catalyst paths.
