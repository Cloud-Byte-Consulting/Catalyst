#!/usr/bin/env bash
# Hints for configuring Gitea → GitHub push mirror on TrueNAS.
# UI configuration is operator-only — this script prints steps and optional tea CLI commands.
# [#336](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/336)
set -euo pipefail

DRY_RUN=true
GITEA_URL="${GITEA_URL:-}"
GITHUB_URL="${GITHUB_URL:-https://github.com/Cloud-Byte-Consulting/Catalyst.git}"
ORG="Cloud-Byte-Consulting"
REPO="Catalyst"
BRANCH="release"

usage() {
  cat <<'EOF'
Usage: gitea-configure-github-mirror.sh [options]

Options:
  --gitea-url URL   Gitea repo URL (https://<host>/<org>/Catalyst.git)
  --github-url URL  GitHub mirror target (default: Cloud-Byte-Consulting/Catalyst)
  --branch NAME     Branch to mirror (default: release)
  --apply           Print tea CLI commands (still requires operator PAT on Gitea)
  --dry-run         Print UI checklist only (default)
  -h, --help

Environment:
  GITEA_TOKEN       Optional: Gitea API token for tea CLI (never commit)

Examples:
  ./scripts/gitea-configure-github-mirror.sh --dry-run \
    --gitea-url https://truenas-scale-1.tail5a208d.ts.net/Cloud-Byte-Consulting/Catalyst.git

  GITEA_TOKEN=... ./scripts/gitea-configure-github-mirror.sh --apply \
    --gitea-url https://truenas-scale-1.tail5a208d.ts.net/Cloud-Byte-Consulting/Catalyst.git
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gitea-url) GITEA_URL="$2"; shift 2 ;;
    --github-url) GITHUB_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --apply) DRY_RUN=false; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

cat <<EOF
=== Gitea → GitHub push mirror checklist ===

Target branch: ${BRANCH}
GitHub remote: ${GITHUB_URL}
Gitea repo:    ${GITEA_URL:-<set --gitea-url>}

Operator steps (TrueNAS Gitea UI):
  1. Repository → Settings → Mirror Settings
  2. Enable Push Mirror
  3. Remote URL: ${GITHUB_URL}
  4. Auth: GitHub PAT (repo scope) — store in Gitea only, never commit
  5. Interval: 1–5 minutes
  6. Limit to branch '${BRANCH}' if supported; always mirror tags

Verify after merge to Gitea ${BRANCH}:
  git fetch origin ${BRANCH} && git fetch github ${BRANCH}
  git rev-parse origin/${BRANCH} github/${BRANCH}

See docs/gitea/mirror-setup.md for full policy.
EOF

if [[ "$DRY_RUN" == true ]]; then
  echo ""
  echo "(dry-run) Re-run with --apply to print tea CLI hints."
  exit 0
fi

if [[ -z "$GITEA_URL" ]]; then
  echo "ERROR: --gitea-url required for --apply" >&2
  exit 1
fi

if ! command -v tea >/dev/null 2>&1; then
  echo ""
  echo "tea CLI not installed. Install: https://gitea.com/gitea/tea"
  echo "Or configure mirror via Gitea web UI (preferred on TrueNAS)."
  exit 0
fi

echo ""
echo "=== tea CLI hints (operator runs manually) ==="
echo "# Login once (store token in tea config, not in repo):"
echo "tea login add --name truenas --url \"\$(echo '${GITEA_URL}' | sed -E 's|(https://[^/]+).*|\1|')\" --token \"\$GITEA_TOKEN\""
echo ""
echo "# List mirrors (verify after UI setup):"
echo "tea repos mirror list --repo ${ORG}/${REPO}"
echo ""
echo "# Force sync (if your Gitea version supports it):"
echo "tea repos mirror sync --repo ${ORG}/${REPO} || echo 'Use Gitea UI Sync Now'"
