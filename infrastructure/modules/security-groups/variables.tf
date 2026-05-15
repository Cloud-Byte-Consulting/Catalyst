variable "vpc_id" {
  type        = string
  description = "VPC the security groups live in"
}

variable "name_prefix" {
  type        = string
  default     = "catalyst"
  description = "Prefix for security-group names"
}

variable "exposure_mode" {
  type    = string
  default = "private"

  validation {
    condition     = contains(["private", "public-alb"], var.exposure_mode)
    error_message = "exposure_mode must be private or public-alb."
  }
}

variable "allowed_runtime_ingress_security_group_ids" {
  type        = list(string)
  default     = []
  description = "SGs that may reach the data tier on 443"
}
