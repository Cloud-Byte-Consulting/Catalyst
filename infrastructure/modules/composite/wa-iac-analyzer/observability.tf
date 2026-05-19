# ---------------------------------------------------------------------------
# wa-iac-analyzer — Phase 1 observability CONTRACT (#285, stacked on #283).
#
# This file declares the analyzer's CloudWatch log group + three CloudWatch
# metric alarms ahead of the Phase 1 implementation. The resources are
# real (not count-gated locally) because the ENTIRE composite is gated at
# the root via `count = var.enable_wa_aws_iac_analyzer ? 1 : 0`
# (infrastructure/main.tf §"ADR-023 Phase 1"). When the flag is false the
# module is never instantiated and these resources do not appear in
# `terraform plan` — that is the zero-impact contract from #283 §Scenario 1
# which #285 inherits.
#
# When `var.sns_topic_arn` is empty (the default), each alarm declares
# `alarm_actions = []` so the alarm is provisioned but never pages. The
# root stack will wire the shared `catalyst-alerts` SNS topic from #63
# (modules/observability) into this composite once the Phase 1 implementer
# lands the ECS service + ALB. This mirrors the #235 ECS-autoscaling
# topic-ARN-via-variable pattern.
#
# Alarm rationale (recorded in the Decision Log on #285):
#   1. analyzer-5xx-rate           — ALB target 5xx > 5 / minute, 3 evals.
#                                    Catches sustained backend errors from
#                                    the ECS Fargate tasks once Phase 1
#                                    provisions the ALB.
#   2. analyzer-bedrock-throttling — Bedrock InvocationThrottles > 0 for
#                                    5 minutes. The analyzer is a heavy
#                                    Bedrock consumer; throttling means
#                                    requests are silently failing.
#   3. analyzer-task-restarts      — ECS service running-task-count drops
#                                    > 1 in 10 minutes. Surfaces crash
#                                    loops the platform team would
#                                    otherwise discover via user reports.
# ---------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# CloudWatch Log Group — analyzer ECS task logs
# -----------------------------------------------------------------------------
# The Phase 1 implementer will attach this log group to the ECS task
# definition's `logConfiguration.options.awslogs-group`. Retention defaults to
# 30 days per ADR-015 §"Log retention". When `var.log_group_kms_key_arn` is
# set, the group is CMK-encrypted via the ADR-016 artifact-key pattern; when
# empty (default) the group uses the AWS-owned CloudWatch Logs key so the
# scaffold remains zero-impact even before the artifact-key CMK lands.
resource "aws_cloudwatch_log_group" "analyzer" {
  name              = "/aws/ecs/${var.name_prefix}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.log_group_kms_key_arn != "" ? var.log_group_kms_key_arn : null

  tags = local.component_tags
}

# -----------------------------------------------------------------------------
# Alarm 1 — analyzer-5xx-rate
# -----------------------------------------------------------------------------
# ALB target-5xx > 5 in any 1-minute window, 3 evaluation periods.
# `LoadBalancer` dimension is filled by `var.alb_arn_suffix` once the Phase 1
# implementer provisions the ALB; until then the alarm's dimension references
# the empty string and the alarm sits dormant (the composite as a whole is
# count = 0 at root, so this is dormant-of-dormant).
resource "aws_cloudwatch_metric_alarm" "analyzer_5xx_rate" {
  alarm_name        = "${var.name_prefix}-5xx-rate"
  alarm_description = "Analyzer ALB target 5xx > 5 requests / minute for 3 evaluation periods. Catches sustained backend errors from the ECS Fargate tasks. See modules/composite/wa-iac-analyzer/README.md §Observability."

  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 3
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_actions = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []
  ok_actions    = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  tags = local.component_tags
}

# -----------------------------------------------------------------------------
# Alarm 2 — analyzer-bedrock-throttling
# -----------------------------------------------------------------------------
# AWS/Bedrock:InvocationThrottles > 0 sustained for 5 minutes. The analyzer
# is a heavy Bedrock consumer (Claude 3.5 Sonnet v2 by default — see
# var.bedrock_model_id) so throttles mean review requests are silently
# failing. Dimension `ModelId` is the Bedrock model the analyzer invokes.
resource "aws_cloudwatch_metric_alarm" "analyzer_bedrock_throttling" {
  alarm_name        = "${var.name_prefix}-bedrock-throttling"
  alarm_description = "Bedrock InvocationThrottles > 0 sustained for 5 minutes for ModelId=${var.bedrock_model_id}. Analyzer is a heavy Bedrock consumer; throttling means review requests are silently failing."

  namespace           = "AWS/Bedrock"
  metric_name         = "InvocationThrottles"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 5
  datapoints_to_alarm = 5
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ModelId = var.bedrock_model_id
  }

  alarm_actions = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []
  ok_actions    = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  tags = local.component_tags
}

# -----------------------------------------------------------------------------
# Alarm 3 — analyzer-task-restarts
# -----------------------------------------------------------------------------
# ECS RunningTaskCount drops below DesiredTaskCount more than once in any
# 10-minute window. Surfaces ECS crash loops that would otherwise be
# discovered via user reports. The metric expression `m_desired - m_running`
# yields the count of missing tasks; > 1 sustained for 2 of 2 5-min periods
# constitutes a restart event worth paging on.
#
# ClusterName + ServiceName dimensions are wired via variables so the Phase
# 1 implementer can plug the ECS service identity in once the resources
# exist; at scaffold stage both default to empty string and the alarm sits
# dormant under the root count = 0 gate.
resource "aws_cloudwatch_metric_alarm" "analyzer_task_restarts" {
  alarm_name        = "${var.name_prefix}-task-restarts"
  alarm_description = "ECS analyzer service has > 1 missing task (DesiredTaskCount - RunningTaskCount) sustained over 10 minutes. Surfaces task crash loops that would otherwise be discovered via user reports."

  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "missing"
    expression  = "m_desired - m_running"
    label       = "Missing tasks"
    return_data = true
  }

  metric_query {
    id = "m_desired"
    metric {
      namespace   = "ECS/ContainerInsights"
      metric_name = "DesiredTaskCount"
      period      = 300
      stat        = "Average"
      dimensions = {
        ClusterName = var.ecs_cluster_name
        ServiceName = var.ecs_service_name
      }
    }
  }

  metric_query {
    id = "m_running"
    metric {
      namespace   = "ECS/ContainerInsights"
      metric_name = "RunningTaskCount"
      period      = 300
      stat        = "Average"
      dimensions = {
        ClusterName = var.ecs_cluster_name
        ServiceName = var.ecs_service_name
      }
    }
  }

  alarm_actions = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []
  ok_actions    = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  tags = local.component_tags
}
