provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

run "iam_module_provisions_documented_groups" {
  command = plan

  module {
    source = "./modules/iam"
  }

  variables {
    bootstrap_owner_iam_user = "arn:aws:iam::123456789012:user/bootstrap"
  }

  assert {
    condition     = aws_iam_group.owners.name == "catalyst-owners"
    error_message = "owners group must be named per ADR-008"
  }

  assert {
    condition     = aws_iam_group.administrators.name == "catalyst-administrators"
    error_message = "administrators group must be named per ADR-008"
  }

  assert {
    condition     = aws_iam_group.viewers.name == "catalyst-viewers"
    error_message = "viewers group must be named per ADR-008"
  }

  assert {
    condition     = aws_iam_openid_connect_provider.github_actions.url == "https://token.actions.githubusercontent.com"
    error_message = "GitHub OIDC provider URL must match documented value"
  }

  assert {
    condition     = length(aws_iam_role.github) == 4
    error_message = "expected four GitHub OIDC roles (plan/apply/deploy/drift) per ADR-006 + CICD-11a (#130)"
  }

  assert {
    condition     = aws_iam_role.github["drift"].name == "catalyst-github-drift"
    error_message = "drift role must exist and follow catalyst-github-{role} naming"
  }
}

run "iam_module_creates_scoped_groups_with_delimiter" {
  command = plan

  module {
    source = "./modules/iam"
  }

  variables {
    bootstrap_owner_iam_user = "arn:aws:iam::123456789012:user/bootstrap"
    scoped_group_bindings = [
      { tenant = "cloud-byte", project = "payments", role = "admins" },
      { tenant = "acme", project = "billing", role = "viewers" },
    ]
  }

  assert {
    condition     = length(aws_iam_group.scoped) == 2
    error_message = "expected one scoped group per binding"
  }

  assert {
    condition     = contains([for g in aws_iam_group.scoped : g.name], "catalyst-cloud-byte--payments--admins")
    error_message = "scoped group name must use the -- delimiter (migration 2026-05-15)"
  }
}
