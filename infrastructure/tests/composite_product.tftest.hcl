provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

# ADR-016 / #228 — modules/kms calls aws_caller_identity + aws_region.
# Override both so plan-only test runs don't hit live STS.
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

run "composite_product_plans_with_firewall_off" {
  command = plan

  module {
    source = "./modules/composite/catalyst-product"
  }

  variables {
    name_prefix              = "catalyst"
    availability_zones       = ["us-west-2a", "us-west-2b"]
    public_subnet_cidrs      = ["10.50.0.0/24", "10.50.1.0/24"]
    private_subnet_cidrs     = ["10.50.10.0/24", "10.50.11.0/24"]
    bootstrap_owner_iam_user = "arn:aws:iam::123456789012:user/bootstrap"
    alb_ingress_allowlist    = ["73.239.59.22", "198.51.100.0/24"]
    enable_network_firewall  = false
  }

  assert {
    condition     = output.deployment_graph.firewall_enabled == false
    error_message = "deployment graph should reflect compliance-tier toggle"
  }
}

run "composite_product_plans_with_firewall_on" {
  command = plan

  module {
    source = "./modules/composite/catalyst-product"
  }

  variables {
    name_prefix              = "catalyst"
    availability_zones       = ["us-west-2a", "us-west-2b"]
    public_subnet_cidrs      = ["10.50.0.0/24", "10.50.1.0/24"]
    private_subnet_cidrs     = ["10.50.10.0/24", "10.50.11.0/24"]
    bootstrap_owner_iam_user = "arn:aws:iam::123456789012:user/bootstrap"
    alb_ingress_allowlist    = ["73.239.59.22", "198.51.100.0/24"]
    enable_network_firewall  = true
  }

  assert {
    condition     = output.deployment_graph.firewall_enabled == true
    error_message = "deployment graph should expose enabled firewall toggle"
  }
}
