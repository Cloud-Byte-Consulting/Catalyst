# ADR-007 — Catalyst API golden paths (v1)

**Status**: Accepted · 2026-05-14
**Related**: [ADR-001](ADR-001-github-issues-as-state-machine.md) · [ADR-002](ADR-002-construct-hierarchy.md) · [ADR-003](ADR-003-static-and-ephemeral-environments.md) · [ADR-006](ADR-006-cicd-pipeline-architecture.md)

---

## Context

The Catalyst API is an Internal Developer Platform (IDP) service that exposes predefined golden paths — opinionated, pre-approved patterns that application teams use to self-serve platform operations without writing Terraform or understanding the underlying AWS service wiring.

Two distinct concerns must be separated:

1. **Platform structure operations** — creating and managing the organisational hierarchy (AWS OUs, landing zones, environments) that defines where workloads live. These operations are performed by the platform team and map directly to the five-level construct address from ADR-002: `tenant / env / lz / project / app`.
2. **Service lifecycle operations** — provisioning, deploying, and querying individual applications within an already-established platform structure. These are the self-service paths consumed by application teams.

Without a defined golden path set, application teams either re-implement AWS patterns inconsistently or raise one-off tickets that the platform team must handle manually. Both outcomes break the self-service model.

---

## Decision

### Tier 1 — Platform structure golden paths

These paths are called by the **platform team** (or automated provisioning tooling) to build out the organisational hierarchy. They correspond to the upper levels of the ADR-002 construct address.

#### `POST /orgs/{tenant}/ous`
Registers an AWS Organisational Unit for a tenant line of business.

| Field | Description |
|---|---|
| `tenant` | Tenant identifier (e.g. `cloud-byte`) |
| `ou_name` | Human-readable OU name |
| `parent_ou_id` | AWS OU ID of the parent (root or intermediate OU) |
| `compliance_scope` | One of: `standard`, `hipaa`, `hipaa-pci` — attaches the correct SCP set |

Side effects: creates the OU in AWS Organizations, tags it with the tenant construct label, records the OU ID in DynamoDB under the construct address `{tenant}/ou`.

---

#### `POST /orgs/{tenant}/landing-zones`
Provisions a landing zone — an AWS account vended via Account Factory for Terraform (AFT) or a manually pre-created account — and registers it in the platform catalog.

| Field | Description |
|---|---|
| `tenant` | Tenant identifier |
| `lz_name` | Landing zone name (e.g. `prod-lz`, `dev-lz`) |
| `account_id` | Pre-vended AWS account ID |
| `region` | Primary AWS region |
| `compliance_scope` | Inherited from OU if omitted |

Side effects: applies the baseline Control Tower customisations (SCPs, CloudTrail, Config, GuardDuty baseline) to the account via Terraform, writes the landing zone record to DynamoDB.

---

#### `POST /orgs/{tenant}/environments`
Defines an environment within a landing zone — maps a lifecycle stage (dev / qa / staging / prod) to the account + region.

| Field | Description |
|---|---|
| `tenant` | Tenant identifier |
| `env` | Environment name (e.g. `dev`, `prod`) |
| `lz_name` | Target landing zone |
| `account_id` | AWS account for this environment |
| `region` | AWS region |

Side effects: provisions the shared VPC, subnets, NAT gateways, VPC endpoints, and baseline IAM boundary policies for the environment using the `modules/network/` module. Records the environment in DynamoDB. Writes SSM parameters under `/catalyst/{tenant}/{env}/` so downstream golden paths can resolve account/region without hard-coding.

---

#### `GET /orgs/{tenant}`
Returns the full construct hierarchy for a tenant: OUs, landing zones, environments, and the projects and applications registered within each.

---

### Tier 2 — Service lifecycle golden paths

These paths are called by **application teams** after a platform environment exists. The team provides a construct address; the API handles all underlying AWS decisions.

#### `POST /services/onboard`
Provisions the base AWS resources for a new application service within an existing environment.

| Field | Description |
|---|---|
| `tenant`, `env`, `lz`, `project`, `app` | Full construct address (ADR-002) |
| `service_type` | One of: `web-service`, `worker`, `scheduled-job` |
| `port` | Container port (default 8000 for web-service) |

Side effects: creates ECR repository, ECS task definition skeleton, IAM execution role + least-privilege task role, ALB listener rule (web-service only), CloudWatch log group, DynamoDB idempotency table entry. Returns `{ "ecr_uri", "service_url", "task_role_arn", "status": "provisioned" }`.

Everything provisioned follows the approved module patterns from #7 — no ad-hoc resource creation.

---

#### `POST /services/{construct_address}/deploy`
Deploys a new container image version to an onboarded service.

`construct_address` path format: `{tenant}/{env}/{lz}/{project}/{app}`

| Field | Description |
|---|---|
| `image_tag` | ECR image tag to deploy (e.g. `v1.2.3` or a git SHA) |
| `idempotency_key` | Caller-supplied key; replays with the same key return the original result |

Side effects: registers a new ECS task definition revision with the given image tag, calls `ecs update-service`, waits for service stabilisation (timeout 120 s), records the deployment in DynamoDB with actor, image tag, and timestamp.

---

#### `GET /services/{construct_address}`
Returns current service state.

Response fields: `current_image_tag`, `desired_task_count`, `running_task_count`, `last_deploy_at`, `last_deploy_actor`, `alb_health_status`, `ecr_uri`.

---

#### `POST /services/{construct_address}/config`
Writes application configuration as SSM Parameter Store entries under the standardised path `/catalyst/{tenant}/{env}/{project}/{app}/config/{key}`.

| Field | Description |
|---|---|
| `params` | `{ "KEY": "value", ... }` map — all values stored as `SecureString` encrypted with the environment KMS CMK |
| `idempotency_key` | Prevents duplicate writes on retry |

The application reads config from SSM at runtime. No secrets are passed through the API response.

---

### Deferred (v2)

| Path | Reason deferred |
|---|---|
| `POST /services/{construct_address}/promote` | Environment promotion requires multi-account OIDC trust setup; deferred until ADR-003 environments are fully provisioned |
| `DELETE /services/{construct_address}` | Decommission path has destructive side effects requiring a multi-step confirmation flow; too risky for v1 |
| `POST /orgs/{tenant}/projects` | Project-level registration is implicit in `onboard` for v1; explicit project catalog is a v2 concern |
| `GET /services/{construct_address}/logs` | CloudWatch Logs Insights query surface; useful but not in scope for the challenge submission |

---

## API contract conventions

- All endpoints require SigV4 request signing (`Authorization: AWS4-HMAC-SHA256 ...`). Callers sign requests with their IAM credentials — the CLI uses `aws-requests-auth`, GitHub Actions uses credentials from the OIDC-assumed role. The API verifies identity server-side via `sts:GetCallerIdentity` and resolves IAM group membership to determine role (ADR-008). No long-lived API keys; no bearer tokens.
- All write endpoints accept an `idempotency_key` field. Replays within 24 hours return the original response with `X-Idempotent-Replay: true`.
- All responses include `correlation_id` for log tracing.
- Error shape: `{ "error": "...", "correlation_id": "...", "docs_url": "..." }` — consistent across all 4xx/5xx.
- Construct address validation is applied at the API boundary using the rules from ADR-002. Requests with unknown tenant/lz combinations are rejected 422 before any AWS call is made.

---

## Consequences

**Positive**
- Application teams need zero AWS or Terraform knowledge to provision and deploy a service — one API call, one set of credentials.
- All provisioned resources follow approved patterns; no snowflake configurations escape into production accounts.
- The Tier 1 / Tier 2 split makes the ownership boundary explicit: platform team owns the hierarchy, app teams own their service lifecycle.
- Idempotent writes make CI/CD pipelines safe to retry without manual cleanup.

**Negative / trade-offs**
- `POST /services/onboard` is slow (Terraform-backed provisioning takes 2–5 minutes). Callers must poll `GET /services/{construct_address}` or accept an async 202 response pattern.
- The approved `service_type` enumeration limits flexibility — teams with unusual patterns (e.g. gRPC services, sidecar meshes) cannot self-serve and must engage the platform team.
- Account vending in Tier 1 (`POST /orgs/{tenant}/landing-zones`) depends on AFT or pre-created accounts. The API cannot create AWS accounts itself; it registers and configures them.

---

## References

- [ADR-002 — Tenant → Environment → LandingZone → Project → Application hierarchy](ADR-002-construct-hierarchy.md)
- [ADR-003 — Static and ephemeral environments](ADR-003-static-and-ephemeral-environments.md)
- [ADR-006 — CI/CD pipeline architecture](ADR-006-cicd-pipeline-architecture.md)
- Service umbrella: [#18](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/18)
- Infrastructure umbrella: [#7](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/7)
