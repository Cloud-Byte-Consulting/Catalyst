# ---------------------------------------------------------------------------
# Input variables for the ecs-autoscaling sub-module (#230, ADR-018).
#
# The module is intentionally narrow: it only owns the application-autoscaling
# target + policies that scale the ECS service from modules/ecs-alb. Cluster
# + service identity flow in as bare strings (not ARNs) because the App
# Autoscaling API addresses targets via the `service/<cluster>/<service>`
# string shape, not by ARN.
# ---------------------------------------------------------------------------

variable "name_prefix" {
  description = "Resource-name prefix for the (optional) CloudWatch metric alarms this module emits. Should match the caller's ECS service name so alarm names are immediately attributable in the console."
  type        = string
  default     = "catalyst-api"

  validation {
    condition     = length(var.name_prefix) > 0
    error_message = "name_prefix must be a non-empty string."
  }
}

variable "cluster_name" {
  description = "Name (NOT ARN) of the ECS cluster the target service runs in. Used to construct the App Autoscaling `service/<cluster>/<service>` resource_id."
  type        = string

  validation {
    condition     = length(var.cluster_name) > 0
    error_message = "cluster_name must be a non-empty string."
  }
}

variable "service_name" {
  description = "Name (NOT ARN) of the ECS service to scale. Used to construct the App Autoscaling `service/<cluster>/<service>` resource_id. The service itself is provisioned outside this module (by the runtime promotion that follows the SVC-8 task-definition rollout)."
  type        = string

  validation {
    condition     = length(var.service_name) > 0
    error_message = "service_name must be a non-empty string."
  }
}

variable "alb_arn_suffix" {
  description = "ARN suffix of the ALB fronting the service (the trailing `app/<alb-name>/<hex>` portion of the ALB ARN). Combined with `target_group_arn_suffix` to form the `resource_label` the ALBRequestCountPerTarget metric requires."
  type        = string

  validation {
    condition     = length(var.alb_arn_suffix) > 0
    error_message = "alb_arn_suffix must be a non-empty string (the App Autoscaling RPT metric requires it to address the load balancer)."
  }
}

variable "target_group_arn_suffix" {
  description = "ARN suffix of the ALB target group the service is registered with (the trailing `targetgroup/<tg-name>/<hex>` portion). Combined with `alb_arn_suffix` for the RPT metric's resource_label."
  type        = string

  validation {
    condition     = length(var.target_group_arn_suffix) > 0
    error_message = "target_group_arn_suffix must be a non-empty string."
  }
}

variable "min_capacity" {
  description = "Minimum ECS desired task count the autoscaling target will hold the service at. Defaults to 1 (cost-optimized for the demo target per ADR-018). Production deployments that require HA should set this to >= 2 to survive a single-task replacement or AZ outage."
  type        = number
  default     = 1

  validation {
    condition     = var.min_capacity >= 1
    error_message = "min_capacity must be >= 1 (App Autoscaling cannot drive a service to zero via target tracking — use scheduled actions for that)."
  }
}

variable "max_capacity" {
  description = "Maximum ECS desired task count the autoscaling target will scale up to. Defaults to 6 — sufficient for the demo workload's expected fan-out per Brief Option 1 §autoscaling."
  type        = number
  default     = 6

  validation {
    condition     = var.max_capacity >= 1
    error_message = "max_capacity must be >= 1."
  }
}

variable "cpu_target_value" {
  description = "Target average CPU utilization (%) for the ECSServiceAverageCPUUtilization target-tracking policy. Default 60 leaves headroom for spikes between scaling iterations (the policy's built-in 3 minute scale-in / 60 second scale-out cool-down windows mean an instantaneous spike above 60 will not pin the service immediately)."
  type        = number
  default     = 60

  validation {
    condition     = var.cpu_target_value > 0 && var.cpu_target_value <= 100
    error_message = "cpu_target_value must be in (0, 100]."
  }
}

variable "rpt_target_value" {
  description = "Target requests-per-task (per-minute average) for the ALBRequestCountPerTarget target-tracking policy. Default 50 RPM/task — calibrated for the demo FastAPI workload. Validates app-layer scaling (works for workloads that block on AWS APIs without saturating CPU)."
  type        = number
  default     = 50

  validation {
    condition     = var.rpt_target_value > 0
    error_message = "rpt_target_value must be > 0."
  }
}

variable "sns_topic_arn" {
  description = "ARN of the SNS topic the optional CloudWatch metric alarms publish to (the shared `catalyst-alerts` topic from #63). When empty, the supplemental alarms are skipped (the target-tracking policies still emit their own AWS-managed CloudWatch alarms automatically; those are NOT routed to SNS without the supplemental wiring below)."
  type        = string
  default     = ""
}

variable "enable_supplemental_alarms" {
  description = "Opt-in: when true (default) and sns_topic_arn is non-empty, this module emits three supplemental CloudWatch metric alarms (overall CPU high, RPT high, low task count) that publish to the SNS topic. The target-tracking policies' AWS-managed alarms are NOT routed to SNS, so this gives operators a visible alarm surface on the shared topic. Set to false to skip the supplemental alarms entirely."
  type        = bool
  default     = true
}
