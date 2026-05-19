<!-- AUTO-GENERATED from skills/pr-open-contract/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: pr-open-contract
description: Hard gate before every `gh pr create` — verify the tracking issue exists, ensure the PR body carries `Closes #<N>`, assign the PR to the Catalyst Progress GitHub Project (#3), and answer the docs/diagrams currency question explicitly. Invoke this skill any time you are about to call `gh pr create`, push a scope-expanding commit to an existing PR branch, or notice a PR open without a project assignment.
---

# pr-open-contract

The opening-side counterpart to `pr-review-triage`. This skill is the hard gate every Catalyst PR passes through *before* it is created. Three checks; all required; none optional.

## 1. Why

Without `Closes #<N>` in the PR body, scope drifts silently — the audit trail loses the link from "what we shipped" back to "what we agreed to ship", and GitHub's auto-close fails so the tracking issue lingers stale. Without a `Catalyst Progress` project assignment, the PR drops off the team's working board — reviewers don't see it on the queue and the kaizen feedback loop breaks. Without an explicit answer to the docs/diagrams currency question, user-facing documentation drifts behind shipped features until a catch-up PR has to retro-document weeks of merges (see PR #252 in this session). All three failures have happened in production this session (see §7). Per user direction 2026-05-19: *"PRs should have issues with them always... and assigned to the project. both of these are requirements for a PR."* + *"we need to make sure our diagrams, and documentation is up to date... we should be asking the question if documentation or diagrams need to be created or updated."* Three equal-weight gates; no exceptions.

## 2. The contract

| Requirement | Mechanism | Enforced by |
|---|---|---|
| PR closes a tracking issue | PR body contains `Closes #<N>` (case-insensitive) | This skill (pre-flight) + AGENTS.md gate 5 + `.claude/settings.json` PreToolUse hook on `gh pr create` |
| PR is on `Catalyst Progress` board | `gh project item-add 3 --owner Cloud-Byte-Consulting --url <pr-url>` runs immediately after `gh pr create` | This skill (post-create) + AGENTS.md gate 5 (refusal trigger if skipped) |
| Docs / diagrams currency answer recorded | PR body carries an explicit yes/no answer to the docs/diagrams update question, with surfaces named and either included-in-PR or filed-as-follow-up references | This skill (§4.5) + AGENTS.md gate 5 (silence is a refusal trigger) |

All three must pass. Refuse to call `gh pr create` if the body lacks `Closes #<N>`, lacks an explicit docs/diagrams answer, or if the project-add will not be run in the same shell session. Refuse to consider a PR "open" until the project-add succeeds and `gh pr view --json projectItems` returns a non-empty list.

## 3. Canonical identifiers — Catalyst Progress project

Hard-coded; do not look these up at runtime:

| Field | Value |
|---|---|
| Owner | `Cloud-Byte-Consulting` |
| Project number | `3` |
| Project name | `Catalyst Progress` |
| Project node id (Projects v2) | `PVT_kwDOCVeAzM4BXpsF` |

The `gh project item-add` CLI takes the **project number** (`3`), not the node id. The node id is recorded here for GraphQL-level work (e.g. cross-checks or backfills) and to disambiguate from any future project with a colliding number.

## 4. Workflow

The literal shell sequence the agent runs around `gh pr create`. Copy-paste-edit; do not paraphrase.

```bash
# 1. Confirm issue exists
gh issue view <N> --repo Cloud-Byte-Consulting/Catalyst

# 2. Open PR with the Closes link in the body file
gh pr create --base release \
  --title "..." \
  --body-file <body-with-Closes-#N>.md

# 3. Assign to Catalyst Progress (project #3)
PR_URL=$(gh pr view --json url --jq .url)
gh project item-add 3 --owner Cloud-Byte-Consulting --url "$PR_URL"

# 4. Verify
gh pr view --json projectItems --jq '.projectItems'  # must be non-empty
```

Failure modes and recoveries:

- Step 1 fails (`gh issue view` 404): the tracking issue does not exist. **Stop.** File the issue first, then resume. Never open a PR against a fictitious issue number.
- Step 2 succeeds but body lacks `Closes #<N>`: amend the PR body with `gh pr edit <PR#> --body-file <fixed>.md` before continuing. The PreToolUse hook (Layer 4) should have caught this; if it did not, file a bug against the hook.
- Step 3 fails: retry once; if still failing, check `gh project list --owner Cloud-Byte-Consulting` to confirm project #3 is reachable. Do not call the PR "open for review" until step 4 passes.
- Step 4 returns `[]`: the project-add silently no-oped. Re-run step 3 with the exact URL from `gh pr view --json url`.

## 4.5. The docs / diagrams currency question

Before step 2 (`gh pr create`), walk this rubric and write a `## Docs & diagrams` section into the PR body containing either:

- `**Yes** — <surface(s)> updated in this PR` (with file paths), OR
- `**Yes** — <surface(s)> will be updated in follow-up #<N>` (with the filed follow-up issue), OR
- `**No** — <one-sentence reason>` (an explicit, deliberate no — silence does not count)

### Surfaces to consider

| Surface | What it covers |
|---|---|
| `README.md` | Project overview, deploy steps, "Recently shipped" highlights, test-coverage gate |
| `DECISIONS.md` | ADR index (every ADR file should appear here) |
| `docs/ADR/` | Architecture decision records (one per material design choice) |
| `docs/onboarding/platform.md` | Operator (cloud / platform engineer) runbook |
| `docs/onboarding/organization.md` | Tenant / LZ / environment registration |
| `docs/onboarding/application.md` | App-developer onboarding for new endpoints + flows |
| `docs/demo-script.md` | 6-minute panel walkthrough; KMS / Aurora / autoscaling / etc. callouts |
| `docs/ai-workflow-narrative.md` | AI-assisted workflow demonstrations with PR citations |
| `diagrams/control-plane.md` + `.drawio` assets | Architecture diagrams (CMK boundaries, runtime paths, data plane) |
| Inline mermaid diagrams in `docs/` | Often the right place for a sequence diagram or a small state machine |

### Decision rubric

| Change shape | Likely needs |
|---|---|
| New endpoint / API surface | `README.md` "Recently shipped" + `docs/onboarding/application.md` + OpenAPI/code annotation |
| New Terraform module | New or updated ADR + `docs/onboarding/platform.md` operator runbook + maybe `diagrams/control-plane.md` |
| New role / IAM change | `docs/ADR/ADR-008-catalyst-api-rbac.md` |
| New runtime path / architectural change | `diagrams/control-plane.md` + relevant ADR |
| New CI workflow | `README.md` + `docs/onboarding/platform.md` Verification section |
| Bug fix touching no public surface | "No" — explicit |
| Test-only PR | "No" — explicit |
| Doc-only PR | "No" (the changes ARE the docs) — explicit |
| Tooling / config-only PR | "No" unless it changes the operator-facing surface |

### Recording convention

Add this section to every PR body, immediately after the `## Scope` block:

```markdown
## Docs & diagrams

**Yes / No / Follow-up #N — <reason or paths>**

- `<file/path>` — <what was updated or why no update was needed>
```

If filing a follow-up: do it BEFORE `gh pr create`, and reference the new issue number in this section. The follow-up issue itself goes on the Catalyst Progress board per the contract above.

## 5. Scope-expansion case

If an agent is about to push a commit on an existing PR branch that **expands scope beyond the original tracking issue**, the rule is:

1. **File a new issue** capturing the expansion (Context / Scope / Gherkin shape per `issue-execution-gherkin-workflow`)
2. **Cross-link** the new issue from the PR via `gh pr comment <PR#> --body "Scope expansion: see #<new-issue>"`
3. *Then* push the expansion commit

If the agent already pushed the expansion commit without filing the issue first (mid-stream drift), the retroactive recovery is: file the issue + post the cross-link comment as soon as the drift is noticed. Retroactive recovery is acceptable but not the habit — the habit is "file first, push second".

The signal for "this is a scope expansion, not a fix" is: the commit touches a file or behavior the original issue's Scope section does not name. If you cannot point at the original issue's Scope and say "this commit lands work named here", it is an expansion.

## 6. Anti-patterns

| Pitfall | Fix |
|---|---|
| Opening a PR with "tracks #N" or "relates to #N" instead of `Closes #N` | Use `Closes` — only `Closes/Fixes/Resolves` trigger GitHub auto-close. The audit trail breaks otherwise. |
| Calling `gh project item-add` with the project node id instead of the number | The CLI takes the number (`3`). Node id is for GraphQL. |
| Assigning to a project after the PR has been open for hours/days | Forward-looking is the policy from this PR onwards; the queue depends on same-session assignment. Late assignment defeats the working-board signal. |
| Pushing scope-expansion commits without filing a new issue | File first, push second. Retroactive recovery is acceptable once; not the habit. |
| Treating Layer 4 (the hook) as the primary enforcement | The skill is primary (cross-tool); the hook is a Claude-Code-only mechanical backstop on the issue-link half only. |
| Opening a PR and then "I'll add the project assignment later" | Later does not happen. Do it in the same shell session, before any merge call. |
| Skipping step 4 verification | The `gh project item-add` call has been observed to silently no-op when the URL is wrong. Always verify. |

## 7. Worked example — recovery pass, this session (2026-05-19)

Real run of the drift this skill exists to prevent.

**Drift observed:** three open PRs (#258, #261, #263) carried `Closes #N` correctly in their bodies but were not on the Catalyst Progress board. Separately, commit `9dbfcc3` was pushed to PR #261's branch as a scope expansion (env loader) without first filing an issue.

**Recovery:**

1. Three `gh project item-add 3 --owner Cloud-Byte-Consulting --url <url>` calls — one per PR. Verified each via `gh pr view <PR#> --json projectItems`.
2. Filed issue #264 retroactively capturing the env-loader expansion. Posted a `gh pr comment 261 --body "Scope expansion captured retroactively in #264"` cross-link.
3. Filed issue #265 (this issue) to make the whole contract durable so the recovery doesn't recur.

**Lesson:** the recovery cost three minutes per PR plus the meta-work of filing #264 and #265. The skill exists so the next agent runs the four-step workflow in §4 once, in-line, at PR-create time, and never needs the recovery pass.

Use this section as the canonical "what to do if you forget" reference. If you find yourself doing the recovery pass, the skill failed to fire at the right moment — file a follow-up to harden it.

## Related

- `AGENTS.md` gate 5 — the refusal-trigger augmentation that names this skill
- `skills/pr-review-triage/SKILL.md` — the closing-side counterpart (this skill *opens*; that one *closes*)
- `skills/issue-execution-gherkin-workflow/SKILL.md` — the issue-shape that step 1 verifies exists
- `.claude/settings.json` PreToolUse hook on `Bash` — **deferred to a follow-up issue**. The Claude Code auto-mode classifier blocked the agent from writing `.claude/settings.json` (self-modification of agent configuration). Landing the hook requires a user-authorized pass. When it ships it will be a mechanical backstop on `gh pr create` (Claude Code only; Cursor has no equivalent surface) that greps the `--body-file` payload for `Closes #<N>` and refuses the Bash invocation if missing. The project-add half of the contract cannot be enforced by the same hook (it runs after `gh pr create`); the skill + AGENTS.md gate cover that asymmetry.
