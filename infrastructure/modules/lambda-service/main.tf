variable "name_prefix" {
  type    = string
  default = "catalyst"
}

variable "image_uri" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "runtime_security_group_id" {
  type = string
}

variable "target_group_arn" {
  type = string
}

variable "enabled" {
  type        = bool
  default     = true
  description = "When false the module provisions nothing; used by the root config to skip Lambda on first apply (before service-cd seeds the ECR `:latest` tag)."
}

resource "aws_iam_role" "lambda_execution" {
  count = var.enabled ? 1 : 0
  name  = "${var.name_prefix}-lambda-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  count      = var.enabled ? 1 : 0
  role       = aws_iam_role.lambda_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_lambda_function" "api" {
  count         = var.enabled ? 1 : 0
  function_name = "${var.name_prefix}-api"
  role          = aws_iam_role.lambda_execution[0].arn
  package_type  = "Image"
  image_uri     = var.image_uri
  timeout       = 30

  tracing_config {
    mode = "Active"
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.runtime_security_group_id]
  }

  # service-cd updates image_uri directly via `aws lambda update-function-code`
  # with the per-commit SHA tag (ECR is IMMUTABLE so each SHA is unique).
  # Terraform must not revert that on the next plan; the seeded `:latest`
  # value is only a bootstrap pointer.
  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_lambda_permission" "alb" {
  count         = var.enabled ? 1 : 0
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api[0].function_name
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = var.target_group_arn
}

resource "aws_lb_target_group_attachment" "lambda" {
  count            = var.enabled ? 1 : 0
  target_group_arn = var.target_group_arn
  target_id        = aws_lambda_function.api[0].arn
  depends_on       = [aws_lambda_permission.alb]
}

resource "aws_ssm_parameter" "lambda_arn" {
  count = var.enabled ? 1 : 0
  name  = "/catalyst/shared/lambda/catalyst-api/arn"
  type  = "String"
  value = aws_lambda_function.api[0].arn
}

output "function_arn" {
  value = try(aws_lambda_function.api[0].arn, null)
}

output "enabled" {
  value = var.enabled
}
