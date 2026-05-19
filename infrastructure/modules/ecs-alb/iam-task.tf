# ---------------------------------------------------------------------------
# SVC-8 — ECS TASK role (per ADR-009 §IAM roles per runtime).
#
# The task role is the application's own AWS identity. It is what the
# FastAPI process inside the container assumes when it calls boto3 — NOT
# what the ECS agent uses to launch the container (that is the execution
# role in iam-execution.tf).
#
# Scope per issue #62:
#   - DynamoDB read/write on the catalyst-platform-state table only
#   - SSM Parameter Store read under /catalyst/* only
#   - CloudWatch PutMetricData with namespace == "Catalyst/API" condition
#
# No wildcard iam:*, no *:* — the tftest under
# infrastructure/tests/ecs-task-def.tftest.hcl enforces this.
# ---------------------------------------------------------------------------

locals {
  # DynamoDB ARN for the platform-state table the API reads + writes.
  catalyst_dynamodb_table_arn = var.enable_task_definition ? (
    "arn:aws:dynamodb:${local.ecs_region}:${local.ecs_account_id}:table/${var.dynamodb_table_name}"
  ) : ""

  # SSM Parameter Store path scoping. The API reads runtime config under
  # /catalyst/*. ARN form for a parameter is `parameter/<name-without-leading-slash>`.
  catalyst_ssm_parameter_arn_prefix = var.enable_task_definition ? (
    "arn:aws:ssm:${local.ecs_region}:${local.ecs_account_id}:parameter/catalyst/*"
  ) : ""
}

data "aws_iam_policy_document" "ecs_task_assume" {
  count = var.enable_task_definition ? 1 : 0

  statement {
    sid     = "EcsTasksAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task" {
  count              = var.enable_task_definition ? 1 : 0
  name               = "${var.name_prefix}-api-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume[0].json

  tags = {
    "catalyst:role" = "ecs-task"
    "catalyst:adr"  = "ADR-009"
  }
}

data "aws_iam_policy_document" "ecs_task_inline" {
  count = var.enable_task_definition ? 1 : 0

  # DynamoDB read + write scoped to the platform-state table. Includes the
  # table-level item APIs; index queries are covered by the `/index/*`
  # subresource glob, which is the same shape the Lambda runtime uses.
  statement {
    sid    = "DynamoDbPlatformStateReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:ConditionCheckItem",
      "dynamodb:DescribeTable",
    ]
    resources = [
      local.catalyst_dynamodb_table_arn,
      "${local.catalyst_dynamodb_table_arn}/index/*",
    ]
  }

  # SSM Parameter Store: read-only under /catalyst/*.
  statement {
    sid    = "SsmParameterStoreReadCatalyst"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = [local.catalyst_ssm_parameter_arn_prefix]
  }

  # CloudWatch Metrics: PutMetricData restricted to namespace "Catalyst/API"
  # via the cloudwatch:namespace condition key. PutMetricData does not
  # accept a resource-level ARN (it must be "*"), so the namespace
  # condition is the only viable scoping mechanism — and it IS sufficient
  # for least-privilege per the AWS IAM docs for CloudWatch metrics.
  statement {
    sid    = "CloudWatchPutMetricDataCatalystApi"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["Catalyst/API"]
    }
  }
}

resource "aws_iam_role_policy" "ecs_task_inline" {
  count  = var.enable_task_definition ? 1 : 0
  name   = "${var.name_prefix}-api-task-inline"
  role   = aws_iam_role.ecs_task[0].id
  policy = data.aws_iam_policy_document.ecs_task_inline[0].json
}

output "ecs_task_role_arn" {
  value       = try(aws_iam_role.ecs_task[0].arn, null)
  description = "ARN of the ECS task role assumed by the FastAPI container at runtime (DynamoDB + SSM + CloudWatch metrics). Null when enable_task_definition = false."
}
