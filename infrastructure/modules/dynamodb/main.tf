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

# DynamoDB SSE uses the AWS-owned KMS key today. Migrating to a customer-
# managed CMK is tracked separately (KMS rollout coordinates with the future
# `modules/kms/` referenced in ADR-006 §"Resources..."). Until the CMK exists
# the AWS-owned key satisfies our encryption-at-rest requirement.
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

  # AWS-owned KMS key is sufficient for the platform-state table at this stage;
  # ADR-008 lays out the CMK migration once the platform graduates from MVP.
  server_side_encryption {
    enabled = true
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
