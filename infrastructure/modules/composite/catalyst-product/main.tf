variable "name_prefix" {
  type    = string
  default = "catalyst"
}

variable "availability_zones" {
  type = list(string)
}

variable "public_subnet_cidrs" {
  type = list(string)
}

variable "private_subnet_cidrs" {
  type = list(string)
}

variable "bootstrap_owner_iam_user" {
  type = string
}

variable "enable_network_firewall" {
  type    = bool
  default = false
}

variable "alb_ingress_allowlist" {
  type    = list(string)
  default = ["73.239.59.22"]
}

# ADR-016 / #228 — admin role ARN granted full kms:* on the platform CMKs.
variable "kms_admin_role_arn" {
  type        = string
  description = "ARN of the SSO admin role granted full kms:* on the platform CMKs. ADR-016."
  default     = "arn:aws:iam::000000000000:role/catalyst-bootstrap-admin"

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", var.kms_admin_role_arn))
    error_message = "kms_admin_role_arn must be a full IAM role ARN."
  }
}

module "backend" {
  source      = "../../terraform-backend"
  name_prefix = var.name_prefix
}

module "network" {
  source               = "../../network"
  name_prefix          = var.name_prefix
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
}

module "security_groups" {
  source                = "../../security-groups"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  exposure_mode         = "public-alb"
  alb_ingress_allowlist = var.alb_ingress_allowlist
}

module "iam" {
  source                   = "../../iam"
  bootstrap_owner_iam_user = var.bootstrap_owner_iam_user
}

module "kms" {
  source             = "../../kms"
  admin_role_arn     = var.kms_admin_role_arn
  consumer_role_arns = []
}

module "ecr" {
  source      = "../../ecr"
  kms_key_arn = module.kms.artifact_key_arn
}

module "ecs_alb" {
  source                = "../../ecs-alb"
  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  alb_security_group_id = module.security_groups.alb_security_group_id
}

module "dynamodb" {
  source      = "../../dynamodb"
  kms_key_arn = module.kms.data_key_arn
}

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

# SVC-9 (#63) — alarms + SNS + operator dashboard. References the metric
# namespace #60's middleware emits (`Catalyst/API`) plus existing
# `Catalyst/Onboard` and AWS-native `AWS/Lambda`. The Lambda function name
# is constructed identically by `modules/lambda-service` so we pass the
# composed value rather than read it back out (which would be null when
# the lambda is gated off on bootstrap, per `var.lambda_image_seeded`).
module "observability" {
  source               = "../../observability"
  name_prefix          = var.name_prefix
  lambda_function_name = "${var.name_prefix}-api"
  depends_on           = [module.lambda_service]
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
    alarm_topic_arn  = module.observability.sns_topic_arn
    dashboard_url    = module.observability.dashboard_url
  }
}

output "alarm_topic_arn" {
  value       = module.observability.sns_topic_arn
  description = "SNS topic ARN for Catalyst CloudWatch alarms. Operators subscribe email/PagerDuty/Slack out-of-band — see docs/onboarding/platform.md §Operator alerts."
}

output "dashboard_url" {
  value       = module.observability.dashboard_url
  description = "Direct CloudWatch console URL for the Catalyst operator dashboard."
}
