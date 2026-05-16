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
    condition     = var.image_uri != ""
    error_message = "lambda-service module should plan successfully"
  }
}