# TrueNAS Gitea + Tailscale Serve — operator runbook

Copy-paste checklist for **Phase 0** of [ADR-021](../ADR/ADR-021-migration-github-to-gitea.md). Tracked in [#335](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/335).

This work runs on the **TrueNAS SCALE box** (Apps UI + Shell/SSH). Agents cannot configure TrueNAS remotely — follow each step as the homelab operator.

**Related:** [tailscale-exposure.md](./tailscale-exposure.md) (deep dive) · [operator-cutover-checklist.md](./operator-cutover-checklist.md) (full hybrid cutover order)

---

## Prerequisites

- [ ] TrueNAS SCALE with **Gitea** app installed and running
- [ ] TrueNAS **Tailscale** app installed and joined to the tailnet
- [ ] Tailnet **MagicDNS** enabled (admin console)
- [ ] Operator has TrueNAS **Shell** or SSH access

---

## Step 1 — Confirm Gitea NodePort

1. TrueNAS → **Apps** → **Installed Applications** → **Gitea**
2. Open **Service** / **Networking** → note **NodePort** (example: `30008`)

On TrueNAS shell:

```bash
NODEPORT=30008   # replace with your NodePort
curl -sI "http://127.0.0.1:${NODEPORT}/"
# Expect: HTTP/1.1 200 or 302
```

---

## Step 2 — Confirm Tailscale on TrueNAS

```bash
tailscale status
# Machine should show as connected; note MagicDNS name (e.g. truenas-scale-1)
```

Record:

| Field | Your value |
|---|---|
| Machine name | `________________` |
| Tailnet name | `________________` |
| MagicDNS base | `https://<machine>.<tailnet>.ts.net` |

---

## Step 3 — Configure Tailscale Serve

On the **TrueNAS host** (same machine as Gitea + Tailscale apps):

```bash
NODEPORT=30008   # from Step 1
tailscale serve --bg --https=443 "http://127.0.0.1:${NODEPORT}"
tailscale serve status
# Expect: https:443 → http://127.0.0.1:<nodeport>
```

**Persistence:** Serve may reset on NAS reboot. Add an init script or `@reboot` cron — see [tailscale-exposure.md](./tailscale-exposure.md#persistence-serve-across-reboot).

---

## Step 4 — Set Gitea `ROOT_URL`

Gitea **Site Administration** → **Configuration** → set `ROOT_URL` to your MagicDNS HTTPS base (trailing slash):

```ini
ROOT_URL = https://truenas-scale-1.tail5a208d.ts.net/
```

Or via chart environment (name varies by ix-chart version):

```text
GITEA__server__ROOT_URL=https://<machine>.<tailnet>.ts.net/
```

Restart the Gitea app after changing `ROOT_URL`.

---

## Step 5 — Verify from a tailnet client

Run from a **laptop on the tailnet** (not only from the NAS):

```bash
export GITEA_HOST="truenas-scale-1.tail5a208d.ts.net"   # your MagicDNS host
export GITEA_ORG="Cloud-Byte-Consulting"                 # prefer correct spelling

curl -sI "https://${GITEA_HOST}/"
git ls-remote "https://${GITEA_HOST}/${GITEA_ORG}/Catalyst.git" HEAD
```

Optional — use the repo verification script:

```bash
./scripts/gitea-truenas-verify.sh \
  --host "${GITEA_HOST}" \
  --org "${GITEA_ORG}" \
  --repo Catalyst
```

---

## Step 6 — Security checklist

- [ ] Gitea NodePort **not** port-forwarded to WAN
- [ ] Tailscale **Funnel** not enabled for Gitea (unless explicitly approved)
- [ ] ACL restricts `443` on the TrueNAS tag to platform engineers — see [tailscale-exposure.md](./tailscale-exposure.md#acl-and-tags)
- [ ] Gitea PVC included in TrueNAS backup/replication policy

---

## Step 7 — Handoff to mirror setup

When Steps 1–6 pass, proceed to [#336](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/336) — [mirror-setup.md](./mirror-setup.md) (push mirror `release` + tags → GitHub).

Update [README.md](./README.md) **Preferred URL** row with your confirmed MagicDNS hostname.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `curl` to MagicDNS fails off-tailnet | Expected — Serve is tailnet-only |
| `curl` fails on-tailnet | `tailscale serve status`; NodePort; Gitea app health |
| Clone URLs show LAN IP | Fix `ROOT_URL`; restart Gitea |
| Legacy org path `Cloud-Byte-Consultling` | Rename org in Gitea or re-create under `Cloud-Byte-Consulting` |
