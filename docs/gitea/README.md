# Gitea hybrid forge — operator overview

Catalyst uses a **hybrid forge model** ([ADR-021](../ADR/ADR-021-migration-github-to-gitea.md)):

| Surface | Host |
|---|---|
| **Git (canonical)** | Gitea on **TrueNAS SCALE** (homelab) |
| **Git (read mirror)** | GitHub `Cloud-Byte-Consulting/Catalyst` |
| **Issues, Projects v2, `gh` / GitHub MCP** | GitHub (permanent) |
| **Non-AWS CI** | Gitea Actions |
| **AWS OIDC CI** | GitHub Actions (on mirror) |

## TrueNAS host layout

Gitea and Tailscale run on the **same TrueNAS SCALE box**:

```text
Tailnet client ──► MagicDNS (Tailscale SCALE app on TrueNAS)
                         │
                    tailscale serve :443 → http://127.0.0.1:<nodeport>
                         │
                    Gitea app (ix-chart / Docker, NodePort e.g. 30008)
```

| Component | Where | Notes |
|---|---|---|
| **Gitea** | TrueNAS **Apps** → Gitea chart | Usually Kubernetes (ix-chart) or Docker app; publishes **NodePort** (legacy example: `30008`) |
| **Tailscale** | TrueNAS **Apps** → Tailscale (already installed) | Joins tailnet; **Serve** runs on the TrueNAS host — no sidecar |
| **Access** | Tailnet **only** via Serve | Do **not** port-forward Gitea NodePort to WAN |

**Legacy LAN URL** (pre-Serve): `http://100.115.245.62:30008/Cloud-Byte-Consultling/Catalyst` — org slug typo `Consultling` per [worklog](../worklog/2026-05-13-migration-to-github.md). Prefer MagicDNS + HTTPS after Serve is configured.

**Preferred URL:** `https://<truenas-machine>.<tailnet>.ts.net/<org>/Catalyst` — see [tailscale-exposure.md](./tailscale-exposure.md).

| Endpoint | Purpose | Access |
|---|---|---|
| **Gitea (legacy LAN / NodePort)** | `http://100.115.245.62:30008/...` | Tailnet or LAN only; not for WAN exposure |
| **Gitea (Tailscale Serve — preferred)** | `https://<machine>.<tailnet>.ts.net` | Tailnet only (MagicDNS) |
| **GitHub mirror** | `https://github.com/Cloud-Byte-Consulting/Catalyst` | Public read; push via mirror automation only |

New deployments should use org **`Cloud-Byte-Consulting`** (correct spelling), not legacy `Cloud-Byte-Consultling`.

## Find Gitea port on TrueNAS

1. TrueNAS UI → **Apps** → **Installed Applications** → **Gitea**.
2. Open **Service** / **Networking** / **Node Port** (wording varies by chart version).
3. Note the **NodePort** (e.g. `30008`) and confirm the in-cluster service port (often `3000`).
4. From the TrueNAS shell (or SSH): `curl -sI http://127.0.0.1:<nodeport>/` — expect HTTP 200 or Gitea redirect.

Serve should target **`http://127.0.0.1:<nodeport>`** on the TrueNAS host (same host where the Tailscale app runs).

## TrueNAS operator checklist

| Item | Guidance |
|---|---|
| **App updates** | Upgrade Gitea via Apps UI; snapshot or backup PVC before major version bumps |
| **Persistent volume** | Gitea data lives on the app PVC/dataset — include in TrueNAS backup/replication policy |
| **Firewall** | Do not expose Gitea NodePort on WAN; no router port-forward for `30008` |
| **Tailscale** | Use the SCALE Tailscale app UI for auth status; configure **Serve** on the TrueNAS host (CLI or documented app hooks) |
| **`ROOT_URL`** | Set to MagicDNS Serve URL — see [tailscale-exposure.md](./tailscale-exposure.md) |
| **Mirror** | Push mirror from TrueNAS Gitea → GitHub — [mirror-setup.md](./mirror-setup.md) |

## Git remotes

```bash
# Canonical layout (after hybrid cutover)
git remote add origin  https://<machine>.<tailnet>.ts.net/<org>/Catalyst.git
git remote add github  https://github.com/Cloud-Byte-Consulting/Catalyst.git
```

See [mirror-setup.md](./mirror-setup.md) for push-mirror configuration and branch/tag policy.

## Documentation map

| Doc | Contents |
|---|---|
| [mirror-setup.md](./mirror-setup.md) | TrueNAS Gitea → GitHub mirror; remotes; `release` + tags |
| [workflow-migration.md](./workflow-migration.md) | Which workflows run on Gitea vs GitHub |
| [tailscale-exposure.md](./tailscale-exposure.md) | TrueNAS + Tailscale Serve; MagicDNS; verification |

## Issue and PR conventions

- **Tracking issues** always live on GitHub — reference with `Closes #N` in commits/PRs.
- **GitHub PRs** opened against the mirror satisfy the PR-open contract (`Closes #N` + Catalyst Progress project).
- **Gitea PRs** may be used for day-to-day review; merge to `release` on Gitea, then mirror propagates to GitHub for AWS CI.

## Related issues

- [#246](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/246) — Gitea deploy, mirror execution, workflow port
- [#243](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/243) — Flux bootstrap; GitOps webhooks from Gitea
