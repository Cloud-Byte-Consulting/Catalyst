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
  vpc_cidr             = var.vpc_cidr
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
}

module "security_groups" {
  source                = "./modules/security-groups"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  vpc_cidr_block        = var.vpc_cidr
  exposure_mode         = "public-alb"
  alb_ingress_allowlist = var.alb_ingress_allowlist
}

# Customer-managed KMS keys (ADR-016 / #228). Emits two keys (data +
# artifact) used by the dynamodb table, ECR repo, and CloudWatch log
# groups. Consumer roles list is empty at root-stack time — the runtime
# roles live in the per-app composite (modules/composite/catalyst-app/)
# which embeds its own kms module instance.
module "kms" {
  source = "./modules/kms"
  # admin_role_arn is OPTIONAL. Passing var.kms_admin_role_arn through
  # directly (defaults to null) lets the module skip the
  # AllowKeyAdministration statement on accounts where no dedicated admin
  # role is configured — admin access then flows via the
  # EnableIAMUserPermissions statement + IAM delegation (per #268). Set
  # TF_VAR_kms_admin_role_arn on environments that want a key-policy-pinned
  # break-glass admin (the previous coalesce-to-bootstrap-admin default
  # was unsafe because the role may not exist; see #268).
  admin_role_arn     = var.kms_admin_role_arn
  consumer_role_arns = []
}

module "ecr" {
  source      = "./modules/ecr"
  kms_key_arn = module.kms.artifact_key_arn
}

module "ecs_alb" {
  source                = "./modules/ecs-alb"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  alb_security_group_id = module.security_groups.alb_security_group_id
}

module "dynamodb" {
  source      = "./modules/dynamodb"
  kms_key_arn = module.kms.data_key_arn
}

# module.lambda_service requires an existing ECR image tag (image_uri must
# resolve at apply time). On a fresh account the bootstrap apply runs BEFORE
# service-cd has ever pushed `:latest`, so we gate the entire module on
# `var.lambda_image_seeded`. First apply (var=false) provisions VPC + SG +
# ECR + ECS/ALB; service-cd then pushes the initial image; a follow-up apply
# with `lambda_image_seeded=true` brings the Lambda online. Once seeded the
# variable stays true and re-applies are idempotent.
module "lambda_service" {
  source                    = "./modules/lambda-service"
  enabled                   = var.lambda_image_seeded
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
