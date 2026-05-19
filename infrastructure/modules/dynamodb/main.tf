variable "name" {
  type        = string
  default     = "catalyst-platform-state"
  description = "DynamoDB table that stores Catalyst control-plane state"
}

variable "ssm_parameter_name" {
  type        = string
  default     = "/catalyst/shared/dynamodb/platform-state/table-name"
  description = "SSM parameter the runtime reads to discover the table"
}

# Optional CMK input (ADR-016). When null the table falls back to the
# AWS-owned key so the module stays backward-compatible with callers that
# have not yet wired the `modules/kms/` outputs through. The composite
# `modules/composite/catalyst-app/` always passes a non-null value.
variable "kms_key_arn" {
  type        = string
  default     = null
  description = "ARN of the customer-managed KMS key encrypting the table at rest. Null preserves the legacy AWS-owned-key behaviour (see ADR-016 §Migration runbook)."
}

# DynamoDB SSE uses the customer-managed `catalyst_data_key` when
# var.kms_key_arn is supplied (ADR-016). Callers that don't pass a key
# fall back to the AWS-owned key — tfsec:ignore guards that path
# explicitly because the composite always supplies a CMK ARN in
# production wiring.
# tfsec:ignore:aws-dynamodb-table-customer-key
resource "aws_dynamodb_table" "platform_state" {
  name         = var.name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # CMK migration per ADR-016: when var.kms_key_arn is set the table uses
  # the customer-managed `catalyst_data_key`; otherwise SSE remains on the
  # AWS-owned key for backward compatibility with callers that have not
  # yet wired the kms module.
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }
}

resource "aws_ssm_parameter" "table_name" {
  name  = var.ssm_parameter_name
  type  = "String"
  value = aws_dynamodb_table.platform_state.name
}

output "table_name" {
  value = aws_dynamodb_table.platform_state.name
}

output "table_arn" {
  value = aws_dynamodb_table.platform_state.arn
}

output "ssm_parameter_name" {
  value = aws_ssm_parameter.table_name.name
}
