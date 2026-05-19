variable "repository_owner" {
  type        = string
  description = "GitHub owner (org) — also used as the `owner` for the `github` provider config."
  default     = "Cloud-Byte-Consulting"
}

variable "repository_name" {
  type        = string
  description = "GitHub repository name."
  default     = "Catalyst"
}

variable "protected_branch" {
  type        = string
  description = "Branch pattern to protect."
  default     = "release"
}
