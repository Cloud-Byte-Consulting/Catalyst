<!-- AUTO-GENERATED from skills/ai-observability/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: ai-observability
description: >-
  Observability for Bedrock AI calls: EMF metrics (BedrockTokensIn,
  BedrockTokensOut, BedrockLatencyMs), X-Ray subsegments per model call,
  cost dimension tracking by agent and model, daily budget monitoring,
  and structured logging for AI pipelines. Use when instrumenting Bedrock
  calls or debugging AI pipeline performance.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/ai-observability/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# AI observability

## Role

You guide the instrumentation of Bedrock API calls in Catalyst with EMF metrics, X-Ray traces, and structured logs per `AGENTS.md` requirements and *Observability in the AI-Native Era* (Lipsig et al., Ch 1-3: observability pillars, Ch 7-8: AIOps).

## Instructions

### 1. Mandatory per-call EMF metrics (from AGENTS.md)

Every Bedrock Converse call MUST emit:

```python
from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit
import time
import structlog

logger = structlog.get_logger()
metrics = Metrics(namespace="Catalyst", service="pr-reviewer")

async def instrumented_converse(
    client: BedrockClient,
    model: BedrockModel,
    system_prompt: str,
    user_message: str,
    agent_name: str,
    **kwargs,
) -> dict:
    """Bedrock Converse with mandatory EMF metrics."""
    start = time.monotonic()

    try:
        response = await client.converse(model, system_prompt, user_message, **kwargs)
        latency_ms = (time.monotonic() - start) * 1000
        usage = extract_usage(response)

        # EMF metrics — dimensioned by Agent and Model
        metrics.add_dimension(name="Agent", value=agent_name)
        metrics.add_dimension(name="Model", value=model.value)
        metrics.add_metric(name="BedrockTokensIn", unit=MetricUnit.Count, value=usage["input_tokens"])
        metrics.add_metric(name="BedrockTokensOut", unit=MetricUnit.Count, value=usage["output_tokens"])
        metrics.add_metric(name="BedrockLatencyMs", unit=MetricUnit.Milliseconds, value=latency_ms)
        metrics.add_metric(name="BedrockCallSuccess", unit=MetricUnit.Count, value=1)

        # Structured log
        logger.info("bedrock_call_complete",
            agent=agent_name,
            model=model.value,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            latency_ms=round(latency_ms, 1),
        )

        return response

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        metrics.add_dimension(name="Agent", value=agent_name)
        metrics.add_dimension(name="Model", value=model.value)
        metrics.add_metric(name="BedrockCallError", unit=MetricUnit.Count, value=1)
        metrics.add_metric(name="BedrockLatencyMs", unit=MetricUnit.Milliseconds, value=latency_ms)

        logger.error("bedrock_call_failed",
            agent=agent_name, model=model.value,
            error_type=type(e).__name__, error=str(e),
            latency_ms=round(latency_ms, 1),
        )
        raise
```

### 2. X-Ray subsegments

```python
from aws_xray_sdk.core import xray_recorder

@xray_recorder.capture_async("bedrock_converse")
async def traced_converse(client, model, system_prompt, user_message, agent_name):
    subsegment = xray_recorder.current_subsegment()
    subsegment.put_annotation("agent", agent_name)
    subsegment.put_annotation("model", model.value)

    response = await instrumented_converse(client, model, system_prompt, user_message, agent_name)

    usage = extract_usage(response)
    subsegment.put_metadata("token_usage", usage)

    return response
```

### 3. Cost tracking

Per *Observability in the AI-Native Era* Ch 7 (AI cost monitoring):

```python
# Approximate cost per 1K tokens (update when pricing changes)
COST_PER_1K_TOKENS = {
    BedrockModel.SONNET: {"input": 0.003, "output": 0.015},
    BedrockModel.HAIKU: {"input": 0.0008, "output": 0.004},
}

def estimate_cost(model: BedrockModel, usage: dict) -> float:
    """Estimate USD cost for a single Bedrock call."""
    rates = COST_PER_1K_TOKENS[model]
    input_cost = (usage["input_tokens"] / 1000) * rates["input"]
    output_cost = (usage["output_tokens"] / 1000) * rates["output"]
    return round(input_cost + output_cost, 6)
```

Emit cost as an EMF metric:
```python
metrics.add_metric(name="BedrockEstimatedCostUSD", unit=MetricUnit.Count, value=cost)
```

### 4. Daily budget monitoring

The `budget-exhausted` modifier label in the state machine (`docs/ADR/STATE-MACHINE.md`) fires when the daily token budget is exceeded:

```python
DAILY_TOKEN_BUDGET = 500_000  # configurable via SSM

async def check_budget(dynamodb, today: str) -> bool:
    """Check if daily token budget is exhausted."""
    item = await dynamodb.get_item(
        TableName="catalyst-audit",
        Key={"actor_arn": {"S": "bedrock-budget"}, "event_ts": {"S": today}},
    )
    used = int(item.get("Item", {}).get("total_tokens", {}).get("N", "0"))
    return used < DAILY_TOKEN_BUDGET
```

### 5. Dashboard metrics

CloudWatch dashboard "Catalyst Andon" includes an AI panel:

| Metric | Statistic | Alarm |
|--------|-----------|-------|
| `BedrockLatencyMs` | p99 | > 30s for 3 consecutive points |
| `BedrockCallError` | Sum | > 5 in 5 min |
| `BedrockEstimatedCostUSD` | Sum (daily) | > $50 (page) |
| `BedrockTokensOut` | Sum (daily) | Budget tracking |

### 6. Structured log fields

Every AI-related log line includes:
- `trace_id` (X-Ray)
- `request_id` (Lambda or ECS task)
- `agent` (security-reviewer, style-reviewer, synthesizer)
- `model` (model ID)
- `input_tokens`, `output_tokens`
- `latency_ms`

Never log: full diff content, system prompts (may contain sensitive rules), raw model output (may be large).

## Output

- **Metric emission**: `instrumented_converse` wrapper with EMF metrics
- **X-Ray tracing**: subsegment with annotations and metadata
- **Cost tracking**: per-call cost estimation + daily budget check
- **Dashboard config**: metric/alarm specifications

## Guardrails

- Every Bedrock call MUST emit the 3 mandatory metrics (tokens in, tokens out, latency).
- Dimensions MUST include `Agent` and `Model` — no undimensioned metrics.
- Never log full diff content or raw model output in production.
- Cost estimates are approximations — use them for budgeting, not billing.
- Budget checks happen before model calls, not after.
