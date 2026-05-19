variable "name_prefix" {
  type        = string
  default     = "catalyst"
  description = "Resource name prefix; aligns with the rest of the Catalyst composite (variables.name_prefix at the root)."
}

variable "lambda_function_name" {
  type        = string
  default     = "catalyst-api"
  description = <<-EOT
    Lambda function name fed into the `AWS/Lambda` namespace's `FunctionName`
    dimension for the LambdaErrorAlarm. Matches the function name composed
    by `modules/lambda-service` as `name_prefix-api` (the SVC-9 alarm fires
    on AWS-native Errors emitted by that exact function).
  EOT
}

# Terraform identifiers cannot start with a digit, so the canonical "5xx"
# specification from issue #63 becomes `http_5xx_…` here. The alarm resource
# and the README both refer to it as the 5xxRateAlarm to keep parity with
# the Decision Log.
variable "http_5xx_rate_threshold_percent" {
  type        = number
  default     = 5
  description = "Threshold percent (0–100) for (5xx ErrorCount / RequestCount) * 100 over 5-minute periods."
}

variable "onboard_p95_threshold_ms" {
  type        = number
  default     = 600000
  description = <<-EOT
    Trip-wire threshold for the ADR-014 §"Deferred — Option B as v3" alarm.
    600,000 ms = 10 minutes. Evaluated as p95 of `Catalyst/Onboard:OnboardDuration`
    over a 30-day rolling window (period 86400s × 30 evaluation periods).
  EOT
}

variable "request_p99_threshold_ms" {
  type        = number
  default     = 30000
  description = "p99 latency threshold for `Catalyst/API:RequestDuration`. 30,000 ms = 30 s."
}

variable "retry_attempt_threshold_count" {
  type        = number
  default     = 50
  description = <<-EOT
    Sum of `Catalyst/API:RetryAttempt` per 5-minute window above which the
    AWSTransientRetryAlarm fires. Tuned to catch capacity issues that retries
    are masking — see #205 (server-side retry/backoff) for the metric source.
  EOT
}
