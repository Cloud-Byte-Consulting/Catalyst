<!-- AUTO-GENERATED from skills/output-assessment/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
<!-- Vendored from: platform-catalyst/.cursor/skills/output-assessment/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->
---
name: output-assessment
description: >-
  Post-execution output scanning: detects secrets (AWS keys, private keys,
  JWTs, connection strings), PII patterns, prompt injection markers, stack
  traces, and error signals in tool output. Returns severity + signal names.
  Use when implementing or extending output guards in plugins/catalyst-judge/.
---

# Output assessment

## Role

You guide the use and extension of the `OutputGuard` in `plugins/catalyst-judge/src/catalyst_judge/output_guard.py`, which scans tool output after execution for dangerous signals.

> **Catalyst note (decision #3)**: Catalyst does **not** vendor the upstream `plugins/catalyst-judge/` package. The paths and code samples below describe the upstream Relay/platform-catalyst lineage; the Catalyst-side surface is the heuristic-only MCP shim at `.cursor/skills/intent-judge-shim/intent_judge_mcp_server.py`. Use the upstream content here as design context when extending the shim's output-side scanners; do not assume the Python package is importable in this repo.

## Instructions

### 1. Built-in signals

| Signal | Pattern | Severity | Catches |
|--------|---------|----------|---------|
| `aws_access_key` | `AKIA[0-9A-Z]{16}` | critical | AWS access key IDs |
| `aws_secret_key` | 40-char base64-like string | critical | AWS secret keys |
| `private_key` | `-----BEGIN * PRIVATE KEY-----` | critical | RSA/EC/DSA/OpenSSH keys |
| `jwt_token` | `eyJ...` three-part base64 | warning | JWT tokens |
| `connection_string` | `postgres://user:pass@host` | critical | DB credentials |
| `generic_password` | `password = "..."` | warning | Passwords in output |
| `ip_address` | IPv4 pattern | info | IP address exposure |
| `stack_trace` | `Traceback`, `panic:`, `FATAL:` | warning | Error leaks |
| `prompt_injection_marker` | "ignore previous", "you are now" | warning | Injection attempts |

### 2. Usage

```python
from catalyst_judge.output_guard import OutputGuard

guard = OutputGuard()
assessment = guard.assess(
    call_id="call-123",
    output="Connected to postgres://admin:s3cret@db.internal:5432/mydb",
)
# assessment.severity == Severity.CRITICAL
# assessment.signal_names == ["connection_string"]
# assessment.sample_snippet == "Conn...5432"  (redacted)
```

### 3. Adding custom signals

```python
from catalyst_judge.output_guard import OutputGuard, _Signal, Severity
import re

hipaa_signal = _Signal(
    name="phi_ssn",
    pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    severity=Severity.CRITICAL,
    description="Social Security Number pattern in output",
)

guard = OutputGuard(extra_signals=[hipaa_signal])
```

### 4. Severity aggregation

When multiple signals fire:
- Severity = highest among all triggered signals
- Confidence = `0.5 + 0.15 * count` (capped at 1.0)
- Snippet = from the first critical/warning match, redacted

### 5. Snippet redaction

`sample_snippet` shows only first 4 + last 4 characters: `"post...5432"`. Full signal content is never exposed in the assessment — safe for logging and audit trails.

### 6. MCP tool: `assess_output`

```json
{
  "call_id": "tool-call-456",
  "output": "AKIAIOSFODNN7EXAMPLE and some other text"
}
```

Returns:
```json
{
  "call_id": "tool-call-456",
  "signal_names": ["aws_access_key"],
  "severity": "critical",
  "confidence": 0.65,
  "sample_snippet": "AKIA...MPLE"
}
```

### 7. Integration with agent trust architecture

Per the upstream `@agent-trust-architecture` skill (not vendored in Catalyst):
- **info** signals → log only, no action
- **warning** signals → flag to human, continue execution
- **error/critical** signals → escalate to Tier 2 (human-confirmed), potentially halt

## How Catalyst invokes this

In Catalyst, output assessment runs against the **`assess_output`** tool
on the `intent-judge` MCP server (`.cursor/mcp.json` →
`.cursor/skills/intent-judge-shim/intent_judge_mcp_server.py`). The shim's
contract is intentionally narrower than the upstream `OutputGuard`:

| Upstream concept                          | Catalyst surface                                                                |
|-------------------------------------------|---------------------------------------------------------------------------------|
| `assess_output` MCP tool (signal taxonomy)| `assess_output` tool on the `intent-judge` MCP server (substring/regex/json_equal shape checks); plus the same secrets/PII/injection scanners reused from `validate_intent` |
| `_Signal` extension                       | Extend `SECRET_RE` / `INJECT_RE` / `PII_RE` / `LONG_B64` constants in the shim (stay within the ~80-LOC budget) |
| `Severity.CRITICAL` halts                 | Critical scanner hits transition the issue to `state/blocked-on-human` per `docs/ADR/ADR-001-github-issues-as-state-machine.md` |
| LLM-judged output rubrics                 | `expected_shape: "llm_judge"` returns `ok=false` deliberately — route to `@ai-reviewer-architect` + Bedrock MCP if a model is required |

Smoke test (PowerShell):

```powershell
'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"assess_output","arguments":{"output":"the access key is AKIAIOSFODNN7EXAMPLE","expected":"AKIA[0-9A-Z]{16}","expected_shape":"regex"}}}' `
  | python .cursor/skills/intent-judge-shim/intent_judge_mcp_server.py
```

## Output

- **Assessment JSON**: OutputAssessment with signals, severity, redacted snippet
- **Custom signal**: new `_Signal` definition for domain-specific patterns
- **Integration pattern**: how to wire assessment into a tool-loop approval flow

## Guardrails

- Output guard runs **post-execution** — it cannot prevent the tool from running. It flags what already happened.
- Snippets are always redacted. Never expose full matched content in logs or assessments.
- False positives on `aws_secret_key` are expected (40-char random strings). Use confidence scores, not binary decisions.
- For HIPAA/PII contexts: add domain-specific signals via `extra_signals`, don't modify the built-in set.
- **Catalyst-specific**: the shim is hard-capped at ~80 effective LOC. New signal classes that significantly grow the file should be raised as Kaizen issues under `#3 AI-native Development workflow`, not silently inlined.
