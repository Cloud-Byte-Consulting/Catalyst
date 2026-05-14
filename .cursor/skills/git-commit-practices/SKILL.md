---
name: git-commit-practices
description: >-
  Git commit and branch practices for Catalyst that satisfy the challenge's
  "good Git practices" requirement and the 10% docs/commit-history evaluation:
  conventional commits, atomic single-concern changes, why-not-what messages,
  AI co-authorship trailers, branch naming, signed commits, no force-push,
  merge vs squash decisions. Use when authoring commits, reviewing PRs, or
  configuring repository policies.
---

<!-- Vendored from: platform-catalyst/.cursor/skills/git-commit-practices/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Git commit practices

## Role

You guide every contributor (human or AI) to produce commits that satisfy the challenge PDF's "good Git practices" line and the 10% docs/commit-history evaluation criterion. You enforce the safety protocols in `AGENTS.md` (no force-push, no `--no-verify`, no destructive operations without explicit consent) and the Honda Construct principle from the Kaizen log (**`type/kaizen`** Issues + `KAIZEN.md` archive: each commit is one car body on the line — visible, atomic, traceable).

## References

### Research

- *DevOps Unleashed with Git and GitHub* (Packt) — `local/research/devopsunleashedwithgitandgithub.pdf`: branching strategies, commit hygiene, PR workflows, conventional commits, semantic versioning.

### Repo sources of truth

- `AGENTS.md` §"Git Safety Protocol" — never update git config, no force-push to main, no `--no-verify`, no destructive operations without explicit user consent
- `AGENTS.md` §"Committing changes with git" — HEREDOC commit messages, Co-Authored-By trailer for AI assistance
- **`type/kaizen`** GitHub Issues — every merged PR that changed a standard opens (or updates) one Kaizen issue; `KAIZEN.md` is format + archive
- Senior Platform Engineer Project PDF — "good Git practices" + 10% docs eval includes "commit history"

### External

- Conventional Commits 1.0.0: https://www.conventionalcommits.org/
- Git documentation: https://git-scm.com/doc

## Challenge alignment

This skill produces evidence for the **10% Communication & Documentation** rubric ("commit history" as evaluation signal). The PDF explicitly asks to "maintain good Git practices" and notes "iterative value delivery" as a team value — small, frequent, meaningful commits demonstrate that iteration directly.

## Instructions

### 1. Conventional Commits format

Every commit subject line follows:

```
<type>(<scope>): <imperative summary, lowercase, no period>

<optional body — WHY this change, not WHAT>

<optional footer trailers>
```

**Allowed types:**

| Type | When to use |
|------|------------|
| `feat` | New user-facing capability |
| `fix` | Bug correction |
| `refactor` | Code restructure with no behavior change |
| `perf` | Performance improvement |
| `test` | Add or correct tests only |
| `docs` | Documentation only |
| `chore` | Tooling, dependencies, build config |
| `ci` | CI/CD pipeline changes |
| `style` | Whitespace/formatting only (rare; ruff usually handles) |
| `revert` | Revert a previous commit |

**Scopes** (Catalyst conventions): `api`, `lambda`, `infra`, `ci`, `docs`, `cli`, `mcp`, `bedrock`, `state-machine`, `score`, `iam`. Use one per commit when scope is meaningful; omit if the commit truly spans concerns (rare — usually means the commit isn't atomic).

**Examples:**

```
feat(api): add construct-scoped deployments endpoint

Customers need to request deploys without hand-editing Terraform.
This adds POST /v1/.../applications/{app}/deployments which validates
the Score spec, opens a state/pending Issue, and returns the issue
URL for status polling.
```

```
fix(lambda): handle empty SQS batch in webhook-handler

Powertools BatchProcessor returned an empty list when the FIFO queue
drained mid-poll. The handler crashed on the subsequent metric emit.
Guard the metric call and return early.
```

```
refactor(state-machine): extract legal-transitions table to module

Pulled the transition map out of state_machine.py into transitions.py
so the OPA policy can import the same constants. No behavior change.
```

### 2. Atomic single-concern commits

One commit = one logical change. If you can't describe it without "and", split it.

**Bad:**
```
feat(api): add deployments endpoint and fix idempotency bug
```

**Good (two commits):**
```
fix(api): idempotency key collision on concurrent retries
feat(api): add construct-scoped deployments endpoint
```

If you discover unrelated cleanup mid-work, either:
- Commit the cleanup separately *before* your feature work
- Stash, do the cleanup on `main`, rebase

**Never** bundle "while I was in there" changes into a feature commit. Reviewers cannot bisect what they cannot separate.

### 3. Commit message body: WHY, not WHAT

The diff shows WHAT. The body explains WHY. Reviewers and future maintainers need motivation, constraints, alternatives considered.

**Bad body:**
```
This commit adds a new endpoint to the deployments router.
It accepts POST requests and returns 201 on success.
```
(Restates the diff.)

**Good body:**
```
Customers asked for status polling without webhooks because some
CI runners block outbound webhooks. Status polling avoids the
firewall problem and aligns with the existing /v1/.../status pattern
used by deploys and previews.

Considered: SSE streaming. Rejected because the API gateway adds
a 30s idle timeout and reconnect logic complicates the CLI client.
```

### 4. AI co-authorship trailer

When an AI assistant contributed substantive work, add a trailer per `AGENTS.md`:

```
feat(api): add deployments endpoint

<body explaining WHY>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Place the trailer at the end of the message, separated by a blank line. Do not add it for trivial assists (single-line typo fixes, format-on-save). Add it when the AI authored a function, designed a module, or made a non-trivial decision.

### 5. Branch naming

Pattern: `<type>/<short-slug>` where type matches conventional commit types.

| Pattern | Use for |
|---------|---------|
| `feat/<slug>` | New feature work |
| `fix/<slug>` | Bug fix |
| `chore/<slug>` | Tooling, deps, config |
| `refactor/<area>-<intent>` | Refactor scoped to an area |
| `docs/<slug>` | Documentation-only changes |
| `ci/<slug>` | CI/CD pipeline changes |

**Rules:**
- Lowercase, kebab-case, no underscores
- Slugs are 2-4 words: `feat/score-translator`, `fix/state-machine-race`, `chore/bump-pydantic-2.10`
- Single-purpose branches — one PR each
- Never branch directly from a feature branch unless explicitly stacking; rebase on `main` before merging

### 6. Force push and main protection

Per `AGENTS.md` Git Safety Protocol:

- **Never** `git push --force` to `main` / `master` — even if the user asks, warn first
- Use `git push --force-with-lease` on personal feature branches only (safer — fails if remote moved)
- Never `--no-verify` to skip hooks — fix the hook failure
- Never `--no-gpg-sign` / `-c commit.gpgsign=false` unless the user explicitly opts out
- Never amend a pushed commit unless explicitly requested

### 7. Signed commits

If the user has GPG or SSH commit signing configured (`git config commit.gpgsign true`), respect it. Never bypass signing. If signing fails:

1. Read the error — usually a missing key, expired key, or wrong agent
2. Surface the error to the user
3. Wait for direction — do NOT disable signing as a workaround

### 8. Squash vs merge vs rebase

| Strategy | When to use |
|----------|------------|
| **Squash & merge** | Default for feature PRs. The PR body becomes the squash commit message. Keeps `main` linear and meaningful. |
| **Merge commit** | When the branch history is itself valuable (e.g., a refactor done in reviewable steps that you want preserved). Rare. |
| **Rebase & merge** | When you want each commit on the branch to land on `main` individually. Use when commits are already atomic and well-formed. |

For Catalyst: squash is the default. The PR description carries the WHY; individual review commits become noise after merge.

### 9. PR title and description

PR title follows the same convention as the squash commit subject. PR description should:

- Open with 1-3 sentence summary of WHY (the motivation)
- Include a `## Test plan` section (markdown checklist of how the change was verified)
- Link related Issues with `Closes #N` or `Refs #N`
- Mention any ADR added or changed
- Note any **`type/kaizen`** Issue if the change altered a standard

Example PR description:

```markdown
## Summary
Customers can now request deploys without hand-editing Terraform.
Score validation happens both client-side (catalyst CLI) and
server-side (catalyst-api); the API is authoritative.

## Test plan
- [x] Unit tests for ScoreValidator (`tests/unit/test_score.py`)
- [x] Integration test against moto-mocked Aurora
- [x] Manual: `catalyst submit ./score.yaml --tenant pharmacy --env dev`
- [x] Confirmed state/pending Issue created with construct-address labels

Closes #42
Refs ADR-002 (construct hierarchy)

🤖 Generated with Claude Code
```

### 10. Kaizen updates

Per `AGENTS.md`: if the PR changed a standard (new policy, new convention, workflow change), open a **`type/kaizen`** GitHub Issue (Kaizen template) describing what changed and the leading indicator. This keeps the operational history queryable without re-reading 200 commits.

## Output

When asked to help with commits:

- **New commit**: type + scope + subject + body draft, with WHY focus
- **PR description**: summary + test plan markdown + linked issues
- **Branch name**: kebab-case slug matching the work
- **Pre-commit issue**: diagnose the hook failure and fix it (never bypass)
- **History audit**: identify non-atomic commits, missing trailers, force-pushed branches

## Guardrails

- **Never** `git push --force` to protected branches; warn the user even if asked
- **Never** `git commit --no-verify` — fix the hook failure
- **Never** `git config` updates that change signing, hooks, or remote behavior without explicit user consent
- **Never** rewrite published history (`rebase -i` on pushed commits) unless explicitly requested
- **Never** include secrets in commit messages — `.env`, credentials, tokens
- HEREDOC the commit message body to preserve formatting (per `AGENTS.md`)
- One concern per commit — if you used "and" to describe it, it's two commits
- Body explains WHY; diff already shows WHAT
