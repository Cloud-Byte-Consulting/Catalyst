# ---------------------------------------------------------------------------
# wa-iac-analyzer — ADR-023 Phase 1 SKELETON composite.
#
# This module is intentionally EMPTY at Phase 1. It exists so the root stack
# can wire the `var.enable_wa_aws_iac_analyzer` feature flag without a
# breaking-change cycle when Phase 1 discovery lands.
#
# Discovery (deferred to the implementation PR, NOT this scaffold PR — see
# README.md §"Discovery: CFN-wrap vs Terraform-native"):
#
#   1. CFN-wrap: wrap the upstream aws-samples CloudFormation deploy stack
#      with `aws_cloudformation_stack`. Lowest divergence from upstream but
#      drift detection becomes opaque + the construct-address tagging
#      contract (ADR-002) cannot be enforced through Terraform.
#
#   2. Terraform-native port: re-author the ECS Fargate + ALB + Cognito +
#      DynamoDB + S3 Vectors + Bedrock IAM topology in Terraform using
#      Catalyst's existing modules/{network,security-groups,ecs-alb,kms}.
#      Higher up-front cost but inherits ADR-005/ADR-008/ADR-009 controls
#      (CMK encryption, RBAC, runtime strategy) for free.
#
# Until the decision is recorded, this module owns zero resources. The
# `count = 0` instantiation in the root stack (infrastructure/main.tf) means
# `terraform plan` on default vars produces NO analyzer resources — the
# zero-impact contract from #283 §Acceptance Criteria Scenario 1.
# ---------------------------------------------------------------------------

locals {
  # Reserved for the Phase 1 implementation PR. Surfaced as a local now so
  # the structural shape (component tag + name prefix) is fixed before the
  # CFN-wrap-vs-Terraform-native call is made.
  component_tags = merge(
    {
      "catalyst:component" = "wa-iac-analyzer"
      "catalyst:adr"       = "ADR-023"
    },
    var.tags,
  )

  # Bedrock model id is held in a local so the downstream IAM policy (Phase
  # 1 implementation) can reference it without re-reading var.bedrock_model_id
  # twice. No-op at scaffold time.
  bedrock_model_id = var.bedrock_model_id
}

# ---------------------------------------------------------------------------
# Phase 1 implementation slot.
#
# When the discovery decision is recorded in README.md, the resource graph
# below will be replaced with either:
#   - `resource "aws_cloudformation_stack" "analyzer"` (CFN-wrap path), OR
#   - the full ECS Fargate + ALB + Cognito + DynamoDB + S3 Vectors + Bedrock
#     IAM stack (Terraform-native path).
#
# For now we declare a single `null_resource` that the PHASE 1 implementer
# will REMOVE before adding real resources. It is gated `count = 0` so it
# produces no plan output even at scaffold time. Treat it as a no-op marker
# only.
#
# A `local-exec` is intentionally NOT wired — null_resource triggers are
# enough to anchor the module's structural shape without inviting an apply
# side effect.
# ---------------------------------------------------------------------------

resource "null_resource" "phase1_placeholder" {
  count = 0

  triggers = {
    component        = local.component_tags["catalyst:component"]
    bedrock_model_id = local.bedrock_model_id
    adr              = "ADR-023"
  }
}
