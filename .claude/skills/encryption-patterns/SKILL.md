<!-- AUTO-GENERATED from skills/encryption-patterns/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: encryption-patterns
description: >-
  KMS and encryption-at-rest patterns for Catalyst: CMK lifecycle, key
  policies, service grants, three-key strategy (data, logs, secrets), and
  encryption configuration for Aurora, S3, DynamoDB, ECS, CloudWatch Logs,
  SNS, and Secrets Manager. Use when configuring encryption on any resource.
---

<!-- Vendored from: platform-catalyst/.cursor/skills/encryption-patterns/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Encryption patterns

## Role

You guide encryption-at-rest configuration for all Catalyst resources using the three-CMK strategy from `AGENTS.md` §5.5. You enforce that every encryption-capable resource uses customer-managed KMS keys with scoped key policies.

## Instructions

### 1. Three-CMK strategy (from AGENTS.md §5.5)

| Key alias | Purpose | Encrypts |
|-----------|---------|----------|
| `alias/catalyst-data` | Application data | Aurora, DynamoDB, app S3 buckets |
| `alias/catalyst-logs` | Logging data | CloudWatch Logs, access-log S3 |
| `alias/catalyst-secrets` | Secrets and config | Secrets Manager, SSM SecureString |

**Why three, not per-resource?** Cost (CMKs are $1/month each) + key-policy management fatigue. Three keys provide sufficient blast-radius isolation while keeping policies reviewable.

### 2. KMS key module

```hcl
# infrastructure/modules/leaf/kms-key/main.tf

resource "aws_kms_key" "this" {
  description             = var.description
  enable_key_rotation     = true  # Annual rotation — mandatory
  deletion_window_in_days = 30
  tags                    = local.common_tags

  policy = data.aws_iam_policy_document.key_policy.json
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.alias_name}"
  target_key_id = aws_kms_key.this.key_id
}
```

### 3. Key policy pattern

Per *CSPM* (Nomani, Ch 1 pp 26-27: cryptography and encryption):

```hcl
data "aws_iam_policy_document" "key_policy" {
  # Key administrators (Terraform role)
  statement {
    sid    = "KeyAdministration"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [var.admin_role_arn]
    }
    actions = [
      "kms:Create*",
      "kms:Describe*",
      "kms:Enable*",
      "kms:List*",
      "kms:Put*",
      "kms:Update*",
      "kms:Revoke*",
      "kms:Disable*",
      "kms:Get*",
      "kms:Delete*",
      "kms:ScheduleKeyDeletion",
      "kms:CancelKeyDeletion",
      "kms:TagResource",
      "kms:UntagResource",
    ]
    resources = ["*"]  # Key policy "Resource" always refers to the key itself
  }

  # Key usage (service roles)
  dynamic "statement" {
    for_each = var.usage_role_arns
    content {
      sid    = "KeyUsage-${statement.key}"
      effect = "Allow"
      principals {
        type        = "AWS"
        identifiers = [statement.value]
      }
      actions = [
        "kms:Decrypt",
        "kms:GenerateDataKey",
        "kms:GenerateDataKeyWithoutPlaintext",
        "kms:DescribeKey",
      ]
      resources = ["*"]  # Within key policy, refers to this key
      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = var.via_services  # e.g., ["s3.us-east-1.amazonaws.com"]
      }
    }
  }

  # Deny all other principals — no Principal: "*" grants
}
```

**Key rule**: No `Principal: "*"` in key policies. Every grant is scoped to a specific role ARN with a `kms:ViaService` condition.

### 4. Service-specific encryption

**Aurora Serverless v2:**
```hcl
resource "aws_rds_cluster" "this" {
  storage_encrypted = true
  kms_key_id        = var.kms_key_arn  # alias/catalyst-data
  # ...
}
```

**S3:**
```hcl
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn  # alias/catalyst-data or catalyst-logs
    }
    bucket_key_enabled = true  # Reduces KMS API calls and cost
  }
}
```

**DynamoDB:**
```hcl
resource "aws_dynamodb_table" "this" {
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn  # alias/catalyst-data
  }
  # ...
}
```

**CloudWatch Logs:**
```hcl
resource "aws_cloudwatch_log_group" "this" {
  name              = "/catalyst/${var.service_name}"
  retention_in_days = var.retention_days
  kms_key_id        = var.kms_key_arn  # alias/catalyst-logs
  tags              = local.common_tags
}
```

**SNS:**
```hcl
resource "aws_sns_topic" "this" {
  name              = var.topic_name
  kms_master_key_id = var.kms_key_arn  # alias/catalyst-data
  tags              = local.common_tags
}
```

**Secrets Manager:**
```hcl
resource "aws_secretsmanager_secret" "this" {
  name       = var.secret_name
  kms_key_id = var.kms_key_arn  # alias/catalyst-secrets
  tags       = local.common_tags
}
```

### 5. ECS task encryption

ECS tasks use encrypted log groups and encrypted environment from Secrets Manager:

```hcl
resource "aws_ecs_task_definition" "this" {
  # ...
  container_definitions = jsonencode([{
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = module.log_group.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = var.service_name
      }
    }
    secrets = [
      {
        name      = "DB_PASSWORD"
        valueFrom = var.db_password_secret_arn
      }
    ]
  }])
}
```

### 6. Bucket key optimization

Per *Platform Engineering for Architects* Ch 8 (cost management): always enable `bucket_key_enabled = true` on S3 encryption. This reduces KMS `GenerateDataKey` API calls from per-object to per-bucket-key-rotation, significantly reducing costs at scale.

### 7. Test assertions for encryption

Every module with encryption MUST assert in `.tftest.hcl`:

```hcl
run "encryption_configured" {
  command = plan

  assert {
    condition     = aws_s3_bucket_server_side_encryption_configuration.this.rule[0].apply_server_side_encryption_by_default[0].sse_algorithm == "aws:kms"
    error_message = "Must use KMS encryption, not AES256"
  }

  assert {
    condition     = aws_s3_bucket_server_side_encryption_configuration.this.rule[0].apply_server_side_encryption_by_default[0].kms_master_key_id != ""
    error_message = "Must specify a customer-managed KMS key, not the AWS-managed default"
  }
}
```

## Output

- **New encrypted resource**: HCL with KMS ARN input + encryption config + key policy grant
- **Key policy update**: new statement for a service role needing decrypt access
- **Test assertion**: `.tftest.hcl` block verifying encryption is configured

## Guardrails

- Every encryption-capable resource uses a customer-managed CMK — never AWS-managed defaults, never unencrypted.
- Key policies use specific role ARNs with `kms:ViaService` — no `Principal: "*"`.
- Annual key rotation is enabled on all CMKs.
- `bucket_key_enabled = true` on all S3 encryption configs.
- The three-key strategy is the standard — do not create per-resource keys without an ADR.
- Deletion window is 30 days — never set to the minimum 7 days in production.
