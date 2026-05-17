# Operator bootstrap runbook

What to gather **before** running `scripts/bootstrap-aws-account.sh`, where each value comes from, and what to configure **after**. Aimed at a new operator with admin access to a fresh AWS account who has never touched Catalyst before.

Authoritative pipeline reference: [`.github/workflows/README.md`](../.github/workflows/README.md). This runbook is the day-0 entry point that flows into it.

---

## What this script provisions

A single, idempotent bash script that creates everything outside the Terraform-pipeline tier:

- IAM **bootstrap-admin** role (used by the bootstrap script itself on re-runs)
- The GitHub OIDC identity provider
- Four GitHub Actions OIDC roles: `catalyst-github-{plan,apply,deploy,drift}` with their AWS managed policies
- RBAC IAM groups: `catalyst-{owners,administrators,viewers,support-admins,support-operators,support-viewers,breakglass}`
- Terraform state S3 bucket + DynamoDB lock table
- Catalyst API data S3 bucket

Re-runs are safe; existing resources are left untouched and only missing pieces are created.

The Terraform pipeline (`terraform.yml`) then takes over for everything else (VPC, ECR, ECS/Lambda, etc.).

---

## Step 1 — Install tools

| Tool | Why | Install |
|------|-----|---------|
| `aws` CLI v2 | Calls AWS APIs to create the bootstrap resources | macOS: `brew install awscli`. Linux: see [AWS docs](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| `gh` CLI | Sets the GitHub Actions secrets and variables after | macOS: `brew install gh`. Then `gh auth login` against `github.com` with `repo`, `read:org`, `workflow` scopes |
| `bash` 4+ | Runs the bootstrap script | Linux has it. macOS default is 3.2; the script works there, but `brew install bash` if you hit a quoting edge case |

Verify:

```bash
aws --version    # aws-cli/2.x
gh auth status   # Logged in to github.com as <you>
bash --version   # bash, version 4.x or 5.x
```

---

## Step 2 — Authenticate the AWS CLI as an admin principal

You need a principal in the target account that can call `iam:CreateRole`, `iam:CreateOpenIDConnectProvider`, `s3:CreateBucket`, `dynamodb:CreateTable`, etc. Pick **one** of the three options below.

### Option A — AWS SSO (recommended for org accounts)

```bash
aws configure sso
# - SSO start URL: <your-org-portal>.awsapps.com/start
# - SSO Region: where your SSO instance lives (often us-east-1)
# - Pick the Catalyst account + an admin permission set
# - Default region: us-east-1
# - Profile name: catalyst-admin

aws sso login --profile catalyst-admin
export AWS_PROFILE=catalyst-admin
```

### Option B — IAM user access keys (only for individual accounts)

Less ideal because the keys are long-lived. If you must:

```bash
aws configure
# AWS Access Key ID:     <your-key-id>
# AWS Secret Access Key: <your-secret>
# Default region name:   us-east-1
# Default output format: json
```

### Option C — Assume an admin role from a parent account

Useful when your daily principal lives in an Identity account and Catalyst lives in a workload account.

```bash
TARGET_ROLE_ARN="arn:aws:iam::<catalyst-account-id>:role/<admin-role-name>"
eval $(aws sts assume-role \
  --role-arn "$TARGET_ROLE_ARN" \
  --role-session-name catalyst-bootstrap \
  --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
  --output text | \
  awk '{printf "export AWS_ACCESS_KEY_ID=%s\nexport AWS_SECRET_ACCESS_KEY=%s\nexport AWS_SESSION_TOKEN=%s\n", $1, $2, $3}')
```

### Verify whichever option you picked

```bash
aws sts get-caller-identity
```

You should see your `Account` (12 digits) and your `Arn`. **Copy the Arn — that is your `BOOTSTRAP_ADMIN_PRINCIPAL_ARN` value.**

---

## Step 3 — Gather the script's input values

| Flag | What | Where to get it | Example |
|------|------|-----------------|---------|
| `--region` | AWS region to deploy into | Project decision. Use `us-east-1` unless data-residency / latency rules dictate otherwise | `us-east-1` |
| `--account-id` | Target AWS account (12 digits) | `aws sts get-caller-identity --query Account --output text` | `061051223073` |
| `--github-repository` | `owner/repo` slug | The repo URL | `Cloud-Byte-Consulting/Catalyst` |
| `--bootstrap-admin-principal-arn` | IAM principal allowed to assume the bootstrap admin role on re-runs. **Use the same Arn `aws sts get-caller-identity` returned in Step 2.** | `aws sts get-caller-identity --query Arn --output text` | `arn:aws:iam::061051223073:role/AWSReservedSSO_AdminAccess_xxx` or `arn:aws:iam::061051223073:user/jane` |
| `--prefix` (optional) | Resource name prefix | Defaults to `catalyst`; only change if you run multiple Catalyst stacks side-by-side in one account | `catalyst` |
| `--bootstrap-role-path` (optional) | IAM path for the bootstrap admin role | Defaults to `/catalyst/bootstrap/` | `/catalyst/bootstrap/` |
| `--dry-run` (optional) | Print intended actions without calling AWS | Add on your first run to preview | — |

> **Day-0 escape hatch**: if you do not yet have a named admin role and are running from `:root`, `arn:aws:iam::<account>:root` is acceptable as `--bootstrap-admin-principal-arn` for the very first run. **Replace it with a named admin user/role immediately afterward** by re-running the script with the proper Arn.

---

## Step 4 — Run the script

Dry-run first to preview:

```bash
cd /path/to/Catalyst
bash scripts/bootstrap-aws-account.sh \
  --dry-run \
  --region us-east-1 \
  --account-id 061051223073 \
  --github-repository Cloud-Byte-Consulting/Catalyst \
  --bootstrap-admin-principal-arn "$(aws sts get-caller-identity --query Arn --output text)"
```

Then for real (drop `--dry-run`):

```bash
bash scripts/bootstrap-aws-account.sh \
  --region us-east-1 \
  --account-id 061051223073 \
  --github-repository Cloud-Byte-Consulting/Catalyst \
  --bootstrap-admin-principal-arn "$(aws sts get-caller-identity --query Arn --output text)"
```

The last log line names the drift role's ARN for the GitHub Actions secret:

```
[INFO] Bootstrap complete.
[INFO] Set the AWS_ROLE_DRIFT_ARN repo secret to: arn:aws:iam::061051223073:role/catalyst-github-drift
```

---

## Step 5 — Configure GitHub Actions secrets and variables

The four OIDC role ARNs all follow the same pattern: `arn:aws:iam::<account-id>:role/catalyst-github-<role>`. Set them as GitHub Actions **repo secrets**:

```bash
ACCOUNT_ID=061051223073   # from Step 3
REPO=Cloud-Byte-Consulting/Catalyst

gh secret set AWS_ROLE_PLAN_ARN   --repo "$REPO" --body "arn:aws:iam::${ACCOUNT_ID}:role/catalyst-github-plan"
gh secret set AWS_ROLE_APPLY_ARN  --repo "$REPO" --body "arn:aws:iam::${ACCOUNT_ID}:role/catalyst-github-apply"
gh secret set AWS_ROLE_DEPLOY_ARN --repo "$REPO" --body "arn:aws:iam::${ACCOUNT_ID}:role/catalyst-github-deploy"
gh secret set AWS_ROLE_DRIFT_ARN  --repo "$REPO" --body "arn:aws:iam::${ACCOUNT_ID}:role/catalyst-github-drift"
```

Then set the repo **variables** the workflows read (these are NOT secrets — they are non-sensitive config):

```bash
gh variable set BOOTSTRAP_AWS_REGION         --repo "$REPO" --body us-east-1
gh variable set BOOTSTRAP_AWS_ACCOUNT_ID     --repo "$REPO" --body "$ACCOUNT_ID"
gh variable set BOOTSTRAP_CATALYST_PREFIX    --repo "$REPO" --body catalyst
gh variable set BOOTSTRAP_GITHUB_REPOSITORY  --repo "$REPO" --body "$REPO"

# Replace with your office/home /32 IP(s) for the ALB ingress allowlist
gh variable set CATALYST_API_INGRESS_ALLOWLIST --repo "$REPO" --body '["73.239.59.22/32"]'

# Leave false until first service-cd has seeded ECR :latest; flip to true after that
gh variable set CATALYST_LAMBDA_IMAGE_SEEDED --repo "$REPO" --body false
```

Optional secrets some workflows pick up if present:

| Secret | Used by | Purpose |
|--------|---------|---------|
| `DRIFT_SNS_TOPIC_ARN` | `tf-drift.yml` | Publish drift detection alerts to SNS |
| `BOOTSTRAP_AWS_VALIDATION_ROLE_ARN` | `bootstrap-smoke.yml` | Optional live AWS validation against a sandbox account |

---

## Step 6 — Verify the bootstrap landed

```bash
# All four OIDC roles exist
aws iam list-roles --query 'Roles[?starts_with(RoleName, `catalyst-github-`)].RoleName' --output text
# Expect: catalyst-github-apply  catalyst-github-deploy  catalyst-github-drift  catalyst-github-plan

# OIDC identity provider exists
aws iam list-open-id-connect-providers \
  --query 'OpenIDConnectProviderList[?contains(Arn, `token.actions.githubusercontent.com`)].Arn' --output text

# Terraform state bucket + lock table
aws s3 ls | grep -E "catalyst-tf-state-|catalyst-api-data-"
aws dynamodb describe-table --table-name catalyst-terraform-locks --query 'Table.TableStatus' --output text

# GitHub Actions secrets/variables look right
gh secret list   --repo Cloud-Byte-Consulting/Catalyst
gh variable list --repo Cloud-Byte-Consulting/Catalyst
```

---

## Step 7 — Trigger the platform pipelines

Once the bootstrap is in place and the secrets/variables are set, the GitHub Actions pipelines do everything else.

Typical day-1 path:

```bash
# 1. Apply the Terraform platform stack (VPC, ECR, ECS/Lambda, DDB, etc.)
gh workflow run terraform.yml --ref release --repo Cloud-Byte-Consulting/Catalyst
gh run watch --repo Cloud-Byte-Consulting/Catalyst

# 2. After terraform apply succeeds, build + deploy the Catalyst API
gh workflow run service-cd.yml --ref release -f runtime=lambda --repo Cloud-Byte-Consulting/Catalyst
gh run watch --repo Cloud-Byte-Consulting/Catalyst

# 3. Flip the Lambda image-seeded flag (only needed once, after first service-cd success)
gh variable set CATALYST_LAMBDA_IMAGE_SEEDED --repo Cloud-Byte-Consulting/Catalyst --body true

# 4. Re-run terraform.yml so the Lambda module now provisions the function
gh workflow run terraform.yml --ref release --repo Cloud-Byte-Consulting/Catalyst
```

`tf-drift.yml` runs nightly at 06:00 UTC.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `aws sts get-caller-identity` says `Unable to locate credentials` | AWS CLI not authenticated | Redo Step 2 |
| `AccessDenied: User: ... is not authorized to perform: iam:CreateRole` | Authenticated principal lacks admin perms | Use a true admin principal, or `aws sts assume-role` into one (Option C) |
| `BOOTSTRAP_ADMIN_PRINCIPAL_ARN still uses the example account 123456789012` | You copy-pasted the docs example | Replace with the Arn from `aws sts get-caller-identity` |
| `EntityAlreadyExists` warnings | Bootstrap already ran on this account | Idempotent — informational, not an error |
| Workflow fails: `Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity` | One of the `AWS_ROLE_*_ARN` secrets is missing, wrong, or pointing at a role that does not exist | `gh secret list` vs `aws iam list-roles --query 'Roles[?starts_with(RoleName, "catalyst-github-")].Arn'`; fix the mismatch |
| `tf-drift.yml` failing after bootstrap | `AWS_ROLE_DRIFT_ARN` not set, or drift role missing in AWS | `gh secret list` + `aws iam get-role --role-name catalyst-github-drift`. If role missing, re-run bootstrap; if secret missing, set it per Step 5 |
| `terraform.yml` apply fails with `iam:Pass*` / `iam:Create*` denied on a `catalyst-*` resource | Apply role's `CatalystApplyIAMScoped` inline policy out of date | Re-run bootstrap script — it refreshes the inline policy |

---

## What gets created — quick reference

After a successful bootstrap, the AWS account has:

```
IAM
  catalyst-bootstrap-admin                (role, used by future bootstrap re-runs)
  catalyst-github-plan                    (role, sub: pull_request,           ReadOnlyAccess)
  catalyst-github-apply                   (role, sub: ref:refs/heads/release, PowerUserAccess + CatalystApplyIAMScoped)
  catalyst-github-deploy                  (role, sub: ref:refs/heads/release, PowerUserAccess)
  catalyst-github-drift                   (role, sub: ref:refs/heads/release, ReadOnlyAccess)  [CICD-11a]
  catalyst-{owners,administrators,viewers,support-admins,support-operators,support-viewers,breakglass}
                                          (RBAC IAM groups per ADR-008)
  OIDC provider: token.actions.githubusercontent.com

S3
  catalyst-tf-state-<account>-<region>    (Terraform remote state)
  catalyst-api-data-<account>-<region>    (Catalyst API runtime storage)

DynamoDB
  catalyst-terraform-locks                (Terraform state-lock table)
```

---

## See also

- [`.github/workflows/README.md`](../.github/workflows/README.md) — full pipeline inventory + OIDC mapping + per-workflow env config
- [`docs/ADR/ADR-006-cicd-pipeline-architecture.md`](ADR/ADR-006-cicd-pipeline-architecture.md) — pipeline design rationale
- [`docs/ADR/ADR-008-catalyst-api-rbac.md`](ADR/ADR-008-catalyst-api-rbac.md) — RBAC group format
- [Issue #130 (CICD-11a)](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/130) — drift role addition rationale
- [Issue #124 (CICD-11b)](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/124) — drift role security hardening (follow-up)
