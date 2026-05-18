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
