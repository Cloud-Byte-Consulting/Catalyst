# ---------------------------------------------------------------------------
# wa-iac-analyzer — input variables (ADR-023 Phase 1 scaffold).
#
# All inputs are OPTIONAL with sensible defaults. The composite is a skeleton
# at Phase 1; variables are declared up-front so callers wiring the flag in
# downstream stacks can pass values without a breaking-change cycle once the
# CFN-wrap-vs-Terraform-native discovery (see README.md) lands.
# ---------------------------------------------------------------------------

variable "name_prefix" {
  description = "Resource name prefix for analyzer resources (ALB, ECS service, Cognito pool). Matches the bootstrap CATALYST_PREFIX convention."
  type        = string
  default     = "catalyst-wa-analyzer"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.name_prefix))
    error_message = "name_prefix must match ^[a-z0-9-]+$ (lowercase, digits, hyphen)."
  }
}

variable "vpc_id" {
  description = "VPC ID hosting the analyzer ECS service + ALB. Optional at scaffold stage; required once Phase 1 implementation lands."
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "Subnet IDs (>=2 AZs) for the analyzer ECS tasks. Optional at scaffold stage."
  type        = list(string)
  default     = []
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the analyzer ALB. Optional at scaffold stage."
  type        = list(string)
  default     = []
}

variable "bedrock_model_id" {
  description = "Bedrock model ID the analyzer invokes (default mirrors the upstream aws-samples default: Claude 3.5 Sonnet v2). ADR-023 §Phase 1."
  type        = string
  default     = "anthropic.claude-3-5-sonnet-20241022-v2:0"
}

variable "tags" {
  description = "Tags merged onto every analyzer resource. The composite always adds `catalyst:component = wa-iac-analyzer` on top of these."
  type        = map(string)
  default     = {}
}
