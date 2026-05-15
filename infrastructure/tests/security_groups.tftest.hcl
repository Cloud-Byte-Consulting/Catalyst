provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "private_mode_does_not_create_public_ingress" {
  command = plan

  module {
    source = "./modules/security-groups"
  }

  variables {
    vpc_id        = "vpc-01234567"
    exposure_mode = "private"
  }

  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.alb_https_public) == 0
    error_message = "private mode must not allow 0.0.0.0/0 ingress on the ALB"
  }
}

run "public_mode_creates_public_ingress" {
  command = plan

  module {
    source = "./modules/security-groups"
  }

  variables {
    vpc_id        = "vpc-01234567"
    exposure_mode = "public-alb"
  }

  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.alb_https_public) == 1
    error_message = "public-alb mode must expose 0.0.0.0/0 on 443"
  }
}

run "rejects_invalid_exposure_mode" {
  command = plan

  module {
    source = "./modules/security-groups"
  }

  variables {
    vpc_id        = "vpc-01234567"
    exposure_mode = "panopticon"
  }

  expect_failures = [
    var.exposure_mode,
  ]
}

run "data_tier_ingress_uses_provided_security_groups" {
  command = plan

  module {
    source = "./modules/security-groups"
  }

  variables {
    vpc_id                                     = "vpc-01234567"
    exposure_mode                              = "private"
    allowed_runtime_ingress_security_group_ids = ["sg-aaa", "sg-bbb"]
  }

  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.data_from_runtime) == 2
    error_message = "expected one data-tier ingress rule per allowed runtime SG"
  }
}
