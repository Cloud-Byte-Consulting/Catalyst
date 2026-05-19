<!-- AUTO-GENERATED from skills/iam-policy-craft/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: iam-policy-craft
description: >-
  IAM policy design for Catalyst: aws_iam_policy_document data sources, explicit
  actions and resource ARNs, zero-wildcard enforcement, condition keys
  (aws:ResourceTag, aws:SourceArn, aws:ResourceAccount), OIDC trust policies
  for GitHub Actions, and the IAM model from AGENTS.md. Use when creating roles,
  policies, or trust relationships.
---

<!-- Vendored from: platform-catalyst/.cursor/skills/iam-policy-craft/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# IAM policy craft

## Role

You guide IAM policy design for Catalyst with an absolute zero-wildcard standard. Every role, policy, and trust relationship uses `aws_iam_policy_document` data sources with explicit actions and pinned resource ARNs. You enforce the IAM model from `AGENTS.md` §7 and Zero Trust principles from *Mastering CSPM* (Nomani, Ch 1: pp 22-24, Zero Trust model and six foundational pillars).

## Instructions

### 1. The zero-wildcard rule

From `AGENTS.md`:
> **No wildcard IAM** (`Action: "*"` or `Resource: "*"`) — every resource is pinned, every action enumerated. There is no scenario where this repo needs a wildcard policy.

Where AWS forces a `*` (e.g., `ecr:GetAuthorizationToken` has no resource-level scope), document why with a comment:

```hcl
statement {
  sid    = "ECRAuth"
  effect = "Allow"
  actions = ["ecr:GetAuthorizationToken"]
  # GetAuthorizationToken does not support resource-level permissions
  # per https://docs.aws.amazon.com/AmazonECR/latest/userguide/security-iam.html
  resources = ["*"]
}
```

### 2. Always use aws_iam_policy_document

Never inline JSON policies. Always use the `aws_iam_policy_document` data source:

```hcl
data "aws_iam_policy_document" "task_permissions" {
  statement {
    sid    = "AuroraConnect"
    effect = "Allow"
    actions = ["rds-db:connect"]
    resources = [
      "arn:aws:rds-db:${local.region}:${local.account_id}:dbuser:${var.aurora_cluster_resource_id}/catalyst_app"
    ]
  }

  statement {
    sid    = "DynamoDBReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = var.dynamodb_table_arns
  }

  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.data_kms_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["dynamodb.${local.region}.amazonaws.com"]
    }
  }
}
```

### 3. IAM roles from AGENTS.md §7

| Role | Trust | Permissions |
|------|-------|-------------|
| `catalyst-api-task-role` | `ecs-tasks.amazonaws.com` | `rds-db:connect` to specific dbuser, RW on 4 DDB tables, `kms:Decrypt` on `catalyst-data`, `secretsmanager:GetSecretValue` on 1 ARN |
| `catalyst-ecs-execution-role` | `ecs-tasks.amazonaws.com` | `ecr:GetAuthorizationToken`, `ecr:BatchGetImage` on specific repos, `logs:CreateLogStream`/`PutLogEvents`, `kms:Decrypt` on `catalyst-secrets` |
| `lambda-deploy-orchestrator-role` | `lambda.amazonaws.com` | `ecs:UpdateService` on 1 ARN, `elasticloadbalancing:ModifyRule` on 1 ARN, DDB write, SNS publish |
| `github-actions-oidc-plan` | `token.actions.githubusercontent.com` | Read-only, `sub` = `repo:<org>/catalyst-idp:pull_request` |
| `github-actions-oidc-apply` | `token.actions.githubusercontent.com` | Scoped write, `sub` = `repo:<org>/catalyst-idp:ref:refs/heads/main`, `aws:ResourceTag/Project = catalyst` |

### 4. Trust policies

```hcl
# ECS task trust
data "aws_iam_policy_document" "ecs_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# GitHub Actions OIDC trust
data "aws_iam_policy_document" "github_oidc_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = var.allowed_repo_subjects  # e.g., ["repo:org/catalyst-idp:ref:refs/heads/main"]
    }
  }
}
```

### 5. Condition keys for defense-in-depth

Per *CSPM* Ch 1 (Zero Trust — verify explicitly):

```hcl
# Restrict by resource tag
condition {
  test     = "StringEquals"
  variable = "aws:ResourceTag/Project"
  values   = ["catalyst"]
}

# Restrict by source account
condition {
  test     = "StringEquals"
  variable = "aws:ResourceAccount"
  values   = [local.account_id]
}

# Restrict KMS usage to specific service
condition {
  test     = "StringEquals"
  variable = "kms:ViaService"
  values   = ["s3.${local.region}.amazonaws.com"]
}

# Restrict by source ARN (for service-linked access)
condition {
  test     = "ArnEquals"
  variable = "aws:SourceArn"
  values   = [var.source_resource_arn]
}
```

### 6. The leaf/iam-role module interface

```hcl
# infrastructure/modules/leaf/iam-role/variables.tf
variable "name" {
  type = string
}

variable "trust_principal" {
  description = "AWS service principal for the trust policy"
  type        = string
}

variable "policy_document" {
  description = "JSON policy document from aws_iam_policy_document data source"
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
```

```hcl
# infrastructure/modules/leaf/iam-role/main.tf
resource "aws_iam_role" "this" {
  name               = var.name
  assume_role_policy = data.aws_iam_policy_document.trust.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "inline" {
  name   = "${var.name}-policy"
  role   = aws_iam_role.this.id
  policy = var.policy_document
}
```

### 7. Probe role isolation (ops-intel)

Each of the 5 ops-intel probe Lambdas gets its own role scoped to its domain:

```hcl
# S3 encryption probe — can only read S3 metadata, not IAM or CloudWatch
data "aws_iam_policy_document" "s3_probe" {
  statement {
    sid    = "S3Read"
    effect = "Allow"
    actions = [
      "s3:GetBucketEncryption",
      "s3:GetBucketPolicy",
      "s3:GetBucketPublicAccessBlock",
      "s3:GetBucketVersioning",
      "s3:ListAllMyBuckets",
    ]
    resources = ["arn:aws:s3:::*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [local.account_id]
    }
  }
}
```

## Output

- **New role**: trust policy + permissions policy via `aws_iam_policy_document` + role resource + `.tftest.hcl`
- **Policy review**: explicit check for wildcards, missing conditions, overly broad resources
- **OIDC setup**: provider + trust policy with `sub` condition + plan vs apply split

## Guardrails

- **Absolute**: no `Action: "*"`, no `Resource: "*"`, no `Principal: "*"` unless AWS forces it (documented).
- Always use `aws_iam_policy_document` data sources — never inline JSON strings.
- Condition keys are not optional — use `aws:ResourceTag`, `aws:SourceArn`, `kms:ViaService` where applicable.
- Task role != execution role for ECS — always separate.
- OIDC trust policies must pin `sub` to specific repo + branch patterns.
- Per *CSPM* Ch 1 (p23): "Never trust, always verify" — every IAM decision assumes the caller might be compromised.
