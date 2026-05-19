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

# Catalog list (unauthenticated demo endpoint)
curl "http://$albDns/catalog/products" | jq '.products | length'
```

Expected: `{"status":"ok"}` on `/health`, a non-empty title from `/openapi.json`,
and a numeric product count from `/catalog/products`.

## Tier 3 — Golden-path validation (authenticated, optional)

The full Tier 2 service-lifecycle path requires SigV4-signed requests under
`CATALYST_AUTH_MODE=sigv4`. Skip for interview demos; useful before a release.

```powershell
# Smoke a signed request with awscurl (pip install awscurl)
awscurl --service execute-api --region us-east-1 "http://$albDns/v1/applications" -X GET
```

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

## Programmatic CLI smoke (alternative to Tier 2 curl path)

The Catalyst CLI ships an opt-in pytest live-smoke suite that exercises
the same endpoints as the Tier 2 curl commands but with pytest's
fixture infrastructure and assertion introspection. Useful as a single
command pre-demo or post-deploy.

```powershell
$env:CATALYST_API_ENDPOINT = "http://$albDns"
pytest -m live clients/catalyst-cli/tests -v
```

The suite auto-skips when `CATALYST_API_ENDPOINT` is unset, so the
default `pytest clients/catalyst-cli/tests` invocation (used in CI)
stays hermetic. Tests:

| Test | Verifies |
|---|---|
| `test_live_health_returns_status_ok` | GET /health returns `{"status":"ok"}` |
| `test_live_catalog_returns_canonical_resources` | GET /catalog count matches `services/catalyst-api/catalyst/catalog.py` `RESOURCE_CATALOG` |
| `test_live_services_status_invalid_address_rejected` | CLI pre-flight rejects malformed construct addresses before HTTP |
| `test_live_render_round_trips_health` | `render()` helper produces stable JSON for live data |

The CLI test suite is gated at **80% coverage** in CI (`--cov-fail-under=80`);
see `.github/workflows/pr-checks.yml` cli-tests job.

## End-to-end regression suite

For the full six-journey regression suite (Track A operator bootstrap,
Track B tenant register, Track C app onboard, idempotency, RBAC, auth
modes) see [`docs/e2e-testing.md`](./e2e-testing.md). That suite runs
in mock mode on every PR via `pr-checks.yml` and can be re-pointed at
a live stack via `CATALYST_E2E_LIVE=1 + CATALYST_API_ENDPOINT=...`,
giving the same coverage as the curl probes above with assertion
introspection instead of jq parsing.

## CI smoke

`ci-smoke.yml` runs on every PR touching `.github/**` and on manual dispatch.
It validates workflow structure and (when `AWS_ROLE_PLAN_ARN` is set) does an
OIDC role-assume + `sts:GetCallerIdentity` call. Treat a green ci-smoke run as
proof the OIDC + role-trust chain is intact.

```powershell
gh workflow run ci-smoke.yml --ref release --repo Cloud-Byte-Consulting/Catalyst
gh run watch --repo Cloud-Byte-Consulting/Catalyst
```
