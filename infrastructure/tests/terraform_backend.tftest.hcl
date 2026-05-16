provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "backend_module_plans" {
  command = plan

  module {
    source = "./modules/terraform-backend"
  }

  assert {
    condition     = aws_kms_key.state.enable_key_rotation == true
    error_message = "state KMS key must rotate annually"
  }

  assert {
    condition     = aws_s3_bucket_public_access_block.state.block_public_acls == true
    error_message = "state bucket must block public ACLs"
  }

  assert {
    condition     = aws_dynamodb_table.lock.hash_key == "LockID"
    error_message = "lock table hash key must be LockID per the documented backend layout"
  }
}
