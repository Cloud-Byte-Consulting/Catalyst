# ADR-003 — Static environment tiers (Dev, Stage, Prod) and ephemeral environments

**Status**: Proposed · 2026-05-13

## Context

Catalyst’s construct model treats **Environment** as the lifecycle stage under a tenant ([construct hierarchy](ADR-002-construct-hierarchy.md)). Without an explicit split, teams overload the same `env/*` label for long-lived shared tiers and for **short-lived** preview stacks. That blurs blast radius, cost attribution, IAM boundaries, and what automation may legally promote between tiers.

The platform needs:

- A **small, fixed vocabulary** of **static** environments every tenant is expected to run for the main delivery spine: integration work, pre-production validation, and production.
- A **separate class** of **ephemeral** environments (PR previews, spike branches, time-boxed demos) that are created and destroyed automatically, are never promotion targets to production, and must not inherit production trust policies.

This ADR fixes the static set to **Dev**, **Stage**, and **Prod** and defines how ephemeral environments relate to the same construct-address scheme without pretending they are fourth/fifth permanent lifecycle stages.

## Decision

**We will treat Dev, Stage, and Prod as the only static, catalog-backed environment slugs** under each tenant. **Ephemeral environments** are first-class for automation and labeling but are **not** additional static tiers: they are short-lived `Environment` records (or equivalent identifiers) with explicit TTL, weaker trust, and a dedicated naming pattern, governed mainly by `type/preview-env` work items and preview-oriented labels ([`docs/ADR/STATE-MACHINE.md`](STATE-MACHINE.md) §2.2, §2.3).

### Static environments (exactly three slugs)

| Display name | Canonical slug (`env/*` label segment) | Role |
|---|---|---|
| Dev | `dev` | Fast iteration; may use relaxed secrets and non-prod data; no customer SLA. |
| Stage | `stage` | Production-like validation; change windows and data handling closer to prod; still non-customer. |
| Prod | `prod` | Customer-impacting workloads; strictest controls and audit. |

**Rules:**

- Every tenant **SHOULD** provision all three static environments in Aurora’s environment catalog before declaring the tenant “live” for application deploys. Exceptions are documented per tenant with a **`type/kaizen`** Issue.
- Static environments are **long-lived**: no automatic teardown; decommissioning is a governed change (same class as retiring a landing zone).
- **Promotion semantics** (what may deploy where) are directional: `dev → stage → prod` only. Automation MUST NOT promote artifacts from an ephemeral identifier into `env/prod` without a human-gated flow that re-anchors the work item to a static `env/stage` (or equivalent) validation record.

### Ephemeral environments

**Definition:** An ephemeral environment is a temporary stack (infrastructure + application revision) scoped to a tenant (and usually a project/application), created to validate a discrete change (typically a branch or PR), with a **mandatory maximum lifetime** and **no standing expectation** of persistence in the environment catalog beyond that lifetime.

**Rules:**

- **Naming / addressing:** Ephemeral targets use a slug under `env/` that is **not** `dev`, `stage`, or `prod`. The canonical pattern is `preview-<unique-suffix>` where `<unique-suffix>` is globally unique within the tenant at minimum (e.g. GitHub issue number, PR number, or ULID). Example construct-address segment: `env/preview-1842`.
- **Catalog:** Ephemeral rows MAY live in the same `environments` table with `kind = ephemeral` (or a sibling table) including `expires_at`, `source_ref` (branch, commit, PR URL), and `parent_static_env` (often `dev` for where artifacts were built). Alternatively, only the **GitHub Issue** holds ephemeral metadata until the stack exists; either way, **TTL and owner** MUST be queryable for cost and security reviews.
- **Automation:** Lifecycle is driven by Issues labeled `type/preview-env` with subtype labels such as `preview/ephemeral` or `preview/extended` per [`docs/ADR/STATE-MACHINE.md`](STATE-MACHINE.md). Teardown MUST be reflected in a terminal Issue state and resource tags removed or isolated so idle previews cannot receive traffic.
- **Trust and data:** Ephemeral environments MUST NOT use production secrets, production databases, or production KMS keys by default. Any exception is `state/blocked-on-human` with explicit compliance sign-off recorded on the Issue.

### Relationship to GitHub Issues and labels

- Static deploys and rotations anchor to `tenant/*`, **`env/dev` | `env/stage` | `env/prod`**, `lz/*`, `project/*`, `app/*` as today.
- Ephemeral work anchors the same five levels, with **`env/preview-*`** (or future approved ephemeral slug family) and `type/preview-env` on the controlling Issue. Agents and services MUST validate `env/*` against the allowed static set **or** the ephemeral pattern before applying changes.

## Consequences

- Good: Clear **promotion story** and **audit narrative** — “this artifact went through stage” is unambiguous.
- Good: Ephemeral previews stay **out of the prod blast-radius** by construction of trust defaults, not by convention alone.
- Good: Cost and **quota governance** can key off `kind = ephemeral` and `expires_at`.
- Trade-off: Tenants that today use **QA**, **Perf**, or **Train** as separate long-lived stages must map them into **`stage`** (same slug, different landing zones or projects) or pursue a **Kaizen** to extend static slugs — intentionally not in scope for this ADR to keep the platform vocabulary small.
- Trade-off: **`stage` vs `staging`**: we standardize on slug **`stage`** to keep labels short and consistent; documentation may say “Stage” in prose.
- Risk: Teams may try to run “long-lived previews.” **Mitigation:** automation alarms on `preview/extended` age; policy that re-labels or blocks after approved window.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Treat previews as `env/dev` with a namespace tag only | Fails the five-property substrate for audit: `env/*` would no longer mean a single lifecycle stage; IAM tag conditions on `Catalyst-Env` become ambiguous. |
| Unlimited static env slugs (`qa`, `perf`, `sandbox`, …) as peers of prod | Explodes policy surface, breaks “assume three static tiers” for rubric and employer demo; better as a later ADR if the enterprise mandates more tiers. |
| Ephemeral environments without Aurora rows (Issues only) | Acceptable for v0, but weak for cost allocation and cross-service joins; hybrid (Issue + optional ephemeral row) is allowed under this ADR. |

## Related

- [ADR-002 — Construct hierarchy](ADR-002-construct-hierarchy.md) (Environment definition and construct address).
- [ADR-001 — GitHub Issues as state machine](ADR-001-github-issues-as-state-machine.md) (audit trail for preview and deploy work).
- [`docs/ADR/STATE-MACHINE.md`](STATE-MACHINE.md) (`type/preview-env`, `preview/*` subtypes, `env/shared` for non-env-specific kaizens).
- [`docs/issue-execution-gherkin-workflow-2026-05-13.md`](../issue-execution-gherkin-workflow-2026-05-13.md) (how agents record preview/ephemeral decisions on Issues).
