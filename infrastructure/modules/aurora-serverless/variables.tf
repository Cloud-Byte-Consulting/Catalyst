# ---------------------------------------------------------------------------
# Inputs for the Aurora Serverless v2 PostgreSQL module (ADR-019 / #229).
#
# The module is opt-in from the catalyst-app composite (`enable_aurora_serverless`)
# so callers that haven't migrated to the IAM-auth Postgres path keep the
# DynamoDB-only persistence shape from ADR-007.
# ---------------------------------------------------------------------------

variable "name" {
  description = "Cluster identifier base; AWS DB resource names are derived as $${name}-cluster, $${name}-writer-0, etc."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}[a-z0-9]$", var.name))
    error_message = "name must be lowercase alphanumeric + hyphen, 3-32 chars, starting with a letter."
  }
}

variable "vpc_id" {
  description = "VPC the cluster + security group live in. The DB subnet group is built from `private_subnet_ids` which must belong to this VPC."
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs that form the `aws_db_subnet_group`. At least 2 across distinct AZs (RDS requirement)."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Aurora requires at least 2 private subnets across distinct AZs."
  }
}

variable "consumer_security_group_ids" {
  description = "Security group IDs of the runtime ENIs (ECS task SG, Lambda VPC SG) allowed to reach the cluster on port 5432. Ingress is restricted to these SGs only — no CIDR-based ingress is opened."
  type        = list(string)
  default     = []
}

variable "kms_key_arn" {
  description = "ARN of the `catalyst_data_key` CMK from `modules/kms` (ADR-016). Both the cluster (`storage_encrypted`) and Performance Insights use this key."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:kms:[a-z0-9-]+:[0-9]{12}:key/.+$", var.kms_key_arn))
    error_message = "kms_key_arn must be a full KMS key ARN (arn:aws:kms:{region}:{account}:key/{key-id})."
  }
}

variable "engine_version" {
  description = "Aurora PostgreSQL engine version (16.x family). Default 16.4 is the latest 16-line release as of ADR-019."
  type        = string
  default     = "16.4"

  validation {
    condition     = can(regex("^16\\.[0-9]+$", var.engine_version))
    error_message = "engine_version must be a 16.x release (ADR-019 settles on the 16 family for rds_iam stability)."
  }
}

variable "min_capacity" {
  description = "Minimum Aurora Serverless v2 ACU. 0.5 is the smallest paid floor; scaling to 0 is intentionally NOT enabled for v1 (cold-start cost vs always-warm trade-off — see ADR-019)."
  type        = number
  default     = 0.5

  validation {
    condition     = var.min_capacity >= 0.5 && var.min_capacity <= 256
    error_message = "min_capacity must be between 0.5 and 256 ACU."
  }
}

variable "max_capacity" {
  description = "Maximum Aurora Serverless v2 ACU. Default 2 keeps the demo cost-bounded; bump for real workloads."
  type        = number
  default     = 2

  validation {
    condition     = var.max_capacity >= 0.5 && var.max_capacity <= 256
    error_message = "max_capacity must be between 0.5 and 256 ACU."
  }
}

variable "master_username" {
  description = "Master (break-glass) username on the cluster. Only used by the bootstrap step + Secrets Manager rotation — normal app traffic authenticates via IAM."
  type        = string
  default     = "catalyst_admin"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{1,15}$", var.master_username))
    error_message = "master_username must be lowercase + underscore, 2-16 chars, starting with a letter."
  }
}

variable "database_name" {
  description = "Initial database name created on the cluster by Aurora. The bootstrap step additionally creates the `catalyst_app` IAM-mapped role."
  type        = string
  default     = "catalyst"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.database_name))
    error_message = "database_name must be lowercase + underscore, 1-63 chars, starting with a letter."
  }
}

variable "app_db_user" {
  description = "PostgreSQL role mapped to IAM auth. The composite layer attaches the `rds-db:connect` policy on the runtime exec role for `dbuser:<cluster_resource_id>/<app_db_user>`."
  type        = string
  default     = "catalyst_app"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{1,30}$", var.app_db_user))
    error_message = "app_db_user must be lowercase + underscore, 2-31 chars, starting with a letter."
  }
}

variable "backup_retention_days" {
  description = "Automated backup retention window (days)."
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_days >= 1 && var.backup_retention_days <= 35
    error_message = "backup_retention_days must be between 1 and 35 (RDS-imposed range)."
  }
}

variable "deletion_protection" {
  description = "Whether to protect the cluster from accidental destroy. Off by default to keep demo `terraform destroy` clean; flip to true for production."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Skip the final snapshot at destroy time. Defaults to true for demo; set false in production to retain a recoverable snapshot."
  type        = bool
  default     = true
}

variable "performance_insights_retention_period" {
  description = "Performance Insights retention period in days (7 is free-tier; 731 is the long-tail option). Only used when performance_insights is enabled (always on per ADR-019)."
  type        = number
  default     = 7

  validation {
    condition     = contains([7, 31, 62, 93, 124, 155, 186, 217, 248, 279, 310, 341, 372, 403, 434, 465, 496, 527, 558, 589, 620, 651, 682, 713, 731], var.performance_insights_retention_period)
    error_message = "performance_insights_retention_period must be 7, a multiple of 31 up to 713, or 731 (AWS-imposed enumeration)."
  }
}

variable "tags" {
  description = "Free-form tag map applied to every resource in the module."
  type        = map(string)
  default     = {}
}
