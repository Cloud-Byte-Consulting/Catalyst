provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "disabled_firewall_creates_no_resources" {
  command = plan

  module {
    source = "./modules/network-firewall"
  }

  variables {
    enabled   = false
    vpc_id    = "vpc-01234567"
    subnet_id = "subnet-01234567"
  }

  assert {
    condition     = length(aws_networkfirewall_firewall.this) == 0
    error_message = "compliance-tier toggle off must keep the module a no-op"
  }
}

run "enabled_firewall_provisions_resources" {
  command = plan

  module {
    source = "./modules/network-firewall"
  }

  variables {
    enabled   = true
    vpc_id    = "vpc-01234567"
    subnet_id = "subnet-01234567"
  }

  assert {
    condition     = length(aws_networkfirewall_firewall.this) == 1
    error_message = "enabled firewall must produce one firewall resource"
  }

  assert {
    condition     = length(aws_networkfirewall_rule_group.fqdn) == 1
    error_message = "enabled firewall must include the FQDN allow-list rule group"
  }

  assert {
    condition     = contains(one(one(aws_networkfirewall_firewall_policy.this[*].firewall_policy)).stateful_default_actions, "aws:drop_strict")
    error_message = "stateful default must be drop_strict per ADR-010"
  }
}
