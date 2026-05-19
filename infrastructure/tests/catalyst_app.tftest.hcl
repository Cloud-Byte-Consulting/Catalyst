provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

# ---------------------------------------------------------------------------
# The catalyst-app composite reads upstream tenant baseline state via the
# `terraform_remote_state` data source (ADR-015 §Cross-tier reference
# contract). For plan-only tftest runs we override that data source with
# fixture values so the test doesn't require a real S3 bucket. The shape
# below mirrors the outputs that the tenant-onboarding composite (#168)
# produces today.
# ---------------------------------------------------------------------------

override_data {
  target = data.terraform_remote_state.tenant
  values = {
    outputs = {
      iam_group_names = {
        owners         = "catalyst-acme--owners"
        administrators = "catalyst-acme--administrators"
        viewers        = "catalyst-acme--viewers"
      }
      vpc_ids                  = { dev = "vpc-fixture-dev" }
      network_firewall_enabled = false
      ssm_parameter_arns       = {}
    }
  }
}

# The embedded modules/kms instance calls aws_caller_identity and
# aws_region. Override both so plan-only test runs don't need live AWS.
override_data {
  target = module.kms.data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
    arn        = "arn:aws:iam::123456789012:user/test-runner"
    user_id    = "AIDATESTUSER12345678"
  }
}

override_data {
  target = module.kms.data.aws_region.current
  values = {
    region = "us-west-2"
  }
}

run "web_service" {
  command = plan

  module {
    source = "./modules/composite/catalyst-app"
  }

  variables {
    tenant       = "acme"
    environment  = "dev"
    project      = "p1"
    app          = "a1"
    state_bucket = "catalyst-tf-state-123456789012-us-west-2"
    aws_region   = "us-west-2"
    service_type = "web-service"

    alb_listener_arn     = "arn:aws:elasticloadbalancing:us-west-2:123456789012:listener/app/catalyst-alb/aaaaaaaaaaaaaaaa/bbbbbbbbbbbbbbbb"
    alb_target_group_arn = "arn:aws:elasticloadbalancing:us-west-2:123456789012:targetgroup/catalyst-shared/cccccccccccccccc"

    kms_admin_role_arn = "arn:aws:iam::123456789012:role/catalyst-platform-admin"
  }

  assert {
    condition     = aws_ecr_repository.app.name == "acme-p1-a1"
    error_message = "ECR repo name must follow {tenant}-{project}-{app}"
  }

  assert {
    condition     = aws_ecr_repository.app.image_tag_mutability == "IMMUTABLE"
    error_message = "ECR image_tag_mutability must be IMMUTABLE for ADR-005 supply-chain controls"
  }

  assert {
    condition     = aws_ecr_repository.app.image_scanning_configuration[0].scan_on_push == true
    error_message = "ECR scan_on_push must be true"
  }

  assert {
    condition     = aws_cloudwatch_log_group.app.name == "/aws/catalyst/acme/dev/p1/a1"
    error_message = "Log group name must follow /aws/catalyst/{tenant}/{env}/{project}/{app}"
  }

  assert {
    condition     = aws_cloudwatch_log_group.app.retention_in_days == 30
    error_message = "Default log retention must be 30 days (ADR-015 §Compliance)"
  }

  assert {
    condition     = aws_iam_role.exec.name == "acme-p1-a1-exec"
    error_message = "Web-service execution role name must end with -exec"
  }

  assert {
    condition     = length(aws_lb_listener_rule.app) == 1
    error_message = "web-service must provision exactly one ALB listener rule when alb_listener_arn is supplied"
  }

  assert {
    condition = anytrue([
      for c in aws_lb_listener_rule.app[0].condition :
      length(c.path_pattern) > 0 && contains(c.path_pattern[0].values, "/acme/dev/p1/a1/*")
    ])
    error_message = "ALB path pattern must route /tenant/env/project/app/* to the target group"
  }
}

run "worker" {
  command = plan

  module {
    source = "./modules/composite/catalyst-app"
  }

  variables {
    tenant       = "acme"
    environment  = "dev"
    project      = "p1"
    app          = "a1"
    state_bucket = "catalyst-tf-state-123456789012-us-west-2"
    aws_region   = "us-west-2"
    service_type = "worker"

    kms_admin_role_arn = "arn:aws:iam::123456789012:role/catalyst-platform-admin"
  }

  assert {
    condition     = aws_ecr_repository.app.name == "acme-p1-a1"
    error_message = "Worker shape must still provision the per-app ECR repo"
  }

  assert {
    condition     = aws_iam_role.exec.name == "acme-p1-a1-exec"
    error_message = "Worker uses the Lambda execution-role naming pattern (same as web-service)"
  }

  assert {
    condition     = length(aws_lb_listener_rule.app) == 0
    error_message = "worker must NOT provision an ALB listener rule"
  }
}
