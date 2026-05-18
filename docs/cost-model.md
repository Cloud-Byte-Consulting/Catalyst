# Catalyst cost model — VPC network module

**Last updated:** 2026-05-18 (us-west-2 public list pricing)
**Module:** [`infrastructure/modules/network`](../infrastructure/modules/network)
**Variable:** `cost_tier` (`dev | prod | hipaa`) — see [`variables.tf`](../infrastructure/modules/network/variables.tf)

This doc captures the **steady-state idle cost** of a single Catalyst VPC and explains how the `cost_tier` variable gates spend-sensitive add-ons. It was written after the PR #151 orphan-VPC incident (a single dev VPC that ran ~7 days while idle cost the demo account ~$100/month — NAT gateway plus interface VPC endpoints plus EIP), so the figures here are deliberately conservative and based on AWS public list pricing rather than discounted rates.

## TL;DR

- The recurring idle cost of the current network module is **NAT gateways + their attached public IPv4 addresses**: ~$66/month NAT + ~$7/month public IPv4 ≈ **~$73/month** for a 2-AZ deployment, before data-processing charges. AWS started charging for all in-use public IPv4 addresses on 2024-02-01 (~$0.005/hr per address); each NAT-attached EIP is one billable address.
- The module today provisions **only the two free gateway endpoints** (S3, DynamoDB). It does **not** provision any interface VPC endpoints.
- `cost_tier` exists as a **future gate**: when interface endpoints are added later (ECR, SSM, STS, KMS, Secrets Manager, CW Logs, Bedrock Runtime, etc.), they MUST be gated `count = var.cost_tier == "dev" ? 0 : 1` so dev VPCs do not silently start bleeding ~$7.30/mo per endpoint per AZ.
- **Network Firewall is NOT gated by `cost_tier`** — it is gated by the composite `tenant-onboarding` module's `compliance_tier` variable (per ADR-010). The cost-tier and compliance-tier knobs travel together but answer different questions; this doc covers the `cost_tier` math only.
- Default is `cost_tier = "dev"`. Recommended for the demo Mon-Fri auto-teardown stack and any non-production environment.

## Unit costs (us-west-2 public list, May 2026)

| Resource | Idle cost | Data processing | Notes |
|---|---|---|---|
| NAT gateway | ~$0.045/hr ≈ **~$33/month per AZ** | $0.045 per GB processed | 2-AZ HA deploy = ~$66/month before traffic |
| Interface VPC endpoint | ~$0.01/hr ≈ **~$7.30/month per endpoint per AZ** | $0.01 per GB processed (first 1 PB) | Charged per ENI, so 2-AZ doubles the line |
| Gateway VPC endpoint (S3, DynamoDB) | **$0.00** | $0.00 | Free; provisioned in all tiers |
| Public IPv4 address (in-use, e.g. NAT-attached EIP) | ~$0.005/hr ≈ **~$3.60/month per address** | n/a | AWS charges all in-use public IPv4 from 2024-02-01; each NAT-attached EIP is one billable address. 2-AZ deploy = ~$7.20/month |
| EIP (unattached) | ~$0.005/hr ≈ **~$3.60/month** | n/a | Same rate as in-use — the difference is which line item it appears under. PR #151's orphan EIP lingered on this line after its NAT was torn down out-of-order |

Source: <https://aws.amazon.com/vpc/pricing/> (Network address translation; PrivateLink interface endpoints). Confirm before quoting in customer-facing material.

## Per-tier monthly idle subtotal

Assumes a 2-AZ deployment (the current module default — `availability_zones` has two entries in every Catalyst caller). "Interface endpoints" column reflects the **target** set if/when the module grows interface endpoints; today the column is `0` for both dev and prod because the module ships only gateway endpoints.

| Env type | NAT gateways (2 AZ) | Public IPv4 (2 NAT EIPs) | Interface endpoints | Gateway endpoints | Monthly idle subtotal |
|---|---|---|---|---|---|
| `dev` (current module today) | ~$66 | ~$7.20 | $0 (none provisioned) | $0 (S3, DynamoDB) | **~$73/mo** |
| `prod` (current module today) | ~$66 | ~$7.20 | $0 (none provisioned) | $0 (S3, DynamoDB) | **~$73/mo** |
| `dev` (after future interface endpoints land, gated off) | ~$66 | ~$7.20 | $0 (gated by `cost_tier`) | $0 | **~$73/mo** |
| `prod` (after future interface endpoints land, gated on, ~10 endpoints × 2 AZ) | ~$66 | ~$7.20 | ~$146 ($7.30 × 10 × 2) | $0 | **~$219/mo** |
| `hipaa` (prod + Network Firewall — wired by **the composite module's `compliance_tier`**, NOT by `cost_tier`, per [ADR-010](./ADR/ADR-010-egress-control.md)) | ~$66 | ~$7.20 | ~$146 | $0 | **~$219/mo + Network Firewall** |

Today dev tier ≈ prod tier (both ~$73/mo) because no interface endpoints are provisioned yet. The point of `cost_tier` is to keep that equality from breaking silently when someone adds an interface endpoint later. **The `hipaa` row's "+ Network Firewall" delta is not produced by this module's `cost_tier` variable** — it is provisioned by the composite tenant-onboarding module's `compliance_tier` variable, captured here only so the operator-facing dollar table is complete.

## What broke and why this doc exists (PR #151 worked example)

PR #151 cleaned up an orphan VPC stack in the demo account that had been idle for ~7 days. The reconstructed cost breakdown for that single stack was approximately:

- 1 NAT gateway in 1 AZ: ~$33/month
- 1 attached public IPv4 (the NAT EIP, in-use): ~$3.60/month (AWS in-use IPv4 charge since 2024-02-01; not yet in effect at the time of the original incident but applies to any re-occurrence today)
- ~10 interface VPC endpoints (ECR API/DKR, SSM, SSM Messages, EC2 Messages, STS, KMS, Secrets Manager, CW Logs, Bedrock Runtime) in 1 AZ: ~$73/month
- 1 unattached EIP after the NAT was torn down out-of-order: ~$3.60/month while unattached

Net: ~$110/month for a stack carrying zero workload traffic at today's IPv4-inclusive pricing (the original PR #151 reconstruction quoted ~$100/month without the in-use IPv4 line; under post-2024-02-01 pricing the same shape is ~$10/month higher). Across multiple dev environments this scales linearly and surprises operators. The `cost_tier=dev` default exists so that the cheap path is also the default path; opting into interface endpoints is now an explicit `prod`/`hipaa` decision instead of a copy-paste accident.

## When to choose which tier

| Scenario | Tier | Why |
|---|---|---|
| Demo Mon-Fri auto-teardown stack | `dev` | Idle weekends; gateway-only endpoints + NAT is enough for the demo's egress needs |
| Operator sandbox / scratch environment | `dev` | Same reasoning; tear down via `docs/teardown.md` when finished |
| Steady-state production | `prod` | Interface endpoints reduce Lambda cold-start latency and keep traffic off public NAT lanes when added |
| HIPAA / regulated workload | `hipaa` on `cost_tier` paired with `compliance_tier = "hipaa"` on the composite | Network Firewall is wired by the **composite's `compliance_tier`** (per [ADR-010](./ADR/ADR-010-egress-control.md)), not by this module's `cost_tier`. Set both to keep cost gating + compliance gating aligned |

## How `cost_tier` is wired

Today: variable accepted, validated (`dev | prod | hipaa`), defaulted to `dev`. No resources are gated on it yet because the module does not currently include interface endpoints.

Tomorrow (when interface endpoints get added in a follow-up PR): each interface endpoint resource gets `count = var.cost_tier == "dev" ? 0 : 1`. The `network.tftest.hcl` cases for `dev` and `prod` will be extended at that time to assert the divergence.

The comment block in [`modules/network/main.tf`](../infrastructure/modules/network/main.tf) above the gateway-endpoint resources is the in-source reminder for future contributors.

## Related

- [ADR-010 — egress control for Catalyst workloads](./ADR/ADR-010-egress-control.md)
- [ADR-012 §Notes — cost review for NAT/interface endpoints](./ADR/ADR-012-onboarding-experience.md)
- [PR #151 — orphan-VPC cleanup](https://github.com/Cloud-Byte-Consulting/Catalyst/pull/151)
- [Issue #170 — cost_tier kaizen](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/170)
- [`docs/teardown.md`](./teardown.md) — environment teardown to avoid leaving NAT/EIPs running
