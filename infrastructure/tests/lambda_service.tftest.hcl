provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "lambda_image_package" {
  command = plan

  module {
    source = "./modules/lambda-service"
  }

  variables {
    image_uri                 = "123456789012.dkr.ecr.us-west-2.amazonaws.com/catalyst-api:latest"
    private_subnet_ids        = ["subnet-a", "subnet-b"]
    runtime_security_group_id = "sg-1234"
    target_group_arn          = "arn:aws:elasticloadbalancing:us-west-2:123456789012:targetgroup/tg/abcd"
  }

  assert {
    condition     = aws_lambda_function.api.package_type == "Image"
    error_message = "Lambda must use container-image packaging per ADR-009"
  }

  assert {
    condition     = aws_lambda_permission.alb.principal == "elasticloadbalancing.amazonaws.com"
    error_message = "Lambda must allow ALB invocation per ADR-009"
  }

  assert {
    condition     = aws_ssm_parameter.lambda_arn.name == "/catalyst/shared/lambda/catalyst-api/arn"
    error_message = "Lambda ARN must publish to documented SSM path for service-cd.yml"
  }
}
