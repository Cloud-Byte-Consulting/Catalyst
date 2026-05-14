## Learned User Preferences

- Prefer GitHub issue comments structured for agent handoff: stable `###` headings (Context, Decision, Rationale, Alternatives considered, Actions taken, Verification, Risks or follow-ups, Next) as described in `docs/issue-execution-gherkin-workflow-2026-05-13.md`.
- When editing Catalyst ADR references, align numbers with files on disk; the in-repo Issues-as-state-machine ADR is ADR-001, and some docs may still mention ADR-008 for the same topic until numbering is reconciled.

## Operating Rules

- **RLM trigger rule** (applies to both Claude Code and Cursor agents): If an artifact to be read exceeds ~50k characters, invoke the RLM workflow before reading inline. The threshold applies to diffs, terraform plan outputs, CloudWatch / CloudTrail exports, and codebase analysis spanning more than ~10 files. The REPL script at `.claude/skills/rlm/scripts/rlm_repl.py` is shared across both platforms. Claude Code agents use the `.claude/skills/rlm/` skill and `.claude/agents/rlm-subcall.md` subagent. Cursor agents use `.cursor/rules/rlm-workflow.mdc` for orchestration guidance and may use the MCP server at `.cursor/skills/rlm/rlm_mcp_server.py` (registered in `.cursor/mcp.json`) for tool-native access. In Cursor, chunk analysis is delegated to `Task` subagents (`subagent_type="generalPurpose"`). See `docs/ADR/ADR-004-rlm-for-long-context-agent-tasks.md` and `docs/rlm-integration-guide.md`.
- After an RLM-assisted run, the issue-comment handoff MUST include the analysis query, chunk count, synthesis decision, next actions, and an explicit callout for any chunk-level finding the synthesis relied on at `confidence: low`. Use the template in `docs/rlm-issue-handoff-template.md`.
- **AWS work uses GitHub OIDC, never long-lived keys.** Container PRs run Trivy (or Docker Scout) with a HIGH/CRITICAL severity gate, produce SPDX 2.3 + CycloneDX 1.5 SBOMs, and upload SARIF to GitHub code scanning. New Python CLIs use Microsoft's `knack` framework; new Python test suites use `pytest` with strict markers + strict config and a `--cov-fail-under=85` gate; AWS-touching tests use `moto` v5 `mock_aws()`. See ADR-005 (`docs/ADR/ADR-005-aws-agentic-platform-engineering.md`) and the plugin assets in `.cursor/agents/aws-platform-engineer.md`, `.cursor/rules/aws-platform-engineering.mdc`, and the two skills under `.cursor/skills/aws-platform-engineering/` and `.cursor/skills/python-cli-and-testing/`.

## Learned Workspace Facts

- Canonical label and transition vocabulary for the GitHub Issues state machine is `docs/ADR/STATE-MACHINE.md` (not `docs/STATE-MACHINE.md`).
- ADR-001 documents GitHub Issues as the durable state machine and comments as the audit trail.
- Static environment slugs are `dev`, `stage`, and `prod`; ephemeral environments use `env/preview-<suffix>` patterns as defined in `docs/ADR/ADR-003-static-and-ephemeral-environments.md`.
- The five-level construct model (Tenant through Application) is `docs/ADR/ADR-002-construct-hierarchy.md`; AWS Organizations aligns at tenant and environment-class boundaries via OUs, landing zones map to accounts, and project or application scope is expressed with tags and IAM rather than one OU per workload by default.
- Agent execution on issues (Gherkin, comment shape, dependency handling) is captured in `docs/issue-execution-gherkin-workflow-2026-05-13.md`.
- Long-context agent tasks (large diffs, terraform plans, CloudWatch / CloudTrail exports, multi-service codebase reads) use the RLM scaffold under `.claude/skills/rlm/` and `.claude/agents/rlm-subcall.md` per `docs/ADR/ADR-004-rlm-for-long-context-agent-tasks.md`. The persistent REPL state pickle lives under `.claude/rlm_state/` and is gitignored.
