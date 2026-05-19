# ---------------------------------------------------------------------------
# SVC-8 (#62) — ECS task definition + execution role + task role plan tests.
#
# command = plan only (no AWS calls). Asserts:
#   - Task def renders with Fargate + awsvpc
#   - Execution role + task role both have inline policies attached
#   - Health check is configured against /health on the container port
#   - Neither role's policy contains wildcard iam:* or *:* actions
#   - All required env vars are present
# ---------------------------------------------------------------------------

provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "ecs_task_def_disabled_by_default" {
  command = plan

  module {
    source = "./modules/ecs-alb"
  }

  variables {
    vpc_id                = "vpc-01234567"
    public_subnet_ids     = ["subnet-aaaa", "subnet-bbbb"]
    alb_security_group_id = "sg-cafebabe"
  }

  # When enable_task_definition is left at its default (false), none of the
  # SVC-8 resources should be planned — Lambda-only deployments stay lean.
  assert {
    condition     = length(aws_ecs_task_definition.catalyst_api) == 0
    error_message = "Task definition must be gated by enable_task_definition; default false should plan zero resources."
  }

  assert {
    condition     = length(aws_iam_role.ecs_execution) == 0
    error_message = "Execution role must be gated by enable_task_definition; default false should plan zero resources."
  }

  assert {
    condition     = length(aws_iam_role.ecs_task) == 0
    error_message = "Task role must be gated by enable_task_definition; default false should plan zero resources."
  }
}

run "ecs_task_def_enabled" {
  command = plan

  module {
    source = "./modules/ecs-alb"
  }

  variables {
    vpc_id                 = "vpc-01234567"
    public_subnet_ids      = ["subnet-aaaa", "subnet-bbbb"]
    alb_security_group_id  = "sg-cafebabe"
    target_group_type      = "ip"
    enable_task_definition = true
    container_image_uri    = "123456789012.dkr.ecr.us-west-2.amazonaws.com/catalyst-api:test"
    ecr_repository_name    = "catalyst-api"
    log_group_name         = "/aws/catalyst/api"
    dynamodb_table_name    = "catalyst-platform-state"
    # Explicit account_id + region so the test does not need real STS creds.
    aws_account_id = "123456789012"
    aws_region     = "us-west-2"
  }

  # ---------- Task definition shape ----------

  assert {
    condition     = aws_ecs_task_definition.catalyst_api[0].family == "catalyst-api"
    error_message = "Task definition family must be catalyst-api so the ECS service (added in #230) can reference it by family name."
  }

  assert {
    condition     = aws_ecs_task_definition.catalyst_api[0].network_mode == "awsvpc"
    error_message = "Task definition must use awsvpc network mode (Fargate requirement per ADR-009)."
  }

  assert {
    condition     = contains(aws_ecs_task_definition.catalyst_api[0].requires_compatibilities, "FARGATE")
    error_message = "Task definition must declare FARGATE in requires_compatibilities."
  }

  # ---------- Both roles created + linked ----------

  assert {
    condition     = aws_iam_role.ecs_execution[0].name == "catalyst-ecs-execution-role"
    error_message = "Execution role name must be catalyst-ecs-execution-role per ADR-009 §IAM roles per runtime."
  }

  assert {
    condition     = aws_iam_role.ecs_task[0].name == "catalyst-api-task-role"
    error_message = "Task role name must be catalyst-api-task-role per ADR-009 §IAM roles per runtime."
  }

  # Both inline policies must exist (one per role). `name` is a known-at-plan
  # value, so we assert on that rather than on `role`/`id` which Terraform
  # only computes during apply.
  assert {
    condition     = aws_iam_role_policy.ecs_execution_inline[0].name == "catalyst-ecs-execution-inline"
    error_message = "Execution role must have an inline policy named catalyst-ecs-execution-inline."
  }

  assert {
    condition     = aws_iam_role_policy.ecs_task_inline[0].name == "catalyst-api-task-inline"
    error_message = "Task role must have an inline policy named catalyst-api-task-inline."
  }

  # ---------- Health check is configured ----------

  assert {
    condition     = length(local.container_definitions) == 1
    error_message = "Exactly one container definition (catalyst-api) must be rendered."
  }

  assert {
    condition     = local.container_definitions[0].healthCheck.command[0] == "CMD-SHELL"
    error_message = "Container health check must use CMD-SHELL form."
  }

  assert {
    condition     = strcontains(local.container_definitions[0].healthCheck.command[1], "/health")
    error_message = "Container health check must hit FastAPI /health endpoint (ADR-007 §health check)."
  }

  assert {
    condition     = local.container_definitions[0].healthCheck.retries == 3
    error_message = "Container health check must retry 3 times before marking unhealthy."
  }

  # ---------- Required env vars present ----------

  assert {
    condition     = length([for e in local.container_definitions[0].environment : e.name if e.name == "CATALYST_LOG_LEVEL"]) == 1
    error_message = "Container must expose CATALYST_LOG_LEVEL env var."
  }

  assert {
    condition     = length([for e in local.container_definitions[0].environment : e.name if e.name == "AWS_REGION"]) == 1
    error_message = "Container must expose AWS_REGION env var."
  }

  assert {
    condition     = length([for e in local.container_definitions[0].environment : e.name if e.name == "DYNAMODB_TABLE_NAME"]) == 1
    error_message = "Container must expose DYNAMODB_TABLE_NAME env var."
  }

  # ---------- No wildcard iam:* or *:* anywhere in either inline policy ----------
  #
  # data.aws_iam_policy_document.*.json renders the same JSON Terraform will
  # send to AWS. We assert the rendered strings contain neither "iam:*" nor
  # "\"*\":\"*\"" / `"*"` as a sole action.

  assert {
    condition     = !strcontains(data.aws_iam_policy_document.ecs_execution_inline[0].json, "iam:*")
    error_message = "Execution role inline policy must not grant iam:* (least-privilege per ADR-009)."
  }

  assert {
    condition     = !strcontains(data.aws_iam_policy_document.ecs_task_inline[0].json, "iam:*")
    error_message = "Task role inline policy must not grant iam:* (least-privilege per ADR-009)."
  }

  # A sole "*" action would render literally as `"Action":"*"` in the JSON.
  assert {
    condition     = !strcontains(data.aws_iam_policy_document.ecs_execution_inline[0].json, "\"Action\":\"*\"")
    error_message = "Execution role inline policy must not grant *:* (least-privilege per ADR-009)."
  }

  assert {
    condition     = !strcontains(data.aws_iam_policy_document.ecs_task_inline[0].json, "\"Action\":\"*\"")
    error_message = "Task role inline policy must not grant *:* (least-privilege per ADR-009)."
  }

  # ---------- Scoping conditions ----------
  #
  # CloudWatch PutMetricData must be gated by the cloudwatch:namespace
  # condition (set to "Catalyst/API"); this is the only viable least-priv
  # mechanism for PutMetricData because that action does not accept a
  # resource-level ARN.

  assert {
    condition     = strcontains(data.aws_iam_policy_document.ecs_task_inline[0].json, "cloudwatch:namespace")
    error_message = "Task role PutMetricData statement must be conditioned on cloudwatch:namespace."
  }

  assert {
    condition     = strcontains(data.aws_iam_policy_document.ecs_task_inline[0].json, "Catalyst/API")
    error_message = "Task role PutMetricData condition must restrict namespace to Catalyst/API."
  }
}
