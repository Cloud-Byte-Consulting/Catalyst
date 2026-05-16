variable "vpc_id" {
  type = string
}

variable "vpc_cidr_block" {
  type        = string
  default     = "10.50.0.0/16"
  description = "CIDR block of the parent VPC; used to scope ALB SG egress to in-VPC targets only."
}

variable "name_prefix" {
  type    = string
  default = "catalyst"
}

variable "exposure_mode" {
  type    = string
  default = "private"

  validation {
    condition     = contains(["private", "public-alb"], var.exposure_mode)
    error_message = "exposure_mode must be private or public-alb."
  }
}

variable "alb_ingress_allowlist" {
  type    = list(string)
  default = ["73.239.59.22"]

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

variable "allowed_runtime_ingress_security_group_ids" {
  type    = list(string)
  default = []
}
