# `observability`

CloudWatch alarms, SNS fan-out, and a single operator dashboard for the
Catalyst control plane. Implements **SVC-9** ([#63](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/63))
against the metric namespaces emitted by **SVC-6** ([#60](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/60)):

| Namespace          | Source                                                   |
|--------------------|----------------------------------------------------------|
| `Catalyst/API`     | FastAPI middleware in `services/catalyst-api/catalyst/observability.py` (#60) |
| `Catalyst/Onboard` | Existing onboard handler (#167) — `OnboardDuration` only |
| `AWS/Lambda`       | AWS-native, free of charge                               |

Subscriber wiring is **out of scope** for this module by design ([#63 Scope:
"Out: PagerDuty/Slack integrations"](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/63)).
Operators subscribe endpoints out-of-band — see
[`docs/onboarding/platform.md`](../../../docs/onboarding/platform.md)
§"Operator alerts".

---

## Inputs

| Name                              | Type     | Default       | Description |
|-----------------------------------|----------|---------------|-------------|
| `name_prefix`                     | `string` | `"catalyst"`  | Resource name prefix; aligns with the rest of the composite. |
| `lambda_function_name`            | `string` | `"catalyst-api"` | Lambda function name fed into the `FunctionName` dimension of `LambdaErrorAlarm`. Matches `${var.name_prefix}-api` from `modules/lambda-service`. |
| `http_5xx_rate_threshold_percent` | `number` | `5`           | Threshold percent for the 5xxRateAlarm. Terraform identifiers cannot begin with a digit so the canonical "5xx" prefix is rendered as `http_5xx_…`. |
| `onboard_p95_threshold_ms`        | `number` | `600000`      | ADR-014 trip-wire threshold (10 min). |
| `request_p99_threshold_ms`        | `number` | `30000`       | p99 latency threshold (30 s). |
| `retry_attempt_threshold_count`   | `number` | `50`          | RetryAttempt sum per 5-minute window above which `AWSTransientRetryAlarm` fires. |

## Outputs

| Name             | Description |
|------------------|-------------|
| `sns_topic_arn`  | ARN of the `catalyst-alarms` SNS topic. |
| `sns_topic_name` | Bare topic name, convenient for `aws sns subscribe …`. |
| `dashboard_name` | CloudWatch dashboard name. |
| `dashboard_url`  | Direct console URL for the dashboard (linked from `docs/onboarding/platform.md`). |
| `alarm_names`    | List of the five alarm names. |

---

## The five alarms

| # | Name                        | Resource                                       | What it catches |
|---|-----------------------------|------------------------------------------------|-----------------|
| 1 | `${prefix}-5xx-rate`        | `aws_cloudwatch_metric_alarm.http_5xx_rate`   | Sustained server-side error spike: `(Catalyst/API:ErrorCount{ErrorClass=5xx} / Catalyst/API:RequestCount) * 100 > 5%` over 1-of-3 periods of 5 min. |
| 2 | `${prefix}-onboard-p95-latency` | `aws_cloudwatch_metric_alarm.onboard_p95_latency` | **ADR-014 trip-wire.** `Catalyst/Onboard:OnboardDuration` p95 > 10 min over a 30-day rolling window. When this fires, open the v3 epic to ship the async pipeline. |
| 3 | `${prefix}-request-p99-latency` | `aws_cloudwatch_metric_alarm.request_p99_latency` | API latency degradation: `Catalyst/API:RequestDuration` p99 > 30 s, 3-of-5 periods of 1 min. |
| 4 | `${prefix}-aws-transient-retry` | `aws_cloudwatch_metric_alarm.retry_attempt_anomaly` | Capacity issues masked by #205's retry/backoff: `Catalyst/API:RetryAttempt` Sum > 50 / 5 min, 1-of-2 periods. |
| 5 | `${prefix}-lambda-errors`   | `aws_cloudwatch_metric_alarm.lambda_errors`    | AWS-native: `AWS/Lambda:Errors > 0` per 1 min for the `catalyst-api` function. Independent failure signal from outside the process. |

### 5xx rate alarm strategy (note)

`Catalyst/API:ErrorCount` is published with dimension `ErrorClass` (per #60's
locked metric specification) but `RequestCount` is published with
`StatusCode`. CloudWatch's `dimensions` matching is exact: enumerating
500–599 on `RequestCount` would scale poorly, so the alarm uses metric
math (`metric_query`) to compute:

```
e1 = (m1 / m2) * 100
m1 = SUM(Catalyst/API:ErrorCount{ErrorClass=5xx})
m2 = SUM(Catalyst/API:RequestCount)   # across all dim combinations
```

This relies on #60 setting `ErrorClass=5xx` on the `ErrorCount` metric for
any 5xx response. The dimension contract is the load-bearing piece — see
the metric-spec table at the top of #60's Decision Log.

### Trip-wire alarm significance (ADR-014)

The `onboard_p95_latency` alarm is the operational realisation of
[ADR-014](../../../docs/ADR/ADR-014-services-onboard-provisioning-mode.md)
§"Deferred — Option B as v3". The ADR commits to *not shipping* the async
onboard pipeline until empirical p95 onboard runtime over a rolling 30-day
window crosses 10 minutes — well under the Lambda 15-min ceiling. This
alarm computes that exact statistic from `Catalyst/Onboard:OnboardDuration`
and pages on the threshold. When it fires, open the v3 epic; until it
does, the synchronous Terraform-in-Lambda path remains the right shape.

---

## Operator action — subscribe to alerts

The Terraform stops at the SNS topic. **Subscribers are deliberately
out-of-band** so operator decisions about routing (email vs PagerDuty vs
Slack) don't require a Terraform PR every time the on-call rotation
changes. The pattern:

```bash
# Email — confirmation step is in-band via the email client
aws sns subscribe \
  --topic-arn "$(terraform -chdir=infrastructure output -raw sns_topic_arn)" \
  --protocol email \
  --notification-endpoint operator@example.com

# PagerDuty (assumes an SNS-aware service is set up in PagerDuty)
aws sns subscribe \
  --topic-arn "$(terraform -chdir=infrastructure output -raw sns_topic_arn)" \
  --protocol https \
  --notification-endpoint "https://events.pagerduty.com/integration/<key>/enqueue"

# Slack (via an SNS-to-Slack relay Lambda; the relay is not provisioned here)
aws sns subscribe \
  --topic-arn "$(terraform -chdir=infrastructure output -raw sns_topic_arn)" \
  --protocol lambda \
  --notification-endpoint "arn:aws:lambda:us-west-2:<account>:function:sns-to-slack"
```

See [`docs/onboarding/platform.md`](../../../docs/onboarding/platform.md)
§"Operator alerts" for the canonical operator runbook.

---

## Cross-PR coordination

- **#60 (parallel)** emits `Catalyst/API:RequestCount`, `RequestDuration`,
  `ErrorCount`, `RetryAttempt`. Until #60 merges, the alarms exist but
  never fire because no datapoints arrive in the namespace. Acceptable
  interim state — the topic and dashboard still come up cleanly.
- **#103 (parallel)** adds `POST /products/{product_id}/deploy`. The
  dashboard widgets aggregate across the `Endpoint` dimension, so the
  new endpoint surfaces automatically once #60's middleware is live.

---

## Related

- [ADR-014 — `POST /services/onboard` provisioning mode](../../../docs/ADR/ADR-014-services-onboard-provisioning-mode.md) §"Deferred — Option B as v3"
- [#60 Decision Log](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/60) — locked metric names/dimensions this module reads
- [`docs/onboarding/platform.md`](../../../docs/onboarding/platform.md) §"Operator alerts"
- [`infrastructure/tests/observability.tftest.hcl`](../../tests/observability.tftest.hcl) — module test
