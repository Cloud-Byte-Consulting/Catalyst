---
name: async-orchestration
description: >-
  Event-driven orchestration patterns for Catalyst: SQS FIFO with dedup,
  EventBridge rules and schedules, DLQ strategies, Step Functions state
  machines, retry policies with tenacity, and async flow design across
  services. Use when designing message flows, error recovery, or multi-step
  orchestration.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/async-orchestration/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->


# Async orchestration

## Role

You guide the design and implementation of Catalyst's event-driven architecture — the message flows, queues, schedules, and state machines that connect the 8 services. You enforce async-first patterns from `AGENTS.md` and orchestration principles from *Platform Engineering for Architects* (Ch 5, pp 188-197: sustainable CI/CD, event-driven lifecycle orchestration, subscribing to events).

## Instructions

### 1. Message flow map (from `AGENTS.md` §3-4)

```
GitHub webhook → API GW → webhook-handler (Lambda)
                              │
                              ├──► SQS FIFO (pr-review queue) → pr-reviewer-consumer (Fargate)
                              └──► catalyst-api (HTTP) → GitHub Issues state machine

EventBridge rate(1 hour) → ops-intel-collector (Lambda)
                              │
                              └──► SQS fan-out → 5 probe Lambdas → S3 raw partitions
                                                                       │
                                                                       └──► ops-intel-reporter (Lambda)
                                                                            → DDB + SNS digest

Step Functions → deploy-orchestrator (Lambda)
                    │
                    ├──► ECS UpdateService (blue/green)
                    ├──► ALB ModifyRule (traffic shift)
                    ├──► DDB write (deployment record)
                    └──► SNS publish (notification)
```

### 2. SQS FIFO patterns

For the PR review queue and webhook processing:

```python
# Sending to SQS FIFO
async def enqueue_pr_review(
    sqs: SQSClient,
    queue_url: str,
    pr_event: PREvent,
) -> str:
    response = await sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=pr_event.model_dump_json(),
        MessageGroupId=f"{pr_event.repo}#{pr_event.pr_number}",
        MessageDeduplicationId=pr_event.delivery_id,
    )
    return response["MessageId"]
```

**Key design decisions:**
- `MessageGroupId` = `repo#pr_number` — serializes processing per PR (no concurrent reviews of same PR).
- `MessageDeduplicationId` = GitHub's `X-GitHub-Delivery` header — prevents duplicate processing of the same webhook.
- Visibility timeout = 6x the expected processing time (Fargate PR review ≈ 5 min → 30 min visibility).

### 3. EventBridge rules

```python
# ops-intel collector schedule (defined in Terraform, documented here for context)
# EventBridge rule: rate(1 hour)
# Target: ops-intel-collector Lambda
# Input: {"trigger": "scheduled", "domains": ["s3", "iam", "cloudwatch", "github", "inventory"]}
```

Per *Platform Engineering for Architects* Ch 5 (p191-193, analyzing events): EventBridge rules should be **specific** — one rule per trigger pattern, not a catch-all. Each rule targets exactly one Lambda with a typed input.

### 4. DLQ strategy

Every queue has a Dead Letter Queue:

| Queue | DLQ | Max receives | Action on DLQ |
|-------|-----|-------------|---------------|
| PR review FIFO | `pr-review-dlq` | 3 | Alert via SNS, create `type/incident` Issue |
| Webhook FIFO | `webhook-dlq` | 3 | Alert, log for manual replay |
| Ops-intel fan-out | `ops-intel-dlq` | 2 | Log, include in next digest as "probe failure" |

**DLQ monitoring**: CloudWatch alarm on `ApproximateNumberOfMessagesVisible > 0` triggers the Andon alert. DLQ messages are never silently discarded.

### 5. Step Functions for deploy orchestration

The deploy-orchestrator uses Step Functions for multi-step deployments:

```json
{
  "Comment": "Blue/green deploy orchestration",
  "StartAt": "ValidateDeployment",
  "States": {
    "ValidateDeployment": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:deploy-orchestrator",
      "Parameters": { "action": "validate", "deployment_id.$": "$.deployment_id" },
      "Next": "UpdateECSService",
      "Catch": [{ "ErrorEquals": ["ValidationError"], "Next": "FailDeploy" }]
    },
    "UpdateECSService": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:deploy-orchestrator",
      "Parameters": { "action": "update_ecs", "deployment_id.$": "$.deployment_id" },
      "Next": "WaitForHealthy",
      "Catch": [{ "ErrorEquals": ["States.ALL"], "Next": "RollbackDeploy" }]
    },
    "WaitForHealthy": {
      "Type": "Wait",
      "Seconds": 60,
      "Next": "ShiftTraffic"
    },
    "ShiftTraffic": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:deploy-orchestrator",
      "Parameters": { "action": "shift_traffic", "deployment_id.$": "$.deployment_id" },
      "Next": "BakeMonitor"
    },
    "BakeMonitor": {
      "Type": "Wait",
      "Seconds": 1800,
      "Next": "CompleteDeploy"
    },
    "CompleteDeploy": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:deploy-orchestrator",
      "Parameters": { "action": "complete" },
      "End": true
    },
    "RollbackDeploy": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:deploy-orchestrator",
      "Parameters": { "action": "rollback" },
      "Next": "FailDeploy"
    },
    "FailDeploy": {
      "Type": "Fail",
      "Cause": "Deployment failed or validation error"
    }
  }
}
```

### 6. Retry patterns with tenacity

For transient AWS failures in service code:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from botocore.exceptions import ClientError

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(ClientError),
    before_sleep=lambda retry_state: logger.warning(
        "retrying_aws_call",
        attempt=retry_state.attempt_number,
        exception=str(retry_state.outcome.exception()),
    ),
)
async def update_ecs_service(ecs, cluster, service, task_def):
    ...
```

**Rules:**
- Retry on `ClientError` (throttling, transient) — max 3 attempts.
- Do NOT retry on `IllegalTransitionError`, `ValidationError`, or auth failures.
- Log every retry with attempt number and exception.

### 7. Fan-out pattern (ops-intel)

The collector fans out to 5 domain-specific probe queues:

```python
PROBE_DOMAINS = ["s3-encryption", "iam-usage", "cw-ingestion", "gha-history", "resource-inventory"]

async def fan_out_probes(sqs, probe_queue_urls: dict[str, str]) -> None:
    tasks = [
        sqs.send_message(
            QueueUrl=probe_queue_urls[domain],
            MessageBody=json.dumps({"domain": domain, "run_id": run_id}),
        )
        for domain in PROBE_DOMAINS
    ]
    await asyncio.gather(*tasks)
```

### 8. Correlation and tracing

Every message carries:
- `trace_id` — X-Ray trace ID propagated across services
- `run_id` — ULID generated at the originating event
- `construct_address` — the five-level address for the affected resource

These flow from webhook → SQS → consumer → GitHub Issue comment → DDB record, creating a complete audit trail queryable by any dimension.

## Output

- **Queue design**: SQS FIFO config + DLQ + monitoring alarm
- **EventBridge rule**: schedule or event pattern + Lambda target
- **Step Functions**: state machine definition + Lambda action dispatcher
- **Retry config**: tenacity decorator + error classification
- **Fan-out**: asyncio.gather pattern + correlation ID propagation

## Guardrails

- No synchronous AWS calls in request paths — all I/O is async via `aioboto3`.
- No unbounded retries — max 3 attempts for transient, 0 for permanent errors.
- DLQ messages are never silently discarded — alarm + Issue creation.
- SQS FIFO `MessageGroupId` must be scoped to prevent head-of-line blocking across unrelated work.
- Step Functions state machines must have explicit `Catch` and `Fail` states — no unhandled errors.
- Visibility timeout must be ≥ 6x expected processing time to prevent phantom duplicates.
