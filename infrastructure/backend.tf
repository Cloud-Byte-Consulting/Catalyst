# Terraform state backend.
#
# The S3 bucket and DynamoDB lock table referenced here are *bootstrap-managed*
# resources created once by `scripts/bootstrap-aws-account.sh` (see ADR-008).
# Everything else for the Catalyst platform is provisioned by Terraform via the
# tf-plan / tf-apply / tf-drift GitHub Actions workflows.
#
# CI passes the bucket name dynamically with `-backend-config="bucket=..."`
# during `terraform init`, so the value is not hard-coded here.
terraform {
  backend "s3" {
    key            = "catalyst/platform.tfstate"
    encrypt        = true
    dynamodb_table = "catalyst-terraform-locks"
  }
}
