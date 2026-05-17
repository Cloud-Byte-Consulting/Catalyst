# Catalyst demo teardown runbook

How to destroy and re-provision Terraform-managed Catalyst resources. Intended for demo and development environments where cost savings matter between working sessions.

## What gets destroyed vs. what survives

| Resource tier | Destroyed? | Notes |
|---|---|---|
| VPC, subnets, NAT gateway | Yes | Recreated on next `terraform apply` |
| Security groups, ALB | Yes | Recreated on next `terraform apply` |
| ECR repository | Yes | Image must be re-pushed by `service-cd.yml` |
| ECS cluster + service | Yes | Recreated on next `terraform apply` |
| Lambda function | Yes | Recreated after ECR is re-seeded |
| DynamoDB platform-state table | Yes | Recreated on next `terraform apply` |
| **IAM roles** (`catalyst-github-*`) | **No** | Bootstrap tier — cost $0 |
| **GitHub OIDC provider** | **No** | Bootstrap tier — cost $0 |
| **S3 state bucket** (`catalyst-tf-state-*`) | **No** | Bootstrap tier — cost $0; holds Terraform state |
| **DynamoDB lock table** (`catalyst-terraform-locks`) | **No** | Bootstrap tier — cost $0 |

`terraform destroy` only removes resources tracked in the Terraform state file. Bootstrap resources were provisioned by `scripts/bootstrap-aws-account.sh` (not Terraform) so they are invisible to `terraform destroy`.

---

## Option A — Scheduled automatic teardown (recommended for demos)

`teardown-scheduled.yml` runs automatically at **22:00 UTC Mon–Fri** and destroys all Terraform-managed resources. No action required from the operator.

To change the schedule without a code change, set a GitHub Actions repository variable:

```bash
# Example: move to midnight UTC on weekdays
gh variable set TEARDOWN_CRON_SCHEDULE \
  --repo Cloud-Byte-Consulting/Catalyst \
  --body "0 0 * * 1-5"
```

> **Note:** The workflow reads `vars.TEARDOWN_CRON_SCHEDULE` if set. The default baked into the workflow YAML is `0 22 * * 1-5`. Changes to a repository variable take effect on the next cron firing without a code push.

### What the scheduled run does

1. Emits a pre-destroy manifest (list of all resources in state) to the job summary.
2. Runs `terraform destroy -auto-approve`.
3. Leaves the S3 state file empty and consistent.
4. Resets the `CATALYST_LAMBDA_IMAGE_SEEDED` repo variable to `false`.

---

## Option B — Manual on-demand teardown (dispatch)

### Via `teardown-scheduled.yml` (no confirmation required)

Use this when you want to tear down immediately without waiting for the cron:

```bash
gh workflow run teardown-scheduled.yml \
  --repo Cloud-Byte-Consulting/Catalyst \
  --ref release
```

Watch the run:

```bash
gh run watch --repo Cloud-Byte-Consulting/Catalyst
```

### Via `teardown.yml` (requires confirmation input)

The original human-gated workflow. Useful when you want an explicit confirmation step in the audit trail:

```bash
gh workflow run teardown.yml \
  --repo Cloud-Byte-Consulting/Catalyst \
  --ref release \
  --field confirmation=destroy
```

---

## Re-provisioning after teardown

Once the state file is empty, re-provisioning is a two-step sequence.

### Step 1 — Apply the Terraform platform stack

```bash
gh workflow run terraform.yml \
  --ref release \
  --repo Cloud-Byte-Consulting/Catalyst

gh run watch --repo Cloud-Byte-Consulting/Catalyst
```

This creates VPC, subnets, NAT, security groups, ECR, ECS cluster, ALB, DynamoDB platform-state table. It does **not** create the Lambda function yet (the ECR image must exist first).

### Step 2 — Build and push the Catalyst API image

```bash
gh workflow run service-cd.yml \
  --ref release \
  --repo Cloud-Byte-Consulting/Catalyst

gh run watch --repo Cloud-Byte-Consulting/Catalyst
```

This seeds ECR with `:latest`. The Lambda function cannot be provisioned until this completes.

### Step 3 — Flip the Lambda image-seeded flag

```bash
gh variable set CATALYST_LAMBDA_IMAGE_SEEDED \
  --repo Cloud-Byte-Consulting/Catalyst \
  --body true
```

### Step 4 — Re-apply to bring Lambda online

```bash
gh workflow run terraform.yml \
  --ref release \
  --repo Cloud-Byte-Consulting/Catalyst

gh run watch --repo Cloud-Byte-Consulting/Catalyst
```

The Lambda function is now live.

---

## Running teardown locally (without GitHub Actions)

If GitHub Actions is unavailable, run teardown locally using the AWS CLI with admin credentials.

### Prerequisites

- AWS CLI v2 authenticated as an admin principal (see `docs/operator-bootstrap.md` Step 2)
- Terraform CLI installed
- Local environment variables set

```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CATALYST_PREFIX=catalyst
```

### Dry run (plan what would be destroyed)

```bash
terraform -chdir=infrastructure init \
  -backend-config="bucket=${CATALYST_PREFIX}-tf-state-${ACCOUNT_ID}-${AWS_REGION}" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="dynamodb_table=${CATALYST_PREFIX}-terraform-locks"

terraform -chdir=infrastructure plan -destroy
```

### Destroy

```bash
terraform -chdir=infrastructure destroy
```

Terraform prompts for confirmation — type `yes`.

After local destroy, reset the seeded flag manually:

```bash
gh variable set CATALYST_LAMBDA_IMAGE_SEEDED \
  --repo Cloud-Byte-Consulting/Catalyst \
  --body false
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `terraform destroy` fails mid-run with `BucketNotEmpty` | ECR or S3 bucket has `force_destroy = false` | Set `force_destroy = true` in the relevant Terraform module and apply before re-running destroy |
| `terraform destroy` fails mid-run with `DependencyViolation` | Security group still attached to an ENI | Wait 2–3 minutes and retry; ENIs attached to Lambda or ECS tasks drain asynchronously |
| State file looks inconsistent after a partial destroy | Destroy exited non-zero mid-run | Run `terraform plan -destroy` to see what remains; then `terraform destroy` again to finish |
| `CATALYST_LAMBDA_IMAGE_SEEDED` not reset after destroy | `actions: write` permission missing from workflow token | Check that `teardown-scheduled.yml` declares `permissions.actions: write` |
| Cron does not fire at expected time | GitHub Actions scheduler can drift ±15 min under heavy load | This is normal. Use `workflow_dispatch` for time-sensitive teardowns. |
| Re-provisioning `terraform apply` errors on Lambda | `CATALYST_LAMBDA_IMAGE_SEEDED` still `false` after service-cd ran | Run Step 3 (flip flag to `true`) then re-run Step 4 |

---

## See also

- [`docs/operator-bootstrap.md`](operator-bootstrap.md) — day-0 credential setup and bootstrap script
- [`.github/workflows/README.md`](../.github/workflows/README.md) — full workflow inventory and OIDC role mapping
- [Issue #134](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/134) — manual teardown (PR #135)
- [Issue #136](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/136) — scheduled teardown (this PR)
