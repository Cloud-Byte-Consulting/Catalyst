# ADR-016 — Customer-Managed KMS Key Strategy

**Status**: Accepted - 2026-05-18
**Related**: [ADR-005](ADR-005-aws-agentic-platform-engineering.md) - [ADR-006](ADR-006-cicd-pipeline-architecture.md) - [ADR-008](ADR-008-catalyst-api-rbac.md) - [ADR-015](ADR-015-terraform-state-partitioning.md)
**Supersedes**: ADR-008 footnote and the per-module `tfsec:ignore:aws-dynamodb-table-customer-key` / `tfsec:ignore:aws-ecr-repository-customer-key` / `tfsec:ignore:aws-cloudwatch-log-group-customer-key` deferrals that previously postponed CMK migration.
**Issue**: [#228](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/228)

---

## Context

Catalyst's challenge-brief Option 1 ("Digging deeper") requires customer-managed KMS keys (CMK) across every data-at-rest surface. The 2026-05-18 audit landed Catalyst at **5/7** on Option 1 - the two remaining gaps were:

| Module | Pre-ADR-016 state | Gap |
|---|---|---|
| `infrastructure/modules/terraform-backend/main.tf` | CMK already in place for the S3 state bucket | none |
| `infrastructure/modules/dynamodb/main.tf` | SSE enabled, AWS-owned key, `tfsec:ignore` in place | no CMK |
| `infrastructure/modules/ecr/main.tf` | `encryption_type = "AES256"` (AWS-managed) | no CMK |
| `infrastructure/modules/composite/catalyst-app/main.tf` | inline ECR + log group, both AWS-managed | no CMK |

Without a dedicated `modules/kms/` the key lifecycle (rotation cadence, key policy, IAM grants) would be scattered across every consumer module. Centralising key material in one module with explicit outputs lets every encrypted-at-rest resource reference a single source of truth and lets future surfaces (Aurora Serverless #229, Secrets Manager parameters) plug in without re-litigating the key-policy shape.

---

## Decision

### Two-key split

The `modules/kms/` module emits **two** customer-managed KMS keys, not one:

| Key | Alias | Consumers | Rationale |
|---|---|---|---|
| `catalyst_data_key` | `alias/catalyst/data` | DynamoDB tables, Secrets Manager parameters, Aurora Serverless (Wave 2) | Hot, data-plane key. Rotation events here affect short-lived ciphertext only. |
| `catalyst_artifact_key` | `alias/catalyst/artifacts` | ECR repositories, CloudWatch log groups | Long-lived artifact key. Decoupling it from the data key means a data-key compromise never invalidates already-signed container images or breaks log-group access. |

Both keys share the same admin / consumer principal model:

- **Admin**: SSO admin role (`var.admin_role_arn`) gets full `kms:*` for key administration (rotation, alias updates, scheduled deletion / cancellation).
- **Consumers**: Lambda exec roles + ECS task roles (`var.consumer_role_arns`) get the data-plane subset (`kms:Encrypt`, `kms:Decrypt`, `kms:ReEncrypt*`, `kms:GenerateDataKey*`, `kms:DescribeKey`).
- **Account root**: full `kms:*` as the AWS-recommended `EnableIAMUserPermissions` anchor statement, so IAM policies can grant additional grants without editing the key policy itself.

The **artifact key additionally trusts** the regional CloudWatch Logs service principal (`logs.${region}.amazonaws.com`) with a `kms:EncryptionContext:aws:logs:arn` condition so log groups can encrypt streams server-side without needing per-role grants.

### Rotation + deletion window

- **`enable_key_rotation = true`** on both keys. AWS issues new backing material yearly; existing ciphertext stays decryptable.
- **`deletion_window_in_days = 30`** by default (variable, range 7-30 per the AWS-imposed bounds). 30 days is the production-safety default for data keys; the existing `terraform-backend` state key uses 7 deliberately for a tighter blast radius on backend rotation.

### Where the module is instantiated

- **`modules/composite/catalyst-app/`** (per-app L4 composite) embeds `module.kms` once per app. Per-app keys keep the blast radius scoped to a single tenant/env/project/app construct address.
- **Future** (#229 Aurora Serverless, #168 tenant-onboarding L2 hardening): reference `module.kms.data_key_arn` from the same per-app instance or instantiate a tenant-level instance, depending on the data lifetime.

### Backward compatibility

The `modules/dynamodb/` `kms_key_arn` input defaults to `null`. When `null`, SSE falls back to the AWS-owned key - identical to the pre-#228 behaviour. This preserves callers that haven't yet wired the kms module. The composite always passes a non-null ARN, so the production wiring is on the CMK path.

`modules/ecr/` is **not** backward-compatible: the `kms_key_arn` variable is required (no default). This is intentional - ECR encryption is settled at creation time and cannot be flipped in place, so silently defaulting to AES256 would create a one-way trap.

---

## Migration runbook

### DynamoDB table — online re-encryption

Flipping `server_side_encryption.kms_master_key_id` on an existing, populated DynamoDB table triggers an **online** re-encryption. Per AWS, throughput is unaffected and the table remains available throughout. Steps:

1. Plan the change: `terraform plan -target=module.dynamodb` and verify only `server_side_encryption.kms_key_arn` shows in the diff (no recreate).
2. Apply: `terraform apply -target=module.dynamodb`.
3. Verify in the AWS console: `Tables -> $name -> Additional settings -> Encryption at rest` should now show the `alias/catalyst/data` CMK.
4. Optional: `aws dynamodb describe-table --table-name $name --query 'Table.SSEDescription'` to confirm `KMSMasterKeyArn` matches.

Rollback path: set `kms_key_arn = null` in the calling module and re-apply. The table re-encrypts back to the AWS-owned key, again online.

### ECR repository — **destructive recreate (no in-place upgrade)**

> **Critical operational caveat**: AWS ECR's `encryption_configuration.encryption_type` is **immutable after repository creation**. Changing it from `AES256` to `KMS` (or vice versa) forces Terraform to destroy and re-create the repository. **All existing images are deleted.**

Migration steps (run during a maintenance window):

1. **Inventory the repo**: `aws ecr describe-images --repository-name $name --query 'imageDetails[].[imageTags[0],imageDigest,imagePushedAt]' --output table`. Confirm which tags are reachable / required for rollback.
2. **Pull and re-tag the live images** to a staging registry or a per-image archive bucket:
   ```bash
   aws ecr get-login-password | docker login --username AWS --password-stdin $registry
   for tag in $(aws ecr describe-images --repository-name $name --query 'imageDetails[].imageTags[0]' --output text); do
     docker pull $registry/$name:$tag
     docker tag  $registry/$name:$tag $staging_registry/$name:$tag
     docker push $staging_registry/$name:$tag
   done
   ```
3. **Pin the running task definition / Lambda function** to a digest, not a tag, so the workload keeps running off the cached image while the repo is gone.
4. **Apply the Terraform change**: `terraform apply` - this destroys + recreates the repo with `encryption_type = "KMS"` and the artifact-key ARN.
5. **Push the images back** from the staging registry into the new repo. Tags are immutable per ADR-005 so push order does not matter - each `name:tag` pair lands exactly once.
6. **Verify**: `aws ecr describe-repositories --repository-names $name --query 'repositories[0].encryptionConfiguration'` should show `{"encryptionType": "KMS", "kmsKey": "arn:aws:kms:...:key/..."}`.
7. **Unpin** the workload tags (or just leave them digest-pinned - that's safer anyway per ADR-005).

For greenfield deployments (no images yet) steps 1-3, 5, 7 are no-ops - just apply.

### CloudWatch log group — recreate via Terraform

CloudWatch log groups can have their `kms_key_id` set at creation time, and updates also work, but the **existing log entries are not re-encrypted in place**. Going forward all new entries use the CMK; historical entries remain under whatever key was active when they were written (typically the AWS-managed CloudWatch key).

If full historical re-encryption is required, the log group must be exported, deleted, and recreated. This is rarely worth doing - the existing entries are already encrypted with an AWS-managed key, just not the customer-managed one. ADR-016 treats the going-forward CMK path as sufficient.

### Verification matrix

After migration, confirm:

```bash
# Data key rotation status
aws kms get-key-rotation-status --key-id alias/catalyst/data
# Expected: { "KeyRotationEnabled": true }

# Artifact key rotation status
aws kms get-key-rotation-status --key-id alias/catalyst/artifacts
# Expected: { "KeyRotationEnabled": true }

# DynamoDB CMK binding
aws dynamodb describe-table --table-name catalyst-platform-state --query 'Table.SSEDescription'
# Expected: { "Status": "ENABLED", "SSEType": "KMS", "KMSMasterKeyArn": "arn:aws:kms:...:key/..." }

# ECR CMK binding
aws ecr describe-repositories --repository-names $name --query 'repositories[0].encryptionConfiguration'
# Expected: { "encryptionType": "KMS", "kmsKey": "arn:aws:kms:...:key/..." }
```

---

## Consequences

**Positive**
- Catalyst now meets Option 1 §CMK-at-rest end-to-end.
- Two-key split bounds the blast radius of a single key compromise to either the data plane or the artifact plane, never both.
- Centralised key policy means future consumers (#229 Aurora, Secrets Manager) onboard by adding their role ARN to the existing `consumer_role_arns` list rather than re-litigating policy shape.
- Per-app composite instantiation aligns key lifetime with construct-address lifetime (per ADR-015).

**Negative / trade-offs**
- **ECR migration is destructive.** Operators MUST follow the runbook above; running `terraform apply` against a populated AES256 ECR repo without staging images first will lose images. The composite docs and the ECR module docstring both point at this ADR.
- KMS calls (Encrypt / Decrypt / GenerateDataKey) are billed per-API-call and are not free at scale. For the v1 Catalyst deployment the volume is negligible; for tenant fan-out we may want shared rather than per-app keys at the L2 tier - that decision is deferred.
- Customer-managed keys do not protect against root-account compromise. They do tighten the cross-tenant + cross-service blast radius and they're a compliance-checklist item (PCI / SOC2 / FedRAMP).

**Deferred**
- Per-tenant or per-environment key namespacing beyond the per-app split. The current model is "one key pair per L4 composite instance" - if we hit alias-name collision (all aliases are literally `alias/catalyst/data`) on a flat-account multi-app deployment, we'll need to slug the alias by construct address. Per-app `.tfstate` partitioning (ADR-015) keeps the keys logically separate even when aliases collide at the AWS API layer; the alias name is a convenience binding, not a primary key.
- Cross-region replication of the CMKs (KMS multi-region keys). Catalyst v1 is single-region; multi-region is a Wave-3 concern.
- KMS grants (rather than key-policy statements) for short-lived runtime identities. The current model relies on resource-policy + IAM-policy intersection.

---

## References

- Issue: [#228](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/228)
- AWS docs: [Rotating AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html) - [DynamoDB encryption at rest](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/encryption.usagenotes.html) - [ECR encryption at rest](https://docs.aws.amazon.com/AmazonECR/latest/userguide/encryption-at-rest.html) - [Encrypt CloudWatch Logs with KMS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/encrypt-log-data-kms.html)
- Catalyst brief: `docs/references/challenge-brief.md` §Digging deeper Option 1
- Audit: 2026-05-18 /rlm Phase 1 report
