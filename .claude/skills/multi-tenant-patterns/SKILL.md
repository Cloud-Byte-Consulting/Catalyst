<!-- AUTO-GENERATED from skills/multi-tenant-patterns/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: multi-tenant-patterns
description: >-
  Multi-tenant SaaS patterns for Catalyst's Tenant level of the construct
  hierarchy: silo vs pool vs bridge isolation, per-tenant IAM scoping, tag-based
  authorization, schema-per-tenant vs row-level security (RLS), noisy-neighbor
  protection, tenant onboarding flows, and per-tenant cost attribution. Use when
  designing or reviewing anything that crosses the tenant boundary.
---

<!-- Vendored from: platform-catalyst/.cursor/skills/multi-tenant-patterns/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Multi-tenant patterns

## Role

You guide tenant-aware design across Catalyst's stack. The `Tenant` level of the construct hierarchy (`<tenant>/<env>/<lz>/<project>/<app>`) is the strongest isolation boundary — stronger than `LandingZone` because tenants represent distinct lines of business with potentially separate compliance regimes (e.g., pharmacy HIPAA vs payer-platform PCI). You enforce isolation, prevent cross-tenant data leaks, and design for cost-attribution-by-tenant.

## References

### Research

- *Building Multi-Tenant SaaS Architectures* (Packt) — `local/research/buildingmulti-tenantsaasarchitectures.pdf`: silo/pool/bridge models, tenant isolation strategies, onboarding automation, noisy-neighbor mitigation, per-tenant observability and cost attribution.
- *AWS for Solutions Architects* (Packt) — `local/research/awsforsolutionsarchitects.pdf`: AWS-native isolation primitives (Organizations, OUs, SCPs, account-level boundaries, resource tagging).

### Repo sources of truth

- `docs/ADR/ADR-002-construct-hierarchy.md` — five-level hierarchy and construct-address rationale
- `docs/research/platform-catalyst-agents-evaluation.md` — 16 binding decisions for the import
- `AGENTS.md` — async-first, zero-wildcard IAM (critical for tenant isolation), service-inventory and tenant-onboarding pointers

## Challenge alignment

The challenge brief lists `Tenant` operations as part of the "self-service API that provisions or configures cloud resources on behalf of development teams" example for the 30% Automation Service. Multi-tenancy is also one of the strongest signals of "real platform engineering" vs "single-team automation script" — and the brief asks for "platform-as-a-product" thinking. The team values "simple architectures conducive to long-term sustainability"; **prefer pool with strong scoping over silo unless the tenant explicitly needs an isolated account**.

## Instructions

### 1. The three isolation models

Per *Building Multi-Tenant SaaS Architectures*:

| Model | Boundary | Use when | Cost | Operational complexity |
|-------|---------|----------|------|----------------------|
| **Silo** | Separate AWS account / VPC per tenant | Compliance-isolated tenants (HIPAA + PCI together); enterprise tier; very large tenants | High (per-tenant overhead) | High (N times the infrastructure) |
| **Pool** | Shared account/cluster/DB; logical separation via IAM, RLS, tags | Most tenants on the same compliance regime; cost matters; rapid onboarding | Low | Lower per-tenant; higher cross-cutting |
| **Bridge** | Hybrid — shared for compute, siloed for data | Mixed compliance needs; cost-sensitive but data-sensitive | Medium | Medium |

**Catalyst default**: **Bridge**. Each `LandingZone` is a separate AWS account (silo for compliance perimeter), but within a landing zone, `Project` and `Application` resources are pool-style (shared cluster, shared Aurora, separated by IAM + tags + schema/RLS). Tenants that need account-level silo open an additional LandingZone.

### 2. Per-tenant IAM scoping (no wildcards)

Every tenant-scoped IAM permission uses `aws:ResourceTag` or `aws:PrincipalTag` conditions. Wildcards are never the isolation mechanism.

```hcl
# leaf module: per-tenant role
data "aws_iam_policy_document" "tenant_app_role" {
  statement {
    sid    = "ReadTenantS3"
    effect = "Allow"
    actions = ["s3:GetObject", "s3:PutObject"]
    resources = ["arn:aws:s3:::catalyst-data/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Tenant"
      values   = [var.tenant_slug]
    }
  }

  statement {
    sid    = "DynamoDBTenantPartition"
    effect = "Allow"
    actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"]
    resources = [var.app_table_arn]
    condition {
      test     = "ForAllValues:StringEquals"
      variable = "dynamodb:LeadingKeys"
      values   = ["${var.tenant_slug}#*"]
    }
  }
}
```

**Rule**: a tenant role can never grant access to another tenant's data via misconfiguration. The condition is the boundary.

### 3. DynamoDB tenant partitioning

Use **construct address as the partition key prefix**:

```
PK: <tenant>#<env>#<resource_type>#<resource_id>
e.g.: pharmacy#prod#deployment#01HQ7K3JZW...
```

This guarantees:
- Tenants only see their own items via the `dynamodb:LeadingKeys` IAM condition
- Cross-tenant scans are physically impossible without explicit policy grant
- Per-tenant query patterns stay efficient (no GSI for tenant filtering)

For Catalyst's DynamoDB tables (defined in the data-layer section of `AGENTS.md`), every PK begins with the tenant slug.

### 4. Aurora multi-tenant strategy

Three options for Aurora Serverless v2:

| Strategy | Implementation | Use when |
|----------|---------------|----------|
| **Database per tenant** | One DB per tenant, shared cluster | Compliance requires DB-level separation |
| **Schema per tenant** | Shared DB, schema-per-tenant | Most Catalyst tenants — gives strong logical separation |
| **Row-level security (RLS)** | Shared DB and schema, PostgreSQL RLS policies | High tenant count, low per-tenant data volume |

**Catalyst default**: schema-per-tenant. Each tenant gets a schema named after its slug (`pharmacy`, `clinical_care`). The `catalyst-api` task role connects via IAM auth (`rds-db:connect`) as a per-tenant database user that has `USAGE` on only its own schema.

```sql
-- Created during tenant onboarding (Terraform tenant-onboarding composite)
CREATE SCHEMA pharmacy;
CREATE USER pharmacy_app;
GRANT USAGE ON SCHEMA pharmacy TO pharmacy_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA pharmacy TO pharmacy_app;
REVOKE ALL ON SCHEMA public FROM pharmacy_app;
```

### 5. Tag-based authorization at the resource layer

Every taggable AWS resource carries:

```hcl
tags = {
  Tenant      = var.tenant_slug              # pharmacy
  Environment = var.environment              # prod
  LandingZone = var.landing_zone             # clinical
  Project     = var.project_slug             # rx-fulfillment
  Application = var.application_slug         # order-service
  Construct   = "${var.tenant}/${var.env}/..." # full address as one tag
}
```

These tags drive:
- IAM `aws:ResourceTag` conditions (least-privilege)
- Cost allocation reports (AWS Cost Explorer by `Tenant` tag)
- CloudWatch metric dimensions (per-tenant observability)
- Resource discovery (`aws resourcegroupstaggingapi` filtered by Tenant)

### 6. Noisy-neighbor mitigation

Pool models risk one tenant degrading others. Mitigations:

| Risk | Mitigation |
|------|-----------|
| **Aurora connection pool exhaustion** | Per-tenant connection limit via PostgreSQL `ALTER USER pharmacy_app CONNECTION LIMIT 50` |
| **DynamoDB hot partition** | Construct-address PK keeps partitions per-tenant; monitor `ConsumedReadCapacityUnits` dimensioned by Tenant |
| **Lambda concurrency** | Reserved concurrency per tenant-scoped function; unreserved pool capped |
| **API request rate** | Per-tenant rate limiting at API Gateway (usage plan keyed on tenant) or in catalyst-api middleware |
| **S3 request rate** | Per-prefix request distribution; prefix = construct address |
| **Bedrock token budget** | Per-tenant daily token budget tracked in DDB; exceeding triggers `budget-exhausted` modifier label |

### 7. Tenant onboarding flow

Per the `tenant-onboarding` composite module described in `AGENTS.md`:

```
1. Validate inputs (tenant slug pattern, owner email, initial environments)
2. Create tenant row in Aurora `tenants` table
3. Create Postgres schema + per-tenant DB user
4. Provision tenant-scoped IAM role
5. Configure CloudWatch log group prefix per tenant
6. Tag all created resources with Tenant=<slug>
7. Open initial GitHub Issue with type/onboarding label
8. Emit EMF metric: TenantsOnboarded with Tenant dimension
```

This is the **first end-to-end flow** an MVP must support. Skip multi-tenancy support entirely in MVP 0; add it in MVP 1 once single-tenant works.

### 8. Per-tenant observability

Every log line, metric, and trace carries the tenant dimension:

```python
logger.info(
    "deployment_created",
    tenant=address.tenant,
    construct_address=str(address),
    deployment_id=dep.id,
)

metrics.add_dimension(name="Tenant", value=address.tenant)
metrics.add_metric(name="DeploymentRequested", unit=MetricUnit.Count, value=1)
```

This enables:
- Per-tenant alarms (SLO violations by tenant)
- Per-tenant cost dashboards
- Tenant-scoped log searches in CloudWatch Logs Insights

### 9. Tenant deprovisioning

When a tenant is offboarded:

1. Disable tenant IAM role (don't delete — preserve audit trail)
2. Snapshot Aurora schema, then drop it
3. Tag-based bulk delete of S3 / DynamoDB items (`aws:ResourceTag/Tenant`)
4. Archive CloudWatch logs to S3 Glacier
5. Set `tenants.deleted_at` in Aurora (soft-delete; never hard-delete the row)

Never reuse a tenant slug after deprovisioning — IAM resource policies may have outstanding references.

### 10. MVP-first tenant design

Per the challenge brief's "iterative value delivery" value:

- **MVP 0**: single-tenant. Hardcode `tenant = "default"`. Build the automation flow end-to-end.
- **MVP 1**: add the tenant column. Multi-tenant reads + writes work. No isolation enforcement yet (still trust-based).
- **MVP 2**: add IAM tenant scoping. Cross-tenant access becomes impossible at the AWS layer.
- **MVP 3**: add schema-per-tenant for Aurora. DB-level isolation.
- **MVP 4**: add per-tenant rate limiting + noisy-neighbor protections.

Each step is a separate PR with its own ADR. Do not build all five at once.

## Output

- **Tenant-scoped IAM**: `aws_iam_policy_document` with `aws:ResourceTag/Tenant` conditions
- **DynamoDB PK design**: construct-address-prefixed partition keys
- **Schema setup**: Postgres DDL for new tenant onboarding
- **Tag map**: Terraform locals for the mandatory tenant tags
- **Onboarding checklist**: step-by-step for the `tenant-onboarding` composite
- **Migration plan**: MVP 0 → MVP 4 progression with one PR per step

## Guardrails

- **Tenancy is not a wildcard problem** — never use `Resource: "*"` "with the assumption tags will filter." The IAM condition is the boundary.
- **Tenant slug is immutable** — once assigned, never renamed. Renames break IAM policies and audit trails. Use a `display_name` for UI changes.
- **No cross-tenant queries in application code** — even with permission, the application layer must not query across tenants. The construct address is in every WHERE clause.
- **Never cache one tenant's data in a shared key** — Redis/ElastiCache keys must include tenant prefix.
- **Tenant deletion is soft** — preserve audit history; the `deleted_at` column gates visibility.
- **MVP-first** — single-tenant comes first. Don't gold-plate multi-tenancy before the automation flow works.
