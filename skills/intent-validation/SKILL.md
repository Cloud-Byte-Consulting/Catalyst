<!-- Vendored from: platform-catalyst/.cursor/skills/intent-validation/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->
---
name: intent-validation
description: >-
  Tool call intent validation: heuristic pattern matching + LLM judge for
  allow/deny/clarify verdicts with risk classification and confidence scoring.
  Use when implementing, configuring, or extending the intent validator in
  plugins/catalyst-judge/.
---

# Intent validation

## Role

You guide the use and extension of the `IntentValidator` in `plugins/catalyst-judge/src/catalyst_judge/intent.py`, which gates tool calls before execution using heuristic rules and an optional LLM judge.

> **Catalyst note (decision #3)**: Catalyst does **not** vendor the upstream `plugins/catalyst-judge/` package. The paths and code samples below describe the upstream Relay/platform-catalyst lineage; the Catalyst-side surface is the heuristic-only MCP shim at `.cursor/skills/intent-judge-shim/intent_judge_mcp_server.py`. Use the upstream content here as design context when extending the shim's scanners; do not assume the Python package is importable in this repo.

## Instructions

### 1. Two-phase validation

```
Tool call pending
       │
       ▼
  Heuristic rules (fast, deterministic)
       │
       ├── confidence >= threshold → return verdict
       │
       └── confidence < threshold or no match
              │
              ▼
         LLM judge (optional, nuanced)
              │
              ├── combine with heuristic → return verdict
              │
              └── LLM unavailable → return heuristic or default allow
```

### 2. Heuristic rules

Built-in patterns in `_DANGEROUS_PATTERNS`:

| Check name | Pattern | Risk | Catches |
|-----------|---------|------|---------|
| `rm_recursive` | `rm -rf` / `rm --force -r` | critical | Destructive file deletion |
| `wildcard_iam` | `"*"` near `Action`/`Resource` | high | Overly permissive IAM |
| `shell_true` | `shell=True` | high | Command injection risk |
| `eval_exec` | `eval(` / `exec(` | high | Dynamic code execution |
| `hardcoded_secret` | `password = "..."` patterns | high | Credentials in code |
| `sql_fstring` | `f"SELECT..."` | critical | SQL injection |
| `force_push` | `git push --force` | high | Destructive git operation |
| `pickle_load` | `pickle.load(` | high | Insecure deserialization |

### 3. Adding custom rules

```python
from catalyst_judge.intent import _DANGEROUS_PATTERNS, Risk
import re

_DANGEROUS_PATTERNS.append((
    "kubectl_delete_ns",
    re.compile(r"kubectl\s+delete\s+(ns|namespace)"),
    Risk.CRITICAL,
    "Kubernetes namespace deletion",
))
```

### 4. LLM judge prompt

The system prompt instructs the LLM to return structured JSON:
```json
{"verdict": "allow|deny|clarify", "risk": "low|medium|high|critical", "confidence": 0.0-1.0, "rationale": "...", "checks": ["..."]}
```

Temperature 0.0 for deterministic output. Max 256 tokens.

### 5. Combination logic

When both heuristic and LLM produce results:
- **Heuristic deny + high/critical risk** always wins (defense in depth)
- Otherwise, higher-confidence verdict wins
- Risk level is the max of both
- Checks and rationale are merged

### 6. MCP tool: `judge_intent`

```json
{
  "tool_name": "Bash",
  "tool_args": "rm -rf /tmp/old-data && echo done"
}
```

Returns:
```json
{
  "verdict": "deny",
  "risk": "critical",
  "confidence": 0.9,
  "rationale": "Destructive recursive delete detected",
  "checks": ["rm_recursive"],
  "source": "heuristic"
}
```

## How Catalyst invokes this

In Catalyst, intent validation is not implemented by importing the upstream
package above. Instead, the `.cursor/rules/intent-judge.mdc` rule activates
on high-risk tool calls and routes through the **`intent-judge` MCP
server** registered in `.cursor/mcp.json` (decision #3, see
`docs/research/platform-catalyst-agents-evaluation.md`).

| Upstream concept                          | Catalyst surface                                                                |
|-------------------------------------------|---------------------------------------------------------------------------------|
| `judge_intent` MCP tool                   | `validate_intent` tool on the `intent-judge` MCP server                         |
| `_DANGEROUS_PATTERNS` rule additions      | Extend the regex constants in `.cursor/skills/intent-judge-shim/intent_judge_mcp_server.py` (keep within the ~80-LOC budget) |
| LLM judge fallback                        | Not implemented in the shim; escalate via `@ai-reviewer-architect` + Bedrock MCP if a model is required |
| Escalation on `deny`                      | Open / transition issue to `state/blocked-on-human` per `docs/ADR/ADR-001-github-issues-as-state-machine.md` |

Smoke test (PowerShell):

```powershell
'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"validate_intent","arguments":{"tool_name":"shell","arguments":{"cmd":"rm -rf /tmp"}}}}' `
  | python .cursor/skills/intent-judge-shim/intent_judge_mcp_server.py
```

## Output

- **Verdict JSON**: structured IntentVerdict for a given tool call
- **Rule addition**: new pattern tuple for `_DANGEROUS_PATTERNS`
- **Configuration**: env vars for LLM client + confidence threshold

## Guardrails

- Heuristic deny on critical/high risk cannot be overridden by LLM allow.
- LLM path: set `JUDGE_LLM_TRANSPORT` to `claude`, `gemini`, or `cursor` for native CLI auth, **or** set `JUDGE_LLM_API_KEY` for HTTP (OpenAI-compatible). See `plugins/catalyst-judge/README.md`.
- Default verdict (no rules match, no LLM) is allow with 0.5 confidence — not silent pass-through.
- Never log full tool arguments — they may contain secrets. Log tool name and check names only.
- **Catalyst-specific**: do not grow the shim past ~80 effective LOC. If the heuristic surface here proves insufficient, raise a Kaizen issue under `#3 AI-native Development workflow` and revisit decision #3 in the open.
