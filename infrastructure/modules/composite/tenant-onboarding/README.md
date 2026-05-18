# `composite/tenant-onboarding`

Tenant-scoped Terraform composite that provisions everything a new
Catalyst tenant needs at the **organisation** layer of the
[ADR-002](../../../../docs/ADR/ADR-002-construct-hierarchy.md) hierarchy
(`Tenant -> Environment -> LandingZone -> Project -> Application`):

- **SSM parameter tree** under `/catalyst/{tenant}/{env}/` exposing
  `landing-zone-account-id` and `compliance-tier` to downstream
  consumers (Tier 2 onboard handler, runtime config bootstrap).
- **Tenant-scoped IAM groups** following the new
  [ADR-008](../../../../docs/ADR/ADR-008-catalyst-api-rbac.md)
  "Tenant-scoped groups (no project)" convention:
  `catalyst-{tenant}--owners`, `catalyst-{tenant}--administrators`,
  `catalyst-{tenant}--viewers`.
- **Per-environment VPCs** by delegating to `modules/network` once
  per entry in `var.environments`.
- **Conditional AWS Network Firewall** by delegating to
  `modules/network-firewall` when the tenant's compliance posture
  requires inspected internet egress
  (see [ADR-010](../../../../docs/ADR/ADR-010-egress-control.md)).

This module is the **eventual replacement for the curl-based Tier 1
onboarding flow** described in
[`docs/onboarding/organization.md`](../../../../docs/onboarding/organization.md).
It is **not** an application-scoped composite — for app-runtime resources
(ECR + Lambda + ALB + ECS + DynamoDB), see
[`composite/catalyst-product`](../catalyst-product/).

---

## Variables

| Name | Type | Default | Description |
|---|---|---|---|
| `tenant` | `string` | _(required)_ | Tenant slug. Must not contain `--`. |
| `landing_zone_account_id` | `string` | _(required)_ | 12-digit AWS account id of the landing zone hosting this tenant. |
| `compliance_tier` | `string` | `"standard"` | One of `standard`, `hipaa`, `pci-dss`. Drives Network Firewall provisioning per ADR-010. |
| `environments` | `list(object)` | _(required, len >= 1)_ | One entry per environment. Fields: `name`, `cidr_block`, `availability_zones`, `public_subnet_cidrs`, `private_subnet_cidrs`. Names must be unique. |

`cost_tier` passthrough to `modules/network` is deferred until
[#170](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/170)
introduces that variable to the network module.

## Outputs

| Name | Description |
|---|---|
| `ssm_parameter_arns` | Map of provisioned SSM parameter ARNs, keyed `env/parameter-name`. |
| `iam_group_names` | Map `role -> group name` for the three tenant-scoped IAM groups. |
| `vpc_ids` | Map `env name -> VPC id`. |
| `network_firewall_enabled` | `true` when `compliance_tier != "standard"`. |

---

## Compliance-tier semantics

Per [ADR-010](../../../../docs/ADR/ADR-010-egress-control.md):

| `compliance_tier` | Baseline egress | Network Firewall | Use cases |
|---|---|---|---|
| `standard` | VPC endpoints + NAT + restrictive SGs + Flow Logs | _(not provisioned)_ | Internal tooling, lower environments, non-regulated workloads |
| `hipaa` | _baseline_ | FQDN allowlist (stateful drop-by-default) | HIPAA-scoped clinical or pharmacy workloads |
| `pci-dss` | _baseline_ | FQDN allowlist (stateful drop-by-default) | PCI-DSS-scoped payer / payments workloads |

The firewall enforces an FQDN allowlist that defaults to
`api.github.com` only; tenants that need additional egress should
extend `modules/network-firewall` (out of scope for this module).

---

## Example usage

```hcl
module "tenant_acme" {
  source = "../../modules/composite/tenant-onboarding"

  tenant                  = "acme"
  landing_zone_account_id = "123456789012"
  compliance_tier         = "hipaa"

  environments = [
    {
      name                 = "dev"
      cidr_block           = "10.20.0.0/16"
      availability_zones   = ["us-west-2a", "us-west-2b"]
      public_subnet_cidrs  = ["10.20.0.0/24", "10.20.1.0/24"]
      private_subnet_cidrs = ["10.20.10.0/24", "10.20.11.0/24"]
    },
    {
      name                 = "prod"
      cidr_block           = "10.30.0.0/16"
      availability_zones   = ["us-west-2a", "us-west-2b"]
      public_subnet_cidrs  = ["10.30.0.0/24", "10.30.1.0/24"]
      private_subnet_cidrs = ["10.30.10.0/24", "10.30.11.0/24"]
    },
  ]
}
```

After apply, the IAM groups `catalyst-acme--owners`,
`catalyst-acme--administrators`, and `catalyst-acme--viewers` can be
populated with users; the Catalyst API (`rbac.py::_parse_scoped_group`)
parses them into a tenant-wide scope (`(acme, "*")`) that grants the
named role across every project in the tenant.

---

## Related ADRs

- [ADR-002 — Construct hierarchy](../../../../docs/ADR/ADR-002-construct-hierarchy.md)
- [ADR-008 — Catalyst API RBAC via AWS IAM Groups](../../../../docs/ADR/ADR-008-catalyst-api-rbac.md) — see "Tenant-scoped groups (no project)" subsection
- [ADR-010 — Egress control for Catalyst workloads](../../../../docs/ADR/ADR-010-egress-control.md)
