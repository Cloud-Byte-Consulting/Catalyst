#!/usr/bin/env bash
# Verify TrueNAS Gitea is reachable via Tailscale Serve (tailnet client).
# Operator/dev runbook helper — [#335](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/335)
set -euo pipefail

HOST=""
ORG="Cloud-Byte-Consulting"
REPO="Catalyst"
NODEPORT=""

usage() {
  cat <<'EOF'
Usage: gitea-truenas-verify.sh --host <magicdns-host> [options]

Options:
  --host HOST       MagicDNS hostname (e.g. truenas-scale-1.tail5a208d.ts.net)
  --org ORG         Gitea org/user (default: Cloud-Byte-Consulting)
  --repo REPO       Repository name (default: Catalyst)
  --nodeport PORT   Optional: probe localhost NodePort on current machine (TrueNAS shell)
  -h, --help        Show this help

Examples:
  # From tailnet laptop
  ./scripts/gitea-truenas-verify.sh --host truenas-scale-1.tail5a208d.ts.net

  # On TrueNAS shell (local NodePort only)
  ./scripts/gitea-truenas-verify.sh --nodeport 30008
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --org) ORG="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --nodeport) NODEPORT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

fail=0

if [[ -n "$NODEPORT" ]]; then
  echo "==> Probing local NodePort http://127.0.0.1:${NODEPORT}/"
  if curl -sfI "http://127.0.0.1:${NODEPORT}/" >/dev/null; then
    echo "OK: Gitea responds on NodePort ${NODEPORT}"
  else
    echo "FAIL: No response on NodePort ${NODEPORT}" >&2
    fail=1
  fi
fi

if [[ -z "$HOST" ]]; then
  if [[ -n "$NODEPORT" ]]; then
    [[ "$fail" -eq 0 ]] && exit 0 || exit 1
  fi
  echo "ERROR: --host required unless --nodeport-only check" >&2
  usage >&2
  exit 1
fi

BASE="https://${HOST}"
CLONE_URL="${BASE}/${ORG}/${REPO}.git"

echo "==> HTTPS probe ${BASE}/"
if code=$(curl -sI -o /dev/null -w '%{http_code}' "${BASE}/"); then
  if [[ "$code" =~ ^(200|302|301)$ ]]; then
    echo "OK: HTTP ${code}"
  else
    echo "FAIL: HTTP ${code} (expected 200/301/302)" >&2
    fail=1
  fi
else
  echo "FAIL: curl error — are you on the tailnet?" >&2
  fail=1
fi

echo "==> Git ls-remote ${CLONE_URL}"
if git ls-remote "$CLONE_URL" HEAD >/dev/null 2>&1; then
  echo "OK: repository readable"
else
  echo "WARN: git ls-remote failed (org typo, auth, or repo not created yet)" >&2
  echo "      Try legacy org Cloud-Byte-Consultling if not renamed" >&2
  fail=1
fi

if command -v tailscale >/dev/null 2>&1; then
  echo "==> tailscale serve status (if on TrueNAS host)"
  tailscale serve status 2>/dev/null || true
fi

[[ "$fail" -eq 0 ]] && echo "All checks passed." && exit 0
echo "One or more checks failed." >&2
exit 1
