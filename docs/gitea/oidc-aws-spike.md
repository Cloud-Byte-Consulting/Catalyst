# Spike: Gitea Actions OIDC + AWS IAM trust

Design notes for [ADR-021 Phase 3](../ADR/ADR-021-migration-github-to-gitea.md) — tracked in [#339](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/339).

**Status:** Spike / not implemented. AWS-touching workflows **remain on GitHub** until this design is accepted and bootstrap trust policies are extended.

---

## Problem

Catalyst AWS CI uses GitHub Actions OIDC (`aws-actions/configure-aws-credentials@v4`) with IAM roles provisioned by `scripts/bootstrap-aws-account.sh`. Trust policies pin JWT `sub` claims to:

```text
repo:Cloud-Byte-Consulting/Catalyst:pull_request
repo:Cloud-Byte-Consulting/Catalyst:ref:refs/heads/release
```

Gitea Actions can emit OIDC tokens (Gitea ≥ 1.21 with Actions enabled), but issuer URL, audience, and claim shape differ from GitHub. Moving `terraform.yml` / `service-cd.yml` to Gitea requires parallel trust — not a drop-in rename.

---

## Current GitHub mapping

| Workflow | Role secret | JWT subject (simplified) |
|---|---|---|
| `terraform.yml` (PR) | `AWS_ROLE_PLAN_ARN` | `repo:…:pull_request` |
| `terraform.yml` (release push) | `AWS_ROLE_APPLY_ARN` | `repo:…:ref:refs/heads/release` |
| `service-cd.yml` | `AWS_ROLE_DEPLOY_ARN` | `repo:…:ref:refs/heads/release` |
| `tf-drift.yml` | `AWS_ROLE_DRIFT_ARN` | `repo:…:ref:refs/heads/release` |
| `bootstrap-smoke.yml` (AWS job) | `BOOTSTRAP_AWS_VALIDATION_ROLE_ARN` | dispatch + env |

See [`.github/workflows/README.md`](../../.github/workflows/README.md) and [ADR-006](../ADR/ADR-006-cicd-pipeline-architecture.md).

---

## Gitea OIDC surface (investigation)

Verify on the homelab Gitea version before implementation:

| Item | GitHub (today) | Gitea (expected — confirm) |
|---|---|---|
| Issuer | `https://token.actions.githubusercontent.com` | `https://<gitea-host>/` or Gitea-documented issuer |
| Audience | `sts.amazonaws.com` | Must match IAM `aud` condition |
| Subject claim | `repo:OWNER/REPO:…` | Gitea repo slug + event type |
| Job permission | `id-token: write` | Same syntax in workflow YAML |

**Action:** On TrueNAS Gitea with Actions enabled, run a debug workflow:

```yaml
jobs:
  dump-oidc:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
    steps:
      - run: |
          curl -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=sts.amazonaws.com"
```

Capture issuer, `sub`, `aud`, and repository identifier for IAM policy design.

---

## Proposed IAM trust sketch

Extend bootstrap roles (or add parallel `catalyst-gitea-*` roles) with a **second** federated principal:

```json
{
  "Effect": "Allow",
  "Principal": {
    "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/<gitea-issuer-host>"
  },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      " <issuer-host>:aud": "sts.amazonaws.com"
    },
    "StringLike": {
      " <issuer-host>:sub": [
        "repo:<gitea-org>/Catalyst:pull_request",
        "repo:<gitea-org>/Catalyst:ref:refs/heads/release"
      ]
    }
  }
}
```

**Open questions:**

1. Exact `sub` format for Gitea pull_request vs push events
2. Whether mirror latency (Gitea merge → GitHub SHA) is acceptable for release apply, or AWS jobs must run on Gitea directly
3. `BOOTSTRAP_GITHUB_REPOSITORY` → add `BOOTSTRAP_GITEA_REPOSITORY` (or unified var)
4. Separate OIDC provider per homelab vs reuse GitHub provider (not possible — different issuers)

---

## Migration options

| Option | Pros | Cons |
|---|---|---|
| **A — Dual trust on existing roles** | One role ARN per function | Trust policy complexity; blast radius if Gitea compromised |
| **B — Parallel `catalyst-gitea-*` roles** | Clear separation | Double secrets; workflow duplication during transition |
| **C — Keep AWS on GitHub mirror only** | No IAM change; JWT unchanged | Requires reliable push mirror; two forges for one deploy |

**Recommendation (spike):** **Option C** until mirror SLA proven; then **Option B** for a bounded pilot (`terraform plan` on Gitea PRs only) before apply/deploy cutover.

---

## Prerequisites before implementation

- [ ] Gitea Actions OIDC issuer live on homelab (HTTPS MagicDNS URL)
- [ ] Sample JWT captured and documented
- [ ] Bootstrap script / Terraform module update for second OIDC provider
- [ ] Security review (trust `sub` narrowness, no `StringLike` over-broad)
- [ ] ADR amendment or ADR-021 addendum accepted

---

## Out of scope for this spike PR

- Modifying `scripts/bootstrap-aws-account.sh`
- Moving `terraform.yml` or `service-cd.yml` to `.gitea/workflows/`
- Disabling GitHub AWS workflows ([#340](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/340) is separate and must not touch AWS jobs)

---

## Related

- [workflow-migration.md](./workflow-migration.md) — what stays on GitHub today
- [operator-cutover-checklist.md](./operator-cutover-checklist.md) — Step 6 interim policy
- [Gitea Actions OIDC docs](https://docs.gitea.com/usage/actions/overview)
