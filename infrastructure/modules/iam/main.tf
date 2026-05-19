variable "bootstrap_owner_iam_user" {
  type        = string
  description = "IAM user added to catalyst-owners during bootstrap (ADR-008)"
}

variable "scoped_group_bindings" {
  type = list(object({
    tenant  = string
    project = string
    role    = string
  }))
  default     = []
  description = "Scoped RBAC groups using catalyst-{tenant}--{project}--{role}"
}

variable "github_repository" {
  type        = string
  default     = "Cloud-Byte-Consulting/Catalyst"
  description = "GitHub repository allowed to assume the OIDC roles"
}

resource "aws_iam_group" "owners" {
  name = "catalyst-owners"
}

resource "aws_iam_group" "administrators" {
  name = "catalyst-administrators"
}

resource "aws_iam_group" "viewers" {
  name = "catalyst-viewers"
}

resource "aws_iam_group" "support_admins" {
  name = "catalyst-support-admins"
}

resource "aws_iam_group" "support_viewers" {
  name = "catalyst-support-viewers"
}

resource "aws_iam_group" "breakglass" {
  name = "catalyst-breakglass"
}

resource "aws_iam_policy" "owner_policy" {
  name = "CatalystOwnerPolicy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "IamGroupManagement"
      Effect = "Allow"
      Action = [
        "iam:AddUserToGroup",
        "iam:RemoveUserFromGroup",
        "iam:GetGroup",
        "iam:ListGroupsForUser",
      ]
      Resource = [
        aws_iam_group.owners.arn,
        aws_iam_group.administrators.arn,
        aws_iam_group.viewers.arn,
        aws_iam_group.support_admins.arn,
        aws_iam_group.support_viewers.arn,
        aws_iam_group.breakglass.arn,
      ]
    }]
  })
}

resource "aws_iam_group_policy_attachment" "owner_attachment" {
  group      = aws_iam_group.owners.name
  policy_arn = aws_iam_policy.owner_policy.arn
}

resource "aws_iam_user_group_membership" "bootstrap_owner" {
  user   = var.bootstrap_owner_iam_user
  groups = [aws_iam_group.owners.name]
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "22ff89586561fc2d52f77491e9f1eff1b80be33e",
  ]
}

locals {
  role_subjects = {
    plan   = "repo:${var.github_repository}:pull_request"
    apply  = "repo:${var.github_repository}:ref:refs/heads/release"
    deploy = "repo:${var.github_repository}:ref:refs/heads/release"
    # CICD-11a (#130): drift role for scheduled tf-drift.yml runs. Uses the
    # same ref-pinned sub as apply/deploy. Security hardening (env-scoped
    # sub + job_workflow_ref) is tracked in #124 (CICD-11b).
    drift = "repo:${var.github_repository}:ref:refs/heads/release"
  }

  scoped_group_map = {
    for binding in var.scoped_group_bindings :
    "${binding.tenant}--${binding.project}--${binding.role}" => binding
  }
}

data "aws_iam_policy_document" "github_assume_role" {
  for_each = local.role_subjects

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [each.value]
    }
  }
}

resource "aws_iam_role" "github" {
  for_each           = local.role_subjects
  name               = "catalyst-github-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.github_assume_role[each.key].json
}

resource "aws_iam_group" "scoped" {
  for_each = local.scoped_group_map
  name     = "catalyst-${each.value.tenant}--${each.value.project}--${each.value.role}"
}

output "group_names" {
  value = [
    aws_iam_group.owners.name,
    aws_iam_group.administrators.name,
    aws_iam_group.viewers.name,
    aws_iam_group.support_admins.name,
    aws_iam_group.support_viewers.name,
    aws_iam_group.breakglass.name,
  ]
}

output "scoped_group_names" {
  value       = [for g in aws_iam_group.scoped : g.name]
  description = "Scoped groups in catalyst-{tenant}--{project}--{role} format"
}

output "github_role_arns" {
  value = { for key, role in aws_iam_role.github : key => role.arn }
}

output "oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github_actions.arn
}
