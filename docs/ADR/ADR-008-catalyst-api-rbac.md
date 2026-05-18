# ADR-008 — Catalyst API RBAC via AWS IAM Groups

**Status**: Accepted · 2026-05-14
**Related**: [ADR-002](ADR-002-construct-hierarchy.md) · [ADR-006](ADR-006-cicd-pipeline-architecture.md) · [ADR-007](ADR-007-catalyst-api-golden-paths.md)

---

## Context

The Catalyst API exposes platform operations at two tiers (ADR-007):
- **Tier 1** — organisational structure (tenants, OUs, landing zones, environments) — structural operations performed by team and lab leaders
- **Tier 2** — service lifecycle (onboard, deploy, status, config) — day-to-day operations performed by platform engineers

Access must be segmented so that:
- Only team/lab leaders can create and modify the platform structure (tenants, applications, landing zones)
- Platform engineers have full visibility into everything running on the platform and can manage services
- Read-only observers can see current state without the ability to mutate anything

The Catalyst API is an AWS-native service. **AWS IAM Groups + scoped IAM policies** provide this segmentation without introducing an external identity provider. Identity is validated at the API boundary using `sts:GetCallerIdentity`.

---

## Decision

### Three IAM groups

| Group name | Role | Who belongs here |
|---|---|---|
| `catalyst-owners` | **Owner** | Team and lab leaders who define the platform structure — they create tenants, applications at the platform level, landing zones, and environments |
| `catalyst-administrators` | **Administrator** | Platform engineers who manage and operate the platform — they have full visibility across everything in Catalyst and manage the service lifecycle |
| `catalyst-viewers` | **Viewer** | Read-only observers — auditors, stakeholders, or app team members who need status visibility without operational access |

All three groups are provisioned by Terraform in `modules/iam/` (TF-7, sub-issue of #7).

---

### Permission matrix

| Endpoint | Owner | Administrator | Viewer |
|---|---|---|---|
| **Tier 1 — structural writes** | | | |
| `POST /orgs/{tenant}/ous` | ✅ | ❌ | ❌ |
| `POST /orgs/{tenant}/landing-zones` | ✅ | ❌ | ❌ |
| `POST /orgs/{tenant}/environments` | ✅ | ❌ | ❌ |
| `POST /orgs/{tenant}/applications` | ✅ | ❌ | ❌ |
| **All GET endpoints (full visibility)** | | | |
| `GET /orgs/{tenant}` | ✅ | ✅ | ✅ |
| `GET /orgs/{tenant}/landing-zones` | ✅ | ✅ | ✅ |
| `GET /orgs/{tenant}/environments` | ✅ | ✅ | ✅ |
| `GET /services/{construct}` | ✅ | ✅ | ✅ |
| `GET /iam/groups` | ✅ | ✅ | ✅ |
| **Tier 2 — service lifecycle writes** | | | |
| `POST /services/onboard` | ✅ | ✅ | ❌ |
| `POST /services/{construct}/deploy` | ✅ | ✅ | ❌ |
| `POST /services/{construct}/config` | ✅ | ✅ | ❌ |
| **Access management** | | | |
| `POST /iam/groups/{group}/members` | ✅ | ❌ | ❌ |

**Key distinctions:**
- Administrators can see everything Owners can see — they have identical GET access. The boundary is write access: Owners write platform structure; Administrators write service lifecycle only.
- Viewers have the same GET access as Administrators. They are differentiated by the inability to call any POST endpoint.

---

### IAM policy design

> **Note on enforcement layer**: The Catalyst API is fronted by an ALB (ADR-009), not API Gateway. ALB does not evaluate `execute-api:Invoke` IAM permissions — it forwards requests regardless of the caller's IAM policies. **RBAC enforcement is application-layer only** (SigV4 verification + STS + IAM group membership check described below). The IAM group policies below grant only the AWS API permissions each role needs to act outside the Catalyst API itself; they do not gate access to the ALB endpoint.

**`CatalystOwnerPolicy`** — attached to `catalyst-owners`

Owners need no special AWS permissions to call the Catalyst API (enforcement is application-side). The policy grants only the IAM management permissions needed to support bootstrapping and GitOps-style Terraform access changes:

```json
{
  "Statement": [
    {
      "Sid": "IamGroupManagement",
      "Effect": "Allow",
      "Action": [
        "iam:AddUserToGroup",
        "iam:RemoveUserFromGroup",
        "iam:GetGroup",
        "iam:ListGroupsForUser"
      ],
      "Resource": [
        "arn:aws:iam::{account}:group/catalyst-owners",
        "arn:aws:iam::{account}:group/catalyst-administrators",
        "arn:aws:iam::{account}:group/catalyst-viewers"
      ]
    }
  ]
}
```

**`CatalystAdministratorPolicy`** and **`CatalystViewerPolicy`** — attached to their respective groups

No additional AWS API permissions are required. Group membership alone determines what the Catalyst API authorises. These policies are empty (`"Statement": []`) in v1; additive permissions (e.g. read-only CloudWatch access for Administrators) can be added as operational needs arise without changing the RBAC model.

---

### API-side enforcement (primary and only gate)

Because the ALB does not enforce IAM caller identity, the FastAPI application is the sole enforcement layer. The production flow is **presigned-STS URL forwarding**, not direct SigV4 request signing:

1. The caller (CLI or GitHub Action) generates a presigned `sts:GetCallerIdentity` URL using their own AWS credentials and attaches it to the API request in the **`x-catalyst-identity-url`** header. The API request itself is not SigV4-signed — the signature lives inside the presigned URL.
2. The API (`services/catalyst-api/catalyst/rbac.py` `_resolve_sigv4`) reads the `x-catalyst-identity-url` header, replays the presigned URL against STS, and parses the returned `<Arn>` to resolve the caller's identity (`catalyst.identity.verify_presigned_identity`).
3. The API calls `iam:ListGroupsForUser` to determine group membership. Result is cached in-process for the `CATALYST_GROUP_CACHE_TTL` window (5 minutes default) per warm execution environment.
4. The resolved role is checked against the permission matrix. If insufficient, the API returns:
```json
{
  "error": "insufficient_permissions",
  "required_role": "owner",
  "caller_role": "administrator",
  "correlation_id": "..."
}
```

> **Why presigned-URL forwarding rather than SigV4-signing the API request directly?** The ALB target is Lambda (ADR-009), not API Gateway. ALB does not validate SigV4 signatures on incoming requests, and the runtime cannot verify a SigV4 signature against the original request body without the caller's secret. Forwarding a presigned URL lets the caller's AWS credentials authenticate the *URL itself* (which STS validates), and the API never sees the caller's secret. The legacy `Authorization: AWS4-HMAC-SHA256 ...` description in earlier drafts of this ADR predated the Lambda runtime decision and was inaccurate.

---

### Naming asymmetry between client and server (#171)

The Catalyst auth env vars use different names on the two sides of the wire for the same flow. New operators routinely get confused by this; the asymmetry is intentional history, not a bug.

| Side | Env var | Value selecting the production flow |
|---|---|---|
| **Server** (`services/catalyst-api/catalyst/rbac.py:150`, via `get_settings().auth_mode`) | `CATALYST_AUTH_MODE` | `sigv4` |
| **Client / CLI** (`clients/catalyst-cli/catalyst_cli.py`) | `CATALYST_AUTH` | `presigned-sts` |

The server reads `CATALYST_AUTH_MODE` via `os.environ.get("CATALYST_AUTH_MODE", "headers").strip().lower()` in `services/catalyst-api/catalyst/settings.py:110`, then exposes it as `Settings.auth_mode` (a frozen dataclass field). The resolution is direct-env-var only — no `.env` file support, no SSM/Secrets parameter fallback for this particular knob. To change it, set the env var on the runtime (Lambda function configuration or ECS task definition).

Both env vars refer to the **same** presigned `sts:GetCallerIdentity` URL flow forwarded in the `x-catalyst-identity-url` header (see `rbac.py:163` and `clients/catalyst-cli/catalyst_cli.py:_call`). The CLI has a separate `CATALYST_AUTH=sigv4` strategy that uses AWS4Auth against `execute-api` — that one is retained for completeness but is not how Catalyst (ALB → Lambda) is wired and is not the production path.

**Why the names differ:** the server-side mode predates the CLI rename. The server's enum value `sigv4` reflects the original RBAC design ("SigV4 request signing"). The CLI's strategy was later renamed `presigned-sts` because that's a more accurate description of what the client actually sends — a presigned URL, not a SigV4-signed direct request. Renaming the server-side value to `presigned-sts` would be a breaking change for deployed environments; that work is tracked separately if anyone wants to take it.

**Operator quick reference:**

```
# Server (Catalyst API runtime):
CATALYST_AUTH_MODE=sigv4

# Client (Catalyst CLI):
CATALYST_AUTH=presigned-sts
# AWS credentials must be available; CLI auto-generates the presigned URL
```

These are the production settings. Both refer to the same flow.

---

### Access management endpoint

Only Owners can manage group membership through the API:

```
POST /iam/groups/{group}/members
  Body: { "user_arn": "arn:aws:iam::123456789:user/jane", "action": "add" | "remove" }

GET /iam/groups
  Returns: group name + member count for each group (all roles can call this)
```

The API runtime role (Lambda execution role for the default runtime; ECS task role for the ECS alternative — see ADR-009) has `iam:AddUserToGroup` and `iam:RemoveUserFromGroup` scoped to the three Catalyst groups only. Member ARNs are not returned in any GET response — group membership enumeration is restricted to the AWS console or Owner-level Terraform.

---

### Terraform resources

```hcl
resource "aws_iam_group" "catalyst_owners"         { name = "catalyst-owners" }
resource "aws_iam_group" "catalyst_administrators" { name = "catalyst-administrators" }
resource "aws_iam_group" "catalyst_viewers"        { name = "catalyst-viewers" }

resource "aws_iam_group_policy_attachment" "owners_policy"  { ... }
resource "aws_iam_group_policy_attachment" "admins_policy"  { ... }
resource "aws_iam_group_policy_attachment" "viewers_policy" { ... }

# At least one owner must exist after bootstrap
resource "aws_iam_user_group_membership" "bootstrap_owner" {
  user   = var.bootstrap_owner_iam_user
  groups = [aws_iam_group.catalyst_owners.name]
}
```

Post-bootstrap, group membership is managed via `POST /iam/groups/{group}/members` (Owner-only) or via Terraform PR for GitOps-style auditable access changes.

---

## Consequences

**Positive**
- Role intent is clear from the names: Owners build and govern the structure; Administrators operate it and see everything; Viewers observe.
- Administrators have full visibility so they can diagnose issues across the entire platform without escalating to an Owner.
- No external identity provider required — pure AWS IAM.
- Group membership is version-controlled in Terraform; access changes are auditable.

**Negative / trade-offs**
- `iam:ListGroupsForUser` per request (mitigated by 5-minute in-memory cache; resets on Lambda cold start or ECS task restart).
- IAM Groups are account-scoped. Multi-account deployments (ADR-002 landing zones) require duplicated group sets per account. IAM Identity Center federation resolves this but is deferred to v2.
- Owners cannot be restricted to a subset of tenants. If tenant isolation between Owner users is needed, ABAC with IAM condition keys is required (deferred).

**Deferred**
- IAM Identity Center (SSO) — central group management across accounts, v2 after multi-account LZs land.
- Per-tenant ABAC scoping — Owner restricted to specific tenants they own; requires IAM condition key `aws:ResourceTag/Tenant`.
- Time-limited access grants (break-glass access for Owners with expiry).

---

## References

- [ADR-002 — Construct hierarchy](ADR-002-construct-hierarchy.md)
- [ADR-007 — Catalyst API golden paths](ADR-007-catalyst-api-golden-paths.md)
- Service umbrella: [#18](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/18)
- Infrastructure / IAM module: [#7](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/7) (TF-7 sub-issue)
- AWS docs: [IAM Groups](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_groups.html) · [STS GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html)
