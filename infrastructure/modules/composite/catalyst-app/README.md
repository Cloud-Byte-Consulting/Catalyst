# `composite/catalyst-app`

L4 per-application Terraform composite per
[ADR-015](../../../../docs/ADR/ADR-015-terraform-state-partitioning.md)
§Tier responsibilities. Owned by `POST /services/onboard`
([ADR-014](../../../../docs/ADR/ADR-014-services-onboard-provisioning-mode.md)),
invoked once per application onboard. Maps cleanly onto the L4 state key
`catalyst/tenants/{tenant}/environments/{env}/apps/{app}.tfstate`.

This module is **not** `composite/catalyst-product` (which is the
platform-level L1 composite — VPC, ALB, shared runtime, etc.). The
L4 composite owns only the per-app resources listed in ADR-015 §Tier
responsibilities and reads everything else via `terraform_remote_state`
from the L2 tenant baseline.

---

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `tenant` | `string` | _(required)_ | Tenant slug. Must match `^[a-z0-9-]+$` and must not contain `--`. |
| `environment` | `string` | _(required)_ | Environment slug. Must match `^[a-z0-9-]+$`. |
| `project` | `string` | _(required)_ | Project slug. Must match `^[a-z0-9-]+$`. |
| `app` | `string` | _(required)_ | Application slug. Must match `^[a-z0-9-]+$`. |
| `state_bucket` | `string` | _(required)_ | S3 bucket holding the Terraform remote backend (used to read the upstream tenant baseline via `terraform_remote_state`). |
| `aws_region` | `string` | _(required)_ | AWS region for local resources and the upstream state lookup. |
| `service_type` | `string` | `"web-service"` | One of `web-service`, `worker`, `batch`. Drives the IAM assume-role principal and whether the ALB listener rule is created. |
| `catalog_table_name` | `string` | `"catalyst-platform-state"` | DynamoDB table receiving the per-app catalog row. |
| `alb_listener_arn` | `string` | `""` | ARN of the shared HTTPS listener; required when `service_type = "web-service"`. |
| `alb_target_group_arn` | `string` | `""` | Target group ARN the listener rule forwards to; required when `service_type = "web-service"`. |
| `log_retention_days` | `number` | `30` | CloudWatch log group retention. ADR-015 §Compliance default. |

The per-segment regex (`^[a-z0-9-]+$`) is the same alphabet that
[`services/catalyst-api/catalyst/constructs.py`](../../../../services/catalyst-api/catalyst/constructs.py)
enforces for the construct address (`CONSTRUCT_PATTERN`). Slug
validation lives in two places (here at plan time, there at request
time) and the construct-regex parity test (#172) keeps them in lockstep.

## Outputs

| Name | Description |
|---|---|
| `ecr_uri` | Repository URL of the per-app ECR repo, e.g. `{account}.dkr.ecr.{region}.amazonaws.com/{tenant}-{project}-{app}`. |
| `execution_role_arn` | ARN of the Lambda exec / ECS task role provisioned for this app. |
| `log_group_name` | CloudWatch log group name: `/aws/catalyst/{tenant}/{env}/{project}/{app}`. |
| `alb_listener_rule_arn` | ARN of the path-based listener rule; `null` for non-web-service apps. |
| `catalog_record_key` | Composite `pk\|sk` for the catalog row written to the platform-state DynamoDB table. |
| `construct_address` | Canonical construct address echoed back for downstream consumers. |

---

## State-key convention

This composite's state file lives at:

```
catalyst/tenants/${tenant}/environments/${environment}/apps/${app}.tfstate
```

The backend `key` MUST be supplied by the caller (the onboard handler)
at `terraform init` time via `-backend-config="key=…"`. The committed
Terraform's `backend "s3" {}` block carries no inline key per ADR-015
§Backend-config generation strategy.

The upstream tenant baseline state is read at
`catalyst/tenants/${tenant}/baseline.tfstate`. The module fails at plan
time if that state does not exist — surfacing the dependency on the
[`composite/tenant-onboarding`](../tenant-onboarding/) module (#168) by
contract rather than by hidden runtime error.

---

## Example caller

This is what the onboard handler (`services/catalyst-api/catalyst/onboard.py`)
writes into the Lambda's `/tmp` working directory at invocation time:

```hcl
terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 5.0" }
  }
  backend "s3" {}   # key supplied via -backend-config at init
}

provider "aws" {
  region = "us-west-2"
}

module "app" {
  source = "/opt/catalyst-app/"   # bundled into the Lambda image

  tenant       = "acme"
  environment  = "dev"
  project      = "payments"
  app          = "checkout"
  state_bucket = "catalyst-tf-state-123456789012-us-west-2"
  aws_region   = "us-west-2"
  service_type = "web-service"

  alb_listener_arn     = "arn:aws:elasticloadbalancing:…/listener/app/catalyst-alb/…/…"
  alb_target_group_arn = "arn:aws:elasticloadbalancing:…/targetgroup/catalyst-shared/…"
}

output "ecr_uri"            { value = module.app.ecr_uri }
output "execution_role_arn" { value = module.app.execution_role_arn }
output "log_group_name"     { value = module.app.log_group_name }
output "alb_rule_arn"       { value = module.app.alb_listener_rule_arn }
output "catalog_record_key" { value = module.app.catalog_record_key }
```

The onboard handler then runs:

```bash
terraform init \
  -backend-config="bucket=${CATALYST_STATE_BUCKET}" \
  -backend-config="key=catalyst/tenants/acme/environments/dev/apps/checkout.tfstate" \
  -backend-config="region=us-west-2" \
  -backend-config="dynamodb_table=${CATALYST_LOCK_TABLE}"

terraform apply -auto-approve
terraform output -json
```

The parsed outputs feed the `POST /services/onboard` 200 response.

---

## Related

- [ADR-002 — Construct hierarchy](../../../../docs/ADR/ADR-002-construct-hierarchy.md) — the four-tier shape this state mirrors
- [ADR-007 — Catalyst API golden paths](../../../../docs/ADR/ADR-007-catalyst-api-golden-paths.md) — Tier 2 onboard contract
- [ADR-009 — Catalyst API runtime strategy](../../../../docs/ADR/ADR-009-runtime-strategy.md) — Lambda vs ECS choice driving the assume-role split
- [ADR-014 — `POST /services/onboard` provisioning mode](../../../../docs/ADR/ADR-014-services-onboard-provisioning-mode.md) — synchronous Terraform-in-Lambda
- [ADR-015 — Terraform state-file partitioning](../../../../docs/ADR/ADR-015-terraform-state-partitioning.md) — L4 state-key contract
- [`composite/tenant-onboarding`](../tenant-onboarding/) — the L2 producer of the tenant baseline state this module reads
- [`composite/catalyst-product`](../catalyst-product/) — platform-level L1 composite (NOT the same shape; included for contrast)
