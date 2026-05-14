## Learned User Preferences

- Prefer GitHub issue comments structured for agent handoff: stable `###` headings (Context, Decision, Rationale, Alternatives considered, Actions taken, Verification, Risks or follow-ups, Next) as described in `docs/issue-execution-gherkin-workflow-2026-05-13.md`.
- When editing Catalyst ADR references, align numbers with files on disk; the in-repo Issues-as-state-machine ADR is ADR-001, and some docs may still mention ADR-008 for the same topic until numbering is reconciled.

## Learned Workspace Facts

- Canonical label and transition vocabulary for the GitHub Issues state machine is `docs/ADR/STATE-MACHINE.md` (not `docs/STATE-MACHINE.md`).
- ADR-001 documents GitHub Issues as the durable state machine and comments as the audit trail.
- Static environment slugs are `dev`, `stage`, and `prod`; ephemeral environments use `env/preview-<suffix>` patterns as defined in `docs/ADR/ADR-003-static-and-ephemeral-environments.md`.
- The five-level construct model (Tenant through Application) is `docs/ADR/ADR-002-construct-hierarchy.md`; AWS Organizations aligns at tenant and environment-class boundaries via OUs, landing zones map to accounts, and project or application scope is expressed with tags and IAM rather than one OU per workload by default.
- Agent execution on issues (Gherkin, comment shape, dependency handling) is captured in `docs/issue-execution-gherkin-workflow-2026-05-13.md`.
