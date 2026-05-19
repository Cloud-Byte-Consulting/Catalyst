# ---------------------------------------------------------------------------
# Input variables for the catalyst-app L4 composite (ADR-015).
#
# Slug shape mirrors the construct-address regex from
# services/catalyst-api/catalyst/constructs.py (CONSTRUCT_PATTERN —
# `^[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+$`). Each of
# tenant/environment/project/app is one of the five segments and MUST
# match the per-segment alphabet of that regex (lowercase, digits, hyphen).
# Validation is enforced here so the module errors at plan time instead
# of producing an unreachable AWS resource name later.
# ---------------------------------------------------------------------------

variable "tenant" {
  description = "Tenant slug (first segment of the construct address). Lowercase alphanumeric + hyphen."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.tenant)) && !can(regex("--", var.tenant))
    error_message = "tenant must match ^[a-z0-9-]+$ and must not contain '--' (collides with the catalyst-{tenant}--{role} group-naming convention)."
  }
}

variable "environment" {
  description = "Environment slug (second segment of the construct address; e.g. dev, qa, staging, prod)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.environment))
    error_message = "environment must match ^[a-z0-9-]+$ (lowercase, digits, hyphen)."
  }
}

variable "project" {
  description = "Project slug (fourth segment of the construct address; groups a portfolio of apps)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project))
    error_message = "project must match ^[a-z0-9-]+$ (lowercase, digits, hyphen)."
  }
}

variable "app" {
  description = "Application slug (fifth segment of the construct address; the deploy unit)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.app))
    error_message = "app must match ^[a-z0-9-]+$ (lowercase, digits, hyphen)."
  }
}

variable "state_bucket" {
  description = "S3 bucket holding the Terraform remote backend (the upstream tenant baseline state, per ADR-015)."
  type        = string

  validation {
    condition     = length(var.state_bucket) > 0
    error_message = "state_bucket must be a non-empty S3 bucket name."
  }
}

variable "aws_region" {
  description = "AWS region for both the local resources provisioned here and the upstream remote-state lookup."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a standard AWS region slug (e.g. us-west-2)."
  }
}

variable "service_type" {
  description = "Runtime shape for the app per ADR-009. 'web-service' routes through the shared ALB; 'worker' and 'batch' do not."
  type        = string
  default     = "web-service"

  validation {
    condition     = contains(["web-service", "worker", "batch"], var.service_type)
    error_message = "service_type must be one of: web-service, worker, batch."
  }
}

variable "catalog_table_name" {
  description = "Name of the cross-tenant catalog DynamoDB table (provisioned at L1) where the per-app row lands. Defaults to the platform-state table name used by the API."
  type        = string
  default     = "catalyst-platform-state"
}

variable "alb_listener_arn" {
  description = "ARN of the shared ALB HTTPS listener that web-service apps attach a path-based rule to. Required when service_type='web-service'; ignored otherwise."
  type        = string
  default     = ""
}

variable "alb_target_group_arn" {
  description = "ARN of the target group the ALB listener rule forwards to (the L1-provisioned shared target group, or a per-app one). Required when service_type='web-service'."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days. ADR-015 §Compliance defaults to 30 days for L4 app logs."
  type        = number
  default     = 30
}

# ---------------------------------------------------------------------------
# KMS — per-app customer-managed key inputs (ADR-016 / issue #228).
# ---------------------------------------------------------------------------

variable "kms_admin_role_arn" {
  description = "ARN of the SSO admin (or platform-engineer break-glass) role granted full kms:* on the per-app CMKs provisioned by the embedded kms module. Sourced from the L1 platform baseline. ADR-016."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", var.kms_admin_role_arn))
    error_message = "kms_admin_role_arn must be a full IAM role ARN."
  }
}

# ---------------------------------------------------------------------------
# SVC-8 (#62) — ADR-009 ECS alternate-runtime wiring.
#
# All variables in this block are OPT-IN and only consulted when
# enable_ecs_runtime = true. Lambda-only consumers can ignore them.
# ---------------------------------------------------------------------------

variable "enable_ecs_runtime" {
  description = "Opt-in toggle for the ADR-009 ECS Fargate runtime. When true, the composite instantiates modules/ecs-alb with enable_task_definition = true and provisions the catalyst-api task definition + execution role + task role. Default false keeps Lambda (the ADR-009 default) as the only runtime."
  type        = bool
  default     = false
}

variable "ecs_vpc_id" {
  description = "VPC ID for the ECS ALB + cluster. Required when enable_ecs_runtime = true."
  type        = string
  default     = ""
}

variable "ecs_public_subnet_ids" {
  description = "Public subnet IDs for the ALB fronting the ECS service. Required when enable_ecs_runtime = true."
  type        = list(string)
  default     = []
}

variable "ecs_alb_security_group_id" {
  description = "Security group attached to the ALB fronting the ECS service. Required when enable_ecs_runtime = true."
  type        = string
  default     = ""
}

variable "ecs_container_image_uri" {
  description = "Fully-qualified ECR image URI (sha-tagged) for the catalyst-api container running on Fargate. Required when enable_ecs_runtime = true."
  type        = string
  default     = ""
}

variable "ecs_log_level" {
  description = "Value for the container CATALYST_LOG_LEVEL env var when ECS runtime is enabled."
  type        = string
  default     = "INFO"
}

variable "ecs_container_extra_env" {
  description = "Additional env vars merged into the catalyst-api container definition on top of the SVC-8 defaults."
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

# ---------------------------------------------------------------------------
# Aurora Serverless v2 — opt-in inputs (ADR-019 / issue #229).
#
# All inputs default to "off / empty" so the composite remains
# backward-compatible: an existing caller that doesn't set
# `enable_aurora_serverless = true` provisions zero RDS resources.
# Pattern mirrors the `enable_ecs_runtime` gating established by #62.
# ---------------------------------------------------------------------------

variable "enable_aurora_serverless" {
  description = "When true, provision a per-app Aurora Serverless v2 (PostgreSQL) cluster and attach the IAM `rds-db:connect` policy to the runtime exec role. Default false keeps DynamoDB-only callers unaffected."
  type        = bool
  default     = false
}

variable "aurora_vpc_id" {
  description = "VPC ID that hosts the Aurora cluster (passed to `modules/aurora-serverless`). Required when `enable_aurora_serverless = true`; ignored otherwise."
  type        = string
  default     = ""
}

variable "aurora_private_subnet_ids" {
  description = "Private subnet IDs (>=2 AZs) used by the Aurora DB subnet group. Required when `enable_aurora_serverless = true`."
  type        = list(string)
  default     = []
}

variable "aurora_consumer_security_group_ids" {
  description = "Security group IDs (ECS task SG, Lambda VPC SG) allowed to reach the cluster on 5432. Required when `enable_aurora_serverless = true`."
  type        = list(string)
  default     = []
}

variable "aurora_engine_version" {
  description = "Aurora PostgreSQL engine version (16.x family); forwarded to `modules/aurora-serverless`."
  type        = string
  default     = "16.4"
}

variable "aurora_min_capacity" {
  description = "Minimum Aurora Serverless v2 ACU; forwarded to `modules/aurora-serverless`."
  type        = number
  default     = 0.5
}

variable "aurora_max_capacity" {
  description = "Maximum Aurora Serverless v2 ACU; forwarded to `modules/aurora-serverless`."
  type        = number
  default     = 2
}

# ---------------------------------------------------------------------------
# #230 — ECS autoscaling inputs (independently gated of enable_ecs_runtime
# because the ECS service is provisioned by the CD pipeline that consumes
# the #62 task definition — at composite-apply time the service may not yet
# exist; see the module wiring in main.tf for the rationale).
# ---------------------------------------------------------------------------

variable "enable_ecs_autoscaling" {
  description = "Opt-in: when true, registers an App Autoscaling target on the running ECS service via modules/ecs-autoscaling. Requires the four cluster/service/ALB/TG identifier vars below to be set."
  type        = bool
  default     = false
}

variable "ecs_autoscaling_cluster_name" {
  description = "ECS cluster name the service runs in. Required when enable_ecs_autoscaling = true."
  type        = string
  default     = ""
}

variable "ecs_autoscaling_service_name" {
  description = "ECS service name to scale. Required when enable_ecs_autoscaling = true."
  type        = string
  default     = ""
}

variable "ecs_autoscaling_alb_arn_suffix" {
  description = "ARN suffix of the ALB fronting the service (the `app/<alb-name>/<hex>` portion of the ALB ARN). Required when enable_ecs_autoscaling = true (the ALBRequestCountPerTarget metric cannot be addressed without it)."
  type        = string
  default     = ""
}

variable "ecs_autoscaling_target_group_arn_suffix" {
  description = "ARN suffix of the ALB target group the service is registered with (the `targetgroup/<tg-name>/<hex>` portion). Required when enable_ecs_autoscaling = true."
  type        = string
  default     = ""
}

variable "ecs_autoscaling_sns_topic_arn" {
  description = "ARN of the shared `catalyst-alerts` SNS topic from #63. When non-empty, the autoscaling module emits supplemental CloudWatch alarms (CPU sustained-high, RPT sustained-high, at-max-capacity) wired to this topic. When empty, only the AWS-managed target-tracking alarms exist (and they are NOT routed to SNS — operator visibility is limited)."
  type        = string
  default     = ""
}

variable "ecs_autoscaling_min_capacity" {
  description = "Minimum ECS task count the autoscaling target will hold the service at. Default 1 (cost-optimized for demo per ADR-018); production with HA requirements should set to >= 2."
  type        = number
  default     = 1
}

variable "ecs_autoscaling_max_capacity" {
  description = "Maximum ECS task count the autoscaling target will scale up to. Default 6 per ADR-018."
  type        = number
  default     = 6
}

variable "ecs_autoscaling_cpu_target_value" {
  description = "Target average CPU utilization (%) for the ECSServiceAverageCPUUtilization target-tracking policy."
  type        = number
  default     = 60
}

variable "ecs_autoscaling_rpt_target_value" {
  description = "Target requests-per-task for the ALBRequestCountPerTarget target-tracking policy."
  type        = number
  default     = 50
}

variable "ecs_autoscaling_enable_supplemental_alarms" {
  description = "When true (default), emit supplemental CloudWatch alarms (CPU high, RPT high, at-max-capacity) wired to ecs_autoscaling_sns_topic_arn. Set to false to skip alarm emission entirely."
  type        = bool
  default     = true
}
