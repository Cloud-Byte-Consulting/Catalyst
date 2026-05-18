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

# Locks in the cost_tier variable: today no resources are gated on it, so the
# dev and prod tiers must produce equivalent plans. Future interface-endpoint
# additions will diverge here and these cases will be updated alongside.

run "network_module_cost_tier_dev" {
  command = plan
  module {
    source = "./modules/network"
  }

  variables {
    cost_tier = "dev"
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 2
    error_message = "cost_tier=dev: NAT gateways still required for egress today"
  }

  assert {
    condition     = aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway"
    error_message = "cost_tier=dev: S3 gateway endpoint must remain provisioned (free)"
  }

  assert {
    condition     = aws_vpc_endpoint.dynamodb.vpc_endpoint_type == "Gateway"
    error_message = "cost_tier=dev: DynamoDB gateway endpoint must remain provisioned (free)"
  }
}

run "network_module_cost_tier_prod" {
  command = plan
  module {
    source = "./modules/network"
  }

  variables {
    cost_tier = "prod"
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 2
    error_message = "cost_tier=prod: NAT gateways must remain provisioned"
  }

  assert {
    condition     = aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway"
    error_message = "cost_tier=prod: S3 gateway endpoint must remain provisioned"
  }

  assert {
    condition     = aws_vpc_endpoint.dynamodb.vpc_endpoint_type == "Gateway"
    error_message = "cost_tier=prod: DynamoDB gateway endpoint must remain provisioned"
  }
}
