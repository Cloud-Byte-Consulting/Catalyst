---
name: test-coverage-discipline
description: Enforces the Catalyst rule that code changes ship with matching test updates AND route to the right component-scoped CI job. Use when implementing a feat/fix/kaizen that touches code paths, or during /pr-review-triage to verify the changed-paths-to-CI-job map is honored. Covers the full-suite override mechanisms (workflow_dispatch + `FORCE_ALL_TESTS=true` repo var + `force-all-tests` PR label).
---

# test-coverage-discipline

Codifies the Catalyst convention that every code change ships with a matching test update AND that CI runs the right subset of jobs for the changed paths — not every job on every PR. The goal: fast PR feedback (under 90 s for a typical single-component PR) without losing regression coverage; a deliberate full-suite escape hatch when a change has wide blast radius.

## When to use

- Implementing a `feat(*)`, `fix(*)`, or `kaizen(*)` PR that touches code (not pure docs)
- During `/pr-review-triage` step 7 — verify the changed-paths CI map is honored (no test job silently skipped)
- After scaffolding a new module / component — register its path → test-file → CI-job mapping in `.github/workflows/pr-checks.yml` (or wherever path-filters live)

## When NOT to use

- Pure-docs PRs (`docs(*)`, ADR amendments, README, `docs/onboarding/*`) — no tests required
- Skill / process artifact PRs (`.claude/skills/*`, AGENTS.md edits) — no tests required
- Generated files (lockfiles, image SHAs) — no tests required

## The component → test → CI-job map (canonical)

This map is the single source of truth for "what tests run when X changes." Keep it in lockstep with `.github/workflows/pr-checks.yml`'s `paths-filter` config.

| Changed-path glob | Test file(s) | CI job |
|---|---|---|
| `services/catalyst-api/**` | `services/catalyst-api/tests/test_*.py` | `python-tests` + `Analyze (python)` |
| `services/catalyst-api/**` AND tests touch e2e surfaces | `tests/e2e/test_journey_*.py` | `e2e-tests` (fast mode) |
| `clients/catalyst-cli/**` | `clients/catalyst-cli/tests/test_*.py` | `cli-tests` |
| `infrastructure/**` (TF code) | `infrastructure/tests/*.tftest.hcl` + per-module `tests/` dirs | `terraform-quality` + `Terraform` |
| `.github/workflows/**` | (validated by actionlint) | `actionlint` + `workflow-structure` |
| `.cursor/**` | (config validated by JSON-schema lint) | `cursor-config` |
| `scripts/bootstrap-aws-account.*` | `scripts/tests/test_bootstrap_scripts.py` | `bootstrap-script-tests` |
| Policy files (`policies/**`, `*.rego`, `*.cue`) | `policies/tests/**` | `conftest` |
| Any code change to a Tier 1 / Tier 2 surface | `tests/e2e/test_journey_*.py` | `e2e-tests` (fast mode, mock AWS) |

When a PR touches **multiple** path globs, **all matching jobs run**. The `dorny/paths-filter@v3` setup handles this naturally.

## Discipline — three rules

### Rule 1: change in component X means test file(s) for X get updated in the same PR

When implementing a code change:

1. Identify the changed-path glob from the map above
2. Open the test file(s) for that component
3. Add or update at least one case that exercises the new code path
4. If the change crosses a component boundary (e.g. API + CLI both change), update both test surfaces

This is enforced by code review (peer-review sub-agent / `/pr-review-triage`), not by CI — CI verifies that tests *pass*, not that tests were *updated*.

**Anti-pattern**: shipping a `feat(api)` PR that touches `services/catalyst-api/catalyst/main.py` but doesn't add a corresponding case to `services/catalyst-api/tests/test_*.py`. Triage flags this as a REJECT-deferred or DEFERRED-ARCH if the reviewer thinks tests should follow.

### Rule 2: CI runs ONLY the component-scoped jobs for changed paths

The `pr-checks.yml` workflow uses `dorny/paths-filter@v3` at the top to compute a set of booleans (`python_changed`, `cli_changed`, `infra_changed`, etc.). Each job's `if:` condition gates on the matching boolean.

A PR that only touches docs runs nothing but `cursor-config`. A PR that only touches `services/catalyst-api/` runs `python-tests` + `Analyze (python)` + (if e2e surface) `e2e-tests`. **Median PR runtime in CI drops from ~2 minutes to ~30 seconds.**

The required-status-check posture (per #72 branch protection) is rooted on a **`test-summary`** aggregator job — NOT on the individual conditional jobs. `test-summary` runs `if: always()`, depends on every conditional job, and fails if any of them failed. This way:
- A skipped job (because its paths didn't match) doesn't block merge
- A failed job (because its tests broke) does block merge
- The single required check is `test-summary`

### Rule 3: full-suite override exists for wide-blast-radius changes

Three ways to force every job to run regardless of changed paths:

1. **`workflow_dispatch` on `full-suite.yml`** — manual button-press from the Actions tab. Use when:
   - You changed something subtle that affects multiple components (e.g. a Pydantic model shape used by the CLI)
   - Pre-cutover validation before a major release
   - Debugging a flaky test that only fails under specific path-filter combinations
2. **Repository variable `FORCE_ALL_TESTS=true`** — flip it in repo settings to force the full suite on every PR for a period. Use when:
   - You're shipping a wide refactor across multiple PRs and want belt-and-suspenders coverage on each
   - Right before a release cut
3. **PR label `force-all-tests`** — apply the label to a specific PR. The `pr-checks.yml` workflow reads `github.event.pull_request.labels.*.name` and short-circuits its path-filter. Use when:
   - One PR touches multiple components but path-filter misclassifies (rare; flag this and update the map)
   - The change is small but you want full reassurance

Pick the narrowest scope that gives you what you need. Most changes shouldn't need any override.

## Adding a new component to the map

When scaffolding a new top-level component (a new `services/*`, a new `clients/*`, a new `infrastructure/modules/composite/*` that needs its own gate):

1. **Decide the path glob** that owns the component
2. **Decide the test directory** and the canonical test-file naming pattern
3. **Add a path-filter entry** to `.github/workflows/pr-checks.yml`'s top filter block
4. **Add an `if:` gate** to the matching CI job (or create a new job if the component needs its own runner)
5. **Wire the new job into `test-summary`'s `needs` list** so branch protection still gates correctly
6. **Update this skill's map table** in the same PR

Don't ship a new component without registering it here. CI will run the new component's tests on every PR (wasted runner time) until the map is updated.

## /pr-review-triage interaction

When triage runs (see `/pr-review-triage` skill), step 7 ("Synchronize issue metadata") should also verify:

- Every changed top-level path glob has its corresponding CI job in the PR's check run
- If a job is **skipped** because the path-filter excluded it, that's correct
- If a job is **missing entirely** from the check run, the path-filter map is out of date — flag as a follow-up kaizen
- If a code change shipped without a matching test update, flag as a DEFERRED-ARCH thread asking the human to confirm "tests deferred to a follow-up"

The triage skill doesn't enforce Rule 1 mechanically (CI can't tell that a code change "should have" had a test update). It does enforce Rule 2 (path-filter correctness) and Rule 3 (full-suite override applied when appropriate).

## Anti-patterns

| Pitfall | Fix |
|---|---|
| Running every CI job on every PR | Use `dorny/paths-filter` + per-job `if:` conditional |
| Marking every conditional job "required" in branch protection | Make `test-summary` the only required check; let conditionals skip safely |
| Forgetting to update the map when adding a new component | The skill ensures the map is the single source of truth — update in the same PR as the scaffold |
| Using `force-all-tests` on every PR "to be safe" | Defeats the optimization. Use only for wide-blast-radius changes. |
| Skipping test updates because "the change is small" | If the code change is small enough not to need a test update, it's probably a docs / formatting / refactor change — those have their own scopes (`docs(*)`, `style(*)`, `refactor(*)`). Code changes get tests. |

## Worked example — applying Rule 1 to PR #199

PR #199 added per-endpoint Pydantic models (`LandingZoneCreateRequest`, etc.) to `services/catalyst-api/catalyst/models.py`. Per Rule 1:

- Changed path: `services/catalyst-api/**`
- Test file to update: `services/catalyst-api/tests/test_api.py`
- New cases added: per-endpoint malformed-input cases, per-endpoint field-coverage cases, `extra="forbid"` rejection cases

The agent added 32 new test cases alongside the model changes. /pr-review-triage step 7 confirmed the python-tests CI job ran AND passed. Coverage went from 88% → 92.27%. **Rule 1 satisfied in the same commit graph** — no "tests coming later" pretense.

## Related

- `/pr-review-triage` skill — closes the loop on review comments (Rule 2 verification happens in its step 7)
- AGENTS.md gate-5 (peer review) — informs the "tests-must-ship-with-changes" cultural expectation
- ADR-006 — CI/CD pipeline architecture (the workflow files this skill governs)
- `.github/workflows/pr-checks.yml` — the path-filter implementation
- `.github/workflows/full-suite.yml` — the workflow_dispatch escape hatch
- `tests/e2e/` — the cross-component journey suite from #207
