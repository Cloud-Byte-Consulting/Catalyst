---
name: observability-alarms
description: >
  CloudWatch alarms, EMF structured metrics, composite alarms, SLO burn-rate
  math, the Andon dashboard, SNS routing (page vs ticket), and the 8 named
  alarms from AGENTS.md. Use when designing monitoring, alerting, or the
  operational dashboard.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/observability-alarms/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

## Role

Observability engineer designing the monitoring, alerting, and dashboarding
layer for the Catalyst IDP. Every production signal flows through structured
metrics (EMF), structured logs (JSON via structlog), and distributed traces
(X-Ray) — the three pillars unified in a single operational view.

## Instructions

### 1. The 8 named alarms

| # | Alarm name | Metric | Threshold | Severity |
|--:|---|---|---|---|
| 1 | `catalyst-api-latency` | p99 response time | > 500ms for 3/5 datapoints | Page |
| 2 | `catalyst-api-error-rate` | 5xx count / total requests | > 1% for 3/5 datapoints | Page |
| 3 | `catalyst-deploy-failure` | CodeDeploy deployment state | any FAILED event | Page |
| 4 | `catalyst-dlq-depth` | SQS ApproximateNumberOfMessagesVisible | > 0 for 2/2 datapoints | Ticket |
| 5 | `catalyst-bedrock-error` | Bedrock Converse API errors | > 5 in 5 min | Ticket |
| 6 | `catalyst-budget-threshold` | AWS Budgets actual > threshold | 80% of monthly budget | Ticket |
| 7 | `catalyst-aurora-cpu` | Aurora CPUUtilization | > 80% for 5/5 datapoints | Ticket |
| 8 | `catalyst-ops-intel-probe-failure` | ops-intel probe Lambda errors | > 0 for 3 consecutive runs | Ticket |

### 2. Page vs ticket split

- **Page** (alarms 1-3): routes to SNS topic `catalyst-pages` which triggers
  PagerDuty/Opsgenie integration. These represent customer-impacting or
  deployment-safety issues requiring immediate human response.
- **Ticket** (alarms 4-8): routes to SNS topic `catalyst-tickets` which
  creates a Jira/GitHub Issue. These represent degradation signals that need
  investigation within SLA but are not immediately customer-impacting.

### 3. EMF metric patterns with structlog

Every service emits metrics via Embedded Metric Format (EMF) in structured
JSON logs. Pattern with `structlog` and `aws-lambda-powertools`:

```python
import structlog
from aws_lambda_powertools.metrics import MetricUnit

logger = structlog.get_logger()

# EMF metric embedded in log line
logger.info(
    "bedrock_converse_complete",
    trace_id=ctx.trace_id,
    request_id=ctx.request_id,
    _aws={
        "Timestamp": int(time.time() * 1000),
        "CloudWatchMetrics": [{
            "Namespace": "Catalyst",
            "Dimensions": [["Agent", "Model"]],
            "Metrics": [
                {"Name": "BedrockTokensIn", "Unit": "Count"},
                {"Name": "BedrockTokensOut", "Unit": "Count"},
                {"Name": "BedrockLatencyMs", "Unit": "Milliseconds"},
            ]
        }]
    },
    Agent=agent_name,
    Model=model_id,
    BedrockTokensIn=response.usage.input_tokens,
    BedrockTokensOut=response.usage.output_tokens,
    BedrockLatencyMs=duration_ms,
)
```

Every log line includes `trace_id` and `request_id` — no exceptions.

### 4. Composite alarms for correlated failures

Create composite alarms that detect correlated failure patterns:

- `catalyst-api-degraded` = `catalyst-api-latency` AND `catalyst-aurora-cpu`
  (database pressure causing API slowdown)
- `catalyst-deploy-unsafe` = `catalyst-api-error-rate` AND
  `catalyst-deploy-failure` (failed deploy causing errors)

Composite alarms use `aws_cloudwatch_composite_alarm` with alarm rule
expressions. They route to the higher severity of their children.

### 5. SLO definitions

| SLI | Target | Window |
|---|---|---|
| Availability (non-5xx / total) | 99.9% | 30-day rolling |
| Latency p99 | < 500ms | 30-day rolling |

Error budget: 0.1% of requests per 30-day window. At current traffic
estimates (~100k requests/month), that is ~100 allowed failures.

### 6. Burn-rate alerting (multi-window multi-burn-rate)

Implement Google SRE burn-rate alerting with three windows:

| Window | Burn rate | Meaning | Action |
|---|---|---|---|
| 1 hour | 14.4x | Budget exhausted in 5 hours | Page |
| 6 hours | 6x | Budget exhausted in 5 days | Page |
| 24 hours | 3x | Budget exhausted in 10 days | Ticket |

Each burn-rate alert is a CloudWatch Metric Math expression:

```
error_rate = m1 / m2  (errors / total)
burn_rate = error_rate / (1 - 0.999)  (normalized to SLO)
```

Short window confirms the burn is current (not a brief spike that already
recovered). Alert fires only when BOTH long and short windows exceed threshold.

### 7. Andon dashboard layout

Single CloudWatch dashboard `Catalyst-Andon` with 6 columns matching the
deploy state machine states:

| Column 1 | Column 2 | Column 3 | Column 4 | Column 5 | Column 6 |
|---|---|---|---|---|---|
| Pending | Validating | Shifting | Baking | Complete | Failed |

Each column contains:
- Active deployment count (number widget)
- State duration (time series)
- Relevant alarms (alarm status widget)
- Key metrics for that phase (latency, error rate, traffic split %)

Additional rows below the state columns:
- SLO burn-rate gauges (availability + latency)
- Error budget remaining (% of 30-day budget consumed)
- DLQ depth across all queues
- Bedrock token usage and cost estimate

### 8. Three pillars unified view (Observability in AI-Native Era)

Per Lipsig et al: metrics, logs, and traces must be correlated — not siloed.

- **Metrics** — EMF dimensions include `trace_id` for drill-down from metric
  anomaly to specific trace.
- **Logs** — structured JSON with `trace_id` and `request_id` fields; CloudWatch
  Logs Insights queries can join on these identifiers.
- **Traces** — X-Ray segments annotated with custom metadata (deployment_id,
  construct_address) enabling trace filtering by business context.

The Andon dashboard links all three: clicking an alarm links to a Logs Insights
query filtered by the alarm's evaluation period; trace maps show the
distributed call path for failing requests.

## Output

- Terraform alarm resources in `infrastructure/modules/leaf/cloudwatch-alarms/`
- Dashboard JSON in `infrastructure/modules/leaf/cloudwatch-dashboard/`
- EMF helper module in `services/shared/metrics.py`
- SLO burn-rate Metric Math expressions in alarm Terraform

## Guardrails

- Never create an alarm without an `alarm_description` that includes the
  RUNBOOK.md section link and escalation path.
- Never use `treat_missing_data = "notBreaching"` on availability alarms —
  missing data means the service may be down.
- Never emit metrics without dimensions — undimensioned metrics are
  unaggregatable and create cost waste.
- Never log PII, secrets, or bearer tokens — even in debug mode.
- Always include `trace_id` and `request_id` in every log line.
- Always use `period = 60` (1 minute) for page-severity alarms — 5-minute
  periods are too slow for customer-impacting issues.
