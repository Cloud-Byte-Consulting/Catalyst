variable "name_prefix" {
  type        = string
  default     = "catalyst"
  description = "Prefix used for parameter / secret naming"
}

variable "ssm_parameters" {
  type = map(object({
    value       = string
    type        = string
    description = string
  }))
  default     = {}
  description = "Non-secret runtime configuration written to SSM Parameter Store"
}

variable "secret_parameters" {
  type        = map(string)
  default     = {}
  description = "Secret values written to AWS Secrets Manager. Keys become secret names suffixed under the prefix."
}

resource "aws_ssm_parameter" "config" {
  for_each    = var.ssm_parameters
  name        = "/${var.name_prefix}/runtime/${each.key}"
  type        = each.value.type
  value       = each.value.value
  description = each.value.description
}

resource "aws_secretsmanager_secret" "secrets" {
  for_each    = var.secret_parameters
  name        = "${var.name_prefix}/runtime/${each.key}"
  description = "Catalyst runtime secret managed by Terraform (${each.key})"
}

resource "aws_secretsmanager_secret_version" "secrets" {
  for_each      = var.secret_parameters
  secret_id     = aws_secretsmanager_secret.secrets[each.key].id
  secret_string = each.value
}

output "ssm_parameter_arns" {
  value       = { for key, p in aws_ssm_parameter.config : key => p.arn }
  description = "ARNs of the runtime SSM parameters this module manages"
}

output "secret_arns" {
  value       = { for key, s in aws_secretsmanager_secret.secrets : key => s.arn }
  description = "ARNs of the runtime secrets this module manages"
}
