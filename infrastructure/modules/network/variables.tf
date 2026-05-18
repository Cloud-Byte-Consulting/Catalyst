variable "name_prefix" {
  type    = string
  default = "catalyst"
}

variable "vpc_cidr" {
  type    = string
  default = "10.50.0.0/16"
}

variable "availability_zones" {
  type = list(string)
}

variable "private_subnet_cidrs" {
  type = list(string)
}

variable "public_subnet_cidrs" {
  type = list(string)
}

variable "cost_tier" {
  type        = string
  default     = "dev"
  description = <<-EOT
    Cost-tier gate for optional VPC endpoints and future spend-sensitive resources.

    Allowed values:
      - "dev":   Free gateway endpoints only (S3, DynamoDB). Any future interface
                 endpoints (ECR, SSM, STS, KMS, Secrets Manager, CW Logs, Bedrock
                 Runtime, etc.) MUST be gated `count = var.cost_tier == "dev" ? 0 : 1`
                 so dev VPCs avoid the ~$7.30/mo idle charge per endpoint per AZ.
      - "prod":  Full interface-endpoint set (when added) for steady-state reliability.
      - "hipaa": Prod set plus Network Firewall (see ADR-010).

    See docs/cost-model.md for per-tier monthly idle cost expectations and the
    PR #151 orphan-VPC incident that motivated this convention.
  EOT
  validation {
    condition     = contains(["dev", "prod", "hipaa"], var.cost_tier)
    error_message = "cost_tier must be one of: dev, prod, hipaa"
  }
}
