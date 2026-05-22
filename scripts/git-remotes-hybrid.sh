#!/usr/bin/env bash
# Configure hybrid forge remotes: origin=Gitea (canonical), github=mirror.
# [#337](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/337)
set -euo pipefail

GITEA_URL=""
GITHUB_URL="https://github.com/Cloud-Byte-Consulting/Catalyst.git"
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: git-remotes-hybrid.sh --gitea-url URL [options]

Rewires remotes for ADR-021 hybrid forge:
  origin  → Gitea (push/pull)
  github  → GitHub read mirror

Options:
  --gitea-url URL    Gitea HTTPS clone URL (required)
  --github-url URL   GitHub mirror URL (default: Cloud-Byte-Consulting/Catalyst)
  --dry-run          Print planned changes without modifying remotes
  -h, --help

Examples:
  # New clone already has origin=gitea — just add github
  git remote add github https://github.com/Cloud-Byte-Consulting/Catalyst.git

  # Legacy GitHub-primary clone
  ./scripts/git-remotes-hybrid.sh \
    --gitea-url https://truenas-scale-1.tail5a208d.ts.net/Cloud-Byte-Consulting/Catalyst.git
EOF
}

run() {
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gitea-url) GITEA_URL="$2"; shift 2 ;;
    --github-url) GITHUB_URL="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$GITEA_URL" ]]; then
  echo "ERROR: --gitea-url is required" >&2
  usage >&2
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository" >&2
  exit 1
fi

echo "=== Hybrid remote migration ==="
echo "Gitea (origin):  ${GITEA_URL}"
echo "GitHub (github): ${GITHUB_URL}"
echo ""

origin_url="$(git remote get-url origin 2>/dev/null || true)"
has_github=false
git remote get-url github >/dev/null 2>&1 && has_github=true

if [[ "$origin_url" == "$GITEA_URL" ]]; then
  echo "origin already points to Gitea URL"
  if [[ "$has_github" == false ]]; then
    run git remote add github "$GITHUB_URL"
    echo "Added github remote"
  else
    echo "github remote already exists"
  fi
  exit 0
fi

if [[ "$origin_url" == "$GITHUB_URL" ]] || [[ "$origin_url" == *"github.com/Cloud-Byte-Consulting/Catalyst"* ]]; then
  echo "Detected GitHub-primary clone — renaming origin → github"
  if [[ "$has_github" == true ]]; then
    run git remote remove github
  fi
  run git remote rename origin github
  run git remote add origin "$GITEA_URL"
  echo "Done: origin=Gitea, github=GitHub mirror"
  exit 0
fi

if git remote get-url gitea-origin >/dev/null 2>&1; then
  echo "Detected legacy gitea-origin remote"
  if [[ "$has_github" == false ]] && [[ -n "$origin_url" ]]; then
    run git remote rename origin github
    has_github=true
  fi
  run git remote rename gitea-origin origin
  run git remote set-url origin "$GITEA_URL"
  if [[ "$has_github" == false ]]; then
    run git remote add github "$GITHUB_URL"
  fi
  echo "Done: origin=Gitea, github=GitHub mirror"
  exit 0
fi

echo "Unrecognized remote layout:"
git remote -v
echo ""
echo "Manual fix:"
echo "  git remote rename origin github   # if origin is GitHub"
echo "  git remote add origin '${GITEA_URL}'"
exit 1
