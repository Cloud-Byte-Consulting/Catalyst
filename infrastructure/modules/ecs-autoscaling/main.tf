# ---------------------------------------------------------------------------
# #230 — ECS application autoscaling (ADR-018).
#
# Owns three concerns and nothing else:
#   1. The aws_appautoscaling_target binding for the ECS service.
#   2. Two target-tracking policies (CPU + ALBRequestCountPerTarget).
#   3. Optional CloudWatch metric alarms routed to the #63 SNS topic.
#
# The ECS service itself is OUT OF SCOPE — it is provisioned by the runtime
# promotion that follows the SVC-8 task-definition rollout (#62). This module
# accepts cluster_name + service_name as inputs so it can be planned, tested,
# and (eventually) applied independently of the service-creation surface.
#
# Why target tracking (not step scaling): see ADR-018 §Decision. tl;dr — the
# operator declares the desired steady state ("CPU should average 60%") and
# AWS picks the thresholds. Step scaling would require ops to tune four
# threshold values per metric, which is brittle for a demo workload.
# ---------------------------------------------------------------------------

locals {
  # App Autoscaling addresses ECS services via the textual resource_id
  # `service/<cluster>/<service>`, NOT via the ECS service ARN. This is the
  # one place where the awkward string shape leaks into Terraform.
  resource_id = "service/${var.cluster_name}/${var.service_name}"

  # ALBRequestCountPerTarget requires the resource_label to identify both
  # the ALB and the target group via their ARN suffixes. Format is:
  #   app/<alb-name>/<hex>/targetgroup/<tg-name>/<hex>
  rpt_resource_label = "${var.alb_arn_suffix}/${var.target_group_arn_suffix}"

  emit_supplemental_alarms = var.enable_supplemental_alarms && var.sns_topic_arn != ""
}

# ---------------------------------------------------------------------------
# Autoscaling target — registers the ECS service with App Autoscaling.
# ---------------------------------------------------------------------------

resource "aws_appautoscaling_target" "ecs_service" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = local.resource_id
  min_capacity       = var.min_capacity
  max_capacity       = var.max_capacity
}

# ---------------------------------------------------------------------------
# Policy 1 — CPU target tracking (ECSServiceAverageCPUUtilization).
#
# Catches runaway compute. AWS creates the underlying CloudWatch alarms
# automatically when a target-tracking policy is registered (one alarm for
# scale-out, one for scale-in). Those alarms are NOT routed to the SNS topic
# from #63 — see the supplemental alarms below for that.
# ---------------------------------------------------------------------------

resource "aws_appautoscaling_policy" "cpu_target_tracking" {
  name               = "${var.name_prefix}-cpu-target-tracking"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_service.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_service.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_service.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = var.cpu_target_value

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    # AWS defaults — 3 minute scale-in, 60 second scale-out — are appropriate
    # for the demo workload. Documented in ADR-018 §Consequences so the
    # default is not implicit.
  }
}

# ---------------------------------------------------------------------------
# Policy 2 — ALB RequestCountPerTarget target tracking.
#
# Catches request-bound load that does not pin CPU (e.g. handlers that block
# on a downstream AWS API call). The resource_label is mandatory for this
# predefined metric and must reference both the ALB and the target group.
# ---------------------------------------------------------------------------

resource "aws_appautoscaling_policy" "request_count_per_target" {
  name               = "${var.name_prefix}-rpt-target-tracking"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_service.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_service.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_service.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = var.rpt_target_value

    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = local.rpt_resource_label
    }
  }
}

# ---------------------------------------------------------------------------
# Supplemental CloudWatch alarms (optional) — wire scaling visibility to the
# #63 SNS topic so operators get the same alarm fan-out as the rest of the
# observability surface. AWS's auto-created target-tracking alarms do NOT
# route to SNS by default.
#
# Three alarms (NOT one per scale-out + one per scale-in — those duplicate
# the AWS-managed alarms uselessly):
#   1. CPU sustained > 80 for 5 minutes — runaway compute beyond what the
#      scale-out policy is keeping up with.
#   2. RPT sustained > 100 for 5 minutes — request flood beyond capacity.
#   3. Desired task count == max_capacity for 15 minutes — capped at the
#      ceiling, indicates max_capacity needs raising.
# ---------------------------------------------------------------------------

# tfsec:ignore:aws-cloudwatch-log-group-customer-key — alarm metadata is not
# sensitive operational data; the AWS-owned SNS encryption is sufficient.
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  count = local.emit_supplemental_alarms ? 1 : 0

  alarm_name          = "${var.name_prefix}-cpu-high"
  alarm_description   = "ECS service CPU sustained above 80% for 5 minutes — scale-out may be lagging. Tied to #230 autoscaling alarms."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 5
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.cluster_name
    ServiceName = var.service_name
  }

  alarm_actions = [var.sns_topic_arn]
  ok_actions    = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "rpt_high" {
  count = local.emit_supplemental_alarms ? 1 : 0

  alarm_name          = "${var.name_prefix}-rpt-high"
  alarm_description   = "ALB RequestCountPerTarget sustained above 100 for 5 minutes — request load beyond target-tracking capacity. Tied to #230 autoscaling alarms."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "RequestCountPerTarget"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 5
  threshold           = 100
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.target_group_arn_suffix
  }

  alarm_actions = [var.sns_topic_arn]
  ok_actions    = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "at_max_capacity" {
  count = local.emit_supplemental_alarms ? 1 : 0

  alarm_name          = "${var.name_prefix}-at-max-capacity"
  alarm_description   = "ECS service DesiredCount has been at max_capacity for 15 minutes — raise max_capacity or investigate sustained load. Tied to #230 autoscaling alarms."
  namespace           = "AWS/ECS"
  metric_name         = "DesiredTaskCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 15
  threshold           = var.max_capacity
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.cluster_name
    ServiceName = var.service_name
  }

  alarm_actions = [var.sns_topic_arn]
  ok_actions    = [var.sns_topic_arn]
}
