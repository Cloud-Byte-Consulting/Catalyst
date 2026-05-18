# Track C — Application-service onboarding

**Audience:** Platform engineer or app team member (Owner or Administrator role per [ADR-008](../ADR/ADR-008-catalyst-api-rbac.md)) provisioning runtime resources for a single application service.
**Outcome:** Application service provisioned at a construct address (`tenant/env/lz/project/app`); deploy and config endpoints unlocked.
**Architectural decision:** [ADR-012](../ADR/ADR-012-onboarding-experience.md).

## Prerequisites

| Prerequisite | Verification |
|---|---|
| Track A complete | Catalyst API responds at the ALB endpoint |
| Track B complete for your construct path | `GET /orgs/{tenant}` returns the landing zone + environment you'll target |
| Your IAM user is in `catalyst-owners` or `catalyst-administrators` | `aws iam list-groups-for-user --user-name <you>` |
| Your egress IP is on the allowlist (if calling from a workstation) | `gh variable list --repo Cloud-Byte-Consulting/Catalyst` |

## Three equivalent call surfaces

The Tier 2 onboard contract is callable from any of:

| Surface | When to use | Detail |
|---|---|---|
| **CLI** (`python catalyst_cli.py services onboard ...`) | Local invocation; ad-hoc onboarding | `clients/catalyst-cli/` |
| **HTTP API** (curl + presigned URL) | Cross-language scripts; CI pipelines without GitHub Actions | `POST /services/onboard` |
| **GitHub Action** (`.github/actions/catalyst-api`) | Onboard from another repo's pipeline | Composite action; uses OIDC role |

All three enforce the same RBAC and validation. Pick the one that matches your context.

## Step 1 — Pick a construct address

```
tenant / env / landing-zone / project / app
```

The pattern is enforced by `CONSTRUCT_RE` in `clients/catalyst-cli/catalyst_cli.py:32` and `catalyst/main.py`. All five segments are lowercase alphanumeric + hyphens. Example:

```
cloud-byte/dev/shared/my-project/my-app
```

The first three segments (`tenant/env/landing-zone`) MUST exist in the Tier 1 catalog (created in Track B). Track C creates entries for the `project/app` segments and provisions the runtime resources.

## Step 2 — Set CLI environment

```powershell
$env:CATALYST_API_ENDPOINT = "http://catalyst-alb-xxxxxxxxxx.us-east-1.elb.amazonaws.com"
$env:CATALYST_AUTH         = "presigned-sts"
$env:AWS_REGION            = "us-east-1"
# AWS credentials must be active and your principal must be in catalyst-owners or catalyst-administrators
```

## Step 3 — Onboard via CLI (preferred)

```bash
python clients/catalyst-cli/catalyst_cli.py services onboard cloud-byte/dev/shared/my-project/my-app
```

Optional flags (see `catalyst_cli.py:services_onboard_command`):

| Flag | Default | Notes |
|---|---|---|
| `--idempotency-key` | unset (recommended to supply) | 24h replay semantics per [ADR-007](../ADR/ADR-007-catalyst-api-golden-paths.md) |

The CLI auto-generates a presigned `sts:GetCallerIdentity` URL and attaches it under `x-catalyst-identity-url`. The API server fetches the URL to confirm caller identity, then resolves your IAM groups for the RBAC check (Owner / Administrator both allowed for onboard; Viewer denied).

## Step 3 (alternative) — Onboard via HTTP

```bash
PRESIGNED_URL=$(python -c "import boto3,os; print(boto3.client('sts', region_name=os.environ['AWS_REGION']).generate_presigned_url('get_caller_identity', Params={}, ExpiresIn=60, HttpMethod='GET'))")

curl -sS -X POST "${CATALYST_API_ENDPOINT}/services/onboard" \
  -H "Content-Type: application/json" \
  -H "x-catalyst-identity-url: ${PRESIGNED_URL}" \
  -d '{
    "construct_address": "cloud-byte/dev/shared/my-project/my-app",
    "service_type": "web-service",
    "port": 8000,
    "idempotency_key": "onboard-my-app-001"
  }'
```

## Step 3 (alternative) — Onboard via GitHub Action from another repo

In your application repo's workflow:

```yaml
permissions:
  id-token: write
  contents: read

jobs:
  onboard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.CATALYST_ACTION_ROLE_ARN }}
          aws-region: us-east-1
      - uses: Cloud-Byte-Consulting/Catalyst/.github/actions/catalyst-api@release
        with:
          operation: services/onboard
          construct_address: cloud-byte/dev/shared/my-project/my-app
          idempotency_key: onboard-${{ github.run_id }}
```

`CATALYST_ACTION_ROLE_ARN` is an OIDC role you set up separately in your application repo's AWS account; it needs membership in `catalyst-administrators` to onboard. See `.github/actions/catalyst-api/README.md` for the full action interface.

## Step 4 — Verify

```bash
python clients/catalyst-cli/catalyst_cli.py services status cloud-byte/dev/shared/my-project/my-app
```

Expected response: 200 with `construct_address`, `service_type`, `status`, and resource ARNs (which may be stubbed in v1; see [ADR-007](../ADR/ADR-007-catalyst-api-golden-paths.md) §Consequences).

## Post-onboard lifecycle

Once onboard succeeds, the construct address unlocks three additional Tier 2 operations:

| Operation | CLI | API |
|---|---|---|
| Deploy a new image | `python catalyst_cli.py services deploy <addr>` (when added) | `POST /services/{construct_address}/deploy` |
| Update config | (not yet in CLI) | `POST /services/{construct_address}/config` |
| Get status | `python catalyst_cli.py services status <addr>` | `GET /services/{construct_address}` |

Application deploy pipelines from your app repo SHOULD use the deploy OIDC role and reference the construct address in run labels and tracking issues — never long-lived AWS keys.

## RBAC matrix (Tier 2, per [ADR-008](../ADR/ADR-008-catalyst-api-rbac.md))

| Operation | Owner | Administrator | Viewer |
|---|:-:|:-:|:-:|
| `POST /services/onboard` | ✅ | ✅ | ❌ (403) |
| `POST /services/{addr}/deploy` | ✅ | ✅ | ❌ |
| `POST /services/{addr}/config` | ✅ | ✅ | ❌ |
| `GET /services/{addr}` | ✅ | ✅ | ✅ |

A Viewer attempting any of the `POST` operations receives `403 Forbidden` with a clear "insufficient permissions" message naming the required group.

## Audit trail

Open a GitHub issue with the `type/onboarding` label for each significant service onboarding. Suggested labels:

```
type/onboarding, kind/service, tenant/<tenant>, env/<env>, project/<project>, app/<app>
```

Include in the body:

- Construct address
- Service type + port
- Idempotency keys used
- Reference to the CI run or the CLI invocation
- Any deviations from defaults (custom ALB rules, special task role permissions, etc.)

This makes the onboarding correlation visible in the durable state machine ([ADR-001](../ADR/ADR-001-github-issues-as-state-machine.md)) — handy when something needs to be debugged days later.

## Anti-patterns

- Onboarding a service whose construct address points at a non-existent tenant or environment — the API rejects, and you'll need Track B first
- Hand-creating per-app ECR repositories or IAM roles in the console and then "registering" the construct address via onboard — onboard is responsible for those resources; if they exist out-of-band you create dual ownership
- Using `CATALYST_AUTH=sigv4` — wrong strategy for Catalyst (ALB+Lambda, not API Gateway). Use `presigned-sts`
- Skipping `idempotency_key` — onboard becomes non-idempotent and a retry creates duplicate side-effects
- Calling onboard from an unallowlisted IP — the ALB security group times out before the API ever sees the request

## Verification (acceptance criteria)

```gherkin
Scenario: Administrator onboards a new application service
  Given Tracks A and B are complete for cloud-byte/dev/shared
  And the administrator has CATALYST_AUTH=presigned-sts and an Administrator-group membership
  When the administrator runs `python catalyst_cli.py services onboard cloud-byte/dev/shared/my-project/my-app`
  Then the CLI returns 200 with a construct_address echo and status field
  And GET /services/cloud-byte/dev/shared/my-project/my-app returns the same construct_address
  And subsequent calls to deploy/config no longer fail on "unknown construct"
```

## Related

- [ADR-007](../ADR/ADR-007-catalyst-api-golden-paths.md) — Tier 2 endpoint contract
- [ADR-008](../ADR/ADR-008-catalyst-api-rbac.md) — RBAC matrix + presigned-STS auth
- [ADR-012](../ADR/ADR-012-onboarding-experience.md) — onboarding decision
- [`clients/catalyst-cli/`](../../clients/catalyst-cli/) — CLI source + tests
- [`.github/actions/catalyst-api/`](../../.github/actions/catalyst-api/) — GitHub Action interface
