# ---------------------------------------------------------------------------
# #230 — ECS app autoscaling plan tests (ADR-018).
#
# command = plan only (no AWS calls). Asserts:
#   - App Autoscaling target registers with the right scalable_dimension /
#     service_namespace / resource_id shape
#   - Both target-tracking policies (CPU + RPT) exist with the right
#     predefined_metric_type and target_value
#   - The RPT policy carries the resource_label built from ALB + target
#     group ARN suffixes (mandatory for that predefined metric)
#   - Supplemental CloudWatch alarms (CPU high, RPT high, at-max-capacity)
#     all reference the SNS topic ARN passed in
#   - When sns_topic_arn is empty, supplemental alarms are NOT emitted
#     (target-tracking AWS-managed alarms still exist, but those are
#     outside this module's surface)
# ---------------------------------------------------------------------------

provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "autoscaling_target_and_policies_render" {
  command = plan

  module {
    source = "./modules/ecs-autoscaling"
  }

  variables {
    name_prefix             = "catalyst-api"
    cluster_name            = "catalyst-cluster"
    service_name            = "catalyst-api-svc"
    alb_arn_suffix          = "app/catalyst-alb/abc123"
    target_group_arn_suffix = "targetgroup/catalyst-tg/def456"
    sns_topic_arn           = "arn:aws:sns:us-west-2:123456789012:catalyst-alerts"
  }

  # ---------- App Autoscaling target ----------

  assert {
    condition     = aws_appautoscaling_target.ecs_service.service_namespace == "ecs"
    error_message = "App Autoscaling target service_namespace must be 'ecs'."
  }

  assert {
    condition     = aws_appautoscaling_target.ecs_service.scalable_dimension == "ecs:service:DesiredCount"
    error_message = "App Autoscaling target scalable_dimension must be 'ecs:service:DesiredCount' (the only dimension that scales an ECS service's task count)."
  }

  assert {
    condition     = aws_appautoscaling_target.ecs_service.resource_id == "service/catalyst-cluster/catalyst-api-svc"
    error_message = "App Autoscaling target resource_id must be the textual 'service/<cluster>/<service>' shape, NOT the service ARN."
  }

  assert {
    condition     = aws_appautoscaling_target.ecs_service.min_capacity == 1
    error_message = "Default min_capacity must be 1 per ADR-018 (cost-optimized for demo)."
  }

  assert {
    condition     = aws_appautoscaling_target.ecs_service.max_capacity == 6
    error_message = "Default max_capacity must be 6 per ADR-018."
  }

  # ---------- CPU target-tracking policy ----------

  assert {
    condition     = aws_appautoscaling_policy.cpu_target_tracking.policy_type == "TargetTrackingScaling"
    error_message = "CPU policy must use TargetTrackingScaling (not StepScaling) per ADR-018 §Decision."
  }

  assert {
    condition     = aws_appautoscaling_policy.cpu_target_tracking.target_tracking_scaling_policy_configuration[0].target_value == 60
    error_message = "CPU target_value must default to 60% per ADR-018."
  }

  assert {
    condition     = aws_appautoscaling_policy.cpu_target_tracking.target_tracking_scaling_policy_configuration[0].predefined_metric_specification[0].predefined_metric_type == "ECSServiceAverageCPUUtilization"
    error_message = "CPU policy must use the ECSServiceAverageCPUUtilization predefined metric."
  }

  # ---------- RPT (ALBRequestCountPerTarget) policy ----------

  assert {
    condition     = aws_appautoscaling_policy.request_count_per_target.policy_type == "TargetTrackingScaling"
    error_message = "RPT policy must use TargetTrackingScaling."
  }

  assert {
    condition     = aws_appautoscaling_policy.request_count_per_target.target_tracking_scaling_policy_configuration[0].target_value == 50
    error_message = "RPT target_value must default to 50 RPM/task per ADR-018."
  }

  assert {
    condition     = aws_appautoscaling_policy.request_count_per_target.target_tracking_scaling_policy_configuration[0].predefined_metric_specification[0].predefined_metric_type == "ALBRequestCountPerTarget"
    error_message = "RPT policy must use the ALBRequestCountPerTarget predefined metric."
  }

  assert {
    condition     = aws_appautoscaling_policy.request_count_per_target.target_tracking_scaling_policy_configuration[0].predefined_metric_specification[0].resource_label == "app/catalyst-alb/abc123/targetgroup/catalyst-tg/def456"
    error_message = "RPT policy resource_label must concatenate alb_arn_suffix + '/' + target_group_arn_suffix (the format the predefined metric requires)."
  }

  # ---------- Supplemental alarms (CPU high, RPT high, at-max-capacity) ----------

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.cpu_high) == 1
    error_message = "CPU-high supplemental alarm must be emitted when sns_topic_arn is non-empty + enable_supplemental_alarms is default true."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.cpu_high[0].alarm_actions[0] == "arn:aws:sns:us-west-2:123456789012:catalyst-alerts"
    error_message = "CPU-high alarm action must publish to the SNS topic ARN passed in."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.rpt_high) == 1
    error_message = "RPT-high supplemental alarm must be emitted when sns_topic_arn is non-empty."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.at_max_capacity) == 1
    error_message = "At-max-capacity supplemental alarm must be emitted when sns_topic_arn is non-empty."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.at_max_capacity[0].threshold == 6
    error_message = "At-max-capacity alarm threshold must mirror max_capacity (default 6) so the alarm fires when the service is pinned at the ceiling."
  }
}

run "supplemental_alarms_skipped_when_no_sns_topic" {
  command = plan

  module {
    source = "./modules/ecs-autoscaling"
  }

  variables {
    name_prefix             = "catalyst-api"
    cluster_name            = "catalyst-cluster"
    service_name            = "catalyst-api-svc"
    alb_arn_suffix          = "app/catalyst-alb/abc123"
    target_group_arn_suffix = "targetgroup/catalyst-tg/def456"
    sns_topic_arn           = ""
  }

  # Empty SNS ARN → supplemental alarms skipped entirely (operator visibility
  # is limited to AWS-managed target-tracking alarms, which is the documented
  # ADR-018 trade-off when the shared SNS topic is unavailable).

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.cpu_high) == 0
    error_message = "CPU-high alarm must be skipped when sns_topic_arn is empty."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.rpt_high) == 0
    error_message = "RPT-high alarm must be skipped when sns_topic_arn is empty."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.at_max_capacity) == 0
    error_message = "At-max-capacity alarm must be skipped when sns_topic_arn is empty."
  }

  # The autoscaling target + policies should still be planned — the
  # autoscaling itself is independent of the SNS wiring.
  assert {
    condition     = aws_appautoscaling_target.ecs_service.resource_id == "service/catalyst-cluster/catalyst-api-svc"
    error_message = "Autoscaling target must still register even when SNS wiring is absent."
  }

  assert {
    condition     = aws_appautoscaling_policy.cpu_target_tracking.target_tracking_scaling_policy_configuration[0].target_value == 60
    error_message = "CPU policy must still plan when SNS wiring is absent."
  }
}

run "supplemental_alarms_can_be_explicitly_disabled" {
  command = plan

  module {
    source = "./modules/ecs-autoscaling"
  }

  variables {
    name_prefix                = "catalyst-api"
    cluster_name               = "catalyst-cluster"
    service_name               = "catalyst-api-svc"
    alb_arn_suffix             = "app/catalyst-alb/abc123"
    target_group_arn_suffix    = "targetgroup/catalyst-tg/def456"
    sns_topic_arn              = "arn:aws:sns:us-west-2:123456789012:catalyst-alerts"
    enable_supplemental_alarms = false
  }

  # When the operator explicitly opts out of supplemental alarms (even with a
  # valid SNS ARN), none should be planned.

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.cpu_high) == 0
    error_message = "CPU-high alarm must be skipped when enable_supplemental_alarms = false."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.rpt_high) == 0
    error_message = "RPT-high alarm must be skipped when enable_supplemental_alarms = false."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.at_max_capacity) == 0
    error_message = "At-max-capacity alarm must be skipped when enable_supplemental_alarms = false."
  }
}
