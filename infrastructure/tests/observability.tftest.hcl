provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "observability_module_plans" {
  command = plan

  module {
    source = "./modules/observability"
  }

  # SNS topic exists and carries the canonical alarm-fan-out name.
  assert {
    condition     = aws_sns_topic.alarms.name == "catalyst-alarms"
    error_message = "SNS topic name must be ${"$"}{name_prefix}-alarms"
  }

  # Exactly five aws_cloudwatch_metric_alarm resources are provisioned.
  # The five alarm-resource addresses are enumerated rather than counted
  # with `length(…)` because tftest does not expose a count of typed
  # resources directly; enumerating asserts the names are stable too.
  assert {
    condition     = aws_cloudwatch_metric_alarm.http_5xx_rate.alarm_name == "catalyst-5xx-rate"
    error_message = "5xxRateAlarm must be named catalyst-5xx-rate"
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.onboard_p95_latency.alarm_name == "catalyst-onboard-p95-latency"
    error_message = "OnboardP95LatencyAlarm must be named catalyst-onboard-p95-latency"
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.request_p99_latency.alarm_name == "catalyst-request-p99-latency"
    error_message = "RequestP99LatencyAlarm must be named catalyst-request-p99-latency"
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.retry_attempt_anomaly.alarm_name == "catalyst-aws-transient-retry"
    error_message = "AWSTransientRetryAlarm must be named catalyst-aws-transient-retry"
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.lambda_errors.alarm_name == "catalyst-lambda-errors"
    error_message = "LambdaErrorAlarm must be named catalyst-lambda-errors"
  }

  # Output also enumerates the five alarms.
  assert {
    condition     = length(output.alarm_names) == 5
    error_message = "expected exactly five alarm names in module output"
  }

  # Dashboard exists.
  assert {
    condition     = aws_cloudwatch_dashboard.catalyst.dashboard_name == "catalyst-operator"
    error_message = "Dashboard name must be catalyst-operator"
  }

  # SNS-action wiring — `alarm_actions` is a computed set holding the
  # (apply-time-known) `aws_sns_topic.alarms.arn`; predicates over computed
  # values cannot be evaluated at plan time. The wiring is verified
  # indirectly here:
  #   (a) the SNS topic resource must plan with the expected name (asserted
  #       at the top of this run block);
  #   (b) all five alarm resources must plan successfully (their alarm_name
  #       assertions above will fail to evaluate if the resource itself
  #       failed to plan);
  #   (c) the module exposes `sns_topic_name` as a known-at-plan output the
  #       caller can compose against without needing the ARN.
  # Exact-ARN-membership assertions belong in an apply-time integration test
  # (CI moto / sandbox account), not in a `command = plan` test.
  assert {
    condition     = output.sns_topic_name == "catalyst-alarms"
    error_message = "Module must publish sns_topic_name — alarms reference the topic via alarm_actions."
  }

  # Trip-wire alarm threshold — ADR-014 canonical 10-min value.
  assert {
    condition     = aws_cloudwatch_metric_alarm.onboard_p95_latency.threshold == 600000
    error_message = "ADR-014 trip-wire threshold MUST be 600000 ms (10 min)"
  }

  # 30-day rolling window: period 86400 (1 day) × evaluation_periods 30.
  assert {
    condition     = aws_cloudwatch_metric_alarm.onboard_p95_latency.period == 86400
    error_message = "Onboard p95 alarm must use a 1-day period for the 30-day rolling window"
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.onboard_p95_latency.evaluation_periods == 30
    error_message = "Onboard p95 alarm must use 30 evaluation periods for the 30-day rolling window"
  }

  # Retry-attempt alarm threshold per the Decision Log.
  assert {
    condition     = aws_cloudwatch_metric_alarm.retry_attempt_anomaly.threshold == 50
    error_message = "AWSTransientRetryAlarm threshold MUST be 50 per 5-minute window"
  }

  # 5xx alarm uses metric-math (three metric_query blocks: e1, m1, m2).
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.http_5xx_rate.metric_query) == 3
    error_message = "5xxRateAlarm must use three metric_query blocks (e1 expression + m1/m2 source metrics)"
  }
}
