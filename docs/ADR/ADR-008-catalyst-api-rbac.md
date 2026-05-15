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

**`CatalystOwnerPolicy`** — attached to `catalyst-owners`
```json
{
  "Statement": [
    {
      "Sid": "CatalystApiFullAccess",
      "Effect": "Allow",
      "Action": "execute-api:Invoke",
      "Resource": "arn:aws:execute-api:{region}:{account}:{api-id}/*/*/*"
    },
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

**`CatalystAdministratorPolicy`** — attached to `catalyst-administrators`

Full read across all endpoints + Tier 2 service lifecycle writes. No Tier 1 structural writes; no access management.

```json
{
  "Statement": [
    {
      "Sid": "CatalystApiFullRead",
      "Effect": "Allow",
      "Action": "execute-api:Invoke",
      "Resource": "arn:aws:execute-api:{region}:{account}:{api-id}/*/GET/*"
    },
    {
      "Sid": "CatalystApiServiceWrites",
      "Effect": "Allow",
      "Action": "execute-api:Invoke",
      "Resource": [
        "arn:aws:execute-api:{region}:{account}:{api-id}/*/POST/services/*"
      ]
    }
  ]
}
```

**`CatalystViewerPolicy`** — attached to `catalyst-viewers`
```json
{
  "Statement": [
    {
      "Sid": "CatalystApiReadOnly",
      "Effect": "Allow",
      "Action": "execute-api:Invoke",
      "Resource": "arn:aws:execute-api:{region}:{account}:{api-id}/*/GET/*"
    }
  ]
}
```

---

### API-side enforcement (defence in depth)

IAM policy at the API Gateway / ALB level is the primary gate. FastAPI adds a second enforcement layer so requests that reach the application via internal network are still rejected:

1. Requests carry `Authorization: AWS4-HMAC-SHA256 ...` (SigV4) generated by the CLI or GitHub Action using the caller's IAM credentials.
2. The API calls `sts:GetCallerIdentity` to resolve the caller's ARN.
3. The API calls `iam:ListGroupsForUser` to determine group membership. Result is cached in-process for 5 minutes per ECS task.
4. The resolved role is checked against the permission matrix. If insufficient, the API returns:
```json
{
  "error": "insufficient_permissions",
  "required_role": "owner",
  "caller_role": "administrator",
  "correlation_id": "..."
}
```

---

### Access management endpoint

Only Owners can manage group membership through the API:

```
POST /iam/groups/{group}/members
  Body: { "user_arn": "arn:aws:iam::123456789:user/jane", "action": "add" | "remove" }

GET /iam/groups
  Returns: group name + member count for each group (all roles can call this)
```

The ECS task role has `iam:AddUserToGroup` and `iam:RemoveUserFromGroup` scoped to the three Catalyst groups only. Member ARNs are not returned in any GET response — group membership enumeration is restricted to the AWS console or Owner-level Terraform.

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
- `iam:ListGroupsForUser` per request (mitigated by 5-minute in-memory cache; cold on ECS task restart).
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
