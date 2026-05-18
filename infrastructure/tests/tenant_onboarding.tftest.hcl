provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "standard_tier" {
  command = plan

  module {
    source = "./modules/composite/tenant-onboarding"
  }

  variables {
    tenant                  = "acme"
    landing_zone_account_id = "123456789012"
    compliance_tier         = "standard"
    environments = [
      {
        name                 = "dev"
        cidr_block           = "10.20.0.0/16"
        availability_zones   = ["us-west-2a", "us-west-2b"]
        public_subnet_cidrs  = ["10.20.0.0/24", "10.20.1.0/24"]
        private_subnet_cidrs = ["10.20.10.0/24", "10.20.11.0/24"]
      },
    ]
  }

  assert {
    condition     = length(aws_ssm_parameter.landing_zone_account_id) == 1
    error_message = "expected one /landing-zone-account-id SSM parameter per environment"
  }

  assert {
    condition     = length(aws_ssm_parameter.compliance_tier) == 1
    error_message = "expected one /compliance-tier SSM parameter per environment"
  }

  assert {
    condition     = length(aws_iam_group.tenant_scoped) == 3
    error_message = "expected three tenant-scoped IAM groups (owners/administrators/viewers)"
  }

  assert {
    condition = alltrue([
      aws_iam_group.tenant_scoped["owners"].name == "catalyst-acme--owners",
      aws_iam_group.tenant_scoped["administrators"].name == "catalyst-acme--administrators",
      aws_iam_group.tenant_scoped["viewers"].name == "catalyst-acme--viewers",
    ])
    error_message = "tenant-scoped IAM groups must follow catalyst-{tenant}--{role} naming"
  }

  assert {
    condition     = output.network_firewall_enabled == false
    error_message = "standard compliance_tier must not provision Network Firewall (ADR-010)"
  }

  assert {
    condition     = length(module.network_firewall) == 0
    error_message = "standard compliance_tier must not invoke the network-firewall submodule"
  }
}

run "hipaa_tier" {
  command = plan

  module {
    source = "./modules/composite/tenant-onboarding"
  }

  variables {
    tenant                  = "acme"
    landing_zone_account_id = "123456789012"
    compliance_tier         = "hipaa"
    environments = [
      {
        name                 = "dev"
        cidr_block           = "10.20.0.0/16"
        availability_zones   = ["us-west-2a", "us-west-2b"]
        public_subnet_cidrs  = ["10.20.0.0/24", "10.20.1.0/24"]
        private_subnet_cidrs = ["10.20.10.0/24", "10.20.11.0/24"]
      },
      {
        name                 = "prod"
        cidr_block           = "10.30.0.0/16"
        availability_zones   = ["us-west-2a", "us-west-2b"]
        public_subnet_cidrs  = ["10.30.0.0/24", "10.30.1.0/24"]
        private_subnet_cidrs = ["10.30.10.0/24", "10.30.11.0/24"]
      },
    ]
  }

  assert {
    condition     = length(aws_ssm_parameter.landing_zone_account_id) == 2
    error_message = "expected one /landing-zone-account-id SSM parameter per environment"
  }

  assert {
    condition     = length(aws_iam_group.tenant_scoped) == 3
    error_message = "expected three tenant-scoped IAM groups regardless of environment count"
  }

  assert {
    condition     = output.network_firewall_enabled == true
    error_message = "hipaa compliance_tier must provision Network Firewall (ADR-010)"
  }

  assert {
    condition     = length(module.network_firewall) == 2
    error_message = "hipaa compliance_tier must invoke network-firewall once per environment"
  }
}
