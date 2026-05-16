variable "name_prefix" { type = string default = "catalyst" }
variable "vpc_cidr" { type = string default = "10.50.0.0/16" }
variable "availability_zones" { type = list(string) }
variable "private_subnet_cidrs" { type = list(string) }
variable "public_subnet_cidrs" { type = list(string) }
