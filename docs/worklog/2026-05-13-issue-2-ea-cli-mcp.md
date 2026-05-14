# Worklog — Issue #2 EA CLI MCP (SUPERSEDED)

> Superseded 2026-05-13 by the GitHub migration. The `tools/ea_cli_mcp/`
> Python MCP server and the `.cursor/mcp.json` workspace registration were
> removed once the project moved to GitHub Projects v2, which provides
> column-move and status automation natively via GraphQL / GitHub Actions.
> This worklog is retained as a historical record of what was built on the
> Gitea-targeted iteration. See `docs/worklog/2026-05-13-migration-to-github.md`.

- **Issue**: [Gitea #2](http://100.115.245.62:30008/Cloud-Byte-Consultling/Catalyst/issues/2) → migrated to [GitHub #1](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/1)
- **Branch**: `rc/issue-2-ea-cli-mcp-server`
- **Date**: 2026-05-13

## What was done

1. Created a self-hosted Git issue to track MCP server implementation work.
2. Added `tools/ea_cli_mcp/` with:
   - `server.py`: stdio MCP server exposing issue verbs and transition helper.
   - `issue_backend.py`: GitHub/Gitea-compatible issue API adapter.
   - `state_machine.py`: legal state transition table and validators.
   - `README.md`: setup and Cursor MCP configuration guidance.
3. Added `.cursor/mcp.json` workspace registration for the new MCP server.
4. Updated root `README.md` with a new section referencing the EA CLI MCP server.
5. Used the new tooling against issue `#2`:
   - Seeded missing ADR state-machine labels on the self-hosted repository.
   - Applied `state/pending` + `type/kaizen` + construct anchor labels.
   - Added a structured issue comment for handoff/audit context.
6. Applied follow-up workflow enhancements:
   - Enforced issue body contract (`Context`, `Scope`, `Acceptance Criteria` as fenced `gherkin`) in `create_issue`.
   - Added workflow phase labels (`phase/todo`, `phase/in-progress`, `phase/on-hold`, `phase/review`) and a `log_workflow_update` helper.
   - Added best-effort automatic project assignment on issue creation using `EA_ISSUE_PROJECT_ID` or `EA_ISSUE_PROJECT_URL`.
   - Updated ADR/process docs to codify phase semantics and done criteria (tests passed + docs updated).
7. Added project-column movement support from captured HAR behavior:
   - Endpoint pattern: `POST /<owner>/<repo>/projects/<project_id>/<column_id>/move`
   - Payload: `{"issues":[{"issueID":<issue_id>,"sorting":0}]}`
   - Configured via `EA_ISSUE_PROJECT_COLUMN_MAP` so phase/state changes can move cards automatically.
   - Added `EA_ISSUE_PROJECT_WEB_BASE_URL` for environments where the web host differs from API host.
8. Added authentication fallback for MCP runtime:
   - If `EA_ISSUE_TOKEN` is unset, backend now attempts `git credential fill` against `EA_ISSUE_BASE_URL`.
   - Keeps Python MCP server in place while reusing existing local credential setup.
9. Tightened done-gate semantics for issue completion:
   - Extended `log_workflow_update(event_type='done')` and `transition_issue_state(to_state='state/done')` to accept `pr_required`, `pr_merged`, and optional `pr_url`.
   - Enforced `tests_passed=true` and `docs_updated=true` for all done transitions.
   - Enforced `pr_merged=true` whenever `pr_required=true`.
   - Added completion comment output for PR gate state and PR URL so audit trail records merge disposition.
10. Updated docs to codify completion rule:
   - `tools/ea_cli_mcp/README.md`
   - `docs/ADR/STATE-MACHINE.md`
   - `docs/ADR/ADR-001-github-issues-as-state-machine.md`
   - `docs/issue-execution-gherkin-workflow-2026-05-13.md`

## ADR alignment

- Uses issue verbs from `docs/ADR/STATE-MACHINE.md` section 4:
  `create`, `comment`, `assign`, `label`, `close`.
- Enforces legal transitions from section 3.
- Emits transition comments to preserve audit history.
- Supports default construct labels for `type/kaizen` issue creation.
- Enforces issue description shape with Gherkin acceptance criteria.
- Attempts project-board assignment at issue creation with non-fatal warnings.

## Validation run

- `python -m py_compile tools/ea_cli_mcp/server.py tools/ea_cli_mcp/issue_backend.py tools/ea_cli_mcp/state_machine.py`
- `python -c "from tools.ea_cli_mcp.server import _tool_definitions; print(len(_tool_definitions()))"`
- `python -c "from tools.ea_cli_mcp.server import _handle_tool_call; print(_handle_tool_call('bootstrap_state_machine_labels', {}))"` (converged with `created_count: 0`)
- `python -c "from tools.ea_cli_mcp.server import _tool_definitions; import json; td={t['name']:t['inputSchema']['properties'] for t in _tool_definitions()}; print(sorted([k for k in td['log_workflow_update'].keys() if k.startswith('pr_')])); print(sorted([k for k in td['transition_issue_state'].keys() if k.startswith('pr_')]))"` (shows `pr_required`, `pr_merged`, `pr_url` on both tools)
