provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "dynamodb_module_plans" {
  command = plan

  module {
    source = "./modules/dynamodb"
  }

  assert {
    condition     = aws_dynamodb_table.platform_state.billing_mode == "PAY_PER_REQUEST"
    error_message = "platform-state table must be on-demand billed"
  }

  assert {
    condition     = aws_dynamodb_table.platform_state.hash_key == "pk"
    error_message = "platform-state hash_key must be 'pk'"
  }

  assert {
    condition     = aws_dynamodb_table.platform_state.range_key == "sk"
    error_message = "platform-state range_key must be 'sk'"
  }

  assert {
    condition     = aws_dynamodb_table.platform_state.point_in_time_recovery[0].enabled == true
    error_message = "PITR must be enabled on the control-plane state table"
  }

  assert {
    condition     = aws_dynamodb_table.platform_state.ttl[0].attribute_name == "expires_at"
    error_message = "TTL attribute must match the idempotency expires_at field"
  }

  assert {
    condition     = aws_ssm_parameter.table_name.name == "/catalyst/shared/dynamodb/platform-state/table-name"
    error_message = "DynamoDB module must publish table name at the documented SSM path"
  }

  # ADR-016: when no CMK is supplied, server_side_encryption falls back
  # to the AWS-owned key (kms_key_arn is null).
  assert {
    condition     = aws_dynamodb_table.platform_state.server_side_encryption[0].enabled == true
    error_message = "DynamoDB SSE must remain enabled regardless of CMK toggle."
  }
}

run "dynamodb_with_cmk" {
  command = plan

  module {
    source = "./modules/dynamodb"
  }

  variables {
    kms_key_arn = "arn:aws:kms:us-west-2:123456789012:key/abcd1234-ef56-7890-abcd-ef1234567890"
  }

  assert {
    condition     = aws_dynamodb_table.platform_state.server_side_encryption[0].kms_key_arn == "arn:aws:kms:us-west-2:123456789012:key/abcd1234-ef56-7890-abcd-ef1234567890"
    error_message = "DynamoDB SSE must use the supplied customer-managed KMS key when var.kms_key_arn is set (ADR-016)."
  }
}
