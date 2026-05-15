variables {
  availability_zones   = ["us-west-2a", "us-west-2b"]
  public_subnet_cidrs  = ["10.50.0.0/24", "10.50.1.0/24"]
  private_subnet_cidrs = ["10.50.10.0/24", "10.50.11.0/24"]
}

provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "network_module_plans" {
  command = plan
  module {
    source = "./modules/network"
  }

  assert {
    condition     = length(aws_subnet.public) == 2
    error_message = "expected two public subnets matching availability_zones input"
  }

  assert {
    condition     = length(aws_subnet.private) == 2
    error_message = "expected two private subnets matching availability_zones input"
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 2
    error_message = "expected one NAT gateway per public subnet"
  }

  assert {
    condition     = length(aws_route_table.private) == 2
    error_message = "expected one private route table per private subnet"
  }
}
