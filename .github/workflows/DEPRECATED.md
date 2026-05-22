# Deprecated GitHub workflows (ADR-021 final cutover)

> **DO NOT MERGE the PR for [#340](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/340) until Gitea Actions workflows ([#338](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/338)) are verified green on homelab Gitea for at least one release cycle.**

After cutover, non-AWS CI runs on **Gitea Actions** (`.gitea/workflows/`). This directory retains **AWS OIDC** workflows that must keep GitHub JWT subjects.

---

## Migrated to Gitea (disable automatic GitHub triggers)

| GitHub workflow | Gitea replacement | Notes |
|---|---|---|
| `pr-checks.yml` | `.gitea/workflows/pr-checks.yaml` | Path-filtered lint/test |
| `validate-policies.yml` | `.gitea/workflows/validate-policies.yaml` | OPA conftest |
| `multi-tool-sync.yml` | `.gitea/workflows/multi-tool-sync.yaml` | ADR-024 bootstrap check |
| `full-suite.yml` | `.gitea/workflows/full-suite.yaml` | Manual dispatch |
| `bootstrap-smoke.yml` (script jobs) | `.gitea/workflows/bootstrap-smoke.yaml` | GitHub copy keeps **AWS validation dispatch only** |

**Disable approach:** `#340` changes `on:` for the above to `workflow_dispatch` only (emergency fallback), except `bootstrap-smoke.yml` which retains dispatch for live AWS validation.

---

## Stays on GitHub (AWS OIDC)

| Workflow | Why |
|---|---|
| `terraform.yml` | Plan/apply; S3 backend + DynamoDB lock |
| `tf-drift.yml` | Scheduled drift detection + SNS |
| `service-cd.yml` | ECR push + Lambda/ECS deploy |
| `teardown.yml` | Manual destroy gate |
| `teardown-scheduled.yml` | EOD demo cost-save (**cron unchanged**) |
| `ci-smoke.yml` | `.github/**` workflow smoke + optional STS |

Until [#339](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/339) lands, all AWS jobs require GitHub mirror `release` sync from Gitea.

---

## Verification before merge

1. Gitea `pr-checks` green on a test PR
2. Gitea `multi-tool-sync` green on push to `release`
3. Push mirror: `git rev-parse origin/release github/release` SHAs match
4. GitHub `terraform.yml` still triggers on mirrored `release` push

---

## Rollback

Re-enable GitHub `on: pull_request` triggers by reverting `#340` if Gitea CI fails.
