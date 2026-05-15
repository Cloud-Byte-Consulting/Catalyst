variable "name_prefix" {
  type        = string
  default     = "catalyst"
  description = "Prefix for the Lambda function and execution role"
}

variable "image_uri" {
  type        = string
  description = "ECR image URI (with tag) used as the Lambda package"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnets the Lambda runs in"
}

variable "runtime_security_group_id" {
  type        = string
  description = "Security group attached to the Lambda runtime"
}

variable "target_group_arn" {
  type        = string
  description = "ALB target group used to invoke the function"
}

variable "ssm_parameter_name" {
  type        = string
  default     = "/catalyst/shared/lambda/catalyst-api/arn"
  description = "SSM parameter that exposes the Lambda ARN for service-cd.yml"
}

resource "aws_iam_role" "lambda_execution" {
  name = "${var.name_prefix}-lambda-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_lambda_function" "api" {
  function_name = "${var.name_prefix}-api"
  role          = aws_iam_role.lambda_execution.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  timeout       = 30
  memory_size   = 1024

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.runtime_security_group_id]
  }
}

resource "aws_lambda_permission" "alb" {
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = var.target_group_arn
}

resource "aws_lb_target_group_attachment" "lambda" {
  target_group_arn = var.target_group_arn
  target_id        = aws_lambda_function.api.arn
  depends_on       = [aws_lambda_permission.alb]
}

resource "aws_ssm_parameter" "lambda_arn" {
  name  = var.ssm_parameter_name
  type  = "String"
  value = aws_lambda_function.api.arn
}

output "function_arn" {
  value = aws_lambda_function.api.arn
}

output "function_name" {
  value = aws_lambda_function.api.function_name
}

output "execution_role_arn" {
  value = aws_iam_role.lambda_execution.arn
}

output "ssm_parameter_name" {
  value = aws_ssm_parameter.lambda_arn.name
}
