# ---------------------------------------------------------------------------
# wa-iac-analyzer — Phase 1 operator dashboard (#285).
#
# Single CloudWatch dashboard with four panels covering the analyzer's Phase
# 1 happy-path observability surface:
#
#   1. ALB request rate + 5xx rate (the analyzer's edge)
#   2. Bedrock model latency p50/p99 (the analyzer's heavy dependency)
#   3. DynamoDB consumed capacity (the analyzer's persistence layer)
#   4. ECS running vs desired task count (the analyzer's runtime)
#
# Metric queries reference dimensions that the Phase 1 implementer will
# populate (ALB arn suffix, ECS cluster/service name, DynamoDB table name,
# Bedrock model id). Until those values are non-empty the widget queries
# return no data — which is the intended view at Phase 1, since the
# composite as a whole is `count = 0` at root and this dashboard is dormant.
#
# Dashboard JSON is inlined via `jsonencode` (not `templatefile`) to keep
# the widget structure visible in `terraform plan` diffs without a side
# file. This mirrors the modules/observability dashboard pattern from #63.
# ---------------------------------------------------------------------------

data "aws_region" "current" {}

resource "aws_cloudwatch_dashboard" "analyzer" {
  dashboard_name = "${var.name_prefix}-operator"

  dashboard_body = jsonencode({
    widgets = [
      # ----- Top-left: ALB request rate + 5xx ---------------------------------
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "ALB requests + target-5xx (per minute)"
          region  = data.aws_region.current.region
          period  = 60
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", var.alb_arn_suffix, { stat = "Sum", label = "Requests" }],
            [".", "HTTPCode_Target_5XX_Count", ".", ".", { stat = "Sum", label = "5xx" }],
          ]
        }
      },

      # ----- Top-right: Bedrock model latency p50/p99 -------------------------
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Bedrock invocation latency p50 / p99 (ms) — ${var.bedrock_model_id}"
          region = data.aws_region.current.region
          period = 60
          view   = "timeSeries"
          metrics = [
            ["AWS/Bedrock", "InvocationLatency", "ModelId", var.bedrock_model_id, { stat = "p50", label = "p50" }],
            [".", ".", ".", ".", { stat = "p99", label = "p99" }],
          ]
        }
      },

      # ----- Middle-left: DynamoDB consumed capacity --------------------------
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "DynamoDB consumed capacity (analyzer table) — ${var.dynamodb_table_name}"
          region  = data.aws_region.current.region
          period  = 60
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", var.dynamodb_table_name, { stat = "Sum", label = "RCU" }],
            [".", "ConsumedWriteCapacityUnits", ".", ".", { stat = "Sum", label = "WCU" }],
          ]
        }
      },

      # ----- Middle-right: ECS running vs desired -----------------------------
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "ECS running vs desired tasks — ${var.ecs_service_name}"
          region  = data.aws_region.current.region
          period  = 60
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name, { stat = "Average", label = "Running" }],
            [".", "DesiredTaskCount", ".", ".", ".", ".", { stat = "Average", label = "Desired" }],
          ]
        }
      },

      # ----- Bottom: alarm summary text ---------------------------------------
      {
        type   = "text"
        x      = 0
        y      = 12
        width  = 24
        height = 4
        properties = {
          markdown = join("\n", [
            "## Analyzer alarm summary",
            "",
            "- **${var.name_prefix}-5xx-rate** — ALB target-5xx > 5 / minute, 3 evals",
            "- **${var.name_prefix}-bedrock-throttling** — Bedrock InvocationThrottles > 0 sustained 5 minutes",
            "- **${var.name_prefix}-task-restarts** — ECS missing-task-count > 1 sustained 10 minutes",
            "",
            "Alarms publish to the shared `catalyst-alerts` SNS topic from #63 when `sns_topic_arn` is wired by the root stack; until then `alarm_actions = []` and alarms are observable in the console but do not page. See README.md §Observability + ADR-014.",
          ])
        }
      },
    ]
  })
}
