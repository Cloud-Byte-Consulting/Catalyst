# ADR-016 — Catalyst homelab deployment

**Status**: Proposed (placeholder) · 2026-05-18

> **Placeholder — design sessions required before Accepted.** This ADR captures intent and open questions only; no homelab topology, toolchain, or parity target is committed yet.

**Related**: [ADR-003](ADR-003-static-and-ephemeral-environments.md) · [ADR-006](ADR-006-cicd-pipeline-architecture.md) · [ADR-009](ADR-009-runtime-strategy.md) · [ADR-011](ADR-011-catalyst-agentic-workflow.md) · [ADR-012](ADR-012-onboarding-experience.md) · [ADR-017](ADR-017-migration-github-to-gitea.md) · [`docs/references/challenge-brief.md`](../references/challenge-brief.md)

---

## Context

Catalyst today targets a **commercial AWS account** pattern: bootstrap provisions the state bucket and lock table, `terraform.yml` applies platform infrastructure on push to `release`, and `service-cd.yml` deploys the control-plane API (Lambda by default per [ADR-009](ADR-009-runtime-strategy.md), ECS as an option) behind ALB with GitHub Actions OIDC for credentials ([ADR-006](ADR-006-cicd-pipeline-architecture.md)).

The platform owner wants the option to run the **Catalyst control plane and supporting infrastructure** on a **homelab / self-hosted** footprint — lab hardware, Proxmox, TrueNAS, or a single-node cluster at home — rather than (or in addition to) the current AWS commercial path. Use cases include cost control, offline development, regulated data residency on owned metal, and co-location with a self-hosted forge ([ADR-017](ADR-017-migration-github-to-gitea.md)).

This ADR does **not** define homelab architecture. It records the **decision to pursue** homelab as a future deployment target and frames scope, phases, and trade-offs for later design sessions.

---

## Decision

**TBD (placeholder).** Documented intent:

- Catalyst **will** support homelab / self-hosted as a **first-class deployment target** in a future phase, without prescribing topology in this ADR.
- Until design sessions complete, **AWS commercial remains the canonical path** for bootstrap, CI/CD, and production-like demos.
- Homelab work **may diverge** from `infrastructure/backend.tf`, `terraform.yml`, and Lambda/ALB assumptions; parity is phased, not assumed day one.

---

## Scope boundaries (open questions)

What “homelab” means is **explicitly unresolved**. Design sessions must choose among (non-exhaustive):

| Dimension | Open options |
|---|---|
| **Compute** | Single-node k8s (k3s/k0s), bare metal + systemd, Proxmox VMs, TrueNAS SCALE apps |
| **“AWS-shaped” infra** | Real mini-AWS account vs [LocalStack](https://localstack.cloud/) / LocalStack Pro vs hybrid (LocalStack + selective real AWS) |
| **State & artifacts** | MinIO (S3-compatible) for Terraform state and ECR substitutes vs NFS on TrueNAS vs cloud-backed state with homelab compute only |
| **Networking** | Tailscale-only API, split-horizon DNS, public ingress on residential ISP |
| **Identity & CI** | Self-hosted runners, Gitea Actions, no OIDC to AWS — see [ADR-017](ADR-017-migration-github-to-gitea.md) |
| **Multi-tenancy** | Single-tenant lab vs replaying ADR-002 construct hierarchy on lab metal |

**In scope (future phases):** control-plane API reachability, minimal Terraform or k8s manifests, documented bootstrap for lab operators.

**Out of scope (this ADR):** production SLAs on homelab, full ADR-010 egress tier parity, or mandatory feature parity with commercial AWS before Accept.

---

## Relationship to existing deploy path

| Commercial AWS (today) | Homelab (anticipated divergence) |
|---|---|
| `scripts/bootstrap` + S3/DynamoDB (or lockfile) state | Likely k3s manifests, Compose, or reduced Terraform root; state on MinIO or local backend |
| `terraform.yml` → OIDC → plan/apply on `release` | Self-hosted runner or manual apply; trust model TBD |
| Lambda + ALB ([ADR-009](ADR-009-runtime-strategy.md)) | Container on k3s, bare metal, or LocalStack-emulated Lambda (if viable) |
| ECR image push from `service-cd.yml` | Local registry (Gitea packages, Harbor, docker on node) |
| Per-tenant state keys ([ADR-015](ADR-015-terraform-state-partitioning.md)) | May collapse to single-tenant lab or simplified key layout |

Homelab is expected to **fork or overlay** the existing roots rather than silently reuse commercial `terraform.yml` without adaptation.

---

## Phased approach (placeholder)

| Phase | Goal | Exit criteria (TBD) |
|---|---|---|
| **Phase 0 — Discovery** | Inventory hardware, network, compliance needs; spike LocalStack vs real AWS vs k3s-only API | Written target topology; list of non-portable AWS services |
| **Phase 1 — Minimal API** | Run Catalyst API + one golden-path endpoint on lab (single tenant) | Documented install path; smoke test without commercial account |
| **Phase 2 — Infra parity** | Optional: onboard/drift patterns, observability module, construct addressing — aligned with [ADR-003](ADR-003-static-and-ephemeral-environments.md) where feasible | Explicit parity matrix vs AWS path |

Phase gates and timelines are **not** set in this placeholder.

---

## Consequences

- **Positive:** Enables local iteration, air-gapped or low-cost environments, and alignment with self-hosted Git ([ADR-017](ADR-017-migration-github-to-gitea.md)).
- **Positive:** Forces explicit documentation of which ADRs assume AWS-only primitives.
- **Cost:** Second deployment matrix — docs, CI, and agent skills must branch or parameterise on `deployment_target`.
- **Risk:** LocalStack / emulated AWS diverges from real IAM, Lambda, and ALB behaviour — mitigated by Phase 0 spikes and labelled “lab-only” in docs.
- **Risk:** Security and compliance (HIPAA/PCI paths in ADR-003/010) may be **unsupported** on homelab until separately designed.

---

## Alternatives considered

| Alternative | Why not chosen (yet) |
|---|---|
| **Stay cloud-only** | Rejects stated owner intent; keeps ops simple but blocks homelab goals |
| **Mirror-only Gitea, deploy only on AWS** | See [ADR-017](ADR-017-migration-github-to-gitea.md) — valid hybrid; does not satisfy “platform runs at home” |
| **Full AWS parity on homelab before any doc** | Too large for placeholder; deferred to Phase 2 |
| **Vendor-managed lab (e.g. dedicated small AWS account)** | May remain a stepping stone; not mutually exclusive with true homelab |

---

## Compliance and operations notes

- Homelab deployments are **not** assumed to meet challenge-brief production bar or regulated tiers without explicit hardening.
- Backup, DR, and secret handling on residential or NAS hosts are **open** — no decision here.
- Agent workflows ([ADR-011](ADR-011-catalyst-agentic-workflow.md), [ADR-012](ADR-012-onboarding-experience.md)) may need `deployment_target=homelab` conventions in `AGENTS.md` and skills when Phase 1 lands.

---

## Related

- [ADR-003](ADR-003-static-and-ephemeral-environments.md) — environment classes and promotion
- [ADR-006](ADR-006-cicd-pipeline-architecture.md) — GitHub Actions + OIDC apply path
- [ADR-009](ADR-009-runtime-strategy.md) — Lambda vs ECS runtime
- [ADR-011](ADR-011-catalyst-agentic-workflow.md) · [ADR-012](ADR-012-onboarding-experience.md) — operator and agent onboarding
- [ADR-017](ADR-017-migration-github-to-gitea.md) — forge co-location on homelab
- [`docs/references/challenge-brief.md`](../references/challenge-brief.md) — submission context (AWS-native demo remains primary until homelab Accepted)
