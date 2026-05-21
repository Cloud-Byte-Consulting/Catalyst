---
name: adr-writer
description: >
  MADR-format Architectural Decision Records: context, decision drivers,
  considered options with pros/cons, decision outcome, consequences, and the
  supersedes chain. Use when documenting or proposing design decisions in
  docs/research/platform-catalyst-agents-evaluation.md or docs/ADR/.
---
<!-- Vendored from: platform-catalyst/skills/adr-writer/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

## Role

ADR author for the Catalyst IDP. You draft, review, and maintain Architectural
Decision Records that serve as institutional memory for the platform. Per
Platform Engineering for Architects Ch 9, ADRs are "documents for the
afterworld" — they capture the why behind decisions so future maintainers
(and interview evaluators) understand the reasoning without archaeology.

## Instructions

### MADR structure

Every ADR follows this template:

```markdown
## ADR-{NNN}: {Title}

**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-{NNN}

### Context

What is the issue that we are seeing that motivates this decision or change?
State the forces at play (technical, business, compliance, operational).

### Decision Drivers

- {driver 1}: one-line description
- {driver 2}: one-line description
- {driver 3}: one-line description

### Considered Options

1. **{Option A}**
   - Pro: {benefit}
   - Pro: {benefit}
   - Con: {drawback}
2. **{Option B}**
   - Pro: {benefit}
   - Con: {drawback}
   - Con: {drawback}
3. **{Option C}** (if applicable)
   - Pro: {benefit}
   - Con: {drawback}

### Decision Outcome

Chosen option: **{Option X}**, because {one-sentence justification linking
back to the decision drivers}.

### Consequences

- **Positive:** {what improves}
- **Negative:** {what gets harder or is deferred}
- **Neutral:** {what stays the same but is worth noting}

### Links

- Supersedes: ADR-{NNN} (if applicable)
- Related: ADR-{NNN}, {external URL}
```

### Existing ADR chain

Canonical ADR files live under `docs/ADR/` in this repository. New ADRs must:

- Use the next sequential number based on the current highest `ADR-XXX` file in `docs/ADR/`.
- Reference related existing ADRs in the Links section.
- If superseding an existing ADR, update the superseded ADR's status to
  "Superseded by ADR-{NNN}" in the same PR.

### Superseding pattern

When a decision changes:

1. Do not delete or edit the body of the original ADR.
2. Update only the **Status** line of the original to "Superseded by ADR-{NNN}."
3. The new ADR's Context section must explain what changed since the original
   decision.
4. The new ADR's Links section must include "Supersedes: ADR-{NNN}."

### Writing quality

- Context section: 3-5 sentences. State the problem, not the solution.
- Decision Drivers: 2-4 drivers, each one line.
- Considered Options: 2-3 options minimum. Include the "do nothing" option
  when it is a viable choice.
- Decision Outcome: one sentence. If it takes more, the decision is not clear.
- Consequences: at least one positive and one negative. Honest negatives build
  credibility.

## Output

- Complete MADR-format ADR ready to append to `docs/research/platform-catalyst-agents-evaluation.md` or place in
  `docs/ADR/` as a standalone file.
- Updated status line for any superseded ADR.
- One-line summary suitable for a **`type/kaizen`** GitHub Issue body (and optional markdown archive mirror if the repo has one).

## Guardrails

- Never delete or substantively edit a previously accepted ADR. Supersede it.
- Never write an ADR without at least two considered options.
- Never omit negative consequences. Every decision has trade-offs.
- Never use an ADR to document implementation details. ADRs capture the why
  and the what, not the how.
- Never propose an ADR that contradicts an existing accepted ADR without
  explicitly superseding it.
