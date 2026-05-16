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

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"
}

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api"
  port        = 443
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    path = "/health"
  }
}

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
