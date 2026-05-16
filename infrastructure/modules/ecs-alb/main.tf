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
