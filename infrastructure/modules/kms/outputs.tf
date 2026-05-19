output "data_key_arn" {
  description = "ARN of catalyst_data_key (alias/catalyst/data). Consumers: DynamoDB tables, Secrets Manager parameters."
  value       = aws_kms_key.data.arn
}

output "data_key_id" {
  description = "Key ID (UUID form) of catalyst_data_key. Use when an AWS resource accepts a key_id rather than an ARN."
  value       = aws_kms_key.data.key_id
}

output "data_key_alias" {
  description = "Alias name (alias/catalyst/data) for catalyst_data_key. Use when an AWS resource accepts an alias."
  value       = aws_kms_alias.data.name
}

output "artifact_key_arn" {
  description = "ARN of catalyst_artifact_key (alias/catalyst/artifacts). Consumers: ECR repositories, CloudWatch log groups."
  value       = aws_kms_key.artifact.arn
}

output "artifact_key_id" {
  description = "Key ID (UUID form) of catalyst_artifact_key."
  value       = aws_kms_key.artifact.key_id
}

output "artifact_key_alias" {
  description = "Alias name (alias/catalyst/artifacts) for catalyst_artifact_key."
  value       = aws_kms_alias.artifact.name
}
