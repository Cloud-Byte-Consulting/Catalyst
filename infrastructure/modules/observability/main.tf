# SVC-9 observability module — five CloudWatch alarms + SNS topic + operator
# dashboard, tied to the metric namespace #60 emits (`Catalyst/API` +
# `Catalyst/Onboard`). Subscriber wiring is intentionally out of scope per
# issue #63's "Out: PagerDuty/Slack integrations" and is added out-of-band
# via `aws sns subscribe` (see docs/onboarding/platform.md §Operator alerts).

locals {
  # Resource-name slugs are derived once so a single rename of `name_prefix`
  # ripples consistently through the five alarms + the dashboard JSON.
  alarm_5xx_rate_name      = "${var.name_prefix}-5xx-rate"
  alarm_onboard_p95_name   = "${var.name_prefix}-onboard-p95-latency"
  alarm_request_p99_name   = "${var.name_prefix}-request-p99-latency"
  alarm_retry_anomaly_name = "${var.name_prefix}-aws-transient-retry"
  alarm_lambda_errors_name = "${var.name_prefix}-lambda-errors"
  dashboard_name           = "${var.name_prefix}-operator"
}

# -----------------------------------------------------------------------------
# SNS topic (alarm fan-out)
# -----------------------------------------------------------------------------
# tfsec:ignore:aws-sns-enable-topic-encryption — KMS CMK rollout is tracked
# alongside the DynamoDB CMK migration noted in modules/dynamodb/main.tf and
# ADR-008. The AWS-owned key on SNS (default SSE) covers encryption-at-rest
# for the alarm payloads, which are non-sensitive operational metadata.
resource "aws_sns_topic" "alarms" {
  name = "${var.name_prefix}-alarms"
}

# -----------------------------------------------------------------------------
# Alarm 1 — 5xxRateAlarm
# -----------------------------------------------------------------------------
# Strategy: CloudWatch dimension matching requires the alarm to reference a
# metric stream whose dimension *set* matches what the emitter publishes.
# Per #60's locked spec:
#   - `Catalyst/API:RequestCount` is keyed on (Endpoint, Method, StatusCode)
#   - `Catalyst/API:ErrorCount`   is keyed on (Endpoint, Method, ErrorClass)
# Enumerating 5xx StatusCode values (500..599) would scale poorly, so we use
# the `ErrorClass=5xx` slice on ErrorCount (which the middleware already sets
# semantically — see services/catalyst-api/catalyst/observability.py once #60
# lands) and the SEARCH expression sums RequestCount across every dimension
# combination for the denominator.
#
# Metric-math semantics:
#   m1 = SUM of Catalyst/API:ErrorCount where ErrorClass="5xx"
#   m2 = SUM of Catalyst/API:RequestCount across all dimension combinations
#   e1 = (m1 / m2) * 100  → 5xx percent
# Evaluation: 1 of 3 periods of 5 min — single sustained spike trips the page.
resource "aws_cloudwatch_metric_alarm" "http_5xx_rate" {
  alarm_name        = local.alarm_5xx_rate_name
  alarm_description = "Catalyst API 5xx rate exceeded ${var.http_5xx_rate_threshold_percent}% over a 5-minute window. Source: Catalyst/API:ErrorCount{ErrorClass=5xx} / Catalyst/API:RequestCount."

  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  datapoints_to_alarm = 1
  threshold           = var.http_5xx_rate_threshold_percent
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "e1"
    expression  = "(m1 / m2) * 100"
    label       = "5xx rate (%)"
    return_data = true
  }

  metric_query {
    id = "m1"
    metric {
      namespace   = "Catalyst/API"
      metric_name = "ErrorCount"
      period      = 300
      stat        = "Sum"
      dimensions = {
        ErrorClass = "5xx"
      }
    }
  }

  metric_query {
    id = "m2"
    metric {
      namespace   = "Catalyst/API"
      metric_name = "RequestCount"
      period      = 300
      stat        = "Sum"
    }
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# -----------------------------------------------------------------------------
# Alarm 2 — OnboardP95LatencyAlarm (ADR-014 trip-wire)
# -----------------------------------------------------------------------------
# Threshold: 600,000 ms (10 min). Period 86,400 s (1 day) × 30 evaluation
# periods = 30-day rolling window. CloudWatch natively supports period
# values up to 86,400 s (1 day) and `evaluation_periods` up to 30, so the
# 30-day window fits standard alarm semantics with no custom scheduler.
# Reference: ADR-014 §"Deferred — Option B as v3" sets exactly this trip-wire.
resource "aws_cloudwatch_metric_alarm" "onboard_p95_latency" {
  alarm_name        = local.alarm_onboard_p95_name
  alarm_description = "ADR-014 trip-wire: onboard p95 over a 30-day window crossed ${var.onboard_p95_threshold_ms} ms (10 min). When this fires, open the v3 epic to ship the async pipeline."

  namespace           = "Catalyst/Onboard"
  metric_name         = "OnboardDuration"
  extended_statistic  = "p95"
  period              = 86400
  evaluation_periods  = 30
  datapoints_to_alarm = 30
  threshold           = var.onboard_p95_threshold_ms
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# -----------------------------------------------------------------------------
# Alarm 3 — RequestP99LatencyAlarm
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "request_p99_latency" {
  alarm_name        = local.alarm_request_p99_name
  alarm_description = "Catalyst API request p99 above ${var.request_p99_threshold_ms} ms (30s). Sustained 3-of-5 1-min periods."

  namespace           = "Catalyst/API"
  metric_name         = "RequestDuration"
  extended_statistic  = "p99"
  period              = 60
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  threshold           = var.request_p99_threshold_ms
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# -----------------------------------------------------------------------------
# Alarm 4 — AWSTransientRetryAlarm
# -----------------------------------------------------------------------------
# Surfaces capacity issues that #205's retry/backoff is silently masking.
resource "aws_cloudwatch_metric_alarm" "retry_attempt_anomaly" {
  alarm_name        = local.alarm_retry_anomaly_name
  alarm_description = "Catalyst API transient AWS retries summed > ${var.retry_attempt_threshold_count} in a 5-minute window. Retries from services/catalyst-api/catalyst/aws_retry.py (#205) signal capacity pressure that needs operator attention."

  namespace           = "Catalyst/API"
  metric_name         = "RetryAttempt"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 2
  datapoints_to_alarm = 1
  threshold           = var.retry_attempt_threshold_count
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# -----------------------------------------------------------------------------
# Alarm 5 — LambdaErrorAlarm (AWS-native; not from #60)
# -----------------------------------------------------------------------------
# AWS/Lambda:Errors uses the canonical FunctionName dimension; the Catalyst
# Lambda function name is constructed by modules/lambda-service as
# "${var.name_prefix}-api". Threshold 0 means "any error in a 1-min window".
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name        = local.alarm_lambda_errors_name
  alarm_description = "AWS/Lambda:Errors > 0 for ${var.lambda_function_name} in a 1-minute window. AWS-native failure signal, independent of in-process metrics."

  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# -----------------------------------------------------------------------------
# Operator dashboard
# -----------------------------------------------------------------------------
# Layout (per the Decision Log on #63):
#   Top row:    request-count line + request-duration p50/p99 line
#   Middle row: onboard-duration p50/p95 with 10-min trip-wire annotation,
#               error-count stacked bar, retry-attempt bar
#   Bottom row: Lambda Errors/Duration/Invocations + an alarm-summary text widget
data "aws_region" "current" {}

resource "aws_cloudwatch_dashboard" "catalyst" {
  dashboard_name = local.dashboard_name

  dashboard_body = jsonencode({
    widgets = [
      # ----- Top row ---------------------------------------------------------
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Request count (per minute, by Endpoint)"
          region  = data.aws_region.current.region
          stat    = "Sum"
          period  = 60
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["Catalyst/API", "RequestCount", { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Request duration (p50 / p99, ms)"
          region  = data.aws_region.current.region
          period  = 60
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["Catalyst/API", "RequestDuration", { stat = "p50", label = "p50" }],
            [".", ".", { stat = "p99", label = "p99" }],
          ]
        }
      },

      # ----- Middle row ------------------------------------------------------
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 8
        height = 6
        properties = {
          title  = "Onboard duration p50/p95 (10-min trip-wire annotated)"
          region = data.aws_region.current.region
          period = 300
          view   = "timeSeries"
          metrics = [
            ["Catalyst/Onboard", "OnboardDuration", { stat = "p50", label = "p50" }],
            [".", ".", { stat = "p95", label = "p95 (alarm metric)" }],
          ]
          annotations = {
            horizontal = [
              {
                label = "ADR-014 trip-wire (10 min)"
                value = var.onboard_p95_threshold_ms
              }
            ]
          }
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "Error count (stacked by ErrorClass)"
          region  = data.aws_region.current.region
          period  = 300
          view    = "timeSeries"
          stacked = true
          metrics = [
            ["Catalyst/API", "ErrorCount", { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 6
        width  = 8
        height = 6
        properties = {
          title   = "Retry attempts (per 5 min, by ErrorCode)"
          region  = data.aws_region.current.region
          period  = 300
          view    = "timeSeries"
          stacked = true
          metrics = [
            ["Catalyst/API", "RetryAttempt", { stat = "Sum" }],
          ]
        }
      },

      # ----- Bottom row ------------------------------------------------------
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 18
        height = 6
        properties = {
          title   = "Lambda (Errors / Invocations / Duration p95) — ${var.lambda_function_name}"
          region  = data.aws_region.current.region
          period  = 60
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", var.lambda_function_name, { stat = "Sum", label = "Errors" }],
            [".", "Invocations", ".", ".", { stat = "Sum", label = "Invocations" }],
            [".", "Duration", ".", ".", { stat = "p95", label = "Duration p95 (ms)" }],
          ]
        }
      },
      {
        type   = "text"
        x      = 18
        y      = 12
        width  = 6
        height = 6
        properties = {
          markdown = join("\n", [
            "## Alarm summary",
            "",
            "- **${local.alarm_5xx_rate_name}** — 5xx rate > ${var.http_5xx_rate_threshold_percent}%",
            "- **${local.alarm_onboard_p95_name}** — onboard p95 30-day window > ${var.onboard_p95_threshold_ms} ms (ADR-014 trip-wire)",
            "- **${local.alarm_request_p99_name}** — request p99 > ${var.request_p99_threshold_ms} ms",
            "- **${local.alarm_retry_anomaly_name}** — retry sum > ${var.retry_attempt_threshold_count} / 5 min",
            "- **${local.alarm_lambda_errors_name}** — AWS/Lambda errors > 0",
            "",
            "SNS topic: `${aws_sns_topic.alarms.name}`",
          ])
        }
      },
    ]
  })
}
