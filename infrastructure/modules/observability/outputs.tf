output "sns_topic_arn" {
  value       = aws_sns_topic.alarms.arn
  description = "ARN of the catalyst-alarms SNS topic. Operators subscribe email/PagerDuty/Slack endpoints out-of-band via `aws sns subscribe` (see docs/onboarding/platform.md §Operator alerts)."
}

output "sns_topic_name" {
  value       = aws_sns_topic.alarms.name
  description = "Name of the catalyst-alarms SNS topic; surfaced for documentation and CLI convenience."
}

output "dashboard_name" {
  value       = aws_cloudwatch_dashboard.catalyst.dashboard_name
  description = "Name of the catalyst-operator CloudWatch dashboard."
}

output "dashboard_url" {
  value       = "https://${data.aws_region.current.region}.console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.region}#dashboards:name=${aws_cloudwatch_dashboard.catalyst.dashboard_name}"
  description = "Direct console link to the operator dashboard. Linked from docs/onboarding/platform.md and the module README."
}

output "alarm_names" {
  value = [
    aws_cloudwatch_metric_alarm.http_5xx_rate.alarm_name,
    aws_cloudwatch_metric_alarm.onboard_p95_latency.alarm_name,
    aws_cloudwatch_metric_alarm.request_p99_latency.alarm_name,
    aws_cloudwatch_metric_alarm.retry_attempt_anomaly.alarm_name,
    aws_cloudwatch_metric_alarm.lambda_errors.alarm_name,
  ]
  description = "Names of the five CloudWatch alarms provisioned by this module."
}
