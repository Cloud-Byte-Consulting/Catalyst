# Expose TrueNAS Gitea via Tailscale Serve

Gitea runs as a **TrueNAS SCALE app** (Kubernetes ix-chart or Docker) and must be reachable by developers **on the tailnet only** — not the public internet. [ADR-021](../ADR/ADR-021-migration-github-to-gitea.md) accepts Tailscale Serve as the exposure mechanism.

**Tailscale is already installed on the same TrueNAS host as Gitea** (SCALE Tailscale app). **Serve runs on the TrueNAS box** — no sidecar or separate proxy VM.

**Legacy endpoint:** `http://100.115.245.62:30008` (NodePort on TrueNAS; org path used typo `Cloud-Byte-Consultling` — see [worklog](../worklog/2026-05-13-migration-to-github.md)). Prefer MagicDNS HTTPS via Serve.

---

## Architecture (TrueNAS SCALE)

```text
Developer (tailnet)
        │
        ▼
https://<truenas-host>.<tailnet>.ts.net     ← MagicDNS (Tailscale app on TrueNAS)
        │
   tailscale serve (TLS, on TrueNAS host)
        │
   http://127.0.0.1:30008                  ← NodePort (example; confirm in Apps UI)
        │
   Gitea SCALE app (k8s ix-chart / Docker)
```

| Layer | Role |
|---|---|
| **TrueNAS Apps → Gitea** | Repository, Actions, push mirror settings |
| **TrueNAS Apps → Tailscale** | Tailnet membership, MagicDNS, optional UI for auth/status |
| **`tailscale serve` on TrueNAS** | Terminates HTTPS on tailnet; proxies to local NodePort |

**Do not:**

- Port-forward Gitea NodePort (e.g. `30008`) on your router to WAN.
- Use **Tailscale Funnel** unless explicitly approved — Funnel exposes services to the public internet.

**Do:**

- Reach Gitea only via tailnet (Serve + ACLs).
- Keep NodePort bound for **localhost / cluster** consumption; Serve is the external tailnet entry.

---

## Prerequisites

- TrueNAS SCALE with **Gitea** and **Tailscale** apps installed and healthy
- Machine joined to your tailnet (`tailscale status` shows online from TrueNAS shell or Tailscale app UI)
- Gitea NodePort known (Apps → Gitea → Service / NodePort — e.g. `30008`)
- Local probe succeeds on TrueNAS: `curl -sI http://127.0.0.1:<nodeport>/`

---

## Find Gitea port (TrueNAS)

1. **Apps** → **Installed Applications** → **Gitea**.
2. **Edit** or **Info** → **Networking** / **Service** → note **NodePort** (host port mapped to Gitea HTTP).
3. Optional — from TrueNAS **Shell** or SSH session on the NAS:

```bash
# Replace 30008 with your NodePort
curl -sI http://127.0.0.1:30008/
```

If the chart only lists a cluster port (e.g. `3000`), the **NodePort** is what Serve must target on `127.0.0.1`.

---

## TrueNAS Tailscale app

The SCALE **Tailscale** app typically provides:

- Auth key or OAuth login to join the tailnet
- Machine name used in MagicDNS (e.g. `truenas-scale-1`)
- Status UI (connected / disconnected)

**Serve** is configured on the **TrueNAS host** where `tailscaled` runs (same host as the Tailscale app). Use the TrueNAS **Shell**, SSH to the NAS, or any documented “post-init” hook your chart supports to run:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:30008
```

Replace `30008` with your Gitea NodePort.

> Some SCALE charts reset Serve on reboot. Persist with a TrueNAS **Init** script, cron `@reboot`, or chart-specific “extra commands” — match your TrueNAS version docs.

---

## MagicDNS hostname

With MagicDNS enabled (tailnet admin console):

```text
https://<machine-name>.<tailnet-name>.ts.net
```

Example from migration worklog — machine `truenas-scale-1` on tailnet `tail5a208d`:

```text
https://truenas-scale-1.tail5a208d.ts.net
```

On TrueNAS (or any tailnet node with CLI):

```bash
tailscale status
tailscale serve status
```

---

## Tailscale Serve commands (TrueNAS host)

### Proxy HTTPS to Gitea NodePort

```bash
# Background Serve: tailnet HTTPS → local Gitea NodePort
tailscale serve --bg --https=443 http://127.0.0.1:30008
```

If Gitea listens on a different NodePort, substitute accordingly.

### Inspect / reset

```bash
tailscale serve status
tailscale serve reset    # removes Serve config; re-run serve after
```

### Version-specific flags

```bash
tailscale serve --help
```

Flag names evolve across Tailscale versions; confirm against the binary on your TrueNAS image.

---

## Gitea `ROOT_URL` and SSH clone URLs

After Serve is live, set Gitea **`ROOT_URL`** (and SSH settings if used) to the **MagicDNS HTTPS** base — not the legacy LAN IP.

| Setting | Example |
|---|---|
| `ROOT_URL` | `https://truenas-scale-1.tail5a208d.ts.net/` |
| Clone URL (HTTPS) | `https://truenas-scale-1.tail5a208d.ts.net/Cloud-Byte-Consulting/Catalyst.git` |
| `SSH_DOMAIN` | Same MagicDNS hostname if exposing git+ssh via Serve or Tailscale SSH |
| `SSH_PORT` | Chart-dependent; may require separate Serve rule for port 22 |

**Where to set:** Gitea **Site Administration** → **Configuration** → `app.ini`, or environment/chart values for `GITEA__server__ROOT_URL`.

Wrong `ROOT_URL` breaks clone links, webhooks (e.g. Flux [#243](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/243)), and email notifications.

---

## ACL and tags

Restrict who can reach the TrueNAS Gitea endpoint:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["group:platform-engineers"],
      "dst": ["tag:truenas-gitea:443"]
    }
  ],
  "tagOwners": {
    "tag:truenas-gitea": ["autogroup:admin"]
  }
}
```

Apply tag `tag:truenas-gitea` to the TrueNAS machine in the admin UI. Deny `autogroup:internet` on that tag. Serve without Funnel keeps traffic tailnet-scoped; ACLs add defense in depth.

---

## TrueNAS-specific operations

| Topic | Guidance |
|---|---|
| **Gitea app updates** | Apps → Gitea → Upgrade; read release notes; restart app after chart bump |
| **Data persistence** | Gitea PVC/dataset on TrueNAS pool — snapshot before upgrades; replicate per backup policy |
| **Firewall** | TrueNAS / network: block WAN → NodePort; no UPnP/port-forward for Gitea |
| **Serve persistence** | Re-apply `tailscale serve` after reboot if not automated |
| **WAN exposure** | **Forbidden** for NodePort; tailnet-only via Serve |

---

## Persistence (Serve across reboot)

TrueNAS does not ship a single standard for Serve persistence. Options (pick one that matches your install):

1. **TrueNAS Init/Post-init script** (SCALE custom script or chart “additional environment”) running:

```bash
/usr/bin/tailscale serve --bg --https=443 http://127.0.0.1:30008
```

2. **Cron `@reboot`** on the host (if available).

3. **Manual** — re-run Serve after NAS reboot until automated.

Adjust port `30008` to your NodePort.

---

## Optional: Tailscale Funnel (public internet)

**Not recommended** for Catalyst homelab Gitea. Default is **Serve-only** on the TrueNAS tailnet identity.

---

## Verification (from another tailnet device)

Run these from a **laptop or workstation on the same tailnet** — not from the NAS alone.

### 1. Tailnet connectivity

```bash
tailscale status | grep -i truenas
# or ping MagicDNS name
ping -c 2 truenas-scale-1.tail5a208d.ts.net
```

### 2. HTTPS / Gitea UI

```bash
curl -sI https://truenas-scale-1.tail5a208d.ts.net/
# Expect: HTTP/2 200 or 302 to Gitea
```

Open the same URL in a browser (logged into Tailscale). Confirm repository list loads.

### 3. Git read over HTTPS

```bash
git ls-remote https://truenas-scale-1.tail5a208d.ts.net/Cloud-Byte-Consulting/Catalyst.git HEAD
# Or legacy org path if not yet renamed:
# git ls-remote https://truenas-scale-1.tail5a208d.ts.net/Cloud-Byte-Consultling/Catalyst.git HEAD
```

### 4. Serve status (on TrueNAS)

```bash
tailscale serve status
# Should show https:443 → http://127.0.0.1:30008 (or your NodePort)
```

### 5. Negative check — WAN must not work

From a device **off** the tailnet (or with Tailscale stopped), the MagicDNS URL should **fail** to reach Gitea. Legacy `http://100.115.245.62:30008` should also be unreachable from the public internet if firewall rules are correct.

Update [README.md](./README.md) once the production MagicDNS hostname is confirmed.

---

## Related

- [#246](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/246) — confirm Gitea URL on TrueNAS vs new cluster
- [mirror-setup.md](./mirror-setup.md) — push mirror after `ROOT_URL` is stable
- [Tailscale Serve docs](https://tailscale.com/kb/1242/tailscale-serve)
- [worklog](../worklog/2026-05-13-migration-to-github.md) — legacy Gitea URL and `truenas-scale-1` hostname
