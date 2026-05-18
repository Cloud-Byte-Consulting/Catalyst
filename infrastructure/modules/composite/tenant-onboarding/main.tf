locals {
  environments_by_name = { for e in var.environments : e.name => e }

  # ADR-010: Network Firewall is provisioned for HIPAA / PCI-DSS landing zones
  # only; baseline (standard) tenants get VPC endpoints + NAT egress without an
  # inspection boundary.
  firewall_required  = var.compliance_tier != "standard"
  firewall_envs      = local.firewall_required ? local.environments_by_name : {}
  iam_group_roles    = ["owners", "administrators", "viewers"]
  iam_groups_by_role = { for role in local.iam_group_roles : role => "catalyst-${var.tenant}--${role}" }
}

# ---------------------------------------------------------------------------
# SSM parameter tree (ADR-002 hierarchy anchor)
#
# Per-environment SSM parameters live under /catalyst/{tenant}/{env}/...
# Downstream consumers (Tier 2 onboard handler, runtime config bootstrap)
# read these to discover the landing-zone account and compliance posture
# without having to call AWS Organizations or carry tenant config in code.
# ---------------------------------------------------------------------------

# tfsec:ignore:aws-ssm-secret-use-secrets-manager
resource "aws_ssm_parameter" "landing_zone_account_id" {
  for_each = local.environments_by_name

  name        = "/catalyst/${var.tenant}/${each.value.name}/landing-zone-account-id"
  type        = "String"
  value       = var.landing_zone_account_id
  description = "Landing-zone AWS account id for ${var.tenant}/${each.value.name}. Provisioned by modules/composite/tenant-onboarding."
}

# tfsec:ignore:aws-ssm-secret-use-secrets-manager
resource "aws_ssm_parameter" "compliance_tier" {
  for_each = local.environments_by_name

  name        = "/catalyst/${var.tenant}/${each.value.name}/compliance-tier"
  type        = "String"
  value       = var.compliance_tier
  description = "Compliance tier (ADR-010) for ${var.tenant}/${each.value.name}. Drives Network Firewall provisioning."
}

# ---------------------------------------------------------------------------
# Tenant-scoped IAM groups (ADR-008 — "Tenant-scoped groups (no project)")
#
# Naming convention: catalyst-{tenant}--{role}
#   role ∈ { owners, administrators, viewers }
#
# Note the double-hyphen separator. The Catalyst API's rbac.py parser uses
# the double-hyphen to disambiguate tenant-scoped groups from the 3-segment
# scoped form (catalyst-{tenant}--{project}--{role}) and from the legacy
# single-hyphen form.
# ---------------------------------------------------------------------------

resource "aws_iam_group" "tenant_scoped" {
  for_each = local.iam_groups_by_role

  name = each.value
}

# ---------------------------------------------------------------------------
# Per-environment network module (ADR-002)
#
# Each environment gets its own VPC with the cidr/AZ/subnet layout supplied
# in the environments list. name_prefix is "{tenant}-{env}" so resource
# names remain unique across tenants sharing an account during pilot
# bootstrap.
# ---------------------------------------------------------------------------

module "network" {
  source   = "../../network"
  for_each = local.environments_by_name

  name_prefix          = "${var.tenant}-${each.value.name}"
  vpc_cidr             = each.value.cidr_block
  availability_zones   = each.value.availability_zones
  public_subnet_cidrs  = each.value.public_subnet_cidrs
  private_subnet_cidrs = each.value.private_subnet_cidrs
}

# ---------------------------------------------------------------------------
# Conditional Network Firewall (ADR-010)
#
# Provisioned only when compliance_tier is hipaa or pci-dss. The standard
# tier keeps the baseline egress (VPC endpoints + NAT + restrictive SGs)
# and does not apply the FQDN allowlist firewall.
# ---------------------------------------------------------------------------

module "network_firewall" {
  source   = "../../network-firewall"
  for_each = local.firewall_envs

  enabled     = true
  name_prefix = "${var.tenant}-${each.value.name}"
  vpc_id      = module.network[each.key].vpc_id
  subnet_id   = module.network[each.key].public_subnet_ids[0]
}
