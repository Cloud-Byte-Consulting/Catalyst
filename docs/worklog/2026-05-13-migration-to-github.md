# Worklog — Migration from Gitea to GitHub

- **Date**: 2026-05-13
- **From**: `http://100.115.245.62:30008/Cloud-Byte-Consultling/Catalyst` (Gitea, self-hosted)
- **To**: `https://github.com/Cloud-Byte-Consulting/Catalyst` (GitHub, private)
- **Project board**: `https://github.com/orgs/Cloud-Byte-Consulting/projects/3/views/1`

## Reason for migration

Gitea project board column-move web endpoint (`POST /<owner>/<repo>/projects/<id>/<column>/move`) returns `404` for all attempted auth modes (PAT token, Bearer, query param, with/without Referer/Origin). This blocks the issue-as-state-machine flow that depends on automated column transitions across the board. GitHub Projects v2 supports the same automation natively via GraphQL.

## What was migrated

### Code and history
- All branches pushed to GitHub with SHA-preserved history:
  - `release` → `3d1e619c58f7aff1e0516626233c1b1e7ca2eb54`
  - `rc/initial` → `a8efb70e459ed5600fe35385ea4a3aba73650b90`
  - `rc/agent-context-history` → `f212e8ff0432179b49278bfd926089abccadd87e`
  - `rc/issue-2-ea-cli-mcp-server` (local-only, pushed)
  - `claude/condescending-pasteur-bc3724` (local-only, pushed)
- Default branch set to `release` on GitHub.
- Stray `HEAD` ref pushed inadvertently was cleaned up.

### Labels
- All 63 unique labels mirrored to GitHub with original colors and descriptions (state/*, type/*, phase/*, severity/*, verdict/*, construct anchors, kind/*, priority/*, status/*, etc.).

### Issues
- `Cloud-Byte-Consultling/Catalyst#2` migrated as `Cloud-Byte-Consulting/Catalyst#1`.
- Body preserved including Context / Scope / Gherkin Acceptance Criteria.
- 6 comments mirrored with original author + timestamp prefix.
- Original labels reapplied: `app/kaizen`, `env/shared`, `lz/shared`, `project/platform`, `state/agent-working`, `tenant/catalyst`, `type/kaizen`.
- Migration footer + closing comment added on the Gitea side.

### Tags
- No tags existed on Gitea; none to migrate.

### Local git remote
- `origin` now points at GitHub. The old Gitea URL is preserved as `gitea-origin` for reference and rollback if needed.

## What was NOT migrated

| Item | Reason |
|---|---|
| Gitea project board column position | Source `truenas-scale-1.tail5a208d.ts.net:30008/.../projects/2` is replaced by GitHub Projects v2; old positions are not portable. |
| GitHub Projects v2 board attachment | Local `gh` token currently lacks `project` / `read:project` scope. Run `gh auth refresh -s project,read:project`, then attach issue #1 to `https://github.com/orgs/Cloud-Byte-Consulting/projects/3/views/1` and set the Status field. |
| Issue numbering | GitHub assigned `#1`; original was Gitea `#2`. Footer + Gitea closing comment cross-link both. |
| Original Gitea timestamps and authorship | Embedded in each migrated comment header as `Migrated comment from Gitea by <user> at <iso8601>` since GitHub API requires the creator to be the API caller. |
| Self-hosted Gitea webhooks, secrets, actions, mirrors | Out of scope of issue/code migration — re-create in GitHub Actions/secrets if applicable. |

## Follow-ups

1. Granted: `gh auth refresh -s project,read:project` (user completed).
2. Done: migrated issue attached to GitHub Projects v2 board #3 with Status = `In progress`.
3. Done: `tools/ea_cli_mcp` removed in favor of GitHub Projects v2 native automation (GraphQL / Actions). See `docs/worklog/2026-05-13-issue-2-ea-cli-mcp.md` for the superseded scope.
4. Archive the Gitea repository once GitHub is confirmed canonical.
