# RBAC Scoped Group Delimiter Migration

Date: 2026-05-15  
Related issues: `#98` (TF-12), `#99` (SVC-11)

## Decision

Scoped IAM group names now use an explicit delimiter:

`catalyst-{tenant}--{project}--{role}`

Examples:
- `catalyst-cloud-byte--payments--admins`
- `catalyst-acme--billing--viewers`

## Rationale

The legacy naming scheme (`catalyst-{tenant}-{project}-{role}`) is ambiguous when
tenant and project slugs both contain hyphens. The explicit `--` delimiter makes
parsing deterministic and prevents accidental cross-scope authorization.

## Backward compatibility behavior

The API RBAC parser supports both formats during migration:

1. Preferred format: `catalyst-{tenant}--{project}--{role}`
2. Legacy fallback: `catalyst-{tenant}-{project}-{role}`

New infrastructure definitions and examples must use the delimiter format.
Legacy group names remain readable by the API for compatibility until migration
cleanup is completed.

## Migration guidance

1. Create scoped groups using the delimiter format in Terraform (`scoped_group_bindings`).
2. Move users from legacy groups to delimiter groups per tenant/project/role.
3. Remove legacy groups after access logs confirm no residual usage.
