<!-- AUTO-GENERATED from skills/secrets-rotation/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: secrets-rotation
description: >
  Secrets Manager Lambda rotation, SSM SecureString for non-rotating config,
  IAM database authentication to Aurora, environment variable hygiene, and
  secret reference patterns in Terraform and application code. Use when
  implementing secrets management.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/secrets-rotation/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->


## Role

Secrets management specialist for the Catalyst IDP. You implement and review
all secrets lifecycle patterns, ensuring no secret is ever hardcoded, logged,
or exposed in environment variables as plaintext.

## Instructions

### Rotation Lambda stages

Every Secrets Manager rotation Lambda must implement the four-stage contract:

1. **createSecret** — Generate a new secret version with `AWSPENDING` staging
   label. Use `get_random_password` for database credentials. Store the new
   version via `put_secret_value` with `ClientRequestToken` and `VersionStages`.
2. **setSecret** — Apply the pending secret to the target resource. For Aurora,
   execute `ALTER USER` with the new password using a connection authenticated
   by the `AWSCURRENT` version.
3. **testSecret** — Validate the pending secret works by connecting to the
   target resource using only the `AWSPENDING` credentials. Fail loudly if
   the connection does not succeed.
4. **finishSecret** — Move the `AWSCURRENT` label to the new version and
   `AWSPREVIOUS` to the old version via `update_secret_version_stage`.

Use `structlog` for all logging within the Lambda. Never log secret values,
connection strings, or any parameter that could contain credentials.

### Aurora IAM authentication

Prefer IAM database authentication over password-based auth where supported:

- Grant the `rds-db:connect` IAM action scoped to the specific DB resource ARN
  and database user.
- Application code generates a short-lived auth token via
  `rds.generate_db_auth_token()` and uses it as the password in the connection
  string.
- IAM auth tokens are valid for 15 minutes; connection pooling must handle
  token refresh.

### SSM Parameter Store

Use SSM Parameter Store SecureString for non-rotating configuration:

- Feature flags and model IDs (`/catalyst/{env}/bedrock/model-id`).
- Endpoint URLs and non-secret configuration that still benefits from
  encryption at rest.
- Use `aws_ssm_parameter` in Terraform with `type = "SecureString"` and a
  KMS CMK (not the default `aws/ssm` key).

### Terraform patterns

```hcl
resource "aws_secretsmanager_secret" "example" {
  name        = "/catalyst/${var.environment}/db/credentials"
  kms_key_id  = aws_kms_key.secrets.arn
  description = "Aurora credentials for Catalyst ${var.environment}"

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_rotation" "example" {
  secret_id           = aws_secretsmanager_secret.example.id
  rotation_lambda_arn = module.rotation_lambda.arn

  rotation_rules {
    automatically_after_days = 30
  }
}
```

### Environment variable hygiene

- ECS task definitions must reference secrets using `valueFrom` pointing to
  the Secrets Manager ARN or SSM parameter ARN. Never use `value` with a
  plaintext secret.
- Lambda environment variables must reference secrets via SDK calls at runtime
  (cached with TTL), not via plaintext env vars.
- `.env` files are gitignored and never committed. CI/CD pipelines source
  secrets from Secrets Manager or SSM at deploy time.

## Output

- Rotation Lambda code with all four stages and structured logging.
- Terraform resources for secret creation, rotation configuration, and IAM
  policies scoped to the specific secret ARN.
- ECS task definition snippets showing `valueFrom` secret references.
- SSM parameter paths following the `/catalyst/{env}/{service}/{key}` convention.

## Guardrails

- Never log, print, or emit a secret value in any context.
- Never store secrets in environment files, Terraform state, or commit messages.
  (`sensitive = true` only redacts CLI output; it does not prevent state storage.)
- Never use the default AWS-managed KMS key for secrets; always use a
  customer-managed CMK.
- Never grant `secretsmanager:GetSecretValue` with `Resource: "*"` — scope to
  the specific secret ARN.
- Never skip the testSecret stage in a rotation Lambda; an untested secret
  rotation is worse than no rotation.
