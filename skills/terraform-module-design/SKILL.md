---
name: terraform-module-design
description: >-
  Terraform module design for Catalyst: leaf vs composite module patterns,
  variable interfaces with validation, output contracts, naming conventions
  (kebab-case resources, snake_case vars), data sources over hardcoded values,
  and the module decomposition tree from AGENTS.md. Use when creating or
  modifying modules under infrastructure/modules/.
---

<!-- Vendored from: platform-catalyst/.cursor/skills/terraform-module-design/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Terraform module design

## Role

You guide the structure and interface design of Terraform modules in the Catalyst `infrastructure/modules/` tree. You enforce the leaf/composite split from `AGENTS.md` §6 and naming conventions from `AGENTS.md`.

## Instructions

### 1. Leaf vs composite modules

**Leaf modules** wrap a single AWS resource type with hardened defaults:

```
infrastructure/modules/leaf/
  kms-key/          # One CMK + alias + rotation + key policy
  s3-secure-bucket/ # One bucket + BPA + SSE-KMS + versioning + TLS policy
  dynamodb-table/   # One table + on-demand + PITR + KMS + tags
  iam-role/         # One role + inline policy via data source
  sg-base/          # One SG with named rules
  cw-log-group/     # One log group + KMS + retention
  sns-topic-encrypted/ # One topic + KMS + subscription policy
```

**Composite modules** compose multiple leaf modules and AWS resources into a functional unit:

```
infrastructure/modules/composite/
  network/                # VPC + subnets + endpoints + NAT + flow logs
  aurora-serverless-v2/   # Cluster + IAM auth + param group + secret
  ecs-fargate-service/    # Cluster + task def + service + ALB + autoscaling + logs
  lambda-python-fn/       # Function + role + log group + alias + alarms
  ...
```

**Rule**: a leaf module should have **one primary resource** and its directly coupled dependencies (e.g., a bucket + its policy + its ACL config). If you're composing 3+ leaf modules, that's a composite.

### 2. Module interface conventions

```hcl
# variables.tf — inputs
variable "name" {
  description = "Resource name (kebab-case, used in AWS identifiers)"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.name))
    error_message = "Name must be kebab-case (lowercase alphanumeric and hyphens)."
  }
}

variable "environment" {
  description = "Deployment environment (dev, stage, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "Environment must be dev, stage, or prod."
  }
}

variable "kms_key_arn" {
  description = "ARN of the KMS key for encryption at rest"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
```

```hcl
# outputs.tf — contracts
output "arn" {
  description = "ARN of the created resource"
  value       = aws_s3_bucket.this.arn
}

output "id" {
  description = "ID of the created resource"
  value       = aws_s3_bucket.this.id
}
```

### 3. Naming conventions

| What | Convention | Example |
|------|-----------|---------|
| Resource names (DNS, IAM, CW) | `kebab-case` | `catalyst-api-task-role` |
| Terraform variables | `snake_case` | `kms_key_arn` |
| Terraform locals | `snake_case` | `common_tags` |
| Module directory names | `kebab-case` | `s3-secure-bucket` |
| Resource labels in HCL | `this` for the primary resource | `aws_s3_bucket.this` |

### 4. Common tags pattern

Every module merges caller-provided tags with mandatory defaults:

```hcl
locals {
  common_tags = merge(
    {
      Project     = "catalyst"
      Environment = var.environment
      ManagedBy   = "terraform"
      Module      = basename(path.module)
    },
    var.tags,
  )
}
```

Per *Platform Engineering for Architects* Ch 8 (pp 271-275): tagging is not optional — it drives cost allocation, security scoping (`aws:ResourceTag` conditions), and observability dimensions.

### 5. Data sources over hardcoded values

```hcl
# Never hardcode account ID or region
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}
```

### 6. Module file layout

```
infrastructure/modules/leaf/s3-secure-bucket/
  main.tf           # Primary resource(s)
  variables.tf      # Input variables with validation
  outputs.tf        # Output contracts
  versions.tf       # required_providers + terraform version constraint
  s3-secure-bucket.tftest.hcl  # Native test file
  README.md         # One-paragraph description (auto-generated is fine)
```

### 7. Composite module composition

```hcl
# infrastructure/modules/composite/ecs-fargate-service/main.tf

module "log_group" {
  source      = "../../leaf/cw-log-group"
  name        = var.service_name
  environment = var.environment
  kms_key_arn = var.log_kms_key_arn
  tags        = local.common_tags
}

module "task_role" {
  source      = "../../leaf/iam-role"
  name        = "${var.service_name}-task-role"
  trust_principal = "ecs-tasks.amazonaws.com"
  policy_document = data.aws_iam_policy_document.task_permissions.json
  tags        = local.common_tags
}

module "execution_role" {
  source      = "../../leaf/iam-role"
  name        = "${var.service_name}-execution-role"
  trust_principal = "ecs-tasks.amazonaws.com"
  policy_document = data.aws_iam_policy_document.execution_permissions.json
  tags        = local.common_tags
}

# Task role != execution role — always separate (AGENTS.md §7)
```

### 8. Version constraints

```hcl
# versions.tf
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```

## Output

- **New leaf module**: `main.tf` + `variables.tf` + `outputs.tf` + `versions.tf` + `.tftest.hcl`
- **New composite module**: same layout + `module` blocks referencing leaf modules
- **Interface review**: variable validation rules + output contract

## Guardrails

- No `*.tfvars` in git — environments use per-env files, gitignored.
- No hardcoded account IDs, region names, or ARNs — data sources or inputs.
- Every variable with a constrained domain gets a `validation` block.
- Leaf modules should not call other modules — that's what composites are for.
- `terraform fmt -check` must pass — the CI gate enforces this.
