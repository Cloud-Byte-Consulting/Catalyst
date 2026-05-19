output "target_resource_id" {
  description = "The App Autoscaling resource_id (`service/<cluster>/<service>`) the target was registered against. Useful for the operator verification commands documented in docs/onboarding/platform.md §Autoscaling."
  value       = aws_appautoscaling_target.ecs_service.resource_id
}

output "cpu_policy_arn" {
  description = "ARN of the CPU target-tracking scaling policy. Downstream consumers (alarm wiring, runbook references) can address the AWS-managed CloudWatch alarms via this ARN's name suffix."
  value       = aws_appautoscaling_policy.cpu_target_tracking.arn
}

output "request_count_policy_arn" {
  description = "ARN of the ALBRequestCountPerTarget scaling policy."
  value       = aws_appautoscaling_policy.request_count_per_target.arn
}

output "alarm_arns" {
  description = "ARNs of the supplemental CloudWatch metric alarms emitted by this module (empty when enable_supplemental_alarms = false or sns_topic_arn is empty)."
  value = concat(
    aws_cloudwatch_metric_alarm.cpu_high[*].arn,
    aws_cloudwatch_metric_alarm.rpt_high[*].arn,
    aws_cloudwatch_metric_alarm.at_max_capacity[*].arn,
  )
}
