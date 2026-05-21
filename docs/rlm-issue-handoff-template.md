# RLM-assisted issue-comment handoff template

When an agent completes an RLM-assisted analysis (PR review, ops-intel finding,
terraform plan, long codebase read), the comment posted to the GitHub Issue MUST
include the fields in this template so a later agent can reproduce or extend the
analysis without re-running the full RLM pass.

This template **composes** the existing `### Context / ### Decision / ### Rationale
/ ### Alternatives considered / ### Actions taken / ### Verification / ### Risks /
### Next` headings from
[`docs/issue-execution-gherkin-workflow-2026-05-13.md`](issue-execution-gherkin-workflow-2026-05-13.md)
with the RLM-specific evidence required by
[ADR-004](ADR/ADR-004-rlm-for-long-context-agent-tasks.md).

---

## Required fields

| Field | Where it lives in the comment | Why it's required |
|---|---|---|
| **Analysis query** | `### Context` (`Query:` line) | Lets the next agent re-run the same RLM pass against an updated artifact. |
| **Chunk count + average chunk size** | `### Context` (`RLM:` line) | Records the chunking strategy so cost / coverage is auditable. |
| **Synthesis decision** | `### Decision` | The single-line outcome (verdict, severity, plan, risk level). |
| **Next actions** | `### Next` (numbered list) | ADR-001 §7 audit-trail requirement; explicit handoff to the next agent or human. |
| **Low-confidence callouts** | `### Risks / follow-ups` | Any chunk-level finding the synthesis relied on at `confidence: low` MUST be listed separately so it isn't presented as confirmed. |
| **Cost-model record** | `### Verification` | Approximate Haiku-vs-Opus token spend per the ADR-004 cost-model table; used for Heijunka throttling decisions. |

The optional machine hint (`<!-- catalyst-agent-log: handoff -->`) on the line after
the summary aligns with the existing convention from the Gherkin workflow doc.

---

## Canonical template

```markdown
<one-line summary including verdict / severity / plan>

<!-- catalyst-agent-log: handoff -->

### Context
- Issue labels at time of comment: `<state/...>`, `<type/...>`, …
- Construct anchors: `tenant/<>`, `env/<>`, `lz/<>`, `project/<>`, `app/<>`
- Artifact: `<path>` (`<size>` chars / `<size>` KB)
- Query: `<exact /rlm query string>`
- RLM: `<N>` chunks @ ~`<size>` chars each (`<chunk_chars>` requested, `<overlap_chars>` overlap); `rlm-subcall` (Haiku) per chunk
- Upstream context (if any): `<links to prior issues / ADRs / runs>`

### Decision
<single-line verdict / severity / plan that the synthesis produced>

### Rationale
<why the root agent reached this synthesis given the chunk-level findings>

### Alternatives considered
- <option rejected> — <one-line reason>

### Actions taken
- Initialised REPL: `python skills/rlm/scripts/rlm_repl.py init <artifact>`
- Scouted with `peek(0, 3000)` and `peek(end-3000, end)`
- Materialised chunks: `write_chunks('.claude/rlm_state/chunks/', size=<N>, overlap=<N>)` → `<N>` files
- Subcall loop: `<N>` `rlm-subcall` invocations; structured JSON appended to `buffers`
- Synthesis: composed in main session; final draft cross-checked against conflicting chunk results
- Labels / state transitions applied: `<list>`
- Commits: `<sha>` `<sha>` …
- PR (if any): `<url>`

### Verification
- All `<N>` chunks processed; non-empty `relevant` list per chunk: `<count>`
- Cost-model estimate (per `docs/ADR/ADR-004-rlm-for-long-context-agent-tasks.md`):
  - scout (Opus): ~`<tokens>` tokens
  - chunk analysis × `<N>` (Haiku): ~`<tokens>` tokens
  - synthesis (Opus): ~`<tokens>` tokens
  - **total**: ~`<tokens>` tokens (~$`<cost>`)
- Tests / policy checks run: `<list>` — outcome: `<pass/fail>`

### Risks / follow-ups
- Low-confidence findings the synthesis relied on (NOT presented as confirmed):
  - `<finding>` — `<reason confidence is low>` (chunk `<id>`)
- Open questions for the next agent / human: `<list>`
- REPL state: `.claude/rlm_state/state.pkl` is ephemeral — discard when issue reaches a terminal state.

### Next
1. <ordered, explicit step for the next agent or human>
2. <…>
3. Do not transition to `state/done` until the ADR-001 §8 done gate is satisfied: `tests_passed`, `docs_updated`, `pr_required` / `pr_merged` (and optional `pr_url`).
```

---

## Worked example (PR review at scale)

This is the same shape as the example in
[`docs/rlm-integration-guide.md`](rlm-integration-guide.md) §Pattern 1, expanded with
every required field:

```markdown
AI review complete — verdict: request-changes — 3 findings across 4 chunks (PR #42, 287 files, 14,200 lines).

<!-- catalyst-agent-log: handoff -->

### Context
- Issue labels at time of comment: `state/agent-working`, `type/pr-review`, `verdict/request-changes`
- Construct anchors: `tenant/catalyst`, `env/shared`, `lz/shared`, `project/platform`, `app/api`
- Artifact: `/tmp/pr-42.diff` (622,144 chars / 622 KB)
- Query: `Find bugs, security issues, API contract violations, and design problems. For each finding: file path, line range, severity (critical/high/medium/low), description, suggested fix.`
- RLM: 4 chunks @ ~155k chars each (`chunk_chars=200000`, `overlap_chars=2000`); `rlm-subcall` (Haiku) per chunk
- Upstream context: PR #42 author thread; ADR-002 (construct-hierarchy)

### Decision
Request changes. Critical SQL injection in `services/api/router.py:47`; medium IAM over-permission in `infrastructure/modules/api/iam.tf:88`; low style nit in `services/api/handlers.py:120`.

### Rationale
Chunk 0 surfaced the SQL injection with `confidence: high` and a direct evidence quote. Chunk 2 surfaced the IAM finding with `confidence: high` and matched the org-policy doc cross-referenced in chunk 1. The style nit is `confidence: medium`; included for completeness but not blocking.

### Alternatives considered
- Approve with comments — rejected: SQL injection is a critical block.
- Defer IAM finding to a follow-up issue — rejected: it is an over-grant on the same PR; cheaper to fix in this PR's diff than open a remediation issue.

### Actions taken
- Exported diff: `gh pr diff 42 > /tmp/pr-42.diff`
- Initialised REPL: `python skills/rlm/scripts/rlm_repl.py init /tmp/pr-42.diff`
- Scouted with `peek(0, 3000)` and `peek(len(content)-3000, len(content))`
- Materialised chunks: `write_chunks('.claude/rlm_state/chunks/', size=200000, overlap=2000)` → 4 files
- Subcall loop: 4 `rlm-subcall` invocations; JSON per chunk appended to `buffers`
- Synthesis: composed in main session
- Labels applied: `verdict/request-changes`
- Commits: (none — review-only)
- PR: https://github.com/Cloud-Byte-Consulting/Catalyst/pull/42

### Verification
- All 4 chunks processed; non-empty `relevant` list per chunk: 3 of 4 (chunk 3 had only documentation changes)
- Cost-model estimate (per ADR-004):
  - scout (Opus): ~2k tokens (~$0.03)
  - chunk analysis × 4 (Haiku): ~160k tokens total (~$0.02)
  - synthesis (Opus): ~10k tokens (~$0.15)
  - **total**: ~172k tokens (~$0.20) — vs ~370k tokens / ~$5.55 reading inline on Opus (≈27× cost reduction)
- Policy checks: `gh pr checks 42` — outcome: pending (CI rerun pending after author fix)

### Risks / follow-ups
- Low-confidence findings the synthesis relied on (NOT presented as confirmed):
  - none for this run; the style nit is `confidence: medium` and is called out as non-blocking.
- Open questions for the author: confirm whether the IAM role's S3 wildcard is intentional for the migration window.
- REPL state: `.claude/rlm_state/state.pkl` discarded after this comment is posted.

### Next
1. Author must remediate SQL injection in `services/api/router.py:47` before re-review.
2. Author must scope the IAM action list in `infrastructure/modules/api/iam.tf:88` (or comment justifying the wildcard).
3. After author pushes fixes, re-run `/rlm context=/tmp/pr-42-v2.diff query=…` against the updated diff.
4. Do not transition this issue to `state/done` until `pr_merged=true` and `pr_url` is recorded.
```

---

## Validation checklist

Before posting the synthesis comment, the agent MUST confirm:

- [ ] `Analysis query` is recorded verbatim in `### Context`.
- [ ] `RLM: <N> chunks @ <size>` is recorded in `### Context`.
- [ ] `### Decision` is a single-line outcome.
- [ ] `### Verification` includes the cost-model estimate.
- [ ] `### Risks / follow-ups` lists every `confidence: low` chunk-level finding the synthesis relied on, called out separately.
- [ ] `### Next` is an ordered list with at least one explicit step (do not leave handoff implicit).
- [ ] `<!-- catalyst-agent-log: handoff -->` machine hint is present so automation can distinguish handoff comments from progress noise.

---

## References

- [ADR-001 — GitHub Issues as state machine](ADR/ADR-001-github-issues-as-state-machine.md)
- [ADR-004 — RLM for long-context agent tasks](ADR/ADR-004-rlm-for-long-context-agent-tasks.md)
- [STATE-MACHINE.md](ADR/STATE-MACHINE.md)
- [docs/rlm-integration-guide.md](rlm-integration-guide.md)
- [docs/issue-execution-gherkin-workflow-2026-05-13.md](issue-execution-gherkin-workflow-2026-05-13.md)
- [docs/catalyst-agent-toolkit-plan.md](catalyst-agent-toolkit-plan.md)
