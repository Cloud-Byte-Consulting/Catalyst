provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "public_alb_uses_allowlist_entries" {
  command = plan

  module {
    source = "./modules/security-groups"
  }

  variables {
    vpc_id                = "vpc-1234"
    exposure_mode         = "public-alb"
    alb_ingress_allowlist = ["73.239.59.22", "198.51.100.0/24"]
  }

  assert {
    condition     = var.exposure_mode == "public-alb"
    error_message = "public-alb mode should permit explicit ingress rules"
  }

  assert {
    condition     = contains(var.alb_ingress_allowlist, "73.239.59.22")
    error_message = "allowlist should accept plain IPv4 entries for /32 normalization"
  }
}

run "rejects_invalid_allowlist_entry" {
  command = plan

  module {
    source = "./modules/security-groups"
  }

  variables {
    vpc_id                = "vpc-1234"
    exposure_mode         = "public-alb"
    alb_ingress_allowlist = ["not-an-ip"]
  }

  expect_failures = [var.alb_ingress_allowlist]
}
