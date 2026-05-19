<!-- AUTO-GENERATED from skills/terraform-native-tests/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: terraform-native-tests
description: >-
  Terraform native test files (.tftest.hcl): run blocks, assert conditions,
  mock providers, plan-only vs apply tests, CI integration, and the mandatory
  assertion set (no wildcard IAM, encryption enabled, happy-path output). Use
  when adding tests for new or existing modules under infrastructure/modules/.
---

<!-- Vendored from: platform-catalyst/.cursor/skills/terraform-native-tests/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Terraform native tests

## Role

You guide the creation of `.tftest.hcl` files for Catalyst Terraform modules using the native test framework (Terraform 1.10+). You enforce the mandatory assertion set from `AGENTS.md` §6 and `AGENTS.md` (every module that touches IAM, encryption, or security must be tested).

## Instructions

### 1. Test file location

Co-located with the module, named `<module-name>.tftest.hcl`:

```
infrastructure/modules/leaf/s3-secure-bucket/
  main.tf
  variables.tf
  outputs.tf
  s3-secure-bucket.tftest.hcl   # <-- here
```

### 2. Basic test structure

```hcl
# s3-secure-bucket.tftest.hcl

variables {
  name        = "test-bucket"
  environment = "dev"
  kms_key_arn = "arn:aws:kms:us-east-1:123456789012:key/test-key-id"
  tags        = { TestRun = "true" }
}

run "creates_bucket_with_encryption" {
  command = plan  # plan-only — no real resources

  assert {
    condition     = aws_s3_bucket.this.bucket == "test-bucket"
    error_message = "Bucket name should match input"
  }

  assert {
    condition     = aws_s3_bucket_server_side_encryption_configuration.this.rule[0].apply_server_side_encryption_by_default[0].sse_algorithm == "aws:kms"
    error_message = "Bucket must use KMS encryption"
  }
}

run "denies_non_tls_access" {
  command = plan

  assert {
    condition     = can(regex("aws:SecureTransport", aws_s3_bucket_policy.this.policy))
    error_message = "Bucket policy must enforce TLS-only access"
  }
}

run "blocks_public_access" {
  command = plan

  assert {
    condition     = aws_s3_bucket_public_access_block.this.block_public_acls == true
    error_message = "Block public ACLs must be enabled"
  }

  assert {
    condition     = aws_s3_bucket_public_access_block.this.block_public_policy == true
    error_message = "Block public policy must be enabled"
  }

  assert {
    condition     = aws_s3_bucket_public_access_block.this.ignore_public_acls == true
    error_message = "Ignore public ACLs must be enabled"
  }

  assert {
    condition     = aws_s3_bucket_public_access_block.this.restrict_public_buckets == true
    error_message = "Restrict public buckets must be enabled"
  }
}

run "versioning_enabled" {
  command = plan

  assert {
    condition     = aws_s3_bucket_versioning.this.versioning_configuration[0].status == "Enabled"
    error_message = "Versioning must be enabled"
  }
}
```

### 3. Mandatory assertion set

Per `AGENTS.md` §6 and `AGENTS.md`, every module MUST assert:

| Module type | Required assertions |
|------------|-------------------|
| Any with IAM | No `"*"` in `Resource` or `Action` of rendered policy |
| Any with encryption | KMS key ARN is set, SSE algorithm is `aws:kms` |
| Any with networking | Security groups have no `0.0.0.0/0` ingress (except ALB on 443) |
| All modules | At least one happy-path output value is non-empty |

### 4. IAM wildcard assertion pattern

```hcl
# iam-role.tftest.hcl

run "no_wildcard_in_policy" {
  command = plan

  assert {
    condition     = !can(regex("\"\\*\"", data.aws_iam_policy_document.permissions.json))
    error_message = "IAM policy must not contain wildcard '*' in Resource or Action"
  }
}

run "trust_policy_matches_input" {
  command = plan

  assert {
    condition     = can(regex(var.trust_principal, aws_iam_role.this.assume_role_policy))
    error_message = "Trust policy principal must match the input trust_principal"
  }
}
```

### 5. Composite module test example

```hcl
# aurora-serverless-v2.tftest.hcl

variables {
  cluster_name    = "test-aurora"
  environment     = "dev"
  kms_key_arn     = "arn:aws:kms:us-east-1:123456789012:key/test"
  min_acu         = 0.5
  max_acu         = 4
  vpc_id          = "vpc-test"
  subnet_ids      = ["subnet-a", "subnet-b"]
  tags            = {}
}

run "iam_auth_enabled" {
  command = plan

  assert {
    condition     = aws_rds_cluster.this.iam_database_authentication_enabled == true
    error_message = "IAM database authentication must be enabled"
  }
}

run "storage_encrypted" {
  command = plan

  assert {
    condition     = aws_rds_cluster.this.storage_encrypted == true
    error_message = "Storage encryption must be enabled"
  }
}

run "deletion_protection" {
  command = plan

  assert {
    condition     = aws_rds_cluster.this.deletion_protection == true
    error_message = "Deletion protection must be enabled"
  }
}

run "acu_within_bounds" {
  command = plan

  assert {
    condition     = aws_rds_cluster.this.serverlessv2_scaling_configuration[0].min_capacity >= 0.5
    error_message = "Min ACU must be >= 0.5"
  }

  assert {
    condition     = aws_rds_cluster.this.serverlessv2_scaling_configuration[0].max_capacity <= 16
    error_message = "Max ACU must be <= 16"
  }
}
```

### 6. Mock providers (for plan-only tests)

```hcl
# At the top of the test file, override provider config
provider "aws" {
  region = "us-east-1"

  # For plan-only tests, mock responses are sufficient
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  default_tags {
    tags = {
      TestRun = "true"
    }
  }
}
```

### 7. CI integration

Tests run in the GitHub Actions PR workflow:

```yaml
- name: Terraform Test
  run: |
    cd infrastructure/modules/leaf/s3-secure-bucket
    terraform init
    terraform test
```

Per `AGENTS.md`: do not bypass `terraform test` — it is the line-stop. Fix the code, don't disable the gate.

### 8. Test naming conventions

- `run` block names use `snake_case` describing what is asserted
- Error messages are actionable: "X must be Y" not "test failed"
- Group related assertions in the same `run` block

## Output

- **New test file**: `.tftest.hcl` with variables block + run blocks covering the mandatory set
- **Assertion pattern**: specific HCL for the resource type being tested
- **CI wiring**: workflow step for running tests in the module directory

## Guardrails

- Every new module MUST have a `.tftest.hcl` before it can be merged.
- Use `command = plan` for assertion tests — no real resources needed.
- Use `command = apply` only for integration tests that verify real AWS behavior (rare, in `infrastructure/tests/`).
- Test assertions must be deterministic — no flaky conditions.
- Per *CSPM* (Nomani, Ch 5-6): policy-as-code is defense-in-depth; tests catch what tfsec/Checkov miss in module-specific logic.
