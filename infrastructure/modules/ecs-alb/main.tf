variable "name_prefix" {
  type    = string
  default = "catalyst"
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "alb_security_group_id" {
  type = string
}

variable "target_group_type" {
  type        = string
  default     = "lambda"
  description = "ALB target group target_type. `lambda` matches modules/lambda-service (the default Catalyst runtime); switch to `ip` for Fargate task ENIs."

  validation {
    condition     = contains(["lambda", "ip"], var.target_group_type)
    error_message = "target_group_type must be one of: lambda, ip."
  }
}

# ---------------------------------------------------------------------------
# SVC-8 (#62) — variables that gate the ECS task definition + roles surface.
# Default `enable_task_definition = false` so a Lambda-only apply (the
# default runtime per ADR-009) does not provision unused IAM resources.
# Operators flip this to true when RUNTIME=ecs is selected.
# ---------------------------------------------------------------------------

variable "enable_task_definition" {
  type        = bool
  default     = false
  description = "When true, provisions the ECS Fargate task definition + execution role + task role for the catalyst-api container (ADR-009 alternate runtime). Default false keeps Lambda-only deployments lean."
}

variable "container_image_uri" {
  type        = string
  default     = ""
  description = "Fully-qualified ECR image URI for the catalyst-api container (e.g. 123456789012.dkr.ecr.us-west-2.amazonaws.com/catalyst-api:sha-abcdef). Required when enable_task_definition = true; ignored otherwise."
}

variable "ecr_repository_name" {
  type        = string
  default     = "catalyst-api"
  description = "Name of the ECR repository the execution role is scoped to pull from. Matches modules/ecr var.name."
}

variable "log_group_name" {
  type        = string
  default     = "/aws/catalyst/api"
  description = "CloudWatch log group the awslogs driver streams container output to; also the only log group the execution role can write to."
}

variable "dynamodb_table_name" {
  type        = string
  default     = "catalyst-platform-state"
  description = "DynamoDB table the task role is scoped to read + write. Matches modules/dynamodb var.name (the platform-state table)."
}

variable "task_cpu" {
  type        = string
  default     = "512"
  description = "Fargate task vCPU units. Defaults to 0.5 vCPU — sufficient for the low-RPS FastAPI workload per ADR-009 §Context."
}

variable "task_memory" {
  type        = string
  default     = "1024"
  description = "Fargate task memory in MiB. 1024 MiB matches the Lambda function's default reservation."
}

variable "container_port" {
  type        = number
  default     = 8080
  description = "TCP port uvicorn binds inside the container. The ALB target group (target_type = ip) forwards to this port."
}

variable "catalyst_log_level" {
  type        = string
  default     = "INFO"
  description = "Value for the CATALYST_LOG_LEVEL container env var."
}

variable "container_extra_env" {
  type = list(object({
    name  = string
    value = string
  }))
  default     = []
  description = "Additional env vars to merge into the container definition on top of the SVC-8 defaults (CATALYST_LOG_LEVEL, AWS_REGION, DYNAMODB_TABLE_NAME)."
}

variable "aws_account_id" {
  type        = string
  default     = ""
  description = "12-digit AWS account ID to construct IAM resource ARNs against. Defaults to data.aws_caller_identity at apply time; pass an explicit value to avoid STS round-trips during `terraform test` or in air-gapped plans."

  validation {
    condition     = var.aws_account_id == "" || can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be empty or a 12-digit AWS account number."
  }
}

variable "aws_region" {
  type        = string
  default     = ""
  description = "AWS region to construct IAM resource ARNs against. Defaults to data.aws_region at apply time; pass an explicit value to avoid an API round-trip during `terraform test`."
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# The Catalyst API ALB is intentionally internet-facing; the public surface is
# strictly constrained by `module.security_groups.alb` ingress, which is pinned
# to `var.alb_ingress_allowlist` (see ADR-007 + docs/runtime.md). This is the
# documented exposure mode — not an ad-hoc carve-out.
# tfsec:ignore:aws-elb-alb-not-public
resource "aws_lb" "this" {
  name                       = "${var.name_prefix}-alb"
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [var.alb_security_group_id]
  subnets                    = var.public_subnet_ids
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api"
  target_type = var.target_group_type
  vpc_id      = var.vpc_id
  # When target_type=lambda, port + protocol are unused on the target group
  # itself (the listener forwards directly to the Lambda integration). When
  # target_type=ip (the ECS rollout) the listener routes 443/HTTP to ENIs.
  port     = var.target_group_type == "lambda" ? null : 443
  protocol = var.target_group_type == "lambda" ? null : "HTTP"

  # Lambda target groups require interval > timeout. The Terraform AWS
  # provider does not adjust default timeout/interval for target_type=lambda,
  # so an unconfigured `health_check { path = ... }` resolves to interval=30
  # / timeout=30 which AWS rejects ("Health check interval must be greater
  # than the timeout"). Set explicit values that are valid for both lambda
  # (timeout 1-120, interval 5-300) and ip target types.
  health_check {
    path     = "/health"
    interval = 35
    timeout  = 30
  }
}

# HTTPS on the public listener requires an ACM certificate plus a DNS-validated
# domain, both of which are tracked separately (TLS rollout — see PR #115
# follow-up note in the consolidated workflow). Today the listener terminates
# HTTP on 443 so the ingress allowlist still gates traffic at the SG layer.
# Once the cert is wired the protocol flips to HTTPS and a redirect listener
# is added on 80. This is intentional baseline debt and the apply role has no
# path to provision ACM resources without a follow-up change.
# tfsec:ignore:aws-elb-http-not-used
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_ssm_parameter" "ecs_cluster" {
  name  = "/catalyst/shared/ecs/cluster/arn"
  type  = "String"
  value = aws_ecs_cluster.this.arn
}

resource "aws_ssm_parameter" "alb_listener" {
  name  = "/catalyst/shared/alb/listener/arn"
  type  = "String"
  value = aws_lb_listener.https.arn
}

output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "target_group_arn" {
  value = aws_lb_target_group.api.arn
}

output "alb_listener_arn" {
  value = aws_lb_listener.https.arn
}

output "alb_dns_name" {
  value = aws_lb.this.dns_name
}
