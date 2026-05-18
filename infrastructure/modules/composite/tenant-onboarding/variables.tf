variable "tenant" {
  description = "Tenant slug (lowercase). Becomes the segment after 'catalyst-' in all tenant-scoped IAM groups and SSM paths."
  type        = string

  validation {
    condition     = length(var.tenant) > 0 && length(regexall("--", var.tenant)) == 0
    error_message = "tenant must be non-empty and must not contain the '--' delimiter (it would collide with the catalyst-{tenant}--{role} group-naming convention)."
  }
}

variable "landing_zone_account_id" {
  description = "AWS account id (12-digit string) of the landing zone hosting this tenant. Surfaced in SSM under /catalyst/{tenant}/{env}/landing-zone-account-id for downstream consumers."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.landing_zone_account_id))
    error_message = "landing_zone_account_id must be a 12-digit AWS account id."
  }
}

variable "compliance_tier" {
  description = "Compliance posture of the tenant per ADR-010. 'standard' provisions baseline egress only; 'hipaa' or 'pci-dss' additionally apply AWS Network Firewall."
  type        = string
  default     = "standard"

  validation {
    condition     = contains(["standard", "hipaa", "pci-dss"], var.compliance_tier)
    error_message = "compliance_tier must be one of: standard, hipaa, pci-dss."
  }
}

variable "environments" {
  description = "One entry per environment (dev/qa/staging/prod/dr) under this tenant. Each entry drives a per-env VPC + SSM tree."
  type = list(object({
    name                 = string
    cidr_block           = string
    availability_zones   = list(string)
    public_subnet_cidrs  = list(string)
    private_subnet_cidrs = list(string)
  }))

  validation {
    condition     = length(var.environments) > 0
    error_message = "environments must contain at least one entry."
  }

  validation {
    condition     = length(var.environments) == length(distinct([for e in var.environments : e.name]))
    error_message = "environments must have unique names."
  }
}
