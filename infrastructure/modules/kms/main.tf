# ---------------------------------------------------------------------------
# Catalyst customer-managed KMS keys (ADR-016).
#
# Two keys with distinct lifecycles:
#   - catalyst_data_key      (alias/catalyst/data)      — DynamoDB + Secrets Manager
#   - catalyst_artifact_key  (alias/catalyst/artifacts) — ECR + CloudWatch Logs
#
# Both use the same admin / consumer principal model: admin via the SSO
# admin role (`var.admin_role_arn`), encrypt/decrypt usage via runtime
# roles (`var.consumer_role_arns`). The split lets us rotate the hot
# data-plane key without invalidating long-lived container artifacts.
#
# Rotation is enabled on both keys; deletion window defaults to 30 days
# (var.deletion_window_in_days). See ADR-016 for the migration runbook,
# particularly the ECR-recreate caveat when flipping encryption_type.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  account_root_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
  base_tags = {
    "catalyst:tier"      = "L1"
    "catalyst:construct" = "shared/kms"
  }
}

# ---------------------------------------------------------------------------
# Shared key-policy document. Same shape for both keys; only the principal
# inputs differ via the data sources. The policy grants:
#   - Account root + admin role: full kms:* (key administrators)
#   - Consumer roles: data-plane operations (Encrypt/Decrypt/ReEncrypt/
#     GenerateDataKey/DescribeKey) so DynamoDB, Secrets Manager, ECR, and
#     CloudWatch Logs can transparently use the key on the consumer's behalf.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "key_policy" {
  statement {
    sid    = "EnableIAMUserPermissions"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [local.account_root_arn]
    }
    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid    = "AllowKeyAdministration"
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
      "kms:TagResource",
      "kms:UntagResource",
      "kms:ScheduleKeyDeletion",
      "kms:CancelKeyDeletion",
    ]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = length(var.consumer_role_arns) > 0 ? [1] : []
    content {
      sid    = "AllowRuntimeUseOfKey"
      effect = "Allow"
      principals {
        type        = "AWS"
        identifiers = var.consumer_role_arns
      }
      actions = [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey",
      ]
      resources = ["*"]
    }
  }
}

# ---------------------------------------------------------------------------
# Artifact-key policy — superset of the data-key policy that ALSO grants
# the CloudWatch Logs service principal use of the key. CloudWatch Logs
# encrypts log streams server-side and needs `kms:Encrypt*` /
# `kms:GenerateDataKey*` on the key the log group references.
# See https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/encrypt-log-data-kms.html
# ---------------------------------------------------------------------------

data "aws_region" "current" {}

data "aws_iam_policy_document" "artifact_key_policy" {
  source_policy_documents = [data.aws_iam_policy_document.key_policy.json]

  statement {
    sid    = "AllowCloudWatchLogsUseOfKey"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["logs.${data.aws_region.current.region}.amazonaws.com"]
    }
    actions = [
      "kms:Encrypt*",
      "kms:Decrypt*",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = ["*"]
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

# ---------------------------------------------------------------------------
# catalyst_data_key — DynamoDB + Secrets Manager.
#
# Hot, data-plane key. Rotation is enabled so AWS will issue a new backing
# material once per year transparently to consumers; existing ciphertext
# remains decryptable.
# ---------------------------------------------------------------------------

resource "aws_kms_key" "data" {
  description             = "Catalyst data-plane CMK (DynamoDB + Secrets Manager). ADR-016."
  deletion_window_in_days = var.deletion_window_in_days
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.key_policy.json

  tags = merge(local.base_tags, var.tags, {
    "catalyst:key-role" = "data"
    "Name"              = "catalyst-data-key"
  })
}

resource "aws_kms_alias" "data" {
  name          = "alias/catalyst/data"
  target_key_id = aws_kms_key.data.key_id
}

# ---------------------------------------------------------------------------
# catalyst_artifact_key — ECR + CloudWatch Logs.
#
# Long-lived artifact key. Same rotation policy as the data key but kept
# logically separate so compromise / rotation events on the data key never
# invalidate already-signed container images.
# ---------------------------------------------------------------------------

resource "aws_kms_key" "artifact" {
  description             = "Catalyst artifact CMK (ECR + CloudWatch Logs). ADR-016."
  deletion_window_in_days = var.deletion_window_in_days
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.artifact_key_policy.json

  tags = merge(local.base_tags, var.tags, {
    "catalyst:key-role" = "artifact"
    "Name"              = "catalyst-artifact-key"
  })
}

resource "aws_kms_alias" "artifact" {
  name          = "alias/catalyst/artifacts"
  target_key_id = aws_kms_key.artifact.key_id
}
