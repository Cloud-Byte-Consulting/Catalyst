# Catalyst cost model — VPC network module

**Last updated:** 2026-05-18 (us-west-2 public list pricing)
**Module:** [`infrastructure/modules/network`](../infrastructure/modules/network)
**Variable:** `cost_tier` (`dev | prod | hipaa`) — see [`variables.tf`](../infrastructure/modules/network/variables.tf)

This doc captures the **steady-state idle cost** of a single Catalyst VPC and explains how the `cost_tier` variable gates spend-sensitive add-ons. It was written after the PR #151 orphan-VPC incident (a single dev VPC that ran ~7 days while idle cost the demo account ~$100/month — NAT gateway plus interface VPC endpoints plus EIP), so the figures here are deliberately conservative and based on AWS public list pricing rather than discounted rates.

## TL;DR

- The only recurring cost in the current network module is the **NAT gateway pair** (~$66/month idle for a 2-AZ deployment, before data-processing charges).
- The module today provisions **only the two free gateway endpoints** (S3, DynamoDB). It does **not** provision any interface VPC endpoints.
- `cost_tier` exists as a **future gate**: when interface endpoints are added later (ECR, SSM, STS, KMS, Secrets Manager, CW Logs, Bedrock Runtime, etc.), they MUST be gated `count = var.cost_tier == "dev" ? 0 : 1` so dev VPCs do not silently start bleeding ~$7.30/mo per endpoint per AZ.
- Default is `cost_tier = "dev"`. Recommended for the demo Mon-Fri auto-teardown stack and any non-production environment.

## Unit costs (us-west-2 public list, May 2026)

| Resource | Idle cost | Data processing | Notes |
|---|---|---|---|
| NAT gateway | ~$0.045/hr ≈ **~$33/month per AZ** | $0.045 per GB processed | 2-AZ HA deploy = ~$66/month before traffic |
| Interface VPC endpoint | ~$0.01/hr ≈ **~$7.30/month per endpoint per AZ** | $0.01 per GB processed (first 1 PB) | Charged per ENI, so 2-AZ doubles the line |
| Gateway VPC endpoint (S3, DynamoDB) | **$0.00** | $0.00 | Free; provisioned in all tiers |
| EIP (attached to NAT) | $0.00 while in use | n/a | Charged $0.005/hr only when *unattached* — that's how the PR #151 orphan leaked |

Source: <https://aws.amazon.com/vpc/pricing/> (Network address translation; PrivateLink interface endpoints). Confirm before quoting in customer-facing material.

## Per-tier monthly idle subtotal

Assumes a 2-AZ deployment (the current module default — `availability_zones` has two entries in every Catalyst caller). "Interface endpoints" column reflects the **target** set if/when the module grows interface endpoints; today the column is `0` for both dev and prod because the module ships only gateway endpoints.

| Env type | NAT gateways (2 AZ) | Interface endpoints | Gateway endpoints | Monthly idle subtotal |
|---|---|---|---|---|
| `dev` (current module today) | ~$66 | $0 (none provisioned) | $0 (S3, DynamoDB) | **~$66/mo** |
| `prod` (current module today) | ~$66 | $0 (none provisioned) | $0 (S3, DynamoDB) | **~$66/mo** |
| `dev` (after future interface endpoints land, gated off) | ~$66 | $0 (gated by `cost_tier`) | $0 | **~$66/mo** |
| `prod` (after future interface endpoints land, gated on, ~10 endpoints × 2 AZ) | ~$66 | ~$146 ($7.30 × 10 × 2) | $0 | **~$212/mo** |
| `hipaa` (prod + Network Firewall per ADR-010) | ~$66 | ~$146 | $0 | **~$212/mo + Network Firewall** |

Today dev tier ≈ prod tier (both ~$66/mo) because no interface endpoints are provisioned yet. The point of `cost_tier` is to keep that equality from breaking silently when someone adds an interface endpoint later.

## What broke and why this doc exists (PR #151 worked example)

PR #151 cleaned up an orphan VPC stack in the demo account that had been idle for ~7 days. The reconstructed cost breakdown for that single stack was approximately:

- 1 NAT gateway in 1 AZ: ~$33/month
- ~10 interface VPC endpoints (ECR API/DKR, SSM, SSM Messages, EC2 Messages, STS, KMS, Secrets Manager, CW Logs, Bedrock Runtime) in 1 AZ: ~$73/month
- 1 unattached EIP after the NAT was torn down out-of-order: small (only billed unattached)

Net: ~$100/month for a stack carrying zero workload traffic. Across multiple dev environments this scales linearly and surprises operators. The `cost_tier=dev` default exists so that the cheap path is also the default path; opting into interface endpoints is now an explicit `prod`/`hipaa` decision instead of a copy-paste accident.

## When to choose which tier

| Scenario | Tier | Why |
|---|---|---|
| Demo Mon-Fri auto-teardown stack | `dev` | Idle weekends; gateway-only endpoints + NAT is enough for the demo's egress needs |
| Operator sandbox / scratch environment | `dev` | Same reasoning; tear down via `docs/teardown.md` when finished |
| Steady-state production | `prod` | Interface endpoints reduce Lambda cold-start latency and keep traffic off public NAT lanes when added |
| HIPAA / regulated workload | `hipaa` | Adds Network Firewall per [ADR-010](./ADR/ADR-010-cell-architecture-and-egress-controls.md) |

## How `cost_tier` is wired

Today: variable accepted, validated (`dev | prod | hipaa`), defaulted to `dev`. No resources are gated on it yet because the module does not currently include interface endpoints.

Tomorrow (when interface endpoints get added in a follow-up PR): each interface endpoint resource gets `count = var.cost_tier == "dev" ? 0 : 1`. The `network.tftest.hcl` cases for `dev` and `prod` will be extended at that time to assert the divergence.

The comment block in [`modules/network/main.tf`](../infrastructure/modules/network/main.tf) above the gateway-endpoint resources is the in-source reminder for future contributors.

## Related

- [ADR-010 — cell architecture and egress controls](./ADR/ADR-010-cell-architecture-and-egress-controls.md)
- [ADR-012 §Notes — cost review for NAT/interface endpoints](./ADR/ADR-012-onboarding-experience.md)
- [PR #151 — orphan-VPC cleanup](https://github.com/Cloud-Byte-Consulting/Catalyst/pull/151)
- [Issue #170 — cost_tier kaizen](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/170)
- [`docs/teardown.md`](./teardown.md) — environment teardown to avoid leaving NAT/EIPs running
