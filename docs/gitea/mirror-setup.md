# Git mirror — TrueNAS Gitea canonical → GitHub read mirror

Policy: developers **push to Gitea on TrueNAS**; GitHub receives a **read mirror** of `release` and all tags. AWS OIDC workflows on GitHub trigger from the mirrored `release` branch.

See [ADR-021](../ADR/ADR-021-migration-github-to-gitea.md) and [README.md](./README.md).

**Gitea host:** TrueNAS SCALE app (NodePort e.g. `30008` on localhost; tailnet access via [tailscale-exposure.md](./tailscale-exposure.md)). Push mirror runs **on the TrueNAS Gitea instance** — outbound HTTPS to `github.com` does not require inbound WAN access to Gitea.

---

## Remote naming

| Remote | URL | Use |
|---|---|---|
| `origin` | Gitea clone URL (MagicDNS preferred) | `git pull`, `git push`, feature branches |
| `github` | `https://github.com/Cloud-Byte-Consulting/Catalyst.git` | Mirror target (automation / operator) |

### New clone (recommended)

Use the Serve / MagicDNS URL after [tailscale-exposure.md](./tailscale-exposure.md) is configured:

```bash
git clone https://<machine>.<tailnet>.ts.net/Cloud-Byte-Consulting/Catalyst.git
cd Catalyst
git remote add github https://github.com/Cloud-Byte-Consulting/Catalyst.git
git checkout release
```

### Legacy clone (GitHub was `origin`)

Clones from May 2026 may have:

```bash
origin       → github.com/Cloud-Byte-Consulting/Catalyst
gitea-origin → http://100.115.245.62:30008/Cloud-Byte-Consultling/Catalyst
```

Renaming:

```bash
git remote rename origin github
git remote rename gitea-origin origin
# Or re-clone from MagicDNS Gitea URL with remotes as above
```

Update `origin` URL when switching from LAN IP to MagicDNS:

```bash
git remote set-url origin https://truenas-scale-1.tail5a208d.ts.net/Cloud-Byte-Consulting/Catalyst.git
```

---

## Branch and tag policy

| Ref | TrueNAS Gitea | GitHub mirror |
|---|---|---|
| `release` | **Canonical** — merge target | Mirrored (required for AWS CI) |
| Feature branches | Gitea only (optional mirror) | Not mirrored by default |
| Tags | Mirrored | Mirrored (release tagging, semver) |
| `main` | Legacy; prefer `release` | Legacy |

---

## Option A — Gitea push mirror on TrueNAS (preferred)

Configure in the TrueNAS Gitea UI: **Repository → Settings → Mirror Settings** (wording may vary by chart).

1. Enable **Push Mirror**.
2. Remote URL: `https://github.com/Cloud-Byte-Consulting/Catalyst.git`
3. Authenticate with a GitHub PAT (`repo` scope) or deploy key with write access — store in Gitea mirror settings only.
4. Mirror interval: 1–5 minutes (or webhook-triggered if supported).
5. Limit to branch `release` if your Gitea version supports branch filters; otherwise use a post-receive hook (below).

**Outbound path:** TrueNAS Gitea → `github.com` (HTTPS). No need for GitHub to reach homelab Gitea — ideal when Gitea is tailnet-only via Serve.

**Prerequisite:** Gitea `ROOT_URL` matches MagicDNS — see [tailscale-exposure.md](./tailscale-exposure.md) — so internal hooks and logs show correct URLs.

Verify after merge to `release` on Gitea:

```bash
# From developer machine (tailnet)
git fetch origin release
git fetch github release
git rev-parse origin/release github/release   # SHAs should match after sync
```

Or on TrueNAS / Gitea admin: check mirror **Last sync** / logs.

---

## Option B — GitHub pull mirror

GitHub **Settings → Repository → Mirroring** pulling from Gitea requires GitHub to reach your Gitea URL. Homelab Gitea behind Tailscale Serve is **not reachable from GitHub’s runners** unless you expose Funnel or a relay.

**Prefer Option A** (push from TrueNAS Gitea → GitHub).

---

## Option C — Operator script / hook

Post-receive hook on TrueNAS Gitea (server-side; path depends on chart):

```bash
#!/bin/sh
# Push release branch and tags to GitHub after each Gitea push
git push github release 2>/dev/null || true
git push github --tags 2>/dev/null || true
```

Local one-shot (operator, tailnet + credentials):

```bash
git push origin release
git push github release
git push github --tags
```

---

## Initial history seed

One-time full mirror to TrueNAS Gitea (if GitHub currently holds history):

```bash
git clone --mirror https://github.com/Cloud-Byte-Consulting/Catalyst.git
cd Catalyst.git
git remote add gitea https://<machine>.<tailnet>.ts.net/Cloud-Byte-Consulting/Catalyst.git
git push --mirror gitea
```

Then flip canonical remotes on developer machines per above.

---

## Mirror health checks

| Check | Command / action |
|---|---|
| SHAs match | `git rev-parse origin/release` vs `github/release` |
| Tags present | `git ls-remote --tags github` after tagging on Gitea |
| AWS CI triggered | Push to Gitea `release` → verify `terraform.yml` / `service-cd.yml` on GitHub |
| Gitea mirror UI | Last sync time; no 401 on PAT |
| TrueNAS | Gitea app healthy; outbound DNS/HTTPS to github.com |

Alert if mirror lag exceeds SLA (e.g. 15 minutes).

---

## Secrets

- Store GitHub mirror PAT in Gitea mirror settings on TrueNAS — **never commit**.
- Rotate PAT when mirror automation fails with 401/403.
- TrueNAS backup policies should treat Gitea PVC as sensitive (contains repo data and may cache credentials per chart).

---

## Related

- [tailscale-exposure.md](./tailscale-exposure.md) — TrueNAS Serve, `ROOT_URL`, verification
- [worklog](../worklog/2026-05-13-migration-to-github.md) — prior Gitea → GitHub migration; legacy URL and org typo
