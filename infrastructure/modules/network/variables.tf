variable "name_prefix" {
  type        = string
  default     = "catalyst"
  description = "Prefix for VPC, gateway, and subnet names"
}

variable "vpc_cidr" {
  type        = string
  default     = "10.50.0.0/16"
  description = "CIDR block assigned to the VPC"
}

variable "availability_zones" {
  type        = list(string)
  description = "AZs that subnet pairs are spread across"
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for private subnets, ordered by availability_zones"
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for public subnets, ordered by availability_zones"
}
