# Terraform state backend.
#
# The S3 bucket referenced here is a *bootstrap-managed* resource created once
# by `scripts/bootstrap-aws-account.sh` (see ADR-008). State locking uses
# Terraform 1.10+ native S3 state locking (`use_lockfile = true`) rather than a
# separate DynamoDB lock table. Everything else for the Catalyst platform is
# provisioned by Terraform via the tf-plan / tf-apply / tf-drift GitHub Actions
# workflows.
#
# CI passes the bucket name dynamically with `-backend-config="bucket=..."`
# during `terraform init`, so the value is not hard-coded here.
terraform {
  backend "s3" {
    key          = "catalyst/platform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
