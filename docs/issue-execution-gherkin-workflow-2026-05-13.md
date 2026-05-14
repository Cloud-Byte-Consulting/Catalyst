# Issue execution skill (Gherkin, tests, docs, dependencies)

## Decision

Introduce a Cursor skill **`issue-execution-gherkin-workflow`** so agents executing work against GitHub Issues (durable state machine per [ADR-001 — GitHub Issues as state machine](ADR/ADR-001-github-issues-as-state-machine.md); there is not yet a separate `ADR-008-github-issues-as-state-machine.md` in this repo — some docs cite **ADR-008** for the same concern until numbering is reconciled) use a consistent pattern: **Gherkin acceptance criteria**, **test mapping**, **documentation checklist**, **legal state transitions** (via `@github-state-machine`), **structured issue comments** that capture decisions and reasoning for later agents, and **dependency on-hold** via comments + `Depends on #N` without misusing `state/blocked-on-human` for pure cross-issue waits.

## Rationale

- ADR-001 (and `docs/ADR/STATE-MACHINE.md`) define **labels, transitions, and comments-as-audit-trail**; they do not spell out **how** to run an implementation session end-to-end or **what shape** agent comments should take so a future run can resume without re-deriving intent.
- The employer rubric rewards **testable acceptance** and **documentation**; Gherkin in the issue body makes both reviewable.
- **`state/blocked-on-dependency`** does not exist yet; the skill documents the gap and a **comment + link** pattern until a Kaizen extends the vocabulary.

## Alternatives considered

| Option | Why not chosen |
|--------|----------------|
| Only extend `@github-state-machine` | That skill stays implementation-focused (webhooks, enums); execution workflow is a different audience. |
| Mandate `state/blocked-on-human` for deps | Semantically wrong per STATE-MACHINE (human decision). |
| Unstructured chatty comments | Later agents cannot scan for decisions, open questions, or legal next states; retrieval cost dominates. |

## Agent comment log (handoff for later runs)

ADR-001 requires that **issue comments** carry the audit trail (transitions, intermediate steps, errors, findings). For **coding agents** resuming work on the same issue, comments should also record **explicit decisions and thought process** in a predictable shape so a later session can `gh issue view <N> --comments` (or API) and reconstruct *what was decided, why, and what remains* without replaying the whole transcript.

### Conventions

- **One logical update per comment** when practical (easier to link and quote than one megathread). Prefer editing the issue body only for durable specs (Gherkin, checklists); use comments for **time-ordered execution narrative**.
- **Top line**: a single-line summary in plain language (shows in GitHub previews and notification emails).
- **Stable section headings** (use these exact `###` titles so agents and humans can skim):

| Section | Purpose |
|---------|---------|
| `### Context` | Issue labels/state at time of comment; files or ADRs read; constraints (e.g. CI red, dependency on #42). |
| `### Decision` | What we are doing **now** (one or two crisp sentences). |
| `### Rationale` | Why this path; trade-offs acknowledged. |
| `### Alternatives considered` | Short bullets of options rejected and one line each on why. |
| `### Actions taken` | Commands run, commits (`abc1234`), PR URLs, label transitions applied. |
| `### Verification` | What was run (tests, policy checks) and outcome; if skipped, say why. |
| `### Risks / follow-ups` | Known debt, flaky tests, timeouts, security notes. |
| `### Next` | **Required for handoff**: explicit checklist for the next agent or human (ordered steps, blockers, “do not merge until …”). |

- **Optional machine hint** (first line inside the comment body, after the summary line): `<!-- catalyst-agent-log: progress | blocked | handoff -->` — lets automation distinguish progress noise from an intentional handoff without parsing prose.
- **Dependencies**: when waiting on another issue, repeat `Depends on #N` in `### Context` or `### Next` and describe what unblocks you (aligns with ADR-001 cross-issue linking).

### Example (illustrative)

```markdown
Summarize: Chose pytest markers over a second job matrix; handoff below.

<!-- catalyst-agent-log: handoff -->

### Context
- Labels: `state/agent-working`, `type/chore`
- Blocked by: none (was considering `Depends on #17` for Terraform label module; dropped — in-repo labels only)

### Decision
Scope smoke tests to `@smoke` only in the default CI workflow; full suite stays on `workflow_dispatch`.

### Rationale
PR feedback asked for faster signal on main; full suite runtime exceeds employer rubric “minutes not tens of minutes” guidance.

### Alternatives considered
- Second matrix dimension for every Python minor — rejected: doubles runner minutes with little gain for this repo size.

### Actions taken
- Commit `a1b2c3d`: narrowed `ci.yml` test job `pytest -m smoke`
- PR https://github.com/org/repo/pull/99

### Verification
- `pytest -m smoke` locally: pass (3 tests)

### Risks / follow-ups
- Nightly full suite not yet added — track as follow-up issue if product asks.

### Next
1. Wait for PR 99 review.
2. After merge, add one comment with `<!-- catalyst-agent-log: progress -->` linking the merge commit and close subtasks in issue body checklist.
3. Do **not** transition to `state/done` until `docs/ADR/STATE-MACHINE.md` transition is legal for this `type/*`.
```

## Implementation

- `.cursor/skills/issue-execution-gherkin-workflow/SKILL.md`
- Cross-link from `.cursor/skills/github-state-machine/SKILL.md`

## Acceptance criteria (Gherkin)

```gherkin
Feature: Issue execution skill discoverability

  Scenario: Skill file exists with frontmatter
    Given the repository root
    When an agent lists `.cursor/skills/issue-execution-gherkin-workflow/`
    Then `SKILL.md` exists with `name` and `description` in YAML frontmatter

  Scenario: State machine skill points to execution skill
    Given `.cursor/skills/github-state-machine/SKILL.md`
    When read for cross-references
    Then it references `@issue-execution-gherkin-workflow`

  Scenario: Dependency pause does not prescribe illegal transitions
    Given `docs/ADR/STATE-MACHINE.md` legal transition table
    When the execution skill describes dependency blocking
    Then it does not assert transitions outside the legal table

  Scenario: Agent handoff comments have a documented shape
    Given `docs/issue-execution-gherkin-workflow-2026-05-13.md`
    When an agent reads execution guidance for GitHub Issues
    Then it defines stable `###` sections for decisions and rationale
    And it requires `### Next` for explicit handoff to a later run
    And it aligns comment expectations with ADR-001 audit-trail semantics
```

## Test mapping

| Scenario | Check |
|----------|--------|
| Skill file exists | `Test-Path .cursor/skills/issue-execution-gherkin-workflow/SKILL.md` |
| Cross-link | `Select-String -Path .cursor/skills/github-state-machine/SKILL.md -Pattern 'issue-execution-gherkin-workflow'` |
| Agent comment handoff doc | `Select-String -Path docs/issue-execution-gherkin-workflow-2026-05-13.md -Pattern '### Next' -Quiet` |

## Validation

```powershell
Test-Path .cursor/skills/issue-execution-gherkin-workflow/SKILL.md
Select-String -Path .cursor/skills/github-state-machine/SKILL.md -Pattern 'issue-execution-gherkin-workflow' -Quiet
Select-String -Path docs/issue-execution-gherkin-workflow-2026-05-13.md -Pattern '### Next' -Quiet
```

The first two checks apply after the skill exists; the third validates this workflow document’s handoff section.
