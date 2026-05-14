---
name: lambda-service-patterns
description: >-
  Lambda handler patterns for Catalyst services: aws-lambda-powertools
  decorators (Logger, Tracer, Metrics, EventHandler, Idempotency), SQS batch
  processing, packaging with Docker, cold-start mitigation, and structured
  error handling. Use when building webhook-handler, deploy-orchestrator,
  secrets-rotator, ops-intel-collector, ops-intel probes, or ops-intel-reporter.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/lambda-service-patterns/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->


# Lambda service patterns

## Role

You guide implementation of Catalyst's 7+ Lambda functions using `aws-lambda-powertools` for Python and async patterns where the runtime supports them. You enforce the standards from `AGENTS.md` and patterns from *Platform Engineering for Architects* (Ch 5, pp 157-198: integration, delivery, deployment automation). For handler clarity, decorator discipline (Powertools stack order), and testable handler cores, invoke `@clean-python-code`.

## Instructions

### 1. Handler skeleton with Powertools

Every Lambda handler follows this structure:

```python
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.idempotency import (
    DynamoDBPersistenceLayer, idempotent,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger(service="webhook-handler")
tracer = Tracer(service="webhook-handler")
metrics = Metrics(namespace="Catalyst", service="webhook-handler")

persistence = DynamoDBPersistenceLayer(table_name="catalyst-idempotency")

@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
@idempotent(persistence_store=persistence)
def handler(event: dict, context: LambdaContext) -> dict:
    ...
```

**Stack order matters**: Logger outermost (captures context), then Tracer, then Metrics, then Idempotency innermost.

### 2. Service-to-handler mapping (from `AGENTS.md` §4)

| Service | Trigger | Key patterns |
|---------|---------|-------------|
| `webhook-handler` | API Gateway HTTP API | HMAC validation, SQS FIFO send, event routing |
| `deploy-orchestrator` | Step Functions invocation | ECS update, ALB rule modify, DDB write, SNS publish |
| `secrets-rotator` | Secrets Manager rotation hook | `createSecret` / `setSecret` / `testSecret` / `finishSecret` stages |
| `ops-intel-collector` | EventBridge `rate(1 hour)` | SQS fan-out to 5 probe queues |
| `ops-intel probes` (5x) | SQS | Domain-scoped AWS API reads, S3 raw partition writes |
| `ops-intel-reporter` | EventBridge on probe completion | S3 read, DDB write, Bedrock Haiku summarize, SNS digest |

### 3. SQS batch processing

Use Powertools `BatchProcessor` for SQS-triggered Lambdas:

```python
from aws_lambda_powertools.utilities.batch import (
    BatchProcessor, EventType, batch_processor,
)

processor = BatchProcessor(event_type=EventType.SQS)

@tracer.capture_method
def record_handler(record: SQSRecord) -> None:
    payload = json.loads(record.body)
    # process one record; raise on failure for partial batch

@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def handler(event: dict, context: LambdaContext) -> dict:
    return processor.process(event, record_handler)
```

**Partial batch failure**: configure `FunctionResponseTypes: ReportBatchItemFailures` in the event source mapping (Terraform side). Failed records retry; successful ones don't.

### 4. Idempotency

Per `AGENTS.md`, the webhook-handler must deduplicate GitHub webhook deliveries:

- **SQS FIFO** deduplicates on `X-GitHub-Delivery` header as `MessageDeduplicationId`.
- **Powertools Idempotency** on the handler uses `catalyst-idempotency` DynamoDB table with `event_key_jmespath` set to the delivery ID.
- TTL: 24 hours (webhooks don't replay beyond that).

### 5. Packaging

Lambda functions are packaged as **Docker images** (not zip):

```dockerfile
FROM public.ecr.aws/lambda/python:3.14 AS builder
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -t /opt/python

FROM public.ecr.aws/lambda/python:3.14
COPY --from=builder /opt/python ${LAMBDA_TASK_ROOT}
COPY src/ ${LAMBDA_TASK_ROOT}/
CMD ["handler.handler"]
```

Per *Platform Engineering for Architects* Ch 5 (pp 167-175): source → container image → metadata-enriched deployment artifact. Tag images with git SHA, never `:latest`.

### 6. Cold-start mitigation

- **Provisioned concurrency** only for `webhook-handler` (latency-sensitive, API Gateway origin).
- Other Lambdas: acceptable cold starts (SQS/EventBridge tolerant).
- **Init-phase optimization**: import heavy modules (aioboto3, httpx) at module level; create clients in `__init__` outside the handler.
- Use `POWERTOOLS_DEV=true` locally for human-readable logs; JSON in production.

### 7. Structured logging

```python
logger.info("webhook_received",
    delivery_id=delivery_id,
    event_type=event["headers"]["X-GitHub-Event"],
    repo=payload["repository"]["full_name"],
)
```

Every log line automatically includes `trace_id` (X-Ray), `request_id` (Lambda context), `service`, `cold_start`, and `sampling_rate` via Powertools.

### 8. EMF metrics

```python
metrics.add_metric(name="WebhookProcessed", unit=MetricUnit.Count, value=1)
metrics.add_dimension(name="EventType", value=event_type)
metrics.add_dimension(name="Repository", value=repo_name)
```

Per `AGENTS.md`: emit EMF metrics for any long-running operation with latency, error count, and relevant dimensions.

### 9. Error handling

- **Retriable errors** (AWS throttling, transient network): raise, let Lambda retry (SQS visibility timeout handles backoff).
- **Permanent errors** (malformed payload, auth failure): log at `error` level, return failure response, do NOT retry.
- **State machine violations**: log `IllegalTransitionError`, comment on the GitHub Issue, move to DLQ.

### 10. Testing

```python
# tests/unit/test_webhook_handler.py
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEventV2

def test_valid_push_event(mock_sqs, sample_push_payload):
    event = APIGatewayProxyEventV2({"body": json.dumps(sample_push_payload), ...})
    result = handler(event.raw_event, MockContext())
    assert result["statusCode"] == 200
    mock_sqs.send_message.assert_called_once()
```

Use Powertools event classes for test fixtures. Mock AWS services with `moto` or manual mocks.

## Output

- **New Lambda**: handler skeleton + Powertools decorators + Terraform module reference (`infrastructure/modules/composite/lambda-python-fn/`)
- **Batch processing**: processor setup + partial failure config + test
- **Idempotency**: persistence layer config + JMESPath key + TTL recommendation

## Guardrails

- No `boto3` in handler hot path — use `aioboto3` or Powertools utilities.
- No `print()` — Powertools `Logger` only.
- No secrets in environment variables or code — use Secrets Manager with `get_secret` utility.
- No `:latest` image tags — git SHA or semver.
- 15-minute Lambda ceiling drives the Fargate/Lambda split — if an operation might exceed 10 minutes, it belongs on Fargate, not Lambda.
- Each probe Lambda gets its own IAM role scoped to its domain only (e.g., S3-audit role can't see IAM).
