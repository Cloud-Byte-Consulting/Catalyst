variable "name_prefix" { type = string default = "catalyst" }
variable "availability_zones" { type = list(string) }
variable "public_subnet_cidrs" { type = list(string) }
variable "private_subnet_cidrs" { type = list(string) }
variable "bootstrap_owner_iam_user" { type = string }
variable "enable_network_firewall" { type = bool default = false }

module "backend" { source = "../../terraform-backend" name_prefix = var.name_prefix }
module "network" {
  source               = "../../network"
  name_prefix          = var.name_prefix
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
}
module "security_groups" {
  source       = "../../security-groups"
  name_prefix  = var.name_prefix
  vpc_id       = module.network.vpc_id
  exposure_mode = "public-alb"
}
module "iam" {
  source = "../../iam"
  bootstrap_owner_iam_user = var.bootstrap_owner_iam_user
}
module "ecr" { source = "../../ecr" }
module "ecs_alb" {
  source                = "../../ecs-alb"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  alb_security_group_id = module.security_groups.alb_security_group_id
}
module "dynamodb" { source = "../../dynamodb" }
module "lambda_service" {
  source                    = "../../lambda-service"
  name_prefix               = var.name_prefix
  image_uri                 = "${module.ecr.repository_url}:latest"
  private_subnet_ids        = module.network.private_subnet_ids
  runtime_security_group_id = module.security_groups.runtime_security_group_id
  target_group_arn          = module.ecs_alb.target_group_arn
}
module "network_firewall" {
  source      = "../../network-firewall"
  enabled     = var.enable_network_firewall
  name_prefix = var.name_prefix
  vpc_id      = module.network.vpc_id
  subnet_id   = module.network.public_subnet_ids[0]
}

output "deployment_graph" {
  value = {
    backend          = module.backend.state_bucket
    network          = module.network.vpc_id
    iam_groups       = module.iam.group_names
    ecr_repo         = module.ecr.repository_url
    runtime_lambda   = module.lambda_service.function_arn
    runtime_ecs      = module.ecs_alb.cluster_arn
    dynamodb         = module.dynamodb.table_name
    alb_dns          = module.ecs_alb.alb_dns_name
    firewall_enabled = var.enable_network_firewall
  }
}
