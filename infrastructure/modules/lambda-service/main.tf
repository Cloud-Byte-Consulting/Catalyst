variable "name_prefix" { type = string default = "catalyst" }
variable "image_uri" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "runtime_security_group_id" { type = string }
variable "target_group_arn" { type = string }

resource "aws_iam_role" "lambda_execution" {
  name = "${var.name_prefix}-lambda-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_lambda_function" "api" {
  function_name = "${var.name_prefix}-api"
  role          = aws_iam_role.lambda_execution.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  timeout       = 30
  vpc_config { subnet_ids = var.private_subnet_ids security_group_ids = [var.runtime_security_group_id] }
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
  name  = "/catalyst/shared/lambda/catalyst-api/arn"
  type  = "String"
  value = aws_lambda_function.api.arn
}

output "function_arn" { value = aws_lambda_function.api.arn }
