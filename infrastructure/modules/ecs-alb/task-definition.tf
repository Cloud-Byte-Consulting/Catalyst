# ---------------------------------------------------------------------------
# SVC-8 — ECS task definition for the catalyst-api Fargate container
# (per ADR-009 §Terraform module structure / §IAM roles per runtime).
#
# Fargate launch type with awsvpc network mode is required by ADR-009
# (the only ECS shape compatible with an ALB target_type = "ip" and the
# shared private subnets). The two role ARNs come from iam-execution.tf
# and iam-task.tf.
#
# The container definition itself is rendered in container-definition.tf
# so the inline JSON does not bloat this file and so the tftest can assert
# on the rendered structure via local.container_definitions.
#
# Out of scope for this PR (do not add here):
#   - aws_ecs_service / aws_appautoscaling_*  → #230 (autoscaling agent)
#   - aws_kms_key for log encryption          → #228 (CMK migration)
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "catalyst_api" {
  count = var.enable_task_definition ? 1 : 0

  family                   = "${var.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory

  execution_role_arn = aws_iam_role.ecs_execution[0].arn
  task_role_arn      = aws_iam_role.ecs_task[0].arn

  container_definitions = local.container_definitions_json

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  tags = {
    "catalyst:adr"     = "ADR-009"
    "catalyst:runtime" = "ecs-fargate"
  }
}

resource "aws_ssm_parameter" "task_definition_arn" {
  count = var.enable_task_definition ? 1 : 0

  name  = "/catalyst/shared/ecs/task-definition/arn"
  type  = "String"
  value = aws_ecs_task_definition.catalyst_api[0].arn
}

output "task_definition_arn" {
  value       = try(aws_ecs_task_definition.catalyst_api[0].arn, null)
  description = "ARN of the catalyst-api Fargate task definition. Null when enable_task_definition = false."
}

output "task_definition_family" {
  value       = try(aws_ecs_task_definition.catalyst_api[0].family, null)
  description = "Task definition family name (used by aws_ecs_service in #230)."
}
