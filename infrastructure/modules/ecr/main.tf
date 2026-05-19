variable "name" {
  type    = string
  default = "catalyst-api"
}

# Required CMK input per ADR-016. The repository encrypts images at rest
# with the customer-managed `catalyst_artifact_key`. NOTE: ECR's
# `encryption_type` cannot be changed in place — switching an existing
# repository from AES256 to KMS forces a recreate. See ADR-016 §Migration
# runbook for the seed-image / re-push workflow.
variable "kms_key_arn" {
  type        = string
  description = "ARN of the customer-managed KMS key (catalyst_artifact_key) encrypting ECR images at rest. Required; ADR-016 made the CMK path mandatory."

  validation {
    condition     = length(var.kms_key_arn) > 0 && can(regex("^arn:aws:kms:", var.kms_key_arn))
    error_message = "kms_key_arn must be a full KMS key ARN (arn:aws:kms:<region>:<account>:key/<uuid>)."
  }
}

# IMMUTABLE tags satisfy tfsec aws-ecr-enforce-immutable-repository and ADR-005
# supply-chain controls: a pushed image:tag pair cannot be overwritten, so a
# rollback always refers to the exact same image digest. The `:latest` tag is
# bootstrap-seeded once by service-cd and intentionally never re-pointed.
# Encryption uses the customer-managed `catalyst_artifact_key` per ADR-016.
resource "aws_ecr_repository" "this" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"
  # Required for terraform destroy to succeed when images are present.
  # Safe because destroy is only triggered intentionally (teardown workflows).
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.kms_key_arn
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire untagged images older than 14 days"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 14
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ssm_parameter" "repository_uri" {
  name  = "/catalyst/shared/ecr/catalyst-api/uri"
  type  = "String"
  value = aws_ecr_repository.this.repository_url
}

output "repository_url" {
  value = aws_ecr_repository.this.repository_url
}
