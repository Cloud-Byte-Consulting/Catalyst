# Catalyst Agent Toolkit — Recursive Language Model (RLM) implementation plan

**Issue**: [#3 — Implementing Recursive Language Models for long running tasks](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/3)
**Branch**: `rc/rlm`
**Authoritative ADRs**: [ADR-001](ADR/ADR-001-github-issues-as-state-machine.md) · [ADR-004](ADR/ADR-004-rlm-for-long-context-agent-tasks.md)
**Operating guide**: [docs/rlm-integration-guide.md](rlm-integration-guide.md)
**Last updated**: 2026-05-13

---

## Goal

Adopt the [Recursive Language Models](https://arxiv.org/abs/2512.24601) pattern as the
standard Catalyst approach for agent tasks that must reason over artifacts above the
~50k-character (~35k-token) inline-read budget. The implementation must keep the agent
substrate (GitHub Issues + Project board per ADR-001) authoritative and add no new
runtime dependencies for the Catalyst services build.

This plan operationalises the decision recorded in ADR-004 by vendoring the upstream
`claude_code_RLM` minimal scaffold into the repo and aligning the operating docs and the
ADR-001 issue-comment handoff format around the new workflow.

## Scope

In-scope:

- Vendor the RLM skill (`.claude/skills/rlm/`) and the `rlm-subcall` subagent
  (`.claude/agents/rlm-subcall.md`) verbatim from
  `https://github.com/BittahCriminal/claude_code_RLM` (sibling clone at
  `Z:\workspace\Cloud-Byte-Consulting\claude_code_RLM`).
- Extend `.gitignore` to exclude RLM REPL state (`**/.claude/rlm_state/`).
- Add the trigger-threshold guardrail to `AGENTS.md`.
- Document the four canonical Catalyst+RLM usage patterns from the integration guide
  (PR review, ops-intel, terraform plan, long codebase reads) and cross-link them from
  the ADR-001 handoff workflow doc.
- Define the issue-comment handoff fields required for an RLM-assisted run (analysis
  query, chunk count, synthesis decision, next actions, low-confidence callouts).
- Validate end-to-end with at least one dry run, capturing artifact size, chunk count,
  per-chunk findings, root synthesis, and the resulting issue-comment shape — recorded
  in `docs/worklog/`.
- Update ADR-004 with implementation findings and bump status if done criteria are met.

Out of scope (per issue #3):

- Production service-side deployment / runtime of RLM in Lambda or ECS.
- Replacing GitHub Issues as the durable state machine — ADR-001 remains authoritative.
- Standing up a separate vector database or RAG stack.

## Phases

The plan is organised into six phases that map 1:1 to the six scope bullets in issue
[#3](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/3). Each phase has a
clear deliverable and an evidence check that gets recorded in the worklog.

### Phase 1 — Vendor RLM assets under `.claude/`

**Deliverables**

- `.claude/skills/rlm/SKILL.md` (verbatim from upstream)
- `.claude/skills/rlm/scripts/rlm_repl.py` (verbatim from upstream)
- `.claude/agents/rlm-subcall.md` (verbatim from upstream)

**Evidence check**

- `python -m py_compile .claude/skills/rlm/scripts/rlm_repl.py` exits 0.
- `python .claude/skills/rlm/scripts/rlm_repl.py --help` lists the `init`, `status`,
  `reset`, `export-buffers`, and `exec` subcommands.
- `Test-Path .claude/skills/rlm/SKILL.md` and `Test-Path .claude/agents/rlm-subcall.md`
  return `True`.

### Phase 2 — `.gitignore` protection for ephemeral REPL state

**Deliverables**

- Append `**/.claude/rlm_state/` to `.gitignore` while preserving the existing
  `.claude/worktrees/`, `__pycache__/`, and `*.pyc` rules.

**Evidence check**

- `git check-ignore -v .claude/rlm_state/state.pkl` matches the new pattern.
- Existing entries remain intact (`Select-String -Path .gitignore -Pattern '^\.claude/worktrees/$'`).

### Phase 3 — `AGENTS.md` trigger guardrail

**Deliverables**

- Add a new "Learned Workspace Facts" bullet (or a dedicated "RLM trigger rule" line):

  > If an artifact to be read exceeds ~50k characters, invoke the RLM workflow before
  > reading inline. Threshold applies to diffs, terraform plan output, CloudWatch /
  > CloudTrail exports, and codebase analysis spanning >10 files.

**Evidence check**

- `Select-String -Path AGENTS.md -Pattern '50k characters' -Quiet` returns `True`.

### Phase 4 — Operating-doc alignment with the four RLM usage patterns

**Deliverables**

- Cross-reference the four canonical usage patterns (PR review, ops-intel, terraform
  plan, long codebase reads) from `docs/issue-execution-gherkin-workflow-2026-05-13.md`
  so coding agents executing on issues land on the RLM guide naturally.
- No edits to ADR-001/STATE-MACHINE except cross-link if the plan calls for it; the
  existing ADRs already accommodate RLM-assisted runs.

**Evidence check**

- `Select-String -Path docs/issue-execution-gherkin-workflow-2026-05-13.md -Pattern 'RLM' -Quiet`
  returns `True`.

### Phase 5 — Issue-comment handoff fields for RLM-assisted runs

**Deliverables**

- New doc `docs/rlm-issue-handoff-template.md` defining the required fields for an
  RLM-assisted handoff comment, including:
  - analysis query
  - chunk count + average chunk size
  - synthesis decision (verdict, severity, plan, etc.)
  - next actions (numbered, ordered)
  - explicit `confidence: low` callouts for any chunk-level finding the synthesis
    relied on but did not cross-corroborate
- Worked example matching the `### Context / ### Decision / ### Rationale /
  ### Actions taken / ### Verification / ### Risks / ### Next` skeleton from the
  Gherkin workflow doc, plus the ADR-004 cost-model fields (chunks × avg size,
  Haiku/Opus token spend estimate).

**Evidence check**

- `Test-Path docs/rlm-issue-handoff-template.md` returns `True`.
- The template includes all required field names verbatim (validated by a worklog
  grep, listed in Phase 6 evidence).

### Phase 6 — End-to-end dry run + worklog evidence

**Deliverables**

- A representative artifact created under `.claude/rlm_state/` (gitignored)
  reproducible from in-repo files (e.g. concatenate ADR-001/STATE-MACHINE.md, and the
  vendored RLM scripts/docs to exceed the 50k-char threshold).
- Run `python .claude/skills/rlm/scripts/rlm_repl.py init <artifact>` and `status`.
- Run `peek` and `chunk_indices` via `exec` and capture the output.
- Run `write_chunks` to produce N chunk files.
- Simulate the `rlm-subcall` (Haiku) per chunk by writing a JSON finding per chunk
  to `buffers` (real subagent invocation requires Claude Code; the dry run validates
  the REPL plumbing and the JSON-per-chunk schema).
- Run `export-buffers` to materialise the synthesis input.
- Compose an example synthesis comment using the Phase 5 template, populated with
  the dry-run numbers.
- Record everything in `docs/worklog/2026-05-13-issue-3-rlm-toolkit.md` with explicit
  done-gate accounting (`tests_passed`, `docs_updated`, `pr_required`, `pr_merged`,
  `pr_url`).

**Evidence check**

- Worklog file exists with chunk count, byte counts, and a quoted example synthesis
  comment.
- `python -m py_compile` output for the REPL script is included.
- All six phases listed with pass/fail.

## Done criteria (ADR-001 §8 gate)

The plan is "done" only when:

1. `tests_passed: true` — all `python -m py_compile` and grep checks above succeed
   and the dry run completes without error.
2. `docs_updated: true` — ADR-004 is updated with the implementation findings, the
   worklog entry exists, and the handoff template is in `docs/`.
3. `pr_required: true`, `pr_merged: true` (PR `rc/rlm` → `release` merged), and
   `pr_url` recorded in the closing issue comment.

Until the PR merges, issue #3 sits at project status `In review` (closest available
column to ADR-001's `review`). It transitions to `Done` only after merge.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Upstream `claude_code_RLM` layout changes after vendor | Vendored copies pinned in repo; ADR-004 records the upstream commit hash in the worklog. |
| Dry-run cannot invoke real Haiku subagent without Claude Code session | Document the simulation explicitly in the worklog so reviewers know which step was stubbed. The REPL plumbing (init/exec/status/write_chunks/export-buffers) is exercised end-to-end. |
| `.claude/rlm_state/` accidentally committed | `.gitignore` entry plus a worklog `git check-ignore` evidence line. |
| Project board status name drift (`In review` vs ADR-001 `review`) | Worklog records both the ADR-001 vocabulary and the actual board option name; future Kaizen issue can rename the board column. |

## References

- Issue [#3](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/3)
- [ADR-001 — GitHub Issues as state machine](ADR/ADR-001-github-issues-as-state-machine.md)
- [ADR-004 — RLM for long-context agent tasks](ADR/ADR-004-rlm-for-long-context-agent-tasks.md)
- [STATE-MACHINE.md](ADR/STATE-MACHINE.md)
- [docs/rlm-integration-guide.md](rlm-integration-guide.md)
- [docs/issue-execution-gherkin-workflow-2026-05-13.md](issue-execution-gherkin-workflow-2026-05-13.md)
- Upstream RLM repo: <https://github.com/BittahCriminal/claude_code_RLM>
- Paper: Zhang, Kraska, Khattab — *Recursive Language Models* (arXiv:2512.24601)
