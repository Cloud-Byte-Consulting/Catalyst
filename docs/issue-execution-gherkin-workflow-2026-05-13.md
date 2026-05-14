# Issue execution skill (Gherkin, tests, docs, dependencies)

## Decision

Introduce a Cursor skill **`issue-execution-gherkin-workflow`** so agents executing work against ADR-008 GitHub Issues use a consistent pattern: **Gherkin acceptance criteria**, **test mapping**, **documentation checklist**, **legal state transitions** (via `@github-state-machine`), and **dependency on-hold** via comments + `Depends on #N` without misusing `state/blocked-on-human` for pure cross-issue waits.

## Rationale

- ADR-008 and `docs/STATE-MACHINE.md` define **labels and transitions**; they do not spell out **how** to run an implementation session end-to-end.
- The employer rubric rewards **testable acceptance** and **documentation**; Gherkin in the issue body makes both reviewable.
- **`state/blocked-on-dependency`** does not exist yet; the skill documents the gap and a **comment + link** pattern until a Kaizen extends the vocabulary.

## Alternatives considered

| Option | Why not chosen |
|--------|----------------|
| Only extend `@github-state-machine` | That skill stays implementation-focused (webhooks, enums); execution workflow is a different audience. |
| Mandate `state/blocked-on-human` for deps | Semantically wrong per STATE-MACHINE (human decision). |

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
    Given `docs/STATE-MACHINE.md` legal transition table
    When the execution skill describes dependency blocking
    Then it does not assert transitions outside the legal table
```

## Test mapping

| Scenario | Check |
|----------|--------|
| Skill file exists | `Test-Path .cursor/skills/issue-execution-gherkin-workflow/SKILL.md` |
| Cross-link | `Select-String -Path .cursor/skills/github-state-machine/SKILL.md -Pattern 'issue-execution-gherkin-workflow'` |

## Validation

```powershell
Test-Path .cursor/skills/issue-execution-gherkin-workflow/SKILL.md
Select-String -Path .cursor/skills/github-state-machine/SKILL.md -Pattern 'issue-execution-gherkin-workflow' -Quiet
```

Both should succeed after the implementing commit is present.
