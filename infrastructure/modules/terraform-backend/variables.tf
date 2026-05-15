variable "name_prefix" {
  type        = string
  default     = "catalyst"
  description = "Prefix for backend resources"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Optional tags applied to backend resources"
}
