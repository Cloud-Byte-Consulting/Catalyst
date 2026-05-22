# Hybrid forge operator cutover checklist

Ordered steps to make **Gitea on TrueNAS** the git source of truth while **GitHub** remains the issue host and AWS OIDC CI runner. [ADR-021](../ADR/ADR-021-migration-github-to-gitea.md) · umbrella [#334](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/334).

| Step | Issue | Doc / action |
|---|---|---|
| 1 | [#335](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/335) | TrueNAS Tailscale Serve + Gitea `ROOT_URL` — [truenas-operator-checklist.md](./truenas-operator-checklist.md) |
| 2 | [#336](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/336) | Push mirror `release` + tags → GitHub — [mirror-setup.md](./mirror-setup.md) |
| 3 | [#337](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/337) | Developer remotes (`origin`=Gitea, `github`=mirror) — [README.md](./README.md#git-remotes) · `scripts/git-remotes-hybrid.sh` |
| 4 | [#338](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/338) | Enable Gitea Actions + register `ubuntu-latest` runner on TrueNAS |
| 5 | [#338](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/338) | Verify `.gitea/workflows/` run on push/PR to Gitea `release` |
| 6 | — | AWS workflows (`terraform.yml`, `service-cd.yml`, etc.) **stay on GitHub** until [#339](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/339) |
| 7 | [#340](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/340) | Disable duplicate non-AWS GitHub workflows **only after** Step 5 is green |

---

## Step 1 — TrueNAS + Tailscale Serve

**Goal:** Developers reach Gitea at `https://<machine>.<tailnet>.ts.net` (tailnet only).

```bash
# On TrueNAS shell (operator)
NODEPORT=30008   # confirm in Apps UI
tailscale serve --bg --https=443 "http://127.0.0.1:${NODEPORT}"
```

Set Gitea `ROOT_URL` to the MagicDNS HTTPS base. Verify:

```bash
./scripts/gitea-truenas-verify.sh --host <machine>.<tailnet>.ts.net --org Cloud-Byte-Consulting
```

Full runbook: [truenas-operator-checklist.md](./truenas-operator-checklist.md).

---

## Step 2 — Push mirror to GitHub

**Goal:** Every merge to Gitea `release` appears on GitHub `release` within minutes (for AWS CI).

1. Gitea repo → **Settings** → **Mirror** → enable **Push Mirror**
2. Remote: `https://github.com/Cloud-Byte-Consulting/Catalyst.git`
3. Auth: GitHub PAT (`repo` scope) stored in Gitea mirror settings only
4. Mirror `release` branch and tags

Verify:

```bash
git fetch origin release && git fetch github release
git rev-parse origin/release github/release   # SHAs should match
```

Optional helper (dry-run hints): `scripts/gitea-configure-github-mirror.sh --dry-run`

---

## Step 3 — Developer remotes

**Goal:** `git push` goes to Gitea; GitHub is read/mirror reference.

```bash
# New clone (preferred)
git clone "https://<machine>.<tailnet>.ts.net/Cloud-Byte-Consulting/Catalyst.git"
cd Catalyst
git remote add github https://github.com/Cloud-Byte-Consulting/Catalyst.git

# Existing GitHub-primary clone
./scripts/git-remotes-hybrid.sh \
  --gitea-url "https://<machine>.<tailnet>.ts.net/Cloud-Byte-Consulting/Catalyst.git"
```

Issues and `gh` commands still target GitHub.

---

## Step 4 — Enable Gitea Actions runners

**Goal:** Non-AWS CI runs on homelab runners.

On TrueNAS Gitea (Site Admin or `app.ini`):

1. Enable `[actions]` (`ENABLED = true`)
2. Register at least one act_runner with label `ubuntu-latest`
3. Confirm runner shows **online** in Gitea → **Site Administration** → **Actions** → **Runners**

Runner install follows [Gitea act_runner docs](https://gitea.com/gitea/act_runner). Homelab tip: run the runner on TrueNAS or a tailnet VM with Docker.

---

## Step 5 — Verify Gitea workflows

**Goal:** `.gitea/workflows/` jobs pass on Gitea PRs/pushes to `release`.

After merging [#338](https://github.com/Cloud-Byte-Consulting/Catalyst/pulls) to Gitea `release`:

1. Open a test PR on Gitea targeting `release`
2. Confirm jobs: `pr-checks`, `validate-policies`, `multi-tool-sync` (path-dependent)
3. Manual dispatch: `full-suite` workflow from Gitea Actions tab
4. Confirm `bootstrap-smoke` script job passes (no AWS validation on Gitea)

Local structural check (developer machine):

```bash
pip install pyyaml pytest
python .github/scripts/validate_workflows.py
pytest .github/scripts/test_workflow_structure.py -v
```

---

## Step 6 — AWS CI stays on GitHub (interim)

**Goal:** OIDC JWT subjects remain `repo:Cloud-Byte-Consulting/Catalyst:...`.

These workflows run on the **GitHub mirror** after Step 2 sync:

- `terraform.yml`, `tf-drift.yml`, `service-cd.yml`
- `teardown.yml`, `teardown-scheduled.yml`
- `ci-smoke.yml` (optional AWS STS)
- `bootstrap-smoke.yml` → `aws-bootstrap-validation` job (dispatch only)

Design spike for Gitea OIDC: [#339](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/339) · [oidc-aws-spike.md](./oidc-aws-spike.md).

---

## Step 7 — Disable duplicate GitHub workflows (final)

**Goal:** Stop running non-AWS checks twice (Gitea + GitHub).

**Do not merge [#340](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/340) until Step 5 is green for one week or agreed SLA.**

[#340](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/340) adds `.github/workflows/DEPRECATED.md` and disables migrated workflows on GitHub. AWS OIDC workflows remain active.

---

## Rollback

| Scenario | Action |
|---|---|
| Gitea unreachable | Developers push to GitHub directly (break-glass); restore Serve |
| Mirror lag | Manual `git push github release` from operator machine |
| Gitea CI broken | Keep GitHub non-AWS workflows until fixed; do not merge #340 |
| AWS deploy needed | Ensure GitHub `release` SHA matches Gitea before merge |

---

## Documentation map

| Doc | Purpose |
|---|---|
| [README.md](./README.md) | Hybrid forge overview |
| [truenas-operator-checklist.md](./truenas-operator-checklist.md) | TrueNAS + Serve runbook |
| [mirror-setup.md](./mirror-setup.md) | Push mirror configuration |
| [workflow-migration.md](./workflow-migration.md) | Gitea vs GitHub workflow matrix |
| [oidc-aws-spike.md](./oidc-aws-spike.md) | Future Gitea OIDC design |
