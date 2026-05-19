provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

# Fixture KMS key ARN shared by every run block. ADR-016 made the CMK
# input mandatory on the ECR module.
variables {
  kms_key_arn = "arn:aws:kms:us-west-2:123456789012:key/abcd1234-ef56-7890-abcd-ef1234567890"
}

run "scan_on_push_is_enabled_by_default" {
  command = plan

  module {
    source = "./modules/ecr"
  }

  assert {
    condition     = aws_ecr_repository.this.image_scanning_configuration[0].scan_on_push == true
    error_message = "ECR scan-on-push must be enabled to satisfy ADR-005 supply-chain controls"
  }

  assert {
    condition     = aws_ecr_repository.this.encryption_configuration[0].encryption_type == "KMS"
    error_message = "ECR module must use KMS encryption (ADR-016)."
  }

  assert {
    condition     = aws_ecr_repository.this.encryption_configuration[0].kms_key == "arn:aws:kms:us-west-2:123456789012:key/abcd1234-ef56-7890-abcd-ef1234567890"
    error_message = "ECR module must pass through the supplied kms_key_arn."
  }
}

run "lifecycle_policy_expires_untagged_images" {
  command = plan

  module {
    source = "./modules/ecr"
  }

  assert {
    condition     = aws_ecr_lifecycle_policy.this.repository == aws_ecr_repository.this.name
    error_message = "lifecycle policy must attach to the managed repository"
  }
}

run "ssm_parameter_publishes_repository_uri" {
  command = plan

  module {
    source = "./modules/ecr"
  }

  variables {
    name = "catalyst-api-test"
  }

  assert {
    condition     = aws_ssm_parameter.repository_uri.name == "/catalyst/shared/ecr/catalyst-api/uri"
    error_message = "ECR module must publish repository URI to the documented SSM path"
  }
}

run "rejects_missing_kms_key_arn" {
  command = plan

  module {
    source = "./modules/ecr"
  }

  variables {
    kms_key_arn = ""
  }

  expect_failures = [var.kms_key_arn]
}
