<!-- Vendored from: platform-catalyst/.cursor/skills/eval-scoring/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->
---
name: eval-scoring
description: >-
  Response grading with pluggable scorers: substring match, regex match,
  JSON deep-equal, and LLM judge (rubric-based 0.0-1.0 with rationale).
  SHA256-cached LLM results. Use when scoring LLM output, designing rubrics,
  or extending the eval harness in plugins/catalyst-judge/.
---

# Eval scoring

## Role

You guide the use and extension of the scoring system in `plugins/catalyst-judge/src/catalyst_judge/scorer.py`, which grades LLM responses against expected outputs or rubrics.

> **Catalyst note (decision #3)**: Catalyst does **not** vendor the upstream `plugins/catalyst-judge/` package. The paths and code samples below describe the upstream Relay/platform-catalyst lineage; the Catalyst-side surface is the heuristic-only MCP shim at `.cursor/skills/intent-judge-shim/intent_judge_mcp_server.py`. Use the upstream content here as design context when extending the shim's scorers; do not assume the Python package is importable in this repo.

## Instructions

### 1. Four scorers

| Scorer | When to use | LLM required? |
|--------|------------|---------------|
| `substring` | Expected text appears in output (case-insensitive) | No |
| `regex` | Output matches a pattern | No |
| `json_equal` | Semantic JSON comparison (ignores whitespace, key order) | No |
| `llm_judge` | Rubric-based grading by a judge model | Yes |

### 2. Usage

```python
from catalyst_judge.scorer import get_scorer
from catalyst_judge.llm_client import create_judge_llm_from_env

# Pure Python scorers (no LLM needed)
scorer = get_scorer("substring")
result = await scorer.score(
    input_text="What is 2+2?",
    output="The answer is 4.",
    expected="4",
    rubric="",
)
# result.score == 1.0, result.rationale == "substring match"

# LLM judge (set JUDGE_LLM_TRANSPORT=claude|gemini|cursor or JUDGE_LLM_API_KEY)
llm = create_judge_llm_from_env()
if llm is not None:
    async with llm:
        judge = get_scorer("llm_judge", llm)
        result = await judge.score(
            input_text="Explain quantum entanglement",
            output="Quantum entanglement is when...",
            expected="",
            rubric="Accurate, clear, mentions non-locality and Bell's theorem",
        )
    # result.score == 0.75, result.rationale == "Mentions non-locality but omits Bell's theorem"
```

### 3. LLM judge system prompt

The judge grades on a 0.0-1.0 scale with structured JSON output:
- Rewards accuracy, relevance, rubric fit
- Penalizes hallucinations, missing requirements, incorrect reasoning
- Returns `{"score": float, "rationale": "...", "issues": [...]}`

### 4. Caching

LLM judge results are SHA256-cached by `output + rubric`. Identical evaluations are not re-graded. Cache is in-process only (not persisted).

### 5. Code fence handling

Both `json_equal` and `llm_judge` strip markdown code fences from model output before parsing:
````
```json
{"key": "value"}
```
````
→ `{"key": "value"}`

### 6. MCP tool: `score_response`

```json
{
  "input_text": "List three AWS services for compute",
  "output": "EC2, Lambda, and Fargate",
  "expected": "",
  "rubric": "Names exactly three distinct AWS compute services",
  "scorer": "llm_judge"
}
```

### 7. Custom scorers

Implement the `Scorer` protocol:

```python
class MyScorer:
    @property
    def name(self) -> str:
        return "my_scorer"

    async def score(self, input_text, output, expected, rubric) -> ScoreResult:
        ...
```

## How Catalyst invokes this

In Catalyst, batch scoring runs through the **`score_eval`** tool on the
`intent-judge` MCP server (`.cursor/mcp.json` →
`.cursor/skills/intent-judge-shim/intent_judge_mcp_server.py`). The shim
aggregates per-case `assess_output` calls into a pass/fail summary; the
LLM-judge scorer is deliberately not implemented.

| Upstream concept                  | Catalyst surface                                                                                                       |
|-----------------------------------|------------------------------------------------------------------------------------------------------------------------|
| `score_response` MCP tool         | `assess_output` (single-case) + `score_eval` (multi-case) on the `intent-judge` MCP server                             |
| `substring` / `regex` / `json_equal` scorers | Pure-stdlib implementations inside the shim — same shapes via `expected_shape` argument                                |
| `llm_judge` scorer                | Intentionally rejected: `expected_shape: "llm_judge"` returns `ok=false`. Use `@ai-reviewer-architect` + Bedrock MCP for LLM-graded evaluation. |
| SHA256 cache                      | Not implemented in the shim (out-of-scope for the ~80-LOC budget); add at the harness layer if needed                  |
| Custom `Scorer` protocol          | Not extensible at runtime in the shim; raise a Kaizen issue if a new scorer is required                                |

Smoke test (PowerShell):

```powershell
'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"score_eval","arguments":{"cases":[{"name":"sum","output":"4","expected":"4","scorer":"substring"},{"name":"shape","output":"{\"a\":1}","expected":"{\"a\":1}","scorer":"json_equal"}]}}}' `
  | python .cursor/skills/intent-judge-shim/intent_judge_mcp_server.py
```

## Output

- **Score result**: ScoreResult JSON with score, rationale, issues
- **Rubric design**: effective rubric text for the llm_judge
- **Scorer selection**: which scorer fits the evaluation need

## Guardrails

- `llm_judge` requires an LLM client — fail explicitly if none is provided.
- Pure Python scorers must be deterministic — no randomness, no external calls.
- Cache is in-process only. Do not persist cache to disk (output may contain sensitive data).
- Rubric text should be specific and measurable — "good response" is not a rubric.
- **Catalyst-specific**: do not add an LLM client to the MCP shim — decision #3 caps it at ~80 effective LOC. LLM-judged evals route through `@ai-reviewer-architect` + the Bedrock binding MCP.
