# Catalyst smoke tests

Quick-fire checks that the deployed Catalyst stack is alive and serving traffic.
Run these after any `terraform.yml` or `service-cd.yml` apply, after a
`teardown-scheduled.yml` rebuild, or as the first step of an interview demo.

Every test below is **read-only** and safe to run repeatedly.

## Prerequisites

```powershell
# Load bootstrap env (AWS_REGION, AWS_ACCOUNT_ID, creds for local validation)
Get-Content .env | Where-Object { $_ -match '^[A-Z]' } | ForEach-Object {
  $k,$v = $_ -split '=',2
  Set-Item -Path "env:$k" -Value $v
}

# Verify auth
aws sts get-caller-identity
```

> **Caller IP must be on the ingress allowlist.** The ALB security group is
> locked to `CATALYST_API_INGRESS_ALLOWLIST` (default `["73.239.59.22/32"]`).
> If your test request times out at the ALB, your egress IP is not on the
> allowlist. Add it with:
> ```powershell
> gh variable set CATALYST_API_INGRESS_ALLOWLIST --repo Cloud-Byte-Consulting/Catalyst --body '["73.239.59.22/32","<your-ip>/32"]'
> gh workflow run terraform.yml --ref release --repo Cloud-Byte-Consulting/Catalyst
> ```

## Tier 1 — Infrastructure liveness (read-only AWS calls)

```powershell
# Lambda function exists and is in 'Active' state
aws lambda get-function --function-name catalyst-api --query 'Configuration.[State,LastUpdateStatus,Runtime]' --output table

# ALB is active
aws elbv2 describe-load-balancers --names catalyst-alb --query 'LoadBalancers[0].[State.Code,DNSName]' --output table

# ALB target group reports the Lambda as healthy
$tgArn = aws elbv2 describe-target-groups --query 'TargetGroups[?contains(TargetGroupName, `catalyst`)].TargetGroupArn' --output text
aws elbv2 describe-target-health --target-group-arn $tgArn --query 'TargetHealthDescriptions[].TargetHealth.State' --output text

# DynamoDB platform-state table is ACTIVE
aws dynamodb describe-table --table-name catalyst-platform-state --query 'Table.TableStatus' --output text

# ECR has at least one image
aws ecr list-images --repository-name catalyst-api --query 'imageIds[].imageTag' --output text
```

Expected output across all five: `Active` / `active` / `healthy` / `ACTIVE` /
at least one tag (usually `latest` + the commit SHA).

## Tier 2 — HTTP smoke (ALB → Lambda)

```powershell
$albDns = aws elbv2 describe-load-balancers --names catalyst-alb --query 'LoadBalancers[0].DNSName' --output text

# Liveness
curl "http://$albDns/health"

# OpenAPI spec
curl "http://$albDns/openapi.json" | jq '.info.title'

# Resource catalog (unauthenticated when CATALYST_AUTH_MODE=headers)
curl "http://$albDns/catalog" | jq '.resources | length'
```

Expected: `{"status":"ok"}` on `/health`, a non-empty title from `/openapi.json`,
and a numeric resource count from `/catalog` (12 entries match the canonical
`RESOURCE_CATALOG` in `services/catalyst-api/catalyst/catalog.py`).

## Tier 3 — Golden-path validation (authenticated, optional)

When `CATALYST_AUTH_MODE=sigv4`, the API verifies callers via a presigned
`sts:GetCallerIdentity` URL passed in the `x-catalyst-identity-url` header
(see `services/catalyst-api/catalyst/identity.py` and ADR-008). The caller
generates the presigned URL with their AWS credentials; the API fetches it
to confirm the caller's IAM identity, then resolves the caller's RBAC role
via `iam:ListGroupsForUser`.

Skip for interview demos; useful before a release.

```powershell
# Generate a presigned GetCallerIdentity URL (requires AWS credentials set in env)
$region = "us-east-1"
$presignedUrl = aws sts get-caller-identity --output json --debug 2>&1 |
    Select-String "Making request for OperationModel" |
    ForEach-Object { $_.ToString() }   # see identity.py for the canonical helper

# Hit a real route (use any Tier 1 / Tier 2 path from main.py — e.g. GET /orgs/{tenant})
curl -H "x-catalyst-identity-url: $presignedUrl" "http://$albDns/orgs/catalyst"
```

The canonical caller is `clients/catalyst-cli/` (which constructs the
presigned URL via boto3's `generate_presigned_url`) or the GitHub Action
in `.github/actions/catalyst-api/`. Hand-crafting the presigned URL with
awscurl + STS is not directly supported because awscurl signs the target
URL itself rather than producing a presigned STS URL to forward; use the
CLI or Action for end-to-end verification.

## Failure triage

| Symptom | Likely cause | Fix |
|---|---|---|
| `lambda get-function` returns `NoSuchEntity` | Terraform apply ran with `CATALYST_LAMBDA_IMAGE_SEEDED=false` and stopped before phase 2 | Re-check `gh variable list`; if false, set to true and re-run `terraform.yml` |
| Target group state = `unused` | Lambda exists but not wired to ALB target group | Inspect `module.ecs_alb` resources in state; usually means a partial apply |
| Target group state = `unhealthy` | Lambda is returning 5xx on the health check path | `aws logs tail /aws/lambda/catalyst-api --follow` |
| HTTP request times out | Your IP isn't on `CATALYST_API_INGRESS_ALLOWLIST` | `gh variable set CATALYST_API_INGRESS_ALLOWLIST --repo Cloud-Byte-Consulting/Catalyst --body '["73.239.59.22/32","<your-ip>/32"]'` then `gh workflow run terraform.yml --ref release` |
| HTTP returns 502 | Lambda cold-start error or handler exception | CloudWatch logs as above |
| ECR `list-images` returns empty | `service-cd.yml` never built a real image | Trigger `service-cd.yml` with `runtime=lambda` |
| DynamoDB table missing | Bootstrap was rolled back or never completed | Re-run `scripts/bootstrap-aws-account.sh` (idempotent) |

## CI smoke

`ci-smoke.yml` runs on every PR touching `.github/**` and on manual dispatch.
It validates workflow structure and (when `AWS_ROLE_PLAN_ARN` is set) does an
OIDC role-assume + `sts:GetCallerIdentity` call. Treat a green ci-smoke run as
proof the OIDC + role-trust chain is intact.

```powershell
gh workflow run ci-smoke.yml --ref release --repo Cloud-Byte-Consulting/Catalyst
gh run watch --repo Cloud-Byte-Consulting/Catalyst
```
