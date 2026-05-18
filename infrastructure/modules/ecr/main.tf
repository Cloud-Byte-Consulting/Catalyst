variable "name" {
  type    = string
  default = "catalyst-api"
}

# IMMUTABLE tags satisfy tfsec aws-ecr-enforce-immutable-repository and ADR-005
# supply-chain controls: a pushed image:tag pair cannot be overwritten, so a
# rollback always refers to the exact same image digest. The `:latest` tag is
# bootstrap-seeded once by service-cd and intentionally never re-pointed.
# Encryption uses AES256 (AWS-managed key); the same CMK migration tracked
# for the DynamoDB table also covers the ECR encryption upgrade.
# tfsec:ignore:aws-ecr-repository-customer-key
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
    encryption_type = "AES256"
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
