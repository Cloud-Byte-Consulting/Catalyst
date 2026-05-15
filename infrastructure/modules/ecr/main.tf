variable "name" {
  type        = string
  default     = "catalyst-api"
  description = "ECR repository name for the Catalyst API image"
}

variable "ssm_parameter_name" {
  type        = string
  default     = "/catalyst/shared/ecr/catalyst-api/uri"
  description = "SSM parameter that exposes the repository URI to service-cd.yml"
}

resource "aws_ecr_repository" "this" {
  name                 = var.name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
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
  name  = var.ssm_parameter_name
  type  = "String"
  value = aws_ecr_repository.this.repository_url
}

output "repository_url" {
  value = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  value = aws_ecr_repository.this.arn
}

output "ssm_parameter_name" {
  value = aws_ssm_parameter.repository_uri.name
}
