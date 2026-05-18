# Catalyst onboarding

Onboarding into Catalyst is **three orthogonal tracks**, each with its own audience, outcome, and runbook. The architectural decision is ratified in [ADR-012](../ADR/ADR-012-onboarding-experience.md).

| Track | Audience | Runbook | Outcome |
|---|---|---|---|
| **A — Platform** | Cloud / platform engineering | [`platform.md`](./platform.md) | Fresh AWS account ready for GitOps; Catalyst API reachable from allowlisted networks |
| **B — Organisation** | Team / lab leaders (Owners) | [`organisation.md`](./organisation.md) | Tenant hierarchy registered (OUs, landing zones, environments) |
| **C — Application** | Platform engineers / app teams (Owners + Administrators) | [`application.md`](./application.md) | Application service provisioned at a construct address |

## Which track applies to me?

- **You have an empty AWS account and want to deploy Catalyst** → start with **Track A**.
- **Catalyst is deployed and you're standing up a new tenant or environment** → **Track B** (assumes Track A is complete).
- **A tenant + environment exist and you want to onboard your application service** → **Track C** (assumes Tracks A + B are complete).

Tracks are sequential at the platform boundary (A before B or C) but B before C only at the data level: `POST /services/onboard` rejects unknown construct addresses until Tier 1 records exist (ADR-007).

## Issue labels

All onboarding work tracks under the `type/onboarding` label (created 2026-05-18). Pair it with the appropriate `kind/*` and audience-scoping labels per [ADR-001](../ADR/ADR-001-github-issues-as-state-machine.md) and [STATE-MACHINE.md](../ADR/STATE-MACHINE.md):

| You are onboarding | Suggested labels |
|---|---|
| A new platform account (Track A) | `type/onboarding`, `kind/iac`, `project/platform`, `tenant/<tenant>` |
| A tenant / LZ / environment (Track B) | `type/onboarding`, `kind/service`, `tenant/<tenant>`, `env/<env>` |
| An application service (Track C) | `type/onboarding`, `kind/service`, `tenant/<tenant>`, `env/<env>`, plus construct labels |

> **Placeholder labels need creating per-tenant.** The placeholders `tenant/<tenant>`, `env/<env>`, `project/<project>`, `app/<app>` above are templates — the concrete labels (`tenant/catalyst`, `env/shared`, `project/platform`, `app/idp-platform`, `app/kaizen`, `app/ops-intel`) are the only ones currently registered. Before running `gh issue create` with a new placeholder, create the label first: `gh label create tenant/<your-tenant> --repo Cloud-Byte-Consulting/Catalyst`.

## Related

- [ADR-012](../ADR/ADR-012-onboarding-experience.md) — the architectural decision
- [`docs/operator-bootstrap.md`](../operator-bootstrap.md) — canonical step-by-step bootstrap runbook (linked from Track A)
- [`docs/smoke-tests.md`](../smoke-tests.md) — post-onboarding verification
- [`.github/workflows/README.md`](../../.github/workflows/README.md) — variables + OIDC role mapping
