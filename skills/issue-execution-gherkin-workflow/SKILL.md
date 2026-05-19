---
name: issue-execution-gherkin-workflow
description: >-
  Executes tracked work against GitHub Issues (ADR-001): advance state labels as
  work completes, require Gherkin acceptance criteria, map scenarios to automated
  tests, verify or update documentation, and handle cross-issue dependencies
  with comments and issue links without illegal state transitions. Use when
  picking up an Issue, implementing a feature behind an Issue, or closing work
  that must stay auditable on the board.
---

<!-- Vendored from: platform-catalyst/.cursor/skills/issue-execution-gherkin-workflow/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Issue execution — Gherkin AC, tests, docs, dependencies (ADR-001)

## Role

You turn a **GitHub Issue** into an **executable contract**: acceptance criteria in **Gherkin**, **tests** that prove each scenario, **documentation** updates when behavior or ops paths change, and **state/label transitions** that match `docs/ADR/STATE-MACHINE.md` as work moves. You complement **`@github-state-machine`** (labels, legal transitions, webhooks) with **human/agent execution discipline**.

**Sources of truth:** [`docs/ADR/ADR-001-github-issues-as-state-machine.md`](../../../docs/ADR/ADR-001-github-issues-as-state-machine.md), [`docs/ADR/STATE-MACHINE.md`](../../../docs/ADR/STATE-MACHINE.md), **`@github-state-machine`**.

## When to load this skill

- Starting or resuming implementation **for a specific Issue** (not drive-by edits).
- Defining or validating **acceptance criteria** before merge.
- Discovering **another Issue or PR must land first** — need a durable on-hold pattern.
- Before closing an Issue: **tests green**, **docs** checked.

## Issue body template (authoring or tightening)

Every executable Issue SHOULD contain:

```markdown
## Context
One paragraph: actor, trigger, outcome.

## Acceptance criteria (Gherkin)

### Scenario: <short name>
Given <precondition>
When <action>
Then <observable outcome>

### Scenario: …
…

## Test mapping
| Scenario | Automated check |
|----------|-----------------|
| <name> | `path/to/test_file.py::test_name` or pytest node id |

## Documentation checklist
- [ ] README / QUICKSTART affected?
- [ ] AGENTS.md / docs/research/platform-catalyst-agents-evaluation.md / ADR if design changed?
- [ ] diagrams/ if topology changed?
- [ ] RUNBOOK / SECURITY if ops or threat surface changed?
```

**Gherkin rules:** scenarios are **testable** (Then = observable); avoid vague “should work”; one primary When per scenario unless clearly compound.

## Execution loop (agent or human)

1. **Read** current labels from GitHub (decision boundary — eventual consistency per `docs/ADR/STATE-MACHINE.md` §6).
2. **Pick up:** `state/pending` → `state/agent-working` only if **`@github-state-machine`** dependency pre-check passes (`Depends on #N` blockers closed — see that skill §9).
3. **Comment** when starting substantive work: short plan + which scenarios you will satisfy this session (audit trail).
4. **Implement** in small steps; **comment** on material progress or errors (ADR-001: comments are proving checks).
5. **Run mapped tests** after each scenario is implemented; fix until green.
6. **Docs:** tick the checklist; if any box is yes, **edit or add** the doc in the same PR as the code.
7. **Complete:** `state/agent-working` → `state/done` (or `rolled-back` / `cancelled` per outcome) with a **final audit comment**: scenarios satisfied, test command run, docs updated (or explicit “N/A” with reason).

Never perform a **silent** label change — every transition pairs with a **comment** (`@github-state-machine` §5–6).

## Dependencies and “on hold”

**Spec fact:** `docs/ADR/STATE-MACHINE.md` has **no** `state/blocked-on-dependency`. Legal transitions are only those in the table (`@github-state-machine`). **`state/blocked-on-human`** means human decision — do **not** use it for pure cross-issue waits.

**Pattern until the vocabulary gains a dependency state (open a `type/kaizen` if you need one):**

1. **Comment** on the working Issue (while still `state/agent-working`):

   ```markdown
   ## ON HOLD — dependency
   
   Blocked by: #<dep> (reason in one sentence).
   Resuming when: #<dep> reaches `state/done` (or link PR that must merge).
   ```

2. **Link issues** in GitHub: ensure body or sidebar includes **`Depends on #<dep>`** (or create a child Issue and link parent/child). Update the **dependency Issue** with a comment: `Blocks: #<this>` so the graph is navigable both ways.

3. **Do not** apply an **illegal** label transition (e.g. `agent-working` → `pending` is not in the legal table).

4. **When the dependency clears:** add a **resume comment**:

   ```markdown
   ## RESUMED — dependency cleared
   
   #<dep> is done / merged. Continuing execution; next step: …
   ```

5. **Relationships:** if GitHub **development** metadata or Projects fields are used, update them when hold/resume happens so the board stays truthful.

If the team later adds **`state/blocked-on-dependency`** (or a modifier) to `docs/ADR/STATE-MACHINE.md` + Terraform, migrate this pattern to that label and update this skill.

## Tests must prove Gherkin

- Each **Then** should map to at least one **automated** check (unit, integration, or contract). If impossible, mark scenario **`@manual`** in the table and justify in a comment — rare for platform code.
- Prefer **`@python-testing`** patterns: pytest node ids in the mapping table match what CI runs.
- For Terraform-only work, “tests” may be **`terraform test`** or policy checks — still list them in **Test mapping**.

## Documentation gate

Before **`state/done`:**

- Walk **Documentation checklist**; if anything changed user-visible behavior, **update docs in-repo** (same PR as code). **`@readme-quickstart`** / **`@adr-writer`** / **`@diagram-author`** as appropriate.
- If no doc change: final comment states **“Docs: N/A — internal-only change”** with one-line reason.

## Related skills

- **`@github-state-machine`** — legal transitions, audit comments, webhooks, dependency parse before pickup.
- **`@python-testing`** — pytest layout, async fixtures, markers.
- **`@git-commit-practices`** — commits reference Issues; conventional subjects.
- **`@adr-writer`** — durable design change → ADR + Issue if policy shifted.

## Guardrails

- No **illegal** state transitions; never “force” labels to match hope.
- No **secrets** in issue bodies or comments (tokens, keys, connection strings).
- **Construct labels** (`tenant/*`, …) remain mandatory per STATE-MACHINE §2 intro — do not close work that should carry construct context without them.
- If execution reveals the **state machine is wrong for reality**, stop and open **`type/kaizen`** + ADR supersede path — do not invent labels outside Terraform-managed set.
