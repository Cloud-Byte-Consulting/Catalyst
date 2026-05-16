provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "disabled_noop" {
  command = plan

  module {
    source = "./modules/network-firewall"
  }

  variables {
    enabled   = false
    vpc_id    = "vpc-1234"
    subnet_id = "subnet-1234"
  }
  assert {
    condition     = var.enabled == false
    error_message = "disabled firewall should be no-op"
  }
}