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

# ---------------------------------------------------------------------------
# Security-contract inputs (issue #284, stacked on #283).
#
# These three variables encode the security choices the Phase 1 implementer
# MUST make explicitly. Defaults are deliberately "deny" / "empty" so that
# silent broadening is impossible — to enable Bedrock invoke, a model ARN
# must be passed; to allow unauthenticated reads, the operator must flip
# `allow_unauthenticated_read = true` knowing the #284 Scenario 2 gherkin
# acceptance rejects that posture for internet-facing ALBs.
# ---------------------------------------------------------------------------

variable "bedrock_model_arns" {
  description = <<-EOT
    Bedrock model ARNs that the analyzer's ECS task role may invoke (via
    `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream`). The
    least-privilege policy document in `iam.tf` scopes Bedrock access to
    EXACTLY this list — no wildcards. Default is empty, which means the
    Bedrock statement is OMITTED from the task-role policy entirely (see
    `iam.tf` §"Bedrock"). Phase 1 implementation must pass at least one
    ARN, e.g.
    `arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0`.
    Per ADR-023 §Phase 1.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for a in var.bedrock_model_arns : can(regex("^arn:aws[a-z0-9-]*:bedrock:", a))])
    error_message = "Every bedrock_model_arns entry must be a Bedrock ARN (start with arn:aws[...]:bedrock:)."
  }
}

variable "cognito_user_pool_existing_id" {
  description = <<-EOT
    Optional ID of a pre-existing Cognito user pool to FEDERATE the analyzer
    against (Catalyst SSO path). If empty, the Phase 1 implementation stands
    up a DEDICATED pool per `cognito.tf` §"User-pool shape". Federation is
    preferred when a Catalyst SSO pool exists — see README §"Security
    contract" §Federation decision.
  EOT
  type        = string
  default     = ""
}

variable "allow_unauthenticated_read" {
  description = <<-EOT
    Hard switch to permit unauthenticated GETs on read-only analyzer UI
    routes. Default `false` is the only posture accepted by #284 Scenario
    2 ("Unauthenticated UI access is blocked"). Flipping to `true` is an
    explicit operator opt-in for internal-ALB-only deployments and MUST be
    paired with an internal ALB (NOT internet-facing). ADR-008 / ADR-010.
  EOT
  type        = bool
  default     = false
}
