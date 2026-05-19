provider "aws" {
  region                      = "us-west-2"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

# ---------------------------------------------------------------------------
# Plan-time fixtures.
#
# The kms module fetches the current caller identity + region via data
# sources; for plan-only test runs we override them so the harness doesn't
# require live AWS credentials.
# ---------------------------------------------------------------------------

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
    arn        = "arn:aws:iam::123456789012:user/test-runner"
    user_id    = "AIDATESTUSER12345678"
  }
}

override_data {
  target = data.aws_region.current
  values = {
    region = "us-west-2"
  }
}

run "data_key_has_rotation_enabled" {
  command = plan

  module {
    source = "./modules/kms"
  }

  variables {
    admin_role_arn = "arn:aws:iam::123456789012:role/catalyst-platform-admin"
    consumer_role_arns = [
      "arn:aws:iam::123456789012:role/catalyst-runtime-lambda",
      "arn:aws:iam::123456789012:role/catalyst-runtime-ecs-task",
    ]
  }

  assert {
    condition     = aws_kms_key.data.enable_key_rotation == true
    error_message = "catalyst_data_key MUST have rotation enabled (ADR-016)."
  }

  assert {
    condition     = aws_kms_key.data.deletion_window_in_days == 30
    error_message = "catalyst_data_key default deletion window must be 30 days (ADR-016 production posture)."
  }

  assert {
    condition     = aws_kms_alias.data.name == "alias/catalyst/data"
    error_message = "catalyst_data_key alias MUST be 'alias/catalyst/data'."
  }
}

run "artifact_key_has_rotation_enabled" {
  command = plan

  module {
    source = "./modules/kms"
  }

  variables {
    admin_role_arn = "arn:aws:iam::123456789012:role/catalyst-platform-admin"
    consumer_role_arns = [
      "arn:aws:iam::123456789012:role/catalyst-runtime-lambda",
    ]
  }

  assert {
    condition     = aws_kms_key.artifact.enable_key_rotation == true
    error_message = "catalyst_artifact_key MUST have rotation enabled (ADR-016)."
  }

  assert {
    condition     = aws_kms_key.artifact.deletion_window_in_days == 30
    error_message = "catalyst_artifact_key default deletion window must be 30 days (ADR-016 production posture)."
  }

  assert {
    condition     = aws_kms_alias.artifact.name == "alias/catalyst/artifacts"
    error_message = "catalyst_artifact_key alias MUST be 'alias/catalyst/artifacts'."
  }
}

run "keys_are_distinct_resources" {
  command = plan

  module {
    source = "./modules/kms"
  }

  variables {
    admin_role_arn     = "arn:aws:iam::123456789012:role/catalyst-platform-admin"
    consumer_role_arns = []
  }

  # Catch the regression where the two keys collapse into one. Same
  # description string + same alias would silently break the two-key
  # split rationale documented in ADR-016.
  assert {
    condition     = aws_kms_key.data.description != aws_kms_key.artifact.description
    error_message = "data and artifact keys must have distinct descriptions to preserve the two-key split."
  }

  assert {
    condition     = aws_kms_alias.data.name != aws_kms_alias.artifact.name
    error_message = "data and artifact key aliases must be distinct."
  }
}

run "data_key_policy_references_admin_and_consumers" {
  command = plan

  module {
    source = "./modules/kms"
  }

  variables {
    admin_role_arn = "arn:aws:iam::123456789012:role/catalyst-platform-admin"
    consumer_role_arns = [
      "arn:aws:iam::123456789012:role/catalyst-runtime-lambda",
    ]
  }

  # The rendered policy JSON must mention the admin role and at least one
  # consumer role. We check via string contains rather than parsing JSON
  # because terraform_test does not expose a jsondecode-on-policy helper.
  assert {
    condition     = strcontains(data.aws_iam_policy_document.key_policy.json, "arn:aws:iam::123456789012:role/catalyst-platform-admin")
    error_message = "data key policy MUST grant kms:* to the admin role ARN."
  }

  assert {
    condition     = strcontains(data.aws_iam_policy_document.key_policy.json, "arn:aws:iam::123456789012:role/catalyst-runtime-lambda")
    error_message = "data key policy MUST grant data-plane actions to the supplied consumer role."
  }
}

run "artifact_key_policy_includes_cloudwatch_logs_service" {
  command = plan

  module {
    source = "./modules/kms"
  }

  variables {
    admin_role_arn     = "arn:aws:iam::123456789012:role/catalyst-platform-admin"
    consumer_role_arns = []
  }

  # The artifact-key policy is a superset of the data-key policy: it
  # additionally trusts the regional CloudWatch Logs service principal
  # so log groups using this key can encrypt streams server-side.
  assert {
    condition     = strcontains(data.aws_iam_policy_document.artifact_key_policy.json, "logs.us-west-2.amazonaws.com")
    error_message = "artifact key policy MUST grant the regional CloudWatch Logs service principal use of the key."
  }
}

run "rejects_malformed_admin_arn" {
  command = plan

  module {
    source = "./modules/kms"
  }

  variables {
    admin_role_arn     = "not-an-arn"
    consumer_role_arns = []
  }

  expect_failures = [var.admin_role_arn]
}

run "rejects_out_of_range_deletion_window" {
  command = plan

  module {
    source = "./modules/kms"
  }

  variables {
    admin_role_arn          = "arn:aws:iam::123456789012:role/catalyst-platform-admin"
    consumer_role_arns      = []
    deletion_window_in_days = 6
  }

  expect_failures = [var.deletion_window_in_days]
}
