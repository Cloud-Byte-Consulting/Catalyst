# ---------------------------------------------------------------------------
# SVC-8 — container definition for the catalyst-api Fargate task.
#
# Kept in its own file so:
#   1. The tftest can assert on local.container_definitions structure.
#   2. The JSON does not bloat task-definition.tf.
#
# Health check hits FastAPI /health (the same path the ALB target group
# uses, defined in main.tf health_check {}). Failure thresholds follow the
# ECS default: 3 consecutive 1xx-non-2xx responses → unhealthy.
# ---------------------------------------------------------------------------

locals {
  # Default container env vars from the issue scope. Operators may extend
  # via var.container_extra_env; everything is funneled through the same
  # `[{ name, value }]` shape ECS requires.
  catalyst_api_default_env = [
    {
      name  = "CATALYST_LOG_LEVEL"
      value = var.catalyst_log_level
    },
    {
      name  = "AWS_REGION"
      value = local.ecs_region
    },
    {
      name  = "DYNAMODB_TABLE_NAME"
      value = var.dynamodb_table_name
    },
  ]

  catalyst_api_env = concat(local.catalyst_api_default_env, var.container_extra_env)

  # Single container definition — the FastAPI app served by uvicorn (per
  # ADR-009 §Application adapter, the same image's uvicorn entrypoint is
  # used on ECS; the Mangum handler is dead code in this runtime).
  #
  # The container CMD override below switches off Lambda's RIC entrypoint
  # so uvicorn binds 0.0.0.0:8080 inside the awsvpc ENI; the ALB target
  # group's target_type = "ip" wires the ENI IP to port 8080.
  container_definitions = var.enable_task_definition ? [
    {
      name      = "${var.name_prefix}-api"
      image     = var.container_image_uri
      essential = true

      # Override the Lambda RIC entrypoint baked into
      # public.ecr.aws/lambda/python:3.12. On ECS we want uvicorn directly.
      entryPoint = ["python", "-m", "uvicorn"]
      command = [
        "catalyst.main:app",
        "--host", "0.0.0.0",
        "--port", tostring(var.container_port),
      ]

      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
          protocol      = "tcp"
        },
      ]

      environment = local.catalyst_api_env

      healthCheck = {
        command = [
          "CMD-SHELL",
          "curl -fsS http://localhost:${var.container_port}/health || exit 1",
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 15
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = var.log_group_name
          "awslogs-region"        = local.ecs_region
          "awslogs-stream-prefix" = "catalyst-api"
        }
      }

      readonlyRootFilesystem = false
    },
  ] : []

  container_definitions_json = jsonencode(local.container_definitions)
}

output "container_definitions" {
  value       = local.container_definitions
  description = "Rendered container definitions for the catalyst-api task. Exposed so consumers (and the tftest) can introspect health check, env, and image without parsing JSON twice."
}
