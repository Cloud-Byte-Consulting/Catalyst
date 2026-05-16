#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
DRY_RUN=false

AWS_REGION="${AWS_REGION:-}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-}"
BOOTSTRAP_ADMIN_PRINCIPAL_ARN="${BOOTSTRAP_ADMIN_PRINCIPAL_ARN:-}"
CATALYST_PREFIX="${CATALYST_PREFIX:-catalyst}"
BOOTSTRAP_ROLE_PATH="${BOOTSTRAP_ROLE_PATH:-/catalyst/bootstrap/}"

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME [options]

Bootstrap Catalyst TF-0 resources in an AWS account.

Options:
  --dry-run                         Print intended actions without calling AWS.
  --region <region>                 AWS region (or AWS_REGION env var).
  --account-id <id>                 AWS account id (or AWS_ACCOUNT_ID env var).
  --github-repository <owner/repo>  GitHub repository allowed for OIDC roles.
  --bootstrap-admin-principal-arn <arn>
                                    IAM principal allowed to assume bootstrap admin role.
  --prefix <name>                   Resource prefix (default: catalyst).
  --bootstrap-role-path <path>      IAM path for bootstrap admin role.
  -h, --help                        Show this help.
EOF
}

log() {
  printf '%s\n' "[INFO] $*"
}

warn() {
  printf '%s\n' "[WARN] $*" >&2
}

fail() {
  printf '%s\n' "[ERROR] $*" >&2
  exit 1
}

run_cmd() {
  if [[ "$DRY_RUN" == "true" ]]; then
    printf '%s\n' "[DRY-RUN] $*"
    return 0
  fi
  "$@"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

entity_exists() {
  local service="$1"
  shift
  if [[ "$DRY_RUN" == "true" ]]; then
    return 1
  fi

  if aws "$service" "$@" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

ensure_group() {
  local group_name="$1"
  if entity_exists iam get-group --group-name "$group_name"; then
    log "Group exists: $group_name"
  else
    log "Creating IAM group: $group_name"
    run_cmd aws iam create-group --group-name "$group_name"
  fi
}

ensure_role_with_trust() {
  local role_name="$1"
  local role_path="$2"
  local trust_policy="$3"

  if entity_exists iam get-role --role-name "$role_name"; then
    log "Role exists: $role_name"
  else
    log "Creating IAM role: $role_name"
    run_cmd aws iam create-role \
      --role-name "$role_name" \
      --path "$role_path" \
      --assume-role-policy-document "file://$trust_policy"
  fi
}

ensure_role_policy_attachment() {
  local role_name="$1"
  local policy_arn="$2"

  if [[ "$DRY_RUN" == "true" ]]; then
    log "Ensuring policy attachment (dry-run): $role_name <- $policy_arn"
    run_cmd aws iam attach-role-policy --role-name "$role_name" --policy-arn "$policy_arn"
    return 0
  fi

  local attached
  attached="$(aws iam list-attached-role-policies \
    --role-name "$role_name" \
    --query "AttachedPolicies[?PolicyArn=='$policy_arn'] | length(@)" \
    --output text)"

  if [[ "$attached" == "1" ]]; then
    log "Role policy already attached: $role_name <- $policy_arn"
  else
    log "Attaching role policy: $role_name <- $policy_arn"
    run_cmd aws iam attach-role-policy --role-name "$role_name" --policy-arn "$policy_arn"
  fi
}

ensure_backend_resources() {
  local bucket_name="${CATALYST_PREFIX}-tf-state-${AWS_ACCOUNT_ID}-${AWS_REGION}"
  local table_name="${CATALYST_PREFIX}-terraform-locks"

  if [[ "$DRY_RUN" == "true" ]]; then
    log "Ensuring backend resources (dry-run)"
    run_cmd aws s3api create-bucket --bucket "$bucket_name" --region "$AWS_REGION"
  else
    if aws s3api head-bucket --bucket "$bucket_name" >/dev/null 2>&1; then
      log "S3 backend bucket exists: $bucket_name"
    else
      log "Creating S3 backend bucket: $bucket_name"
      if [[ "$AWS_REGION" == "us-east-1" ]]; then
        run_cmd aws s3api create-bucket --bucket "$bucket_name" --region "$AWS_REGION"
      else
        run_cmd aws s3api create-bucket \
          --bucket "$bucket_name" \
          --region "$AWS_REGION" \
          --create-bucket-configuration "LocationConstraint=$AWS_REGION"
      fi
    fi
  fi

  run_cmd aws s3api put-bucket-versioning \
    --bucket "$bucket_name" \
    --versioning-configuration "Status=Enabled"

  run_cmd aws s3api put-public-access-block \
    --bucket "$bucket_name" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

  run_cmd aws s3api put-bucket-encryption \
    --bucket "$bucket_name" \
    --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

  if entity_exists dynamodb describe-table --table-name "$table_name"; then
    log "DynamoDB lock table exists: $table_name"
  else
    log "Creating DynamoDB lock table: $table_name"
    run_cmd aws dynamodb create-table \
      --table-name "$table_name" \
      --attribute-definitions "AttributeName=LockID,AttributeType=S" \
      --key-schema "AttributeName=LockID,KeyType=HASH" \
      --billing-mode PAY_PER_REQUEST
  fi
}

ensure_github_oidc_provider() {
  local existing
  if [[ "$DRY_RUN" == "true" ]]; then
    log "Ensuring GitHub OIDC provider (dry-run)"
    run_cmd aws iam create-open-id-connect-provider \
      --url "https://token.actions.githubusercontent.com" \
      --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" \
      --client-id-list "sts.amazonaws.com"
    return 0
  fi

  existing="$(aws iam list-open-id-connect-providers --query 'OpenIDConnectProviderList[].Arn' --output text || true)"
  if [[ -n "$existing" ]]; then
    while IFS= read -r arn; do
      [[ -z "$arn" ]] && continue
      local url
      url="$(aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$arn" --query 'Url' --output text || true)"
      if [[ "$url" == "token.actions.githubusercontent.com" ]]; then
        local client_id_ok
        local thumbprint_ok
        client_id_ok="$(aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$arn" --query "contains(ClientIDList, 'sts.amazonaws.com')" --output text || true)"
        thumbprint_ok="$(aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$arn" --query "contains(ThumbprintList, '6938fd4d98bab03faadb97b34396831e3780aea1')" --output text || true)"
        if [[ "$client_id_ok" == "True" && "$thumbprint_ok" == "True" ]]; then
          log "GitHub OIDC provider exists and matches expected configuration: $arn"
          return 0
        fi
        fail "Existing GitHub OIDC provider has unexpected client ID list or thumbprints: $arn"
      fi
    done <<<"$(printf '%s\n' "$existing" | tr '\t' '\n')"
  fi

  log "Creating GitHub OIDC provider"
  run_cmd aws iam create-open-id-connect-provider \
    --url "https://token.actions.githubusercontent.com" \
    --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" \
    --client-id-list "sts.amazonaws.com"
}

create_temp_file() {
  local file_path
  file_path="$(mktemp)"
  printf '%s\n' "$2" >"$file_path"
  eval "$1='$file_path'"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --region)
        AWS_REGION="${2:-}"
        shift 2
        ;;
      --account-id)
        AWS_ACCOUNT_ID="${2:-}"
        shift 2
        ;;
      --github-repository)
        GITHUB_REPOSITORY="${2:-}"
        shift 2
        ;;
      --bootstrap-admin-principal-arn)
        BOOTSTRAP_ADMIN_PRINCIPAL_ARN="${2:-}"
        shift 2
        ;;
      --prefix)
        CATALYST_PREFIX="${2:-}"
        shift 2
        ;;
      --bootstrap-role-path)
        BOOTSTRAP_ROLE_PATH="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done
}

validate_inputs() {
  [[ -n "$AWS_REGION" ]] || fail "Missing AWS region. Use --region or set AWS_REGION."
  [[ -n "$AWS_ACCOUNT_ID" ]] || fail "Missing AWS account id. Use --account-id or set AWS_ACCOUNT_ID."
  [[ -n "$GITHUB_REPOSITORY" ]] || fail "Missing GitHub repository. Use --github-repository or set GITHUB_REPOSITORY."
  [[ -n "$BOOTSTRAP_ADMIN_PRINCIPAL_ARN" ]] || fail "Missing bootstrap admin principal ARN. Use --bootstrap-admin-principal-arn or set BOOTSTRAP_ADMIN_PRINCIPAL_ARN."
}

emit_root_guardrails() {
  warn "Root-account changes are intentionally NOT automated by this script."
  warn "Manual root checks required before Terraform apply:"
  warn "  1) Verify root MFA enabled."
  warn "  2) Verify no active root access keys."
  warn "  3) Verify alternate contacts and account alias."
}

main() {
  parse_args "$@"
  validate_inputs

  require_cmd aws
  if [[ "$DRY_RUN" != "true" ]]; then
    require_cmd mktemp
  fi

  log "Starting TF-0 AWS bootstrap (dry-run=$DRY_RUN)"
  emit_root_guardrails

  local bootstrap_role_name="${CATALYST_PREFIX}-bootstrap-admin"
  local plan_role_name="${CATALYST_PREFIX}-github-plan"
  local apply_role_name="${CATALYST_PREFIX}-github-apply"
  local deploy_role_name="${CATALYST_PREFIX}-github-deploy"

  local bootstrap_trust_json
  bootstrap_trust_json="$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "AWS": "$BOOTSTRAP_ADMIN_PRINCIPAL_ARN" },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON
)"

  local oidc_provider_arn="arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

  local plan_sub="repo:${GITHUB_REPOSITORY}:pull_request"
  local release_sub="repo:${GITHUB_REPOSITORY}:ref:refs/heads/release"

  local role_plan_trust_json
  role_plan_trust_json="$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Principal": { "Federated": "$oidc_provider_arn" },
      "Condition": {
        "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
        "StringLike": { "token.actions.githubusercontent.com:sub": "$plan_sub" }
      }
    }
  ]
}
JSON
)"

  local role_release_trust_json
  role_release_trust_json="$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Principal": { "Federated": "$oidc_provider_arn" },
      "Condition": {
        "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
        "StringLike": { "token.actions.githubusercontent.com:sub": "$release_sub" }
      }
    }
  ]
}
JSON
)"

  local bootstrap_trust_file=""
  local plan_trust_file=""
  local apply_trust_file=""
  local deploy_trust_file=""

  if [[ "$DRY_RUN" != "true" ]]; then
    create_temp_file bootstrap_trust_file "$bootstrap_trust_json"
    create_temp_file plan_trust_file "$role_plan_trust_json"
    create_temp_file apply_trust_file "$role_release_trust_json"
    create_temp_file deploy_trust_file "$role_release_trust_json"
  else
    bootstrap_trust_file="/tmp/bootstrap-trust.json"
    plan_trust_file="/tmp/plan-trust.json"
    apply_trust_file="/tmp/apply-trust.json"
    deploy_trust_file="/tmp/deploy-trust.json"
  fi

  ensure_role_with_trust "$bootstrap_role_name" "$BOOTSTRAP_ROLE_PATH" "$bootstrap_trust_file"
  ensure_role_policy_attachment "$bootstrap_role_name" "arn:aws:iam::aws:policy/AdministratorAccess"

  ensure_backend_resources
  ensure_github_oidc_provider

  ensure_role_with_trust "$plan_role_name" "/" "$plan_trust_file"
  ensure_role_with_trust "$apply_role_name" "/" "$apply_trust_file"
  ensure_role_with_trust "$deploy_role_name" "/" "$deploy_trust_file"

  ensure_role_policy_attachment "$plan_role_name" "arn:aws:iam::aws:policy/ReadOnlyAccess"
  ensure_role_policy_attachment "$apply_role_name" "arn:aws:iam::aws:policy/PowerUserAccess"
  ensure_role_policy_attachment "$deploy_role_name" "arn:aws:iam::aws:policy/PowerUserAccess"

  ensure_group "${CATALYST_PREFIX}-owners"
  ensure_group "${CATALYST_PREFIX}-administrators"
  ensure_group "${CATALYST_PREFIX}-viewers"
  ensure_group "${CATALYST_PREFIX}-support-admins"
  ensure_group "${CATALYST_PREFIX}-support-operators"
  ensure_group "${CATALYST_PREFIX}-support-viewers"
  ensure_group "${CATALYST_PREFIX}-breakglass"

  if [[ "$DRY_RUN" != "true" ]]; then
    rm -f "$bootstrap_trust_file" "$plan_trust_file" "$apply_trust_file" "$deploy_trust_file"
  fi

  log "Bootstrap complete."
}

main "$@"
