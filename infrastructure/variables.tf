variable "aws_region" {
  type        = string
  description = "AWS region for all Catalyst platform resources."
  default     = "us-east-1"
}

variable "name_prefix" {
  type        = string
  description = "Resource name prefix; must match the bootstrap script's CATALYST_PREFIX."
  default     = "catalyst"
}

variable "availability_zones" {
  type        = list(string)
  description = "Availability zones used for VPC subnet placement."
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "Public subnet CIDRs (one per AZ in the same order as availability_zones)."
  default     = ["10.50.0.0/24", "10.50.1.0/24"]
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "Private subnet CIDRs (one per AZ in the same order as availability_zones)."
  default     = ["10.50.10.0/24", "10.50.11.0/24"]
}

variable "vpc_cidr" {
  type        = string
  description = "Parent VPC CIDR block; must enclose all public_subnet_cidrs and private_subnet_cidrs."
  default     = "10.50.0.0/16"
}

variable "lambda_image_seeded" {
  type        = bool
  description = "Set to true once the catalyst-api `:latest` image exists in ECR (seeded by service-cd). First-apply bootstraps everything except the Lambda; flipping this true brings the Lambda online on the next apply."
  default     = false
}

variable "alb_ingress_allowlist" {
  type        = list(string)
  description = "IPv4 CIDRs (or bare addresses, normalized to /32) allowed to reach the public ALB on 443. Sourced from the CATALYST_API_INGRESS_ALLOWLIST GitHub Actions variable via the tf-plan/apply/drift workflows."
  default     = ["73.239.59.22/32"]

  validation {
    condition = (
      length(var.alb_ingress_allowlist) > 0 &&
      alltrue([
        for entry in var.alb_ingress_allowlist :
        length(trimspace(entry)) > 0 && (
          can(cidrhost(trimspace(entry), 0)) ||
          can(cidrhost(format("%s/32", trimspace(entry)), 0))
        )
      ])
    )
    error_message = "alb_ingress_allowlist must include at least one non-empty IPv4 CIDR or IPv4 address."
  }
}

variable "enable_network_firewall" {
  type        = bool
  description = "When true, provision the optional AWS Network Firewall for egress controls."
  default     = false
}
