# ---------------------------------------------------------------------------
# Inputs for the Catalyst CMK module (ADR-016).
#
# The module emits two keys (data + artifact) sharing the same admin /
# consumer principal model; the inputs are flat rather than nested because
# every Catalyst tenant uses the same SSO admin role and the same Lambda /
# ECS task role set across both keys.
# ---------------------------------------------------------------------------

variable "admin_role_arn" {
  description = "Optional ARN of an SSO admin / break-glass IAM role granted full `kms:*` via a key-policy statement. When null or empty, the AllowKeyAdministration statement is OMITTED — admin access then flows exclusively through the EnableIAMUserPermissions statement (account root + IAM-policy-delegated grants, e.g. PowerUserAccess on the apply role). Setting an explicit value pins a key-policy admin in addition. Per #268: the null/empty path is the safe default for fresh accounts where no dedicated admin role exists yet."
  type        = string
  default     = null

  validation {
    condition     = var.admin_role_arn == null || var.admin_role_arn == "" || can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", var.admin_role_arn))
    error_message = "admin_role_arn must be null, empty, OR a full IAM role ARN (arn:aws:iam::<account>:role/<name>)."
  }
}

variable "consumer_role_arns" {
  description = "ARNs of the runtime roles (Lambda exec, ECS task) that need Encrypt/Decrypt/GenerateDataKey on both keys. Empty list is allowed at bootstrap when no runtime exists yet."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for arn in var.consumer_role_arns : can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", arn))
    ])
    error_message = "every consumer_role_arns entry must be a full IAM role ARN."
  }
}

variable "deletion_window_in_days" {
  description = "Days before a scheduled key deletion actually destroys the key material. Defaults to 30 (AWS max-safety recommendation for production data keys); the terraform-backend state key uses 7 deliberately for a tighter blast radius on backend rotation."
  type        = number
  default     = 30

  validation {
    condition     = var.deletion_window_in_days >= 7 && var.deletion_window_in_days <= 30
    error_message = "deletion_window_in_days must be between 7 and 30 inclusive (AWS-imposed range)."
  }
}

variable "tags" {
  description = "Free-form tag map applied to both keys. The module always adds `catalyst:tier = L1` and a per-key `catalyst:key-role` tag on top of this."
  type        = map(string)
  default     = {}
}
