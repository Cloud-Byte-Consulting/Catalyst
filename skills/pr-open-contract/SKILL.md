---
name: pr-open-contract
description: Hard gate before every `gh pr create` — verify the tracking issue exists, ensure the PR body carries `Closes #<N>`, then assign the PR to the Catalyst Progress GitHub Project (#3). Invoke this skill any time you are about to call `gh pr create`, push a scope-expanding commit to an existing PR branch, or notice a PR open without a project assignment.
---

# pr-open-contract

The opening-side counterpart to `pr-review-triage`. This skill is the hard gate every Catalyst PR passes through *before* it is created. Two checks; both required; neither optional.

## 1. Why

Without `Closes #<N>` in the PR body, scope drifts silently — the audit trail loses the link from "what we shipped" back to "what we agreed to ship", and GitHub's auto-close fails so the tracking issue lingers stale. Without a `Catalyst Progress` project assignment, the PR drops off the team's working board — reviewers don't see it on the queue and the kaizen feedback loop breaks. Both failures have happened in production this session (see §7). Per user direction 2026-05-19: *"PRs should have issues with them always... and assigned to the project. both of these are requirements for a PR."* Equal weight; both gates; no exceptions.

## 2. The contract

| Requirement | Mechanism | Enforced by |
|---|---|---|
| PR closes a tracking issue | PR body contains `Closes #<N>` (case-insensitive) | This skill (pre-flight) + AGENTS.md gate 5 + `.claude/settings.json` PreToolUse hook on `gh pr create` |
| PR is on `Catalyst Progress` board | `gh project item-add 3 --owner Cloud-Byte-Consulting --url <pr-url>` runs immediately after `gh pr create` | This skill (post-create) + AGENTS.md gate 5 (refusal trigger if skipped) |

Both must pass. Refuse to call `gh pr create` if the body lacks `Closes #<N>`. Refuse to consider a PR "open" until the project-add succeeds and `gh pr view --json projectItems` returns a non-empty list.

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
