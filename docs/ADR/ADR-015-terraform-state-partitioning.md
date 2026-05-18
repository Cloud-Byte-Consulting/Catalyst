# ADR-015 — Terraform state-file partitioning across the construct hierarchy

**Status**: Accepted · 2026-05-18
**Related**: [ADR-002](ADR-002-construct-hierarchy.md) · [ADR-006](ADR-006-cicd-pipeline-architecture.md) · [ADR-008](ADR-008-catalyst-api-rbac.md) · [ADR-010](ADR-010-egress-control.md) · [ADR-014](ADR-014-services-onboard-provisioning-mode.md)

---

## Context

`infrastructure/backend.tf` defines a single state-file key (`catalyst/platform.tfstate`) that covers every resource Catalyst manages — bootstrap, Catalyst API runtime, every tenant onboard, every per-app deployment. The S3 bucket and DynamoDB lock table are bootstrap-managed singletons. This works for the single-account demo and does not work for multi-tenant production:

- **Lock contention.** One DynamoDB lock serialises every apply. Tenant A's onboard blocks tenant B's drift run.
- **Blast radius.** A corrupted state file affects every resource in the platform. Recovery cost is platform-wide regardless of which resource caused the corruption.
- **No ABAC anchor.** Per-tenant IAM policies have nowhere to land on the S3 key — every operator with state-write IAM can touch every tenant's resources.
- **Drift scan cost.** `terraform plan` reads the whole state on every run; cost scales with total platform tenancy, not per-tenant volume.
- **Apply duration.** Linear in resource count regardless of which subset is changing.

[ADR-014](ADR-014-services-onboard-provisioning-mode.md) commits v2 of `POST /services/onboard` to synchronous `terraform apply` inside the Lambda. Under a single-state model, every onboard locks the entire platform — Option A becomes untenable at the second concurrent tenant. Per-tier state partitioning is a prerequisite for ADR-014's choice to remain viable.

---

## Decision

**Partition the Terraform state into four tiers aligned with the [ADR-002](ADR-002-construct-hierarchy.md) construct hierarchy.** All tiers share the existing S3 bucket and DynamoDB lock table; the partition is by S3 key, not by additional infrastructure.

### State-key convention

```
catalyst/platform.tfstate                                              (L1 — bootstrap)
catalyst/tenants/{tenant}/baseline.tfstate                             (L2 — tenant baseline)
catalyst/tenants/{tenant}/environments/{env}/network.tfstate           (L3 — environment, split case only)
catalyst/tenants/{tenant}/environments/{env}/apps/{app}.tfstate        (L4 — application)
```

Slugs MUST be lowercase, hyphen-separated, no path-traversal characters. The construct-address regex from [`services/catalyst-api/catalyst/constructs.py`](../../services/catalyst-api/catalyst/constructs.py) (`CONSTRUCT_PATTERN`) is the canonical validator; the parity test at [`services/catalyst-api/tests/test_construct_pattern_parity.py`](../../services/catalyst-api/tests/test_construct_pattern_parity.py) keeps the client and server in lockstep.

### Tier responsibilities

| Tier | Key | Owns | Provisioned by | Lock blast radius |
|---|---|---|---|---|
| **L1 — Platform** | `catalyst/platform.tfstate` | Bootstrap singletons: GitHub OIDC roles, the state-bucket + lock-table themselves, Catalyst API ECR + Lambda + ALB, cross-tenant catalog DynamoDB | Bootstrap script + `infrastructure/backend.tf` (the existing root, unchanged by this ADR) | Platform-wide; rare changes |
| **L2 — Tenant baseline** | `…/tenants/{tenant}/baseline.tfstate` | SSM parameter tree, tenant-scoped IAM groups, tenant-wide policy attachments | The `tenant-onboarding` composite (#168) invoked per tenant | One tenant |
| **L3 — Environment** | `…/tenants/{tenant}/environments/{env}/network.tfstate` | Per-env VPC, subnets, NAT, optional Network Firewall | The same composite, called per environment **when split** (see rule below) | One tenant/env |
| **L4 — Application** | `…/tenants/{tenant}/environments/{env}/apps/{app}.tfstate` | ECR repo, exec role, log group, ALB rule, app catalog row | #167's onboard handler at apply time | One application |

### Environment split rule (L3)

L3 is **conditionally split** from L2, controlled by the tenant's compliance tier (mirroring the `cost_tier` pattern from #170):

| `compliance_tier` | L3 disposition | State key emitted |
|---|---|---|
| `standard` | **Rolled into L2** — single tenant baseline state holds all environments | (no separate L3 key) |
| `hipaa` | **Split** — one L3 state per environment | `…/tenants/{tenant}/environments/{env}/network.tfstate` |
| `pci-dss` | **Split** — same as hipaa | same as above |

Rationale: regulated tiers require demonstrable per-environment isolation for audit. The demo and standard-tier tenants don't pay the plumbing cost for isolation they don't need. L2 already serialises within a tenant; rolling L3 in keeps the standard-tier shape simple.

The composite module from #168 exposes a `split_environment_states` boolean output (derived from its `compliance_tier` variable) and honours the rule internally; callers do not duplicate the decision.

### Backend-config generation strategy

**Backend configuration is generated by the caller at apply time, not committed to the repo.** Each tier's Terraform root carries only the backend type declaration:

```hcl
terraform {
  backend "s3" {}   # bucket, key, region, lock table supplied via -backend-config
}
```

The caller — `tf-plan`/`tf-apply` GitHub Actions for L1/L2/L3, the onboard Lambda for L4 — emits the per-call backend config:

```bash
terraform init \
  -backend-config="bucket=${CATALYST_STATE_BUCKET}" \
  -backend-config="key=catalyst/tenants/${TENANT}/environments/${ENV}/apps/${APP}.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="dynamodb_table=${CATALYST_LOCK_TABLE}"
```

This keeps the committed Terraform tier-agnostic and lets the API mint new L4 state keys without a commit. The CI pipelines and the onboard Lambda are the only producers of backend-config strings; they reference these tier templates rather than hard-coding keys.

### Cross-tier reference contract

Tiers MUST reference upstream outputs via `terraform_remote_state`, never via hard-coded ARNs or implicit data lookups:

```hcl
data "terraform_remote_state" "tenant" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = "catalyst/tenants/${var.tenant}/baseline.tfstate"
    region = var.aws_region
  }
}
```

Reference direction MUST be **strictly upward** (L4 reads L3 reads L2 reads L1). Cross-tenant references are forbidden — a tenant's state MUST NOT read another tenant's state. Cross-environment references within a tenant are allowed only when L3 is rolled into L2 (i.e. standard tier).

Each tier MUST publish a stable output contract documented in its `outputs.tf`. Breaking changes to that contract are major-version events for callers and require coordinated PRs across consumers.

---

## Consequences

### Positive

- **Parallel onboards.** Per-app state means tenant A's onboard does not lock tenant B's onboard or any other app's drift.
- **Bounded blast radius.** A corrupt L4 state recovers one application. A corrupt L2 recovers one tenant. L1 is the only platform-wide recovery surface, and it changes rarely.
- **ABAC-ready.** Per-tier S3 key prefixes are the anchor for tenant-scoped IAM policies (`s3:GetObject` on `arn:…:catalyst/tenants/${aws:PrincipalTag/Tenant}/*`). Wires directly into [ADR-008](ADR-008-catalyst-api-rbac.md)'s scoped-group model.
- **Faster drift detection.** Per-tier drift runs in parallel; each scans a small state.
- **ADR-014 stays viable.** Sync `terraform apply` in the onboard Lambda touches only the L4 state, not the platform. The 15-min Lambda cap and 2–5 min p50 estimate remain valid as tenancy grows.

### Negative / trade-offs

- **More `terraform_remote_state` plumbing.** Every L3/L4 module that needs L2 outputs adds a data block. Mitigated by helper modules and clear `outputs.tf` contracts.
- **More IAM policy surface.** Per-tier `s3:*` policies replace one platform-wide policy. Generated from a template, not hand-maintained.
- **Cross-tier breakage discoverable only at plan time.** Renaming an output in L2 doesn't break the L2 apply; it breaks the next L3/L4 plan that reads it. Required mitigation: an `outputs.tf` contract test in CI that lints for removed fields.
- **Backup surface grows.** S3 versioning is per-key; per-tenant compliance posture for backups (e.g. cross-region replication for HIPAA tenants) now applies per-key, not platform-wide. Treat as a feature, not a cost.
- **Migration from the current monolithic state.** Existing single-state-file resources must be `terraform state mv`'d into their new homes in a dedicated migration PR. Captured as a deferred follow-up.

### Deferred

- **Cross-account state federation.** When tenants vend into separate landing-zone accounts, L2+ states may live in the LZ account's own state bucket. Pattern: L1 stays in the platform account; L2-L4 federate. Orthogonal to this ADR; opens once multi-account vending lands.
- **State-file backup and disaster-recovery runbook.** Per-tier RPO/RTO targets — separate operational concern, filed when the first tenant cuts over.
- **Migration from the existing monolithic state.** A separate PR (post-ADR) using `terraform state mv` to relocate existing resources into the new key hierarchy. The current `catalyst/platform.tfstate` continues to apply until that migration lands.

---

## Compliance

- L4 backend keys MUST be generated by the caller at apply time; the committed Terraform MUST NOT hardcode a tenant/env/app slug in `backend.tf`.
- All `terraform_remote_state` references MUST flow upward (L4→L3→L2→L1). Lateral or downward references are a CI lint failure.
- Each tier's `outputs.tf` MUST be treated as a public contract; removing or renaming an output requires a paired update of every downstream consumer in the same PR.
- L2 IAM policies on the state bucket MUST scope `s3:*` to `catalyst/tenants/${aws:PrincipalTag/Tenant}/*` for tenant-scoped principals (per [ADR-008](ADR-008-catalyst-api-rbac.md) tenant-scoped groups).
- The onboard Lambda's apply step MUST emit the backend key as a structured log field (`state_key=…`) on entry, alongside `correlation_id` (per [ADR-014](ADR-014-services-onboard-provisioning-mode.md)'s compliance bullets).

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| **Keep monolithic state** | Locks the platform on every onboard. Incompatible with [ADR-014](ADR-014-services-onboard-provisioning-mode.md) Option A at >1 tenant. |
| **Per-tenant Terraform root directories committed to the repo** | Tenancy is dynamic; committing per-tenant roots means a PR per tenant to onboard. Doesn't fit the [ADR-007](ADR-007-catalyst-api-golden-paths.md) self-serve Tier 1 contract. |
| **Terragrunt with dynamic backend generation** | Adds a runtime tool the team doesn't currently use; the dynamic backend-config approach achieves the same result with stock Terraform. |
| **One state file per AZ or per region** | Solves a different problem (regional blast radius) but doesn't address per-tenant isolation, which is the dominant concern. |
| **Split L3 unconditionally** | Pays the plumbing cost on every tenant, including standard-tier and demo tenants that don't need per-env isolation. Conditional split honours the cost/complexity gradient already established by `cost_tier` (#170) and `compliance_tier` ([ADR-010](ADR-010-egress-control.md)). |
| **Workspaces (`terraform workspace`)** | Workspaces share state schema and provider config; they're a single-resource-graph trick, not an isolation primitive. Per-tenant blast radius and ABAC scoping still require separate keys. |

---

## References

- [ADR-002 — Construct hierarchy](ADR-002-construct-hierarchy.md) — the shape this state mirrors
- [ADR-006 — CI/CD pipeline architecture](ADR-006-cicd-pipeline-architecture.md) — where pipeline-level state applies happen
- [ADR-008 — Catalyst API RBAC via AWS IAM groups](ADR-008-catalyst-api-rbac.md) — tenant-scoped groups that anchor ABAC on the state-key prefix
- [ADR-010 — Egress control for Catalyst workloads](ADR-010-egress-control.md) — defines `compliance_tier`, which drives the L3 split rule
- [ADR-014 — `POST /services/onboard` provisioning mode (sync)](ADR-014-services-onboard-provisioning-mode.md) — why per-app state is load-bearing for Option A
- `infrastructure/backend.tf` — the current L1 root (unchanged by this ADR)
- `infrastructure/modules/terraform-backend/` — the bucket/lock/KMS module shared across all tiers
- Tracking issue: [#187](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/187)
- Implementation issues: [#167](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/167) (consumes L4 contract), [#168](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/168) (provisions L2/L3 baseline)
