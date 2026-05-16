variable "vpc_id" { type = string }
variable "name_prefix" { type = string default = "catalyst" }
variable "exposure_mode" {
  type    = string
  default = "private"
  validation {
    condition     = contains(["private", "public-alb"], var.exposure_mode)
    error_message = "exposure_mode must be private or public-alb."
  }
}
variable "allowed_runtime_ingress_security_group_ids" { type = list(string) default = [] }
