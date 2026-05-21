# ADR-024 — Unified agent config (Cursor, Claude, Gemini) and GitHub Issue indexing

**Status**: Accepted · 2026-05-20  
**Related**: [ADR-001](ADR-001-github-issues-as-state-machine.md), [ADR-011](ADR-011-catalyst-agentic-workflow.md), [ADR-022](ADR-022-multi-tool-skill-layout.md), [`STATE-MACHINE.md`](STATE-MACHINE.md), [`docs/multi-tool-config.md`](../multi-tool-config.md)

## Context

Catalyst is a single application agent system (not a multi-repo coordinator like TRAPI/Cordillera). ADR-022 established canonical `skills/` and `agents/` trees with auto-generated stubs copied into `.cursor/`, `.claude/`, and `.gemini/`. That removed dual-maintenance between Cursor and Claude but still commits **~120 skill stubs and agent copies** per change — four on-disk copies of every skill, triple PR diffs, and Claude adapter files that duplicate full persona bodies with different frontmatter.

Separately, Catalyst's durable context lives in **GitHub Issues** (~300+ issues, structured comment headings, Gherkin AC) and ADRs — not in a static `knowledge-base/` tree. Agents need a **machine-queryable index** over that context. The repo already uses namespaced labels (`state/*`, `type/*`, `kind/*`) but also carries **legacy parallel vocabularies** (`Kind/*`, `Priority/*`, `Status/*`) and incomplete `kind/*` coverage on open work (~43 `kind/iac` vs ~74 `type/feat` in a recent sample). Construct anchor labels (`env/shared`, `lz/shared`) appear on most issues and add little search discrimination today.

The goal is to improve the agent system in place: one source of truth for skills and personas across Cursor, Claude Code, and Gemini CLI; GitHub Issues as the live knowledge layer; and a cleaned label vocabulary agents can search deterministically.

## Decision drivers

- **Single edit surface**: Authors must change one file per skill or persona, not three committed stubs.
- **Three-tool parity**: Cursor, Claude Code, and Gemini CLI must discover the same content without drift.
- **Issue-as-KB**: Tracking issues and audit comments are authoritative; labels index them for routing and search.
- **STATE-MACHINE integrity**: Label changes must not break exclusive-group rules or webhook enforcement in `services/catalyst-api/catalyst/state_machine.py`.
- **Cross-platform contributors**: Any wiring mechanism must work on macOS/Linux and degrade gracefully on Windows (ADR-022 symlink probe).

## Considered options

### 1. Keep ADR-022 committed stubs + `sync_tool_skills.py` (status quo)

- **Pro**: Already implemented; CI enforces drift; works on Windows without symlinks.
- **Pro**: No bootstrap step after clone.
- **Con**: Three committed copies per skill; PR noise; Claude adapters duplicate persona bodies.
- **Con**: Gemini stubs not yet guarded by CI the same way as Cursor/Claude.

### 2. Git-tracked symlinks from tool trees to canonical paths

- **Pro**: Literally one file on disk; zero sync script for content.
- **Con**: ADR-022 rejected for Windows (`core.symlinks=false` on MSYS git).
- **Con**: Broken checkouts for contributors without symlink support.

### 3. Canonical-only in git + bootstrap-generated tool trees (chosen for config)

- **Pro**: One file per skill/persona **in the repository**; PRs touch canonical only.
- **Pro**: Bootstrap uses symlinks on Unix, copy fallback on Windows — same author experience everywhere.
- **Pro**: Replaces `scripts/sync_tool_skills.py` copy loop with link/create-on-clone; `--check` validates tool trees exist.
- **Con**: Requires `python platform/bootstrap.py` after clone or pull that changes `skills/` / `agents/`.
- **Con**: Tool-specific glue (Cursor rules, hooks, prompts) remains separate by necessity.

### 4. Mass retag all ~300 issues with finer labels

- **Pro**: Maximum historical search coverage.
- **Con**: High audit-trail noise; low ROI on closed/superseded issues.
- **Con**: Risk of illegal multi-label conflicts if done carelessly.

### 5. Selective label cleanup + `kind/*` as routing axis (chosen for indexing)

- **Pro**: `kind/*` already maps to persona domains (`iac`, `cicd`, `service`, `ai-workflow`); extend and document rather than invent `persona/*`.
- **Pro**: Backfill open issues only; enforce via templates on create.
- **Con**: Legacy labels remain on old issues until touched.
- **Con**: Labels stay coarse — body and comments remain source of truth.

## Decision outcome

**Chosen**: Option 3 for agent config (canonical-only in git, bootstrap-wired tool trees, unified MCP manifest) **and** Option 5 for issue indexing (consolidate label vocabulary, extend `kind/*`, backfill open issues, enforce on new issues). This **amends** ADR-022's delivery mechanism (committed stubs → bootstrap-generated trees) while **preserving** ADR-022's canonical paths (`skills/`, `agents/`).

## Consequences

### Positive

- Skill or persona edits produce **one-file PR diffs** on canonical paths.
- Cursor, Claude, and Gemini read the same bytes (symlink or ephemeral copy).
- Agents query issues via stable `kind/*` + `state/*` + `type/*` labels mapped to personas.
- GitHub Issues remain the audit-grade knowledge layer per ADR-001; no parallel static KB to maintain.
- Single `platform/mcp.servers.json` feeds all MCP client configs.

### Negative

- New contributors must run bootstrap after clone (document in README, `CLAUDE.md`, `GEMINI.md`).
- Claude dispatch metadata (`model`, `tools`) moves to canonical frontmatter or a small `platform/personas.meta.yaml` — adapters with duplicated bodies are retired.
- Label backfill is manual/script-assisted for open issues; full history stays heterogeneous.
- Cursor-only surfaces (`.cursor/rules/*.mdc`, hooks, prompts) remain tool-specific.

### Neutral

- ADR-011 six-gate contract unchanged; this ADR improves how agents load context and route, not delivery gates.
- Construct anchor labels stay mandatory per ADR-002 even when most platform work uses `env/shared` / `lz/shared`.

---

## Part A — Unified agent configuration

### A.1 Target repository layout

```text
Catalyst/
├── AGENTS.md                          # single operating contract (unchanged authority)
├── agents/                            # ONLY persona files (canonical)
├── skills/                            # ONLY skill files (canonical)
├── platform/
│   ├── mcp.servers.json               # single MCP registry (edit here)
│   ├── personas.meta.yaml             # optional Claude model/tools overlay
│   └── bootstrap.py                   # wire tool trees → canonical paths
├── .cursor/
│   ├── rules/                         # Cursor-only auto-activation (keep)
│   ├── prompts/                       # review prompts (keep)
│   ├── hooks/                         # Cursor-only (keep)
│   ├── mcp.json                       # generated from platform/mcp.servers.json
│   ├── skills/                        # generated — not committed
│   └── agents/                        # generated — not committed
├── .claude/
│   ├── agents/                        # generated (except Claude-only rlm-subcall.md)
│   └── skills/                        # generated — not committed
└── .gemini/
    ├── settings.json                  # generated MCP section
    ├── agents/                        # generated — not committed
    └── skills/                        # generated — not committed
```

**Author workflow**: edit `skills/<name>/SKILL.md` or `agents/<name>.md`, run `python platform/bootstrap.py`, commit **canonical paths only**.

### A.2 Bootstrap behavior

`platform/bootstrap.py`:

1. Create **symlinks** on Unix: `.cursor/skills/<name>` → `../../skills/<name>`, same for `.claude/` and `.gemini/`; symlink `agents/<file>.md` into each tool's `agents/` directory.
2. **Copy fallback** on Windows when symlinks are unavailable (preserves ADR-022 semantics without committing copies).
3. Emit `.cursor/mcp.json`, `.gemini/settings.json` (MCP block), and `.mcp.json` from `platform/mcp.servers.json`.
4. Support `--check` for CI: fail if tool trees missing or stale relative to canonical.

**Retire over time**: committed `.cursor/skills/**`, `.claude/skills/**`, `.gemini/skills/**`, and generated agent stubs in git; replace `scripts/sync_tool_skills.py` copy loop with bootstrap.

### A.3 Unified persona frontmatter

Canonical `agents/*.md` carries all discovery metadata. Claude-specific dispatch fields live in frontmatter or `platform/personas.meta.yaml` — **not** a second full copy of the persona body:

```yaml
---
name: terraform-engineer
description: >-
  Discovery text for all tools (routing, auto-activation).
claude:
  model: sonnet
  tools: [Read, Grep, Glob, Bash, Edit]
cursor:
  model: inherit
gemini:
  model: inherit
---
```

Delete hand-maintained `.claude/agents/*` body duplication; keep `.claude/agents/rlm-subcall.md` as Claude-only sub-LLM.

### A.4 Single MCP registry

MCP server **scripts** already live under `skills/<name>/`. Consolidate client JSON into `platform/mcp.servers.json`; bootstrap writes per-tool configs. Secret-scanning HTTP server retains `${env:GITHUB_MCP_PAT}` in Cursor config only where required.

### A.5 Tool-specific surfaces (cannot unify)

| Artifact | Reason |
|---|---|
| `.cursor/rules/*.mdc` | Cursor file-pattern auto-activation |
| `.cursor/hooks/` | Cursor filesystem events vs Claude PreToolUse |
| `.cursor/prompts/*.md` | Cursor / Copilot review UI |
| `CLAUDE.md`, `GEMINI.md` | Thin entrypoints pointing at `AGENTS.md` + bootstrap instructions |

Migrate rule **content** into skills where possible (precedent: `catalyst-agent-routing` migrated from `catalyst-agents.mdc`). Rules become thin triggers.

### A.6 Path references in docs and skills

All prose and scripts reference **`skills/<name>/...`** and **`agents/<name>.md`**, never `.claude/skills/` or `.cursor/skills/` (tool trees are implementation detail).

### A.7 Implementation phases (agent config)

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 1 | `platform/bootstrap.py` + gitignore tool skill/agent trees | Local bootstrap works; stubs can remain committed temporarily |
| 2 | `platform/mcp.servers.json` + generated MCP configs | One MCP edit updates all tools |
| 3 | Unified persona frontmatter; retire Claude body duplication | One agent file per persona in git |
| 4 | Remove committed stubs; CI runs `bootstrap --check` | PRs touch canonical only |
| 5 | Extend CI to Gemini; fix path references | Three-tool parity in CI |
| 6 | Fold remaining rule content into skills | Smaller Cursor-only surface |

---

## Part B — GitHub Issues as agent knowledge and label indexing

### B.1 Knowledge layering

| Layer | Source of truth | Agent use |
|---|---|---|
| Decisions, rationale | Issue comments (`### Decision`, `### Rationale`, …) | Session handoff, audit |
| Acceptance criteria | Issue body (Gherkin) | Pre-PR peer review (ADR-011 gate 5) |
| Architecture | `docs/ADR/*.md` | ADR compliance checks |
| Known patterns / bugs | Closed issues, `type/ops-intel-finding` | Search + cite |
| Live workflow state | `state/*` labels, Catalyst Andon board | Legal transitions |
| PR queue | Catalyst Progress project #3 | `pr-open-contract` only |
| Search index | Namespaced labels (below) | `gh issue list`, future `catalyst-issue-context.py` |

**Rule**: Do not duplicate live issue state in static markdown. Optional `knowledge-base/` may hold **generated snapshots** only, never hand-maintained parallel truth.

Long artifacts (>~50k chars) still route through RLM (ADR-004) before inline read.

### B.2 Label vocabulary consolidation

**Keep** (Catalyst namespaced — agents query these only):

| Family | Cardinality | Purpose |
|---|---|---|
| `state/*` | exactly one | State machine (STATE-MACHINE §2.1) |
| `type/*` | exactly one | Work category |
| `tenant/*`, `env/*`, `lz/*`, `project/*`, `app/*` | exactly one each | Construct address (ADR-002) |
| `kind/*` | exactly one for implementable work | **Agent routing / domain index** |
| `severity/*`, `verdict/*`, `deploy/*`, modifiers | additive | Contextual |

**Deprecate** (do not add to new issues; remove when editing):

- `Kind/*`, `Priority/*`, `Status/*`, `Reviewed/*` — duplicate `kind/*`, `severity/*`, `state/*`
- Bare GitHub defaults where namespaced equivalent exists (`bug`, `enhancement`, `documentation`)

**Time-boxed**: `phase/*` labels are campaign modifiers; exclude from default agent queries after campaign ends.

### B.3 `kind/*` registry (agent routing axis)

Formalize `kind/*` in `STATE-MACHINE.md` §2 (currently used in plans but incomplete in the spec):

| Label | Persona(s) | Signals |
|---|---|---|
| `kind/iac` | terraform-engineer, checkov-expert, opa-expert | Terraform, HCL, Checkov, OPA, modules |
| `kind/cicd` | cicd-operator | GitHub Actions, deploy pipelines, OIDC workflows |
| `kind/service` | automation-architect | FastAPI, Lambda, services/, async orchestration |
| `kind/ai-workflow` | ai-reviewer-architect | Bedrock, PR review, prompts, pydantic output |
| `kind/security` | security-hardener | IAM, secrets, containers, scanning, WAF |
| `kind/docs` | platform-engineering-architect | ADRs, README, diagrams, onboarding |
| `kind/score` | score-expert | score.yaml, portability |
| `kind/platform` | platform-engineering-architect | IDP strategy, golden paths, cross-cutting |
| `kind/umbrella` | platform-engineering-architect | Parent / epic issues |

**Optional additive** (multi-cloud and area scoping):

- `cloud/aws`, `cloud/azure`, `cloud/gcp`
- `area/infrastructure`, `area/services`, `area/docs`

**Do not** add `persona/<name>` labels — too granular, duplicates `skills/catalyst-agent-routing`, drifts when personas change.

### B.4 Backfill and enforcement policy

| Scope | Action |
|---|---|
| Open issues (`state/pending`, `state/agent-working`, `state/blocked-on-human`) | Add missing `kind/*`; remove deprecated legacy labels |
| Recently closed (30–60 days) | Same if agents still reference them |
| Old closed / superseded | Leave unless frequently retrieved |
| **New issues** | Issue templates enforce full label set |

**Do not** mass-retag all historical issues for precision — titles, bodies, and ADR references already carry detail.

### B.5 Agent tooling integration

Future scripts (not blocking this ADR's acceptance):

- `scripts/catalyst-issue-context.py` — export issue body, comments, linked PRs by `#N` or label query
- `scripts/catalyst-ask.py` — deterministic classifier; maps `kind/*` → persona list
- `scripts/validate_issue_labels.py` — optional CI check on new/edited issues

Example queries:

```bash
gh issue list --repo Cloud-Byte-Consulting/Catalyst \
  --label "kind/iac" --label "state/agent-working" --limit 20
```

### B.6 Implementation phases (issue indexing)

| Phase | Deliverable | Exit criteria |
|---|---|---|
| A | Document `kind/*` in STATE-MACHINE; add label registry section | Spec matches repo usage |
| B | Audit open issues: add missing `kind/*`, strip legacy labels | Every open implementable issue has one `kind/*` |
| C | Issue templates enforce required labels | New issues fail template if incomplete |
| D | Add new `kind/security`, `kind/docs`, `kind/platform`, `kind/score`, `cloud/*` | Labels exist in GitHub |
| E | Wire label → persona map into routing and issue-context scripts | Classifier uses labels deterministically |

---

## Part C — Acceptance criteria

This ADR is fully implemented when:

1. A skill or persona change produces a **single canonical file** in git PRs.
2. Bootstrap wires Cursor, Claude, and Gemini to the same canonical content; CI `--check` passes.
3. MCP configs generate from one manifest.
4. Every **open implementable issue** carries exactly one `kind/*` label.
5. New issues cannot omit `kind/*` (template-enforced).
6. Agents can list and filter issues by `state/*` + `type/*` + `kind/*` without legacy label noise.
7. ADR-011 gates and ADR-001 state machine semantics remain unchanged.

## Alternatives explicitly rejected

| Alternative | Why rejected |
|---|---|
| Separate `agent-coordination` repo for Catalyst | Catalyst is the application agent system; no sibling systems to route to today |
| Static `knowledge-base/*.md` as primary KB | Issues + ADRs already authoritative; static KB would drift |
| `persona/*` labels per agent file | Duplicates routing table; high churn |
| Per-file path labels | Refactor churn; poor durability |
| Bulk retag all closed issues | Low ROI, noisy audit trail |

## Links

- **Amends**: [ADR-022](ADR-022-multi-tool-skill-layout.md) (canonical paths unchanged; stub delivery mechanism superseded by bootstrap)
- **Related**: [ADR-001](ADR-001-github-issues-as-state-machine.md), [ADR-004](ADR-004-rlm-for-long-context-agent-tasks.md), [ADR-011](ADR-011-catalyst-agentic-workflow.md), [`STATE-MACHINE.md`](STATE-MACHINE.md), [`docs/multi-tool-config.md`](../multi-tool-config.md), [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](../issue-execution-gherkin-workflow-2026-05-13.md)
- **Implementation tracking**: umbrella issue [#306](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/306) with sub-issues #307–#317 (see sub-issue index comment on #306)

## One-line summary (for issue body)

Adopt bootstrap-wired single-source agent config for Cursor/Claude/Gemini and formalize `kind/*` labels as the GitHub Issue search index for agent routing — amending ADR-022 stub copies with canonical-only git + issue-as-KB indexing.
