# RLM Integration Guide — Catalyst

Practical patterns for using the Recursive Language Model (RLM) skill inside Catalyst's
GitHub Issues state-machine workflow. Read ADR-004 first for the decision rationale.

---

## What problem this solves

Catalyst agents read large artifacts — diffs, Terraform plans, CloudWatch exports, codebase
trees, accumulated issue comment threads. When an artifact exceeds ~50k characters (~35k tokens),
reading it inline burns most of the model's context budget, leaves little room for quality output,
and risks silent truncation.

RLM externalises the artifact into a persistent Python REPL (pickle-backed state on disk).
A root Opus session orchestrates: it splits the artifact into chunks, fires `rlm-subcall`
subagent (Haiku 4.5) on each chunk to extract structured JSON findings, then synthesises all
findings into a final answer. The root's context window only ever holds structured JSON —
never raw artifact text.

---

## Setup (one-time per Catalyst workspace)

```bash
# From Cloud-Byte-Consulting workspace root:
# RLM is already cloned at cloud-byte-consulting/claude_code_RLM

# Copy skill and subagent into Catalyst .claude/
cp -r claude_code_RLM/.claude/skills/rlm        Catalyst/.claude/skills/rlm
cp -r claude_code_RLM/.claude/agents/rlm-subcall.md  Catalyst/.claude/agents/rlm-subcall.md

# Add gitignore entry so pickle state is never committed
echo '**/.claude/rlm_state/' >> Catalyst/.gitignore
```

Add to Catalyst's `AGENTS.md` (workspace memory):
```
**RLM trigger rule**: If an artifact to be read exceeds ~50k characters, invoke /rlm
before reading it inline. Threshold applies to: diffs, terraform plan outputs, CloudWatch
exports, codebase analysis spanning >10 files.
```

---

## Trigger threshold

| Artifact size | Approach |
|---|---|
| < ~50k characters (~35k tokens) | Read inline — no chunking overhead needed |
| 50k – 500k characters | `/rlm` with default 200k-char chunks (1–3 chunks, typically) |
| > 500k characters | `/rlm` with explicit `chunk_chars=` tuned to semantic boundaries |

---

## Pattern 1 — PR Review (`type/pr-review`)

**When**: AI reviewer agent picks up an issue in `state/agent-working` for a large PR.

**Artifact**: `git diff main...HEAD` output or `gh pr diff <N>`.

```bash
# 1. Export the diff to a file (diff can be hundreds of KB)
gh pr diff 42 > /tmp/pr-42.diff

# 2. In Claude Code, invoke the skill
/rlm context=/tmp/pr-42.diff query="Find bugs, security issues, API contract violations, and design problems. For each finding: file path, line range, severity (critical/high/medium/low), description, suggested fix."
```

**What the skill does**:
1. Initialises REPL state with the diff file
2. Scouts the structure (which files changed, hunk headers)
3. Chunks by ~200k chars (or by file boundary if diff is structured markdown)
4. Fires `rlm-subcall` (Haiku) on each chunk → JSON per chunk:
   ```json
   {
     "chunk_id": "0",
     "relevant": [
       { "point": "SQL query constructed with f-string interpolation", "evidence": "Line +47 in services/api/router.py", "confidence": "high" }
     ],
     "missing": ["couldn't assess IAM policy in chunk 2"],
     "suggested_next_queries": ["check IAM role used by the Lambda in this diff"]
   }
   ```
5. Root Opus synthesises → produces structured verdict per the `.cursor/prompts/skeptic.md` schema

**Issue comment after synthesis** (per `docs/issue-execution-gherkin-workflow-2026-05-13.md`):
```markdown
AI review complete — 3 findings across 4 chunks (PR #42, 287 files, 14,200 lines).

<!-- catalyst-agent-log: handoff -->

### Context
- Labels: state/agent-working, type/pr-review, verdict/request-changes
- RLM: 4 chunks @ 200k chars each; rlm-subcall (Haiku) per chunk

### Decision
Verdict: request-changes. Critical SQL injection in services/api/router.py:47.

### Actions taken
- diff exported: /tmp/pr-42.diff (622 KB)
- rlm chunks: 4 files in .claude/rlm_state/chunks/
- Findings synthesised; label verdict/request-changes applied

### Verification
- All 4 chunks processed; no chunk returned empty relevant list

### Next
1. Author must remediate SQL injection before re-review.
2. Re-open with /rlm on updated diff after fix.
```

---

## Pattern 2 — Ops-Intel finding (`type/ops-intel-finding`)

**When**: Ops-intel probe dumps a large CloudWatch Logs export or CloudTrail event file.

**Artifact**: log file exported from the probe, or a piped `aws cloudtrail lookup-events` output.

```bash
# Export CloudTrail events to file (can be >1 MB for active accounts)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=CreateBucket \
  --start-time 2026-04-13T00:00:00Z \
  --output json > /tmp/cloudtrail-s3-creates.json

/rlm context=/tmp/cloudtrail-s3-creates.json \
     query="Find S3 buckets created without server-side encryption or without public-access-block enabled. Return: bucket name, creator ARN, creation time, missing controls."
```

**Synthesis output** feeds directly into the ops-intel GitHub Issue body template from
`STATE-MACHINE.md §8`:

```
Resource ARN: arn:aws:s3:::my-unencrypted-bucket-2026
Severity: high
Evidence excerpt: CreateBucket event at 2026-05-01T14:32Z by arn:aws:iam::123456789:user/dev-ops; PutBucketEncryption never called for this bucket in the 30-day window
Proposed remediation: Enable SSE-KMS via aws s3api put-bucket-encryption; add Terraform resource to enforce via SCPs
Probe run ID: ops-intel-20260513-142200
```

---

## Pattern 3 — Terraform plan analysis (`type/deploy`)

**When**: A deploy issue enters `state/agent-working`; agent needs to validate the plan before
approving or posting a risk summary.

**Artifact**: `terraform plan -out=tfplan.bin && terraform show -json tfplan.bin`

```bash
terraform -chdir=infrastructure/modules/composite/github-bootstrap plan \
  -out=tfplan.bin 2>&1 | tee /tmp/plan-output.txt

/rlm context=/tmp/plan-output.txt \
     query="Identify: resources being destroyed, resources changing IAM permissions, resources touching KMS keys, estimated cost delta, any policy violations flagged by tfsec or Checkov comments."
```

**Chunk strategy**: plan output is line-structured. Use `chunk_chars=150000` with
`overlap_chars=2000` so resource blocks are unlikely to be split mid-block.

**Risk summary** is posted as an issue comment before the agent transitions from
`state/agent-working` → `state/blocked-on-human` (human approves if risky changes detected)
or → `state/done` (if plan is low-risk and Gherkin acceptance criteria pass).

---

## Pattern 4 — Feature implementation (long codebase read)

**When**: An issue's Acceptance Criteria requires implementing a new feature that spans multiple
services and the agent needs full codebase context before writing a plan.

**Artifact**: A concatenated dump of relevant source files, or the output of a broad `grep`/`glob`
scan.

```bash
# Produce a single context file from relevant source paths
find services/ infrastructure/ docs/ADR/ \
  -name "*.py" -o -name "*.tf" -o -name "*.md" | \
  xargs cat > /tmp/codebase-context.txt

/rlm context=/tmp/codebase-context.txt \
     query="Locate all places where the construct address (tenant/env/lz/project/app) is
            parsed or validated. Find the canonical type definitions, validation functions,
            and any callers that must be updated when we add a new construct level."
```

**After synthesis**: the root agent has a map of relevant files, symbols, and callers — enough
to write a targeted implementation plan without re-reading the full codebase. The plan is
posted as a structured issue comment (`### Decision`, `### Actions taken`) before any edits begin.

**Long-session note**: if the feature spans multiple agent sessions (issue passes through
`state/blocked-on-human` and back to `state/agent-working`), the REPL state pkl will be stale
because `.claude/rlm_state/` is ephemeral. The resuming agent MUST re-initialise:
```bash
python .claude/skills/rlm/scripts/rlm_repl.py reset
python .claude/skills/rlm/scripts/rlm_repl.py init /tmp/codebase-context.txt
```

---

## Mapping to the Catalyst state machine

```
Issue enters state/agent-working
        │
        ▼
Artifact size check (peek first 100 chars for format, check total length)
        │
        ├─ < 50k chars ──────────────────────── Read inline → proceed
        │
        └─ ≥ 50k chars
                │
                ▼
         python rlm_repl.py init <artifact>   ← externalise context
                │
                ▼
         Scout: peek(0, 3000) + peek(end-3000, end)
                │
                ▼
         Choose chunk strategy (semantic or char-based)
                │
                ▼
         write_chunks('.claude/rlm_state/chunks/', size=200000)
                │
                ▼
         For each chunk:
           rlm-subcall (Haiku) → JSON findings
           add_buffer(json_result)
                │
                ▼
         Root (Opus) synthesises all buffers
                │
                ▼
         Post structured finding/plan as issue comment
         (stable ### headings — Context, Decision, Rationale,
          Actions taken, Verification, Risks/follow-ups, Next)
                │
                ▼
         Transition label per legal state machine
         (state/done, state/blocked-on-human, verdict/*, etc.)
```

---

## Cost model

Approximate token spend for a 500 KB artifact (4 chunks × 125 KB):

| Step | Model | Tokens (est.) | Cost (est.) |
|---|---|---|---|
| Scout (peek × 2) | Opus | ~2k | ~$0.03 |
| Chunk analysis × 4 | Haiku (per chunk) | ~40k each = 160k total | ~$0.02 |
| Synthesis | Opus | ~10k | ~$0.15 |
| **Total** | — | **~172k** | **~$0.20** |

Compare to reading the same 500 KB inline on Opus: ~370k tokens ≈ $5.55 — a **27× cost reduction**.
The Haiku subagent calls can be parallelised (each chunk is an independent file read) for near-linear
latency reduction.

---

## Guardrails

- **Never paste raw chunk content into the main conversation** — all chunk data goes through the REPL
  and surfaces only as structured JSON from `rlm-subcall`.
- **`rlm-subcall` cannot spawn subagents** — depth-1 handoff only. Orchestration always returns
  to the root Opus session.
- **REPL state is not the state machine** — GitHub Issues + labels per ADR-001 remain the durable
  record. The `.pkl` file is a session scratchpad.
- **Evidence excerpts ≤ 25 words** in subagent output — keeps synthesis context manageable.
- **Confidence field is load-bearing** — root synthesis must note `confidence: low` findings
  separately; don't present them as confirmed.

---

## Cursor agent usage

The RLM workflow is platform-agnostic. The `rlm_repl.py` script is shared between
Claude Code and Cursor — the only difference is how the root agent orchestrates
chunk-level analysis. In Cursor, use the **Shell tool** for REPL commands and the
**Task tool** (`subagent_type="generalPurpose"`) for parallel chunk analysis.

### Quick-start (Cursor)

```powershell
# 1. Initialise — same command, any shell
python .claude/skills/rlm/scripts/rlm_repl.py init <artifact_path>
python .claude/skills/rlm/scripts/rlm_repl.py status

# 2. Scout
python .claude/skills/rlm/scripts/rlm_repl.py exec -c "print(peek(0, 3000))"

# 3. Chunk
python .claude/skills/rlm/scripts/rlm_repl.py exec -c "paths = write_chunks('.claude/rlm_state/chunks', size=200000); print(paths)"

# 4. Analyse — launch Task subagents (see below)
# 5. Synthesise — collect subagent JSON, compose in root context
# 6. Clean up
python .claude/skills/rlm/scripts/rlm_repl.py reset
```

### MCP tool alternative

If `.cursor/mcp.json` is configured with the `rlm-repl` server, Cursor agents can
call RLM operations as MCP tools instead of Shell commands:

| MCP tool | Equivalent Shell command |
|---|---|
| `rlm_init` | `python rlm_repl.py init <path>` |
| `rlm_status` | `python rlm_repl.py status` |
| `rlm_peek` | `python rlm_repl.py exec -c "print(peek(start, end))"` |
| `rlm_grep` | `python rlm_repl.py exec -c "print(grep(pattern))"` |
| `rlm_chunk` | `python rlm_repl.py exec -c "write_chunks(...)"` |
| `rlm_exec` | `python rlm_repl.py exec -c "<code>"` |
| `rlm_reset` | `python rlm_repl.py reset` |
| `rlm_export_buffers` | `python rlm_repl.py export-buffers <path>` |

The MCP server is at `.cursor/skills/rlm/rlm_mcp_server.py` and delegates to the
same `rlm_repl.py` without forking it.

### Cursor subagent mapping

| Claude Code primitive | Cursor equivalent |
|---|---|
| Main Claude Code session (root LM) | Root Cursor agent |
| `rlm-subcall` subagent (Haiku) | `Task` tool with `subagent_type="generalPurpose"` |
| `/rlm` skill invocation | `.cursor/rules/rlm-workflow.mdc` rule (auto-activates) |
| Bash tool | Shell tool |
| Subagent results in chat | Task subagent return values |

### Pattern equivalents for Cursor

Each of the four patterns above works identically in Cursor with these substitutions:

**Pattern 1 — PR Review (Cursor)**:
```
# Shell tool:
gh pr diff 42 > /tmp/pr-42.diff
python .claude/skills/rlm/scripts/rlm_repl.py init /tmp/pr-42.diff
python .claude/skills/rlm/scripts/rlm_repl.py exec -c "paths = write_chunks('.claude/rlm_state/chunks', size=200000); print(paths)"

# For each chunk — Task tool (generalPurpose, run_in_background=true):
# Prompt: "Read .claude/rlm_state/chunks/chunk_0000.txt and extract bugs,
# security issues, API contract violations. Return JSON per RLM schema."
```

**Pattern 2 — Ops-Intel (Cursor)**: same REPL commands via Shell tool; Task subagents
replace `rlm-subcall` for chunk-level CloudTrail/CloudWatch analysis.

**Pattern 3 — Terraform plan (Cursor)**: same REPL commands via Shell tool; use
`size=150000, overlap=2000` for structured plan output; Task subagents flag drift,
cost, and policy violations per chunk.

**Pattern 4 — Feature implementation (Cursor)**:
```powershell
# PowerShell variant for concatenating source files:
Get-ChildItem -Recurse -Include *.py,*.tf,*.md | Get-Content | Out-File /tmp/codebase-context.txt

# Then standard REPL init/chunk/subagent flow via Shell + Task tools.
```

### Cursor orchestration checklist

1. **Init**: Shell → `rlm_repl.py init <artifact>` (or MCP `rlm_init`)
2. **Scout**: Shell → `peek()` + `grep()` (or MCP `rlm_peek` / `rlm_grep`)
3. **Chunk**: Shell → `write_chunks()` (or MCP `rlm_chunk`)
4. **Analyse**: Task subagents (one per chunk, `run_in_background: true`, parallel)
5. **Collect**: Shell → `add_buffer()` per subagent result (or MCP `rlm_exec`)
6. **Export**: Shell → `export-buffers` (or MCP `rlm_export_buffers`)
7. **Synthesise**: Root agent reads synthesis file, composes structured comment
8. **Post**: Root agent posts to GitHub Issue per handoff template
9. **Clean up**: Shell → `rlm_repl.py reset` (or MCP `rlm_reset`)

---

## References

- [ADR-004 — RLM for long-context agent tasks](ADR/ADR-004-rlm-for-long-context-agent-tasks.md)
- [ADR-001 — GitHub Issues as durable state machine](ADR/ADR-001-github-issues-as-state-machine.md)
- [STATE-MACHINE.md](ADR/STATE-MACHINE.md)
- [issue-execution-gherkin-workflow-2026-05-13.md](issue-execution-gherkin-workflow-2026-05-13.md)
- Cursor rule: `.cursor/rules/rlm-workflow.mdc`
- MCP server: `.cursor/skills/rlm/rlm_mcp_server.py`
- MCP config: `.cursor/mcp.json`
- Source repo: `https://github.com/BittahCriminal/claude_code_RLM`
- Paper: Zhang, Kraska, Khattab — *Recursive Language Models* (arXiv:2512.24601)
