# Track B — Organization / tenant onboarding

**Audience:** Team / lab leader (Owner role per [ADR-008](../ADR/ADR-008-catalyst-api-rbac.md)) registering a new tenant, landing zone, or environment.
**Outcome:** Construct hierarchy recorded in the Catalyst control plane; environments resolvable; Tier 2 (application) onboarding unblocked.
**Architectural decision:** [ADR-012](../ADR/ADR-012-onboarding-experience.md).

## Prerequisites

| Prerequisite | Verification |
|---|---|
| Track A (platform onboarding) complete | `curl http://$albDns/health` returns `{"status":"ok"}` from an allowlisted IP |
| Your IAM user is in `catalyst-owners` | `aws iam list-groups-for-user --user-name <you>` includes `catalyst-owners` |
| Your egress IP is on `CATALYST_API_INGRESS_ALLOWLIST` | `gh variable list --repo Cloud-Byte-Consulting/Catalyst` shows your `/32` |
| AWS credentials active locally | `aws sts get-caller-identity` returns your principal |

If you don't have Owner-group membership, ask a platform engineer to add you via `POST /iam/groups/{group}/members` or a Terraform PR to `infrastructure/modules/iam`.

## What you'll create

A tenant typically maps 1:1 to an organization or business unit. Underneath, the hierarchy is:

```
tenant
  └── landing-zone     (AWS account + compliance scope — HIPAA, PCI-DSS, baseline)
        └── environment   (dev / stage / prod lifecycle stage)
              └── project    (codename for an initiative)
                    └── application   (specific service unit at the construct address)
```

Track B creates everything down to the **environment** level (and optionally project / application catalog entries). The actual app *runtime* resources happen in Track C.

## Auth setup

Production auth is `CATALYST_AUTH=presigned-sts` (per [ADR-008](../ADR/ADR-008-catalyst-api-rbac.md) and the CLI auth flow). The CLI auto-generates the presigned `sts:GetCallerIdentity` URL when AWS credentials are available and forwards it in the `x-catalyst-identity-url` header.

```powershell
$env:CATALYST_API_ENDPOINT = "http://catalyst-alb-xxxxxxxxxx.us-east-1.elb.amazonaws.com"
$env:CATALYST_AUTH         = "presigned-sts"
$env:AWS_REGION            = "us-east-1"
# AWS credentials must already be active (aws sts get-caller-identity)
```

The CLI exposes the Tier 1 `orgs` commands directly (added in PR #169 / closes that). The examples below use the CLI as the primary path; curl equivalents are in the [Alternatives appendix](#alternatives-curl-against-the-api) for environments where the CLI isn't available.

## Step 1 — Register a landing zone

A landing zone scopes IAM, cost, and compliance for a tenant.

```bash
# AWS_ACCOUNT_ID comes from your .env (or `aws sts get-caller-identity --query Account --output text`)
# In CI it pairs with the BOOTSTRAP_AWS_ACCOUNT_ID repo variable
python clients/catalyst-cli/catalyst_cli.py orgs landing-zones create \
  --tenant cloud-byte \
  --name shared \
  --account-id "$AWS_ACCOUNT_ID" \
  --compliance standard \
  --idempotency-key lz-shared-001
```

Expected response: 201 with `landing_zone_id`, `construct_address` (`cloud-byte/shared`), and `status: provisioned`.

## Step 2 — Register an environment

```bash
python clients/catalyst-cli/catalyst_cli.py orgs environments create \
  --tenant cloud-byte \
  --name dev \
  --landing-zone shared \
  --idempotency-key env-dev-001
```

The environment write also seeds shared SSM paths under `/catalyst/{tenant}/{env}/` that Track C reads when provisioning per-app resources.

## Step 3 — (Optional) Register OUs or applications

For multi-OU topologies:

```bash
python clients/catalyst-cli/catalyst_cli.py orgs ous create \
  --tenant cloud-byte \
  --name engineering \
  --idempotency-key ou-eng-001
```

For pre-catalog application entries (without a runtime yet):

```bash
python clients/catalyst-cli/catalyst_cli.py orgs applications create \
  --tenant cloud-byte \
  --project my-project \
  --name my-app \
  --idempotency-key app-my-app-001
```

## Step 4 — Verify the hierarchy

```bash
python clients/catalyst-cli/catalyst_cli.py orgs get --tenant cloud-byte
```

Expected response: JSON with `tenant`, `landing_zones`, `environments`, `applications` arrays reflecting Steps 1-3.

This `GET` is the **source-of-truth check** Track C uses. `POST /services/onboard` rejects unknown construct addresses, so the hierarchy must be in place before any application onboarding.

## Audit trail

Open a GitHub issue with the `type/onboarding` label for each significant tenant or environment registration. The issue body should include:

- The construct address being created
- Compliance scope (standard / hipaa / pci-dss)
- Idempotency keys used
- A reference to the run (`gh run view ...`) if the call went through CI

This puts approval, evidence, and correlation IDs into the durable state machine ([ADR-001](../ADR/ADR-001-github-issues-as-state-machine.md)). Suggested labels:

```
type/onboarding, kind/service, tenant/<tenant>, env/<env>, project/<project>
```

## Verification (acceptance criteria)

```gherkin
Scenario: Owner registers a new tenant + environment
  Given the operator has CATALYST_AUTH=presigned-sts and an Owner-group membership
  When the operator POSTs landing-zone + environment to /orgs/cloud-byte/...
  Then GET /orgs/cloud-byte returns the new entries
  And SSM parameters under /catalyst/cloud-byte/dev/ exist (where applicable)
  And POST /services/onboard with construct cloud-byte/dev/shared/.../... no longer fails on "unknown construct address"
```

## Anti-patterns

- Skipping the landing-zone registration and trying to onboard a service directly (Track C will reject the construct address)
- Hand-editing the catalog DynamoDB table to create a tenant — bypass the API and you lose the idempotency + RBAC layer
- Using `CATALYST_AUTH=sigv4` for these calls — the API server's RBAC layer reads `x-catalyst-identity-url`, not the SigV4 signature on the request itself
- Calling these endpoints from an unallowlisted IP — the ALB security group will time out the request before authn runs

## Next track

Once the hierarchy is in place, hand off to [`application.md`](./application.md) for Track C (per-app runtime resources).

## Alternatives — curl against the API

Use these only if the CLI is unavailable in your environment. Both approaches hit the same endpoints with the same `x-catalyst-identity-url` header pattern; the CLI just packages the boto3 presigning + HTTP call.

```bash
# Generate the presigned STS URL (one-liner using boto3)
PRESIGNED_URL=$(python -c "import boto3,os; print(boto3.client('sts', region_name=os.environ['AWS_REGION']).generate_presigned_url('get_caller_identity', Params={}, ExpiresIn=60, HttpMethod='GET'))")

# Landing zone
curl -sS -X POST "${CATALYST_API_ENDPOINT}/orgs/cloud-byte/landing-zones" \
  -H "Content-Type: application/json" \
  -H "x-catalyst-identity-url: ${PRESIGNED_URL}" \
  -d "{\"tenant\":\"cloud-byte\",\"name\":\"shared\",\"account_id\":\"${AWS_ACCOUNT_ID}\",\"compliance\":\"standard\",\"idempotency_key\":\"lz-shared-001\"}"

# Environment
curl -sS -X POST "${CATALYST_API_ENDPOINT}/orgs/cloud-byte/environments" \
  -H "Content-Type: application/json" \
  -H "x-catalyst-identity-url: ${PRESIGNED_URL}" \
  -d '{"tenant":"cloud-byte","name":"dev","landing_zone":"shared","idempotency_key":"env-dev-001"}'

# Verify
curl -sS "${CATALYST_API_ENDPOINT}/orgs/cloud-byte" \
  -H "x-catalyst-identity-url: ${PRESIGNED_URL}"
```

The presigned URL expires in 60 seconds by default; regenerate per request batch.

## Future Terraform path

The curl + CLI flow above is the **bootstrap** path. Once a tenant's IAM groups, SSM tree, and per-env VPCs are stable, the equivalent provisioning is available declaratively via [`infrastructure/modules/composite/tenant-onboarding/`](../../infrastructure/modules/composite/tenant-onboarding/README.md) (#168). That composite emits the same SSM parameters under `/catalyst/{tenant}/{env}/`, the tenant-scoped IAM groups described in [ADR-008 § Tenant-scoped groups (no project)](../ADR/ADR-008-catalyst-api-rbac.md#tenant-scoped-groups-no-project), and conditionally applies AWS Network Firewall per [ADR-010](../ADR/ADR-010-egress-control.md). The Terraform path is the eventual long-term home for Tier 1 onboarding; the API flow above remains supported for pilot tenants and demo flows.

## Related

- [ADR-007](../ADR/ADR-007-catalyst-api-golden-paths.md) — Tier 1 endpoint contract
- [ADR-008](../ADR/ADR-008-catalyst-api-rbac.md) — RBAC + SigV4-presigned identity
- [ADR-012](../ADR/ADR-012-onboarding-experience.md) — onboarding decision
- [`docs/smoke-tests.md`](../smoke-tests.md) Tier 2 — verification commands
