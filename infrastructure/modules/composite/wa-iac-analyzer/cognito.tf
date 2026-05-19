# ---------------------------------------------------------------------------
# wa-iac-analyzer — COGNITO/RBAC CONTRACT (issue #284, stacked on #283).
#
# This file declares the *shape* of the Cognito identity layer the Phase 1
# implementation will stand up, but creates NO `aws_cognito_user_pool` or
# `aws_cognito_user_pool_client` resources yet. Only `locals` and inline
# documentation — zero billable resources, zero plan output on default vars.
#
# Why "shape-only" and not the user pool yet:
#   - The implementer must first make the federation decision (federate to
#     an existing Catalyst SSO pool vs stand up a dedicated pool — see
#     README §"Security contract"). Standing up a pool here would prejudge
#     that call.
#   - Group names, attribute schema, and MFA posture, however, are fixed by
#     ADR-008 and can be codified now. Doing so locks the API-permission
#     mapping ahead of implementation so the reviewer can challenge the
#     RBAC model without the noise of pool-resource plumbing.
#
# Reviewer focus: do the group names align with ADR-008's `catalyst-{role}`
# convention? Is the attribute set minimal (no PII bloat)? Is MFA required?
# Is unauthenticated access truly off by default?
# ---------------------------------------------------------------------------

locals {
  # -------------------------------------------------------------------------
  # Group convention — matches ADR-008 `catalyst-{tenant?}-{role}` shape.
  #
  # The analyzer is a platform-level tool (not tenant-scoped), so we drop
  # the tenant segment and use the 2-segment global form:
  #   catalyst-wa-analyzer-readers   → read analysis results only
  #   catalyst-wa-analyzer-admins    → run new analyses + manage stored runs
  #
  # API permission mapping (enforced at the analyzer's ALB → ECS layer once
  # Phase 1 implementation lands; documented here as the binding contract):
  #
  #   Group                            | UI routes                       | API actions
  #   ---------------------------------|---------------------------------|------------------------------
  #   catalyst-wa-analyzer-readers     | GET /analyses, GET /analyses/:id| read-only
  #   catalyst-wa-analyzer-admins      | all reader routes + POST /analyses, DELETE /analyses/:id | read + write
  #   (no group)                       | 401/403 (per #284 Scenario 2)   | none
  # -------------------------------------------------------------------------
  cognito_groups = {
    readers = "${var.name_prefix}-readers"
    admins  = "${var.name_prefix}-admins"
  }

  # -------------------------------------------------------------------------
  # User-pool shape — documented but NOT created.
  #
  # The Phase 1 implementer instantiates `aws_cognito_user_pool` with these
  # settings. Any deviation requires explicit PR-review justification.
  #
  #   mfa_configuration            = "ON"     # ADR-008: workforce MFA mandatory
  #   password_policy              = {
  #     minimum_length             = 14       # NIST 800-63B aligned
  #     require_symbols            = true
  #     require_numbers            = true
  #     require_uppercase          = true
  #     require_lowercase          = true
  #     temporary_password_validity_days = 1
  #   }
  #   account_recovery             = "verified_email"
  #   admin_create_user_only       = true     # NO self-signup — ADR-008
  #   schema (minimal):
  #     - email           (required, mutable=false after create)
  #     - given_name      (required, mutable=true)
  #     - family_name     (required, mutable=true)
  #     - custom:scope    (string, optional — for future tenant-scoping)
  #   alias_attributes             = ["email"]
  #   auto_verified_attributes     = ["email"]
  #   advanced_security_mode       = "ENFORCED"  # threat protection on
  #   deletion_protection          = "ACTIVE"
  #
  # Per #284 Scenario 2: unauthenticated UI access MUST be blocked. The ALB
  # listener rule the Phase 1 implementer wires must use
  # `authenticate-cognito` action with `OnUnauthenticatedRequest = deny`
  # (NOT `authenticate`), so anonymous requests get 401 — not a redirect
  # loop that could be bypassed.
  # -------------------------------------------------------------------------
  cognito_shape_contract = {
    mfa                            = "ON"
    advanced_security_mode         = "ENFORCED"
    admin_create_user_only         = true
    deletion_protection            = "ACTIVE"
    on_unauthenticated_alb_action  = "deny"
    federation_default             = "catalyst-sso-if-present"
    federation_fallback            = "dedicated-pool"
    unauthenticated_read_permitted = var.allow_unauthenticated_read
  }
}

# ---------------------------------------------------------------------------
# Phase 1 implementer hook.
#
# When this composite stops being a skeleton, add (in this same file or a
# `cognito_resources.tf` sibling):
#
#   resource "aws_cognito_user_pool" "analyzer" {
#     count = var.enable_wa_aws_iac_analyzer && var.cognito_user_pool_existing_id == "" ? 1 : 0
#     # ... settings per local.cognito_shape_contract ...
#   }
#
#   resource "aws_cognito_user_group" "analyzer" {
#     for_each     = var.enable_wa_aws_iac_analyzer ? local.cognito_groups : {}
#     name         = each.value
#     user_pool_id = coalesce(
#       var.cognito_user_pool_existing_id,
#       try(aws_cognito_user_pool.analyzer[0].id, null),
#     )
#   }
#
# Until then, the locals above are the binding contract.
# ---------------------------------------------------------------------------
