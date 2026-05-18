# Terraform state backend for the GitHub branch-protection root.
#
# ADR-015 (Terraform state partitioning) places L1 platform-wide concerns at
# sibling state keys alongside `catalyst/platform.tfstate`. Branch protection is
# repo-level (not tenant-, environment-, or service-level) so its state key
# lives at the same L1 layer:
#
#   catalyst/platform.tfstate          # main infra root
#   catalyst/branch-protection.tfstate # this root
#
# The S3 bucket name is supplied at init time:
#   terraform init -backend-config="bucket=<state-bucket-from-bootstrap>"

terraform {
  backend "s3" {
    key          = "catalyst/branch-protection.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
