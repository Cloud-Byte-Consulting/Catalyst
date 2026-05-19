# ---------------------------------------------------------------------------
# wa-iac-analyzer — IAM SECURITY CONTRACT (issue #284, stacked on #283).
#
# This file is the *contract* the Phase 1 implementation PR will conform to.
# It declares the least-privilege policy *documents* (data sources) and the
# assume-role trust shape, but does NOT yet attach them to an `aws_iam_role`.
# Role creation moves with the rest of Phase 1 (CFN-wrap vs Terraform-native
# discovery, see README §"Discovery"). Until then, this file holds only data
# sources + locals — zero billable resources, zero plan output on default vars.
#
# Why "documents-only" and not roles yet:
#   - The composite is a SKELETON per #283 (root `count = 0`).
#   - Declaring `aws_iam_role` here would force the Phase 1 implementer to
#     either (a) duplicate the policy JSON in their final stack or (b) keep
#     the role attached to nothing, which Checkov flags. Keeping the contract
#     at the *policy document* layer means the implementer drops in their
#     `aws_iam_role` + `aws_iam_role_policy` with this document as `policy =
#     data.aws_iam_policy_document.analyzer_task_role.json` and ships.
#   - ADR-008 dictates the IAM shape; this file is where that shape is
#     codified ahead of implementation so reviewers can challenge the scope
#     envelope WITHOUT being distracted by resource-attachment plumbing.
#
# Reviewer focus: every `statement {}` block below must justify itself
# against the upstream `aws-samples/well-architected-iac-analyzer`
# CloudFormation default. Upstream ships managed policies broader than
# Catalyst's ADR-008/ADR-010 bar. This contract narrows them to:
#   - Bedrock InvokeModel  → ONLY the specific model ARNs the operator approves
#   - DynamoDB *Item       → ONLY the analyzer table (passed in at Phase 1)
#   - S3 Get/Put           → ONLY the S3-Vectors bucket
#   - CloudWatch Logs      → ONLY the analyzer log group
#
# Acceptance gate from #284 Scenario 1: "no statement allows Action \"*\" on
# Resource \"*\"". Every statement here is explicit-action + explicit-resource.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Trust policy — ECS task service principal only.
#
# Why ECS-only: the analyzer runs as an ECS Fargate task per ADR-009 (runtime
# strategy). NO Lambda, NO EC2 instance profile, NO cross-account assume
# allowed at this phase. If Phase 1 implementation discovers a different
# runtime, this trust policy must be updated explicitly — silent broadening
# is rejected by the reviewer contract.
#
# `count` is bound to the same flag that gates the composite as a whole so
# the data source is not even evaluated on default vars.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "analyzer_assume" {
  # count = 0 keeps this a documents-only contract at scaffold stage. Phase 1
  # implementation flips this to `var.enable_wa_aws_iac_analyzer ? 1 : 0`
  # (where that flag is plumbed from the root stack into a module-level
  # variable). For now: zero plan output, regardless of root flag state.
  count = 0

  statement {
    sid     = "EcsTaskAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    # Condition: confused-deputy guard — the role can only be assumed when
    # the calling ECS task lives in *this* account. Without this, a cross-
    # account ECS task in another principal's account that happens to know
    # this role's ARN could assume it. ADR-008 §"Least privilege" implies
    # this guard; making it explicit costs nothing.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current[0].account_id]
    }
  }
}

data "aws_caller_identity" "current" {
  count = 0
}

# ---------------------------------------------------------------------------
# Task role policy — the actual permissions the running ECS task gets.
#
# Each statement below is scoped by Action AND by Resource. Wildcards on
# Resource appear ONLY where the AWS API genuinely requires them (e.g. some
# Bedrock model-list operations that the analyzer does not need — those are
# deliberately ABSENT from this contract).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "analyzer_task_role" {
  count = 0

  # -------------------------------------------------------------------------
  # Bedrock — Claude model invocation.
  #
  # Action set: InvokeModel + InvokeModelWithResponseStream. The analyzer
  # streams Claude responses to the UI so the streaming variant is required.
  #
  # Resource set: ONLY the ARNs passed in via `var.bedrock_model_arns`. The
  # default is `[]` so on default vars this statement collapses to
  # Resource=[] which Terraform serialises as an invalid policy — to avoid
  # that, the statement is wrapped in a `dynamic` block so it is OMITTED
  # entirely when the operator has not yet approved any model ARNs. This
  # forces the Phase 1 implementer to pass at least one model ARN, which is
  # the correct UX: no implicit Bedrock access.
  #
  # NOT granted: bedrock:ListFoundationModels, bedrock:GetFoundationModel
  # (the analyzer UI does not need a model picker; the model is fixed by
  # the operator at deploy time per ADR-023).
  # -------------------------------------------------------------------------
  dynamic "statement" {
    for_each = length(var.bedrock_model_arns) > 0 ? [1] : []
    content {
      sid    = "BedrockInvokeApprovedModels"
      effect = "Allow"
      actions = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
      ]
      resources = var.bedrock_model_arns
    }
  }

  # -------------------------------------------------------------------------
  # DynamoDB — analyzer state table.
  #
  # The upstream stack uses DynamoDB to persist analysis runs (input IaC blob
  # hash, pillar findings, recommendation IDs). The analyzer needs item-level
  # CRUD but NOT table-level admin (no CreateTable / DeleteTable / UpdateTable
  # — those belong to Terraform at apply time, not to the running task).
  #
  # Resource ARN is parameterised so the Phase 1 implementer can pass the
  # actual table ARN once it exists. At contract stage we use a placeholder
  # local that the Phase 1 implementer will replace; the policy document
  # still validates against the placeholder.
  # -------------------------------------------------------------------------
  statement {
    sid    = "DynamoDbAnalyzerTableItemCrud"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
    ]
    # Resource is intentionally a placeholder ARN — Phase 1 implementer
    # replaces with the real table ARN. The placeholder is account/region
    # parameterised so `terraform validate` succeeds without hard-coding.
    resources = [
      "arn:aws:dynamodb:*:${data.aws_caller_identity.current[0].account_id}:table/${var.name_prefix}-analyses",
      "arn:aws:dynamodb:*:${data.aws_caller_identity.current[0].account_id}:table/${var.name_prefix}-analyses/index/*",
    ]
  }

  # -------------------------------------------------------------------------
  # S3 — S3-Vectors bucket for embedding storage.
  #
  # The analyzer chunks IaC, embeds it, and stores vectors in S3 for RAG
  # retrieval. The task needs object-level Get/Put + List on the prefix it
  # owns. NO s3:* on the bucket, NO PutBucketPolicy, NO DeleteBucket.
  #
  # `s3:ListBucket` is scoped via a Condition on `s3:prefix` so the task
  # cannot enumerate sibling prefixes — multi-tenant safety per ADR-008.
  # -------------------------------------------------------------------------
  statement {
    sid    = "S3VectorsObjectAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      "arn:aws:s3:::${var.name_prefix}-vectors-*/*",
    ]
  }

  statement {
    sid       = "S3VectorsBucketListScoped"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.name_prefix}-vectors-*"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["analyses/*", "embeddings/*"]
    }
  }

  # -------------------------------------------------------------------------
  # CloudWatch Logs — task log stream.
  #
  # CreateLogStream + PutLogEvents only. NO CreateLogGroup (Terraform owns
  # the log group at apply time, NOT the running task — this prevents log-
  # group sprawl from a misbehaving task).
  # -------------------------------------------------------------------------
  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:*:${data.aws_caller_identity.current[0].account_id}:log-group:/aws/ecs/${var.name_prefix}:log-stream:*",
    ]
  }
}

# ---------------------------------------------------------------------------
# Phase 1 implementer hook.
#
# When this composite stops being a skeleton, add (in this same file or a
# `roles.tf` sibling):
#
#   resource "aws_iam_role" "analyzer_task" {
#     count              = var.enable_wa_aws_iac_analyzer ? 1 : 0
#     name_prefix        = "${var.name_prefix}-task-"
#     assume_role_policy = data.aws_iam_policy_document.analyzer_assume[0].json
#     tags               = local.component_tags
#   }
#
#   resource "aws_iam_role_policy" "analyzer_task" {
#     count  = var.enable_wa_aws_iac_analyzer ? 1 : 0
#     name   = "task-role-policy"
#     role   = aws_iam_role.analyzer_task[0].id
#     policy = data.aws_iam_policy_document.analyzer_task_role[0].json
#   }
#
# Until then, the data sources above are the binding contract. Any deviation
# (adding actions, broadening resources) MUST be challenged in PR review
# against the ADR-008 / ADR-010 / ADR-023 bar.
# ---------------------------------------------------------------------------
