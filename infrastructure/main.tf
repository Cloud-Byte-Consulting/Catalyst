# Catalyst platform root configuration.
#
# This root wires together the Terraform modules that the CI pipeline owns.
# Bootstrap-managed resources (IAM bootstrap roles/groups/OIDC, the Terraform
# state S3 bucket + DynamoDB lock table, and the Catalyst API data S3 bucket)
# are intentionally NOT modeled here. They are provisioned by
# `scripts/bootstrap-aws-account.sh` and live outside this state.
#
# Division of responsibility:
#   Bootstrap (one-time, scripts/bootstrap-aws-account.sh)
#     - IAM bootstrap admin role
#     - GitHub OIDC provider + catalyst-github-{plan,apply,deploy} roles
#     - Global RBAC IAM groups (catalyst-owners, ...)
#     - S3 bucket for Terraform remote state
#     - DynamoDB lock table for Terraform
#     - S3 bucket for Catalyst API data
#   Terraform pipeline (this stack, tf-plan / tf-apply / tf-drift)
#     - VPC, subnets, route tables, NAT, gateway endpoints
#     - Security groups + ALB ingress allowlist
#     - ECR repository
#     - ECS cluster + ALB + target group
#     - Lambda runtime (image-based)
#     - DynamoDB platform-state table
#     - Optional AWS Network Firewall (off by default)

provider "aws" {
  region = var.aws_region
}

module "network" {
  source               = "./modules/network"
  name_prefix          = var.name_prefix
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
}

module "security_groups" {
  source                = "./modules/security-groups"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  exposure_mode         = "public-alb"
  alb_ingress_allowlist = var.alb_ingress_allowlist
}

module "ecr" {
  source = "./modules/ecr"
}

module "ecs_alb" {
  source                = "./modules/ecs-alb"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  alb_security_group_id = module.security_groups.alb_security_group_id
}

module "dynamodb" {
  source = "./modules/dynamodb"
}

module "lambda_service" {
  source                    = "./modules/lambda-service"
  name_prefix               = var.name_prefix
  image_uri                 = "${module.ecr.repository_url}:latest"
  private_subnet_ids        = module.network.private_subnet_ids
  runtime_security_group_id = module.security_groups.runtime_security_group_id
  target_group_arn          = module.ecs_alb.target_group_arn
}

module "network_firewall" {
  source      = "./modules/network-firewall"
  enabled     = var.enable_network_firewall
  name_prefix = var.name_prefix
  vpc_id      = module.network.vpc_id
  subnet_id   = module.network.public_subnet_ids[0]
}
