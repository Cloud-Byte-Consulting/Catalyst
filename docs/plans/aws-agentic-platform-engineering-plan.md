# AWS Agentic Platform Engineering — implementation plan

**Issue**: [#19 — Adapt MS Agentic Platform Engineering pattern to AWS as Cursor plugin](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/19)
**Branch**: `rc/aws-agentic-platform-engineering`
**Status**: Active — Phases 1-6 landed; Phases 7-9 in progress
**Authoritative ADR**: [ADR-005](../ADR/ADR-005-aws-agentic-platform-engineering.md)
**Research synthesis**: [`docs/research/aws-agentic-platform-engineering.md`](../research/aws-agentic-platform-engineering.md)
**Cross-references**: [ADR-001](../ADR/ADR-001-github-issues-as-state-machine.md), [ADR-002](../ADR/ADR-002-construct-hierarchy.md), [ADR-003](../ADR/ADR-003-static-and-ephemeral-environments.md), [ADR-004](../ADR/ADR-004-rlm-for-long-context-agent-tasks.md), [STATE-MACHINE.md](../ADR/STATE-MACHINE.md), [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](../issue-execution-gherkin-workflow-2026-05-13.md), [`docs/rlm-integration-guide.md`](../rlm-integration-guide.md)

---

## Goal

Land an **additive** Cursor plugin inside Catalyst that adapts Microsoft's
"Agentic Platform Engineering" pattern (microsoftgbb/agentic-platform-engineering,
its blog series, the Cluster Doctor agent) to AWS-native primitives,
encodes AWS-prescriptive guidance (CAF Platform, IDP guide, SRA, landing
zones, ALB/subnet routing, static-egress pattern, ADR process, GenAI
blueprint) as binding constraints, and wires the persona / skill / prompts
into the existing Catalyst state machine (ADR-001) without inventing new
state vocabulary.

In addition, this plan covers two scope folds-in landed on the same
branch:

- **Container supply-chain layer** — Trivy primary / Docker Scout
  alternative; SPDX 2.3 + CycloneDX 1.5 SBOMs; ECR scan-on-push +
  Inspector V2; binding base-image policy; Dependabot for `docker` +
  `github-actions` ecosystems.
- **Python tooling layer** — `knack` for CLIs; `pytest` (strict markers
  + strict config + 85% coverage gate) for tests; `moto` v5 for AWS
  service mocking.

## Non-goals

- **Not** standing up new AWS infrastructure as part of this branch. The
  scaffolds / generators are emitted; provisioning lands as separate
  `type/kaizen` issues under existing milestones.
- **Not** porting existing Claude / RLM assets. The plugin is purely
  additive; `.claude/` and the RLM skill stay untouched.
- **Not** introducing a runtime AWS-MCP. Only a *generation-time* MCP
  wrapper ships in this branch; runtime AWS access remains in the human /
  CI loop until a first-party AWS-MCP exists.
- **Not** auto-merging the PR. Stop at "Ready for review"; merge gates on
  human approval.
- **Not** retrofitting existing Catalyst Terraform to the SRA OU shape.
  Migration is a separate `type/kaizen`; this branch ships the scaffold
  for *new* landing zones.
- **Not** rewriting existing `argparse` / `unittest` Python in Catalyst.
  Existing code stays in place; new Python work uses `knack` / `pytest` /
  `moto`.

---

## Phased plan

The phases below are wall-clock-ordered for the agent doing the work and
tagged to existing Catalyst milestones (no new milestones invented per the
issue body's constraint). Where a phase touches a multi-issue milestone,
the relevant existing open issues are linked.

### Phase 1 — Research synthesis and source citation

**Milestone**: `Communication and Documentation`
**Status**: ✅ landed (commit `9ae2251`)

Tasks:

- [x] Recursively fetch Microsoft sources (repo tree, agent file,
  workflows, blogs).
- [x] Recursively fetch AWS sources (CAF Platform, IDP guide intro / sub-
  pages, GenAI blog, ADR process welcome / process / appendix).
- [x] Recursively fetch the second-batch AWS-prescriptive sources (SRA
  welcome / architecture / Organizations / Security Tooling, landing-zone
  understanding / setup, ALB subnet routing, static-outbound-IP pattern).
- [x] Recursively fetch the container-supply-chain sources (Trivy, Docker
  Scout, SPDX, CycloneDX, ECR enhanced, Inspector V2, GitHub code
  scanning, SARIF spec, distroless, AL2023 minimal, Dependabot).
- [x] Recursively fetch the Python-tooling sources (pytest fixtures /
  parametrize / configuration / monkeypatch / tmp_path / capture / markers,
  pytest-cov, pytest-xdist, moto, knack repo + dev-branch docs commands /
  arguments / help / output).
- [x] Synthesise to `docs/research/aws-agentic-platform-engineering.md`
  with mapping table, recommended Catalyst-fit architecture, AWS-prescriptive
  markers on normative sources.

**Acceptance gate**: research doc cites every source; mapping table
covers every Microsoft construct that has an AWS analogue; AWS sources
are explicitly marked `AWS-prescriptive` where normative.

### Phase 2 — ADR-005 (Proposed)

**Milestone**: `Communication and Documentation`
**Status**: ✅ landed (commit `9ae2251`)
**Related**: ADR-001 (state machine), ADR-002 (constructs), ADR-003 (envs), ADR-004 (RLM).

Tasks:

- [x] Write `docs/ADR/ADR-005-aws-agentic-platform-engineering.md` per
  Catalyst ADR template; cite AWS prescriptive ADR process and SRA;
  include §Container supply chain and §Python tooling subsections;
  document the immutability rule.

**Acceptance gate**: ADR matches both the in-repo template and the AWS
prescriptive ADR shape (Title / Status / Date / Context / Decision /
Consequences / Compliance / Notes); status `Proposed`; alternatives table
populated; cross-references to ADR-001..004.

### Phase 3 — AWS Platform Engineer persona + workspace rule

**Milestone**: `AI-native Development workflow` (issue #19; related #11, #10)
**Status**: ✅ landed (commit `9ae2251`)

Tasks:

- [x] `.cursor/agents/aws-platform-engineer.md` — persona with G-1..G-12
  guardrails (later extended to G-14 with container supply-chain and
  Python tooling).
- [x] `.cursor/rules/aws-platform-engineering.mdc` — workspace rule with
  trigger contexts, IaC preferences, the OIDC mandate, the SRA-aligned
  table of resource defaults / overrides, and (later) container
  supply-chain + Python tooling stanzas.

**Acceptance gate**: rule auto-activates on AWS contexts; persona body
binds to the skill + prompts + ADR-005 + research doc; refusal patterns
documented.

### Phase 4 — `aws-platform-engineering` skill + templates

**Milestone**: `AI-native Development workflow` (issue #19); also touches
`Infrastructure Design and Terraform Quality` (issue #7), `CI/CD and
operational Maturity` (no current open issue), `Automation Service`
(issue #8).
**Status**: ✅ landed (commit `40758ba`); container supply-chain extension
landed in commit `953c12c`.

Tasks:

- [x] `.cursor/skills/aws-platform-engineering/SKILL.md` with eight
  initial capabilities.
- [x] Templates for landing zone, Terraform module, OIDC workflow, ADR,
  ECS Fargate service, Bedrock service, static-egress VPC, golden path.
- [x] Container supply-chain extension: capabilities #9-#13
  (`generate-container-scan-workflow` Trivy; `generate-container-scan-scout-workflow`;
  `generate-ecr-scan-on-push`; `generate-base-image-policy`;
  `generate-dependabot-container`).
- [x] Templates for Trivy / Scout workflows, ECR scan-on-push Terraform,
  base-image policy doc, Dependabot config.

**Acceptance gate**: every capability has a template under `templates/`;
each template names the AWS-prescriptive sources it encodes in a header
comment; templates use `123456789012` as the placeholder account ID.

### Phase 5 — AWS-flavoured prompts

**Milestone**: `AI-native Development workflow` (issue #19); secondary:
`Communication and Documentation` (issue #9 — threat model).
**Status**: ✅ landed (commit `40758ba`); container + Python additions
landed in commits `953c12c`, `57cdb21`.

Tasks:

- [x] `.cursor/prompts/aws-architect.md` (SRA + landing-zone reasoning).
- [x] `.cursor/prompts/aws-cost-engineer.md` (FinOps levers + tagging
  audits).
- [x] `.cursor/prompts/aws-security-engineer.md` (IAM / SCP / OIDC / SRA
  finding triage; later: container supply-chain review G-13).
- [x] `.cursor/prompts/aws-sre.md` (alarm design, incident triage,
  runbooks; later: container scan SLOs and Python tooling expectations).
- [x] `.cursor/prompts/aws-idp-product-owner.md` (golden-path proposals,
  survey synthesis).

**Acceptance gate**: each prompt emits a structured output template;
each cites the AWS-prescriptive sources it draws from; refusal patterns
documented (where applicable) with the rule cited and the sanctioned
alternative offered.

### Phase 6 — Optional `aws-pe` MCP wrapper

**Milestone**: `Automation Service` (issue #8)
**Status**: ✅ landed (commit `40758ba`); extended in `953c12c`.

Tasks:

- [x] `.cursor/skills/aws-platform-engineering/aws_pe_mcp_server.py` —
  pure stdlib MCP server mirroring `rlm_mcp_server.py` shape; exposes the
  eight original capabilities as MCP tools and (post-extension) the five
  container supply-chain capabilities.
- [x] Register in `.cursor/mcp.json` alongside `rlm-repl`.
- [x] CLI mode for one-off renders outside an agent session.
- [x] `python -m py_compile` verified.
- [x] Smoke-tested via `--cli adr` and `--cli container_scan_trivy`.

**Acceptance gate**: server starts under MCP stdio; `tools/list` returns
13 tools; `--cli` mode renders a complete ADR / container-scan workflow
without errors.

### Phase 6.5 — Container supply-chain layer (folded-in scope)

**Milestone**: `CI/CD and operational Maturity` (no current open issue;
new `type/kaizen` will land here when this branch merges); cross-cuts
`Infrastructure Design and Terraform Quality` (issue #7).
**Status**: ✅ landed (commit `953c12c`).

Tasks:

- [x] Five new templates (Trivy workflow, Scout workflow, ECR
  scan-on-push Terraform, base-image policy doc, Dependabot config).
- [x] Skill capability index extended #9-#13.
- [x] MCP server tool descriptors extended.
- [x] Persona G-13 (container supply chain).
- [x] Workspace rule §Container supply chain stanza.
- [x] Security prompt §Container supply-chain review.
- [x] SRE prompt §Container supply-chain SLOs.
- [x] ADR-005 §Container supply chain (Decision / Rationale / Consequences /
  Alternatives).
- [x] Research doc §2.7 (Trivy / Scout / SBOM / ECR Enhanced citations).

**Acceptance gates**:

- Every container workflow produces SPDX 2.3 + CycloneDX 1.5 SBOMs and
  fails on HIGH/CRITICAL findings unless an exception is documented in
  `.trivyignore` (with `# rationale:` and `review-by:`).
- Every ECR repo provisioned by Catalyst Terraform has `scan_on_push = true`;
  the registry has `aws_ecr_registry_scanning_configuration` set to
  `ENHANCED` (Inspector V2) declared once per account.
- Decision boundary respected: Trivy default; Scout alternative; **no
  third scanner** (per ADR-005 §Container supply chain Alternatives).
- Base-image policy B-1..B-8 enforced for prod workloads; dev/preview
  may waive B-1 with documented expiration.

### Phase 6.6 — Python tooling layer (folded-in scope)

**Milestone**: `Communication and Documentation` (skill spec doc lives
under `.cursor/skills/`, but the canonical CLI itself lands under
`Automation Service` (issue #8)); cross-cuts `CI/CD and operational
Maturity` (pytest CI workflow).
**Status**: ✅ landed (commit `57cdb21`).

Tasks:

- [x] New companion skill `.cursor/skills/python-cli-and-testing/SKILL.md`
  with three capabilities (`scaffold-knack-cli`, `scaffold-pytest-config`,
  `scaffold-pytest-ci-workflow`).
- [x] Reference scaffolds embedded in the skill (CLI: `cli.py`,
  `commands.py`, `arguments.py`, `validators.py`, `formatters.py` —
  including the YAML formatter glue, `help.py`, `exceptions.py`; tests:
  `pyproject.toml` config, `conftest.py`, parametrize examples,
  automation-service handler test pattern, moto-backed test).
- [x] Persona G-14 (Python tooling).
- [x] Workspace rule §Python tooling stanza.
- [x] SRE prompt §Python tooling expectations.
- [x] ADR-005 §Python tooling (Decision / Rationale / Consequences /
  Alternatives).
- [x] Research doc §2.8 (pytest / knack / moto citations).

**Acceptance gates**:

- "Adopt pytest with strict config and coverage gate" — landed in skill;
  CI runs `pytest -q -ra --strict-markers --strict-config --cov
  --cov-report=xml --cov-fail-under=85 -m "not e2e and not slow"`.
- "Adopt knack for Catalyst CLI; scaffold subcommands" — landed in skill;
  CLI has `--help` per subcommand AND
  `--output {table,json,tsv,yaml}` AND structured non-zero exits on
  validator failure.
- "Adopt moto for AWS service mocking in tests" — landed in skill;
  `aws_credentials` / `s3_client` / `ddb_client` fixtures wired via
  `mock_aws()`.
- Decision boundary respected: knack / pytest / moto only; Click /
  Typer / argparse / unittest / nose2 / placebo / vcrpy require written
  justification (per ADR-005 §Python tooling Alternatives).

### Phase 7 — Plan file (this document)

**Milestone**: `Communication and Documentation` (issue #9 adjacent)
**Status**: ⏳ in progress

Tasks:

- [x] Write `docs/plans/aws-agentic-platform-engineering-plan.md` with
  goals, non-goals, phased plan, milestone tags, acceptance gates, risks,
  cross-references.
- [ ] Commit + push.

**Acceptance gate**: plan cross-references ADR-001 / ADR-002 / ADR-003 /
ADR-004 / STATE-MACHINE / RLM docs and the linked open issues.

### Phase 8 — README + AGENTS.md touchups

**Milestone**: `Communication and Documentation` (issue #9 adjacent)
**Status**: ⏳ pending

Tasks:

- [ ] Add a tight "AWS Agentic Platform Engineering" section to top-level
  `README.md` linking to ADR-005, this plan, the persona, the workspace
  rule, the two skills, and the prompts. Keep it short — README does not
  bloat.
- [ ] Append one new operating rule to `AGENTS.md`: "AWS work uses
  GitHub OIDC, never long-lived keys; container PRs run Trivy (or Scout)
  with HIGH/CRITICAL gate + SPDX 2.3 + CycloneDX 1.5 SBOMs; new Python
  uses knack for CLIs and pytest with --cov-fail-under=85 for tests."

**Acceptance gate**: README section under 25 lines; AGENTS.md addition
under 8 lines; both link out rather than duplicate.

### Phase 9 — Open PR; ready-for-review on tracking issue

**Milestone**: `AI-native Development workflow` (issue #19)
**Status**: ⏳ pending

Tasks:

- [ ] `gh pr create` from `rc/aws-agentic-platform-engineering` to
  `release` with a body that lists every deliverable, the four scope
  folds (initial AWS sources / second-batch AWS-prescriptive / container
  supply chain / Python tooling), and the done-gate fields
  (`tests_passed`, `docs_updated`, `pr_required`, `pr_merged`, `pr_url`).
- [ ] Post a "ready for review" comment on issue #19 per
  `docs/issue-execution-gherkin-workflow-2026-05-13.md`.
- [ ] Move issue #19 project board status to `In review`.

**Acceptance gate**: PR open (NOT merged); `state/agent-working` -> 
`state/in-review` transition logged on the issue per STATE-MACHINE §4.2;
PR body lists files + scope folds + sources cited.

---

## Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Cursor agent file format evolves; persona auto-activation breaks | medium | medium | Persona is plain markdown w/ frontmatter; rule is explicit; both can be migrated mechanically. Watch Cursor release notes; track in `type/kaizen` if breaking change lands. |
| 2 | AWS-prescriptive sources change; sources cited become stale | medium | low | Research doc §7 enumerates URLs; the persona / SKILL / templates re-cite them; quarterly re-fetch via a `type/kaizen`. |
| 3 | Optional MCP wrapper drifts from skill capabilities | low | low | MCP descriptors live next to handler functions; CI check (future) can compare the descriptor list to the skill capability list. |
| 4 | Trivy / Scout Action API drifts; SHA pins go stale | medium | low | Dependabot watches `github-actions` ecosystem (capability #13); PRs land as `type/kaizen`. |
| 5 | knack `dev`-branch doc URLs change | low | low | Cited URLs include `/dev/` explicitly so they pin to the active docs branch; quarterly re-fetch. |
| 6 | moto v5 API drifts; `mock_aws()` semantics change | low | medium | conftest.py is the only place moto is wired; one-place fix on a breaking change. |
| 7 | Container scan workflow latency creeps as service set grows | medium | low | `concurrency` block prevents cancel-in-progress; per-PR matrix cap; future kaizen to factor scan into a reusable workflow if duplication grows. |
| 8 | `.trivyignore` accumulates expired entries | high | medium | Quarterly review by the `aws-platform-engineer` persona; expired entries open `type/kaizen`. |
| 9 | Cluster Doctor analogue not actually demonstrated | medium | low | Composes from existing `webhook-handler` + ADR-001 + construct-anchor labels; no new state vocabulary; demonstration belongs to the *Automation Service* milestone (issue #8). |
| 10 | Coverage gate at 85% blocks legitimate prototypes | medium | low | Override per-project via local `pyproject.toml`; the skill ships 85% as the *default* not the floor. |

---

## Cross-references

- **State machine**: [`docs/ADR/STATE-MACHINE.md`](../ADR/STATE-MACHINE.md)
  — label vocabulary; transition rules; audit-comment shape.
- **Issue execution**: [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](../issue-execution-gherkin-workflow-2026-05-13.md)
  — structured handoff comments shape.
- **RLM workflow**: [`.cursor/rules/rlm-workflow.mdc`](../../.cursor/rules/rlm-workflow.mdc),
  [`docs/rlm-integration-guide.md`](../rlm-integration-guide.md),
  [`docs/rlm-issue-handoff-template.md`](../rlm-issue-handoff-template.md).
- **Construct hierarchy**: [`docs/ADR/ADR-002-construct-hierarchy.md`](../ADR/ADR-002-construct-hierarchy.md).
- **Static + ephemeral envs**: [`docs/ADR/ADR-003-static-and-ephemeral-environments.md`](../ADR/ADR-003-static-and-ephemeral-environments.md).
- **GitHub Issues as state machine**: [`docs/ADR/ADR-001-github-issues-as-state-machine.md`](../ADR/ADR-001-github-issues-as-state-machine.md).
- **AWS prescriptive sources**: enumerated in research doc §7.
- **Linked open issues**:
  - #19 — this work (`AI-native Development workflow`).
  - #10, #11 — agentic workflow policies (`AI-native Development workflow`).
  - #7 — IaC best practices (`Infrastructure Design and Terraform Quality`).
  - #8 — AWS application stack / automation service (`Automation Service`).
  - #9 — threat model (`Communication and Documentation`).

---

## Done-gate (when all phases land)

- [x] Tracking issue #19 created with Context / Scope / Gherkin AC,
  labelled, milestoned, on the project board.
- [x] Branch `rc/aws-agentic-platform-engineering` cut from `release`.
- [x] Phases 1-6.6 committed and pushed.
- [ ] Phase 7 (this plan file) committed and pushed.
- [ ] Phase 8 (README + AGENTS.md touchups) committed and pushed.
- [ ] Phase 9 PR opened; ready-for-review comment posted; project status
  moved to `In review`.

> Final hand-off: this branch stops at "Ready for review". Merge gates
> on human approval per ADR-001 and the README's "human-supervised line
> stop" framing.
