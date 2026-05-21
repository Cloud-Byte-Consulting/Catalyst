---
name: pr-review-triage
description: Triage all unresolved review comments on a Catalyst PR — read each comment, classify as ACCEPT / REJECT / DEFERRED-ARCH / STALE, apply fixes for ACCEPTs, reply with disposition on every thread, resolve everything except DEFERRED-ARCH, post a summary, and stop. Never merges. Use after Copilot, a human reviewer, or an automated bot has left feedback on an open PR; or as the closing step of gate 5 per AGENTS.md / ADR-011.
---

# pr-review-triage

Closes the loop on every reviewer comment so the PR is genuinely ready for a human merge call. Single PR per invocation. Sequential — the skill is the triage, not an agent spawner.

## Inputs

`/pr-review-triage <PR-number>` — operates on that PR.
`/pr-review-triage` — ask the user which PR.

## Disposition vocabulary

Every unresolved comment gets exactly one of these:

| Verdict | When | Action |
|---|---|---|
| **ACCEPT** | Concrete, valid fix the agent can apply now | Patch the code/doc, reply `ACCEPT — fixed in {sha}`, resolve thread |
| **REJECT** | Reviewer misread or out-of-scope for this PR | Reply with corrected reading + evidence, resolve thread. If material, file a follow-up issue and link it |
| **STALE** | Comment refers to code that has since changed | Reply noting the change + commit SHA where it landed, resolve thread |
| **DEFERRED-ARCH** | Raises a design question that needs human judgment | Reply with the ADR link + a one-line note of the human decision needed, **do NOT resolve** |

Conversation-only comments ("looks good") need no disposition.

## Workflow

The triage runs as nine steps. Steps 1-2 establish facts; step 2.5 challenges the facts; steps 3-9 act on what survives.

### 1. Discover

Get every unresolved review thread + every top-level issue comment, with author + path + line + body. The GraphQL `reviewThreads` query is the only reliable source for thread IDs needed by the resolve mutation.

```bash
gh api graphql -f query='
query($owner:String!, $repo:String!, $pr:Int!) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$pr) {
      reviewThreads(first:50) {
        nodes {
          id
          isResolved
          isOutdated
          comments(first:5) {
            nodes { databaseId author { login } path line body }
          }
        }
      }
    }
  }
}' -F owner=Cloud-Byte-Consulting -F repo=Catalyst -F pr=<PR#>
```

```bash
gh pr view <PR#> --repo Cloud-Byte-Consulting/Catalyst --json comments \
  --jq '.comments[] | {author: .author.login, snippet: (.body | .[0:150])}'
```

Filter out comments from yourself (the agent) — those don't need re-disposition. Filter out `github-actions` workflow warnings unless they're actionable.

### 2. Classify

For each unresolved thread, decide the verdict. Use these signal phrases as flags for DEFERRED-ARCH:

- "should we [redesign / refactor / split / merge]"
- "is this the right abstraction"
- "does this conflict with ADR-N"
- "consider if we instead..." (when "instead" implies a different design)
- Anything that questions the PR's *premise* rather than its *execution*

A comment that points at a *concrete line* with a *specific change* is almost always ACCEPT or REJECT, not DEFERRED-ARCH. Don't escalate to the human what the agent can settle.

### 2.5. Skeptic pass — second opinion on ACCEPTs and DEFERRED-ARCHes

After classifying but **before** acting, run a skeptic pass on each ACCEPT and DEFERRED-ARCH disposition. The skeptic is a fresh sub-agent (`Agent` tool, `subagent_type: general-purpose`) that doesn't see the triage agent's reasoning — only the raw inputs — and either CONFIRMs the classification or CHALLENGEs it.

The skeptic catches two recurring failure modes:

1. **Over-eager ACCEPTs** — the triage agent agrees with the reviewer too readily, applies a fix that papers over a deeper issue or that wasn't actually needed.
2. **Punted DEFERRED-ARCHes** — the triage agent escalates to the human something the agent could have settled with one more lookup.

The skeptic is NOT invoked on REJECT or STALE — those verdicts are factual claims (reviewer misread the code; commit already addressed it) that are cheap to verify in the reply text. Spawning a skeptic for them is wasted context.

#### 2.5a — Skeptic prompt for ACCEPTs

Spawn one sub-agent per ACCEPT thread (or batch when threads share a file and a theme — see below). Prompt template:

```
You are the skeptic for /pr-review-triage. Read the reviewer's comment and the planned fix critically. Either CONFIRM (and explain in one sentence why the fix is right and minimal) or CHALLENGE (and explain why + suggest the better disposition).

Reviewer comment:
<full comment body>

File: <path>:<line>
Current code (5 lines of context):
<git show ${PR_BRANCH}:${path} | sed -n '${line-2},${line+2}p'>

Planned fix (your view of what the triage agent intends to write):
<short description + diff sketch>

Answer one of:
- CONFIRM — one sentence rationale.
- CHALLENGE — why the fix is wrong / over-broad / papering over deeper issue, AND the better verdict (REJECT, DEFERRED-ARCH, or a different ACCEPT-fix). Cite specific evidence (line numbers, ADR sections, test cases).

Bias toward CHALLENGE when the fix changes behavior beyond what the reviewer asked for, or when the reviewer's premise is actually questionable.
```

If the skeptic CONFIRMs: proceed to §3 (apply fix). If it CHALLENGEs: re-classify and reply on the thread with the new verdict + reference the skeptic's reasoning in the disposition body.

**Batch when possible**: if three ACCEPTs all touch the same file with the same kind of fix (e.g. three "remove `iam:*`" findings), spawn one skeptic per file, not per thread. Same context, one cost.

#### 2.5b — Skeptic prompt for DEFERRED-ARCHes

DEFERRED-ARCH is expensive — every escalation costs the human time and decision-cycles. The agent should settle anything decidable. The skeptic pushes back specifically on the escalation premise:

```
You are the skeptic for /pr-review-triage. The triage agent classified this comment as DEFERRED-ARCH (escalating to human review). Your job: push back. Is this really a design question the agent can't settle?

Reviewer comment:
<full comment body>

File: <path>:<line>
Triage agent's reasoning for escalation:
<short rationale>

Linked ADR/spec the agent cited (if any):
<link + relevant ADR section excerpt>

Answer one of:
- CONFIRM-ESCALATION — explain why no agent-resolvable answer exists. The reviewer is asking about a genuinely undetermined design choice (one not covered by existing ADRs / specs / past decisions).
- CAN-SETTLE — propose the concrete next action that resolves this without human input. Common patterns:
  * "Read ADR-N §X — the answer is there."
  * "The pattern in module Y already establishes the convention."
  * "Pick the option that matches the most recently shipped PR (#NNN)."
  * "Reply with the agent's preference + rationale; mark as ACCEPT-with-justification."

Bias toward CAN-SETTLE. The agent should escalate ONLY when escalation is the cheapest correct action — not when the agent is hedging.
```

If CONFIRM-ESCALATION: proceed to §4 (reply with DEFERRED-ARCH; leave unresolved). If CAN-SETTLE: re-classify (usually to ACCEPT) and proceed accordingly.

#### Skeptic-pass mechanics

- The skeptic sub-agent is spawned via the `Agent` tool with `subagent_type: general-purpose` (no `isolation: worktree` — it's read-only)
- One sub-agent per thread (or per-batch when threads share a file + theme)
- Report-back: under 100 words per thread. CONFIRM / CHALLENGE / CONFIRM-ESCALATION / CAN-SETTLE verdict + one-paragraph rationale + (for CHALLENGEs / CAN-SETTLEs) the concrete next action
- The triage agent integrates the skeptic's response into its own disposition reply when relevant — quote one sentence from the skeptic to show the second-pair-of-eyes was real

#### When to skip the skeptic

- Pure-STALE pass (every unresolved thread is outdated) — nothing to second-guess
- Threads that have been triaged before in the same session and the disposition is unchanged — re-running is redundant
- One-line typo/spelling fixes where the cost of the skeptic outweighs the value of the second opinion (judgment call — if the fix is < 3 chars changed, skip)

### 3. Apply fixes (ACCEPT cases)

- Switch to the PR branch — if an agent worktree owns it, edit there; otherwise `git switch <branch>` in the main repo
- Apply minimal, surgical edits — no adjacent refactors
- Run the relevant local gates: `pytest` for Python diffs, `terraform validate` + `terraform test` for TF diffs, markdown sanity for docs
- Batch related fixes into one commit when they share a file or theme. Keep history navigable
- Commit message format: `fix(<scope>): <what>` body explains *which Copilot/reviewer finding* triggered the fix + which PR it lives on. Co-author trailer with the agent name.
- Push (never amend a pushed commit)

### 4. Reply per-thread

Line-level review-comment reply (REST):
```bash
gh api -X POST repos/Cloud-Byte-Consulting/Catalyst/pulls/<PR#>/comments/<comment-databaseId>/replies \
  -f body="<disposition>"
```

Top-level issue comment — post a new comment on the PR (no per-thread reply primitive):
```bash
gh pr comment <PR#> --repo Cloud-Byte-Consulting/Catalyst --body "<disposition>"
```

Reply body MUST include:
- The verdict word (`ACCEPT` / `REJECT` / `STALE` / `DEFERRED-ARCH`)
- One sentence of rationale
- For ACCEPT: the commit SHA where the fix lands (link with backticks)
- For REJECT: cited evidence (line numbers, ADR sections, test cases)
- For STALE: the prior commit SHA that already addressed it
- For DEFERRED-ARCH: the ADR link + explicit "leaving this for human review" sentence

No "thanks for catching this" preamble. Direct verdict first.

### 5. Resolve threads

For ACCEPT / REJECT / STALE, resolve via:

```bash
gh api graphql -f query='
mutation($threadId:ID!) {
  resolveReviewThread(input:{threadId:$threadId}) {
    thread { id isResolved }
  }
}' -f threadId=<thread-id-from-step-1>
```

DEFERRED-ARCH threads stay unresolved — they're the artifact telling the human "decide before merging".

Top-level issue comments don't have a resolve primitive; disposition replies alone are sufficient.

### 6. Summary comment

One final top-level comment on the PR. Includes:
- Totals by verdict (`5 ACCEPT, 2 REJECT, 1 DEFERRED-ARCH, 1 STALE`)
- Commit SHAs that landed fixes, with one-line each on what they did
- DEFERRED-ARCH threads listed by file:line with a one-line summary of the human decision needed
- Post-fix CI status snapshot (`gh pr checks <PR#>` output)
- Explicit `Ready for human merge call.` line if no DEFERRED-ARCH, or `Awaiting human decision on N DEFERRED-ARCH thread(s) before merge.` if any

### 7. Synchronize issue metadata

Two pieces of issue metadata MUST be kept correct while a PR is in flight. Triage is the right place to enforce both because triage runs with the PR open and the branch known.

#### 7a. `state/*` label

| Situation | Required label |
|---|---|
| PR open, no unresolved DEFERRED-ARCH threads | `state/agent-working` |
| PR open, at least one DEFERRED-ARCH thread waiting on a human | `state/blocked-on-human` |
| PR merged or closed | label set by the merge contract (`Closes #N` auto-closes the issue; no further label change) |

NEVER leave an issue at `state/pending` if a PR exists for it — the open PR contradicts the "pending pickup" semantics of that label.

```bash
gh issue edit <issue#> --repo Cloud-Byte-Consulting/Catalyst \
  --remove-label "state/pending" \
  --add-label "state/agent-working"   # or state/blocked-on-human
```

If the issue lacks a `state/*` label entirely, add the appropriate one. If it carries both `state/pending` and one of the active states (drift from a previous triage), drop `state/pending`.

#### 7b. Branch named on the tracking issue

A reader opening the issue should be able to find the working branch without guessing the naming convention or clicking through to the PR. Two mechanisms exist; both are documented here because GitHub's native primitive only covers half the cases.

**GitHub's native `linkedBranches` (Development panel)** — useful but limited:

| When the branch is created via … | Behavior |
|---|---|
| `gh issue develop <issue#> --base release --name <branch>` | Branch + link created together. Appears in the Development panel automatically. **Preferred for new work.** |
| `git switch -c <branch>` in an agent worktree | No link. The branch is on origin but the issue's `linkedBranches` collection stays empty. |
| `gh pr create` referencing `Closes #N` | The PR is linked, the branch is **not**. Clicking through the PR shows the branch — indirect navigation. |

The `createLinkedBranch` GraphQL mutation is a *create* operation, not a *link* operation — passing the oid + name of an existing branch returns `linkedBranch: null` (silent noop). There is no API to retroactively link an already-existing branch to an issue as of 2026-05-18; only the web UI's "Link a branch" dropdown does that, and it has no CLI/MCP equivalent.

**Catalyst convention — Decision Log carries the branch name (always works):**

Every Decision Log posted to a tracking issue MUST name the branch explicitly:

```markdown
**Contract:**
- Branch from `origin/release` as `<branch-name>`
- ...
```

This is the navigable artifact regardless of GitHub's Development-panel state. Triage verifies the branch name appears in *some* comment on the issue; if not (drift from an older convention or a branch renamed mid-flight), the skill posts a one-line clarifying comment:

```bash
ISSUE_NUM=<issue#>
BRANCH=<branch-name>

if ! gh issue view "$ISSUE_NUM" --repo Cloud-Byte-Consulting/Catalyst --json comments,body \
     --jq ".body + \"\n\" + ([.comments[].body] | join(\"\n\"))" \
     | grep -Fq "$BRANCH"; then
  gh issue comment "$ISSUE_NUM" --repo Cloud-Byte-Consulting/Catalyst \
    --body "Working branch: \`$BRANCH\` (PR: <pr-url>). Recorded by /pr-review-triage so the branch is discoverable from this issue."
fi
```

**For future branches**, prefer `gh issue develop` upfront so both mechanisms light up — the branch lands in the Development panel AND the agent's Decision Log mentions it by name.

After the PR merges and the branch is auto-deleted, both mechanisms decay gracefully: GitHub drops the linked-branch record automatically, and the Decision Log comment stays as a historical record of where the work happened.

### 8. Stop

The skill never:
- Merges the PR (`gh pr merge`)
- Closes the PR
- Marks the PR ready/draft
- Marks DEFERRED-ARCH threads resolved
- Edits PR title or body (unless the title was wrong and the user told you so)

The skill always:
- Pushes commits if any fixes applied
- Leaves a single trail-end summary comment
- Synchronizes the tracking issue's `state/*` label (step 7a)
- Ensures the working branch is named in the issue (step 7b) — `gh issue develop` upfront when possible, otherwise a Decision-Log-style comment
- Reports back to the user with the merge readiness state

## Anti-patterns

| Pitfall | Fix |
|---|---|
| Replying "I'll consider this" | No — decide now. Every comment gets a verdict. |
| Bulk-resolving without per-thread replies | Each thread gets its own reply. The audit trail is the value. |
| Escalating concrete fixes to DEFERRED-ARCH | Read again. If the reviewer points at a specific line with a specific change, it's not architectural. The §2.5b skeptic catches this. |
| Skipping the skeptic pass to save time | The skeptic catches over-eager ACCEPTs and punted DEFERRED-ARCHes — both are *more* expensive to recover from than the skeptic cost. Skip only the cases in §2.5's "When to skip" list. |
| Auto-merging after the summary | Never. Stop at "ready for human merge call". |
| Reaching for fancy GraphQL for everything | Use REST (`pulls/{N}/comments/{C}/replies`) for line-comment replies. Use GraphQL only for `reviewThreads` discovery and `resolveReviewThread` mutation. |
| Filing a follow-up issue every time you REJECT | Only if the REJECT identifies a real problem that belongs in *another* PR. "Out of scope" alone doesn't mean "file an issue". |
| Skipping the summary comment | The summary is what lets the human approve at a glance. Always post it. |
| Amending a pushed commit | Make a new commit. The PR's commit history is part of the review record. |
| Letting the skeptic relitigate after CHALLENGE | The skeptic's verdict is final for the current pass. If the triage agent disagrees with the skeptic, log it in the disposition reply ("Skeptic challenged with X; triage agent stands by Y because Z") — but don't loop. The human can adjudicate at merge time. |

## Edge cases

**Outdated threads** (`isOutdated: true`): the comment refers to a line that has since been changed. Mark `STALE`, reply with the SHA that already addressed it, resolve. Don't re-implement what's already there.

**Threads with no `line` (file-level review)**: still process. Path-only context — the reviewer is commenting on the whole file. Apply the same verdict logic.

**Multi-comment threads**: read the whole thread before disposing. The reviewer may have already qualified the suggestion in a follow-up.

**Workflow / CI warnings posted as bot comments**: if it's a deprecation notice (e.g. github-actions warning about `dynamodb_table` → `use_lockfile`), classify as DEFERRED-ARCH if it requires touching pipeline files (separate PR concern), otherwise STALE if already addressed.

**Self-comments (your own gate-5 review summaries)**: skip — these aren't external feedback. Same for the dispositions you just posted.

**Architecture-disagreement chains**: if a reviewer pushes back on a DEFERRED-ARCH reply with more design points, do NOT relitigate. Add one more clarifying reply ("escalating to human") and leave it. Don't get sucked into a multi-turn design argument the human will want to have themselves.

## Worked example — PR #186 (this session, 2026-05-18)

> **Note**: this worked example predates §2.5 (skeptic pass). It documents a STALE-only triage, and STALE is on §2.5's *When to skip* list — so the skeptic step would not fire on this triage even today. A future worked example showing the skeptic catching an over-eager ACCEPT or punted DEFERRED-ARCH will be added once §2.5 actually fires in production triage.

A real run of this skill, abbreviated:

1. Discovery: 1 unresolved thread (Copilot, `test_rbac_parser.py` — dead `if False else` ternary). Marked `isOutdated: true` because commit `906420c` had already removed the ternary.
2. Classification: **STALE**.
3. No fix needed (already in `906420c`).
4. Reply: `STALE — already removed in 906420c during gate-5 peer review (commit predates this Copilot comment).`
5. Resolved the thread.
6. Summary: 0 ACCEPT, 0 REJECT, 0 DEFERRED-ARCH, 1 STALE. CI green. `Ready for human merge call.`
7. Stopped.

The example shows the skill applies cleanly even when the triage surface is small. The discipline is what makes the audit trail trustworthy, not the volume.

## Related

- AGENTS.md — gate-5 peer-review contract
- ADR-011 — six-gate operating workflow
- `skills/review-prompt-engineering/` — companion skill for *generating* reviews (this one *closes* them)
- `skills/github-state-machine/` — broader state-machine convention the gate-5 boundary plugs into
