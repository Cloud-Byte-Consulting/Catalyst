#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$Region = $env:AWS_REGION,
    [string]$AccountId = $env:AWS_ACCOUNT_ID,
    [string]$GitHubRepository = $env:GITHUB_REPOSITORY,
    [string]$BootstrapAdminPrincipalArn = $env:BOOTSTRAP_ADMIN_PRINCIPAL_ARN,
    [string]$Prefix = $(if ($env:CATALYST_PREFIX) { $env:CATALYST_PREFIX } else { "catalyst" }),
    [string]$BootstrapRolePath = $(if ($env:BOOTSTRAP_ROLE_PATH) { $env:BOOTSTRAP_ROLE_PATH } else { "/catalyst/bootstrap/" })
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message"
}

function Write-Warn {
    param([string]$Message)
    Write-Warning $Message
}

function Fail {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

function Assert-Value {
    param(
        [string]$Value,
        [string]$Message
    )
    if ([string]::IsNullOrWhiteSpace($Value)) {
        Fail $Message
    }
}

function Invoke-BootstrapAws {
    param([string[]]$Arguments)
    $joined = $Arguments -join " "
    if ($DryRun) {
        Write-Host "[DRY-RUN] aws $joined"
        return @{
            Success = $true
            StdOut = ""
        }
    }

    $output = & aws @Arguments 2>&1
    $exitCode = if (Test-Path variable:LASTEXITCODE) { $LASTEXITCODE } else { 0 }
    if ($exitCode -ne 0) {
        return @{
            Success = $false
            StdOut = ($output | Out-String).Trim()
        }
    }

    return @{
        Success = $true
        StdOut = ($output | Out-String).Trim()
    }
}

function Test-EntityExists {
    param([string[]]$Arguments)
    if ($DryRun) {
        return $false
    }
    $result = Invoke-BootstrapAws -Arguments $Arguments
    return $result.Success
}

function Ensure-Role {
    param(
        [string]$RoleName,
        [string]$Path,
        [string]$TrustFilePath
    )

    if (Test-EntityExists -Arguments @("iam", "get-role", "--role-name", $RoleName)) {
        Write-Info "Role exists: $RoleName"
        return
    }

    Write-Info "Creating role: $RoleName"
    $result = Invoke-BootstrapAws -Arguments @(
        "iam",
        "create-role",
        "--role-name", $RoleName,
        "--path", $Path,
        "--assume-role-policy-document", "file://$TrustFilePath"
    )
    if (-not $result.Success) {
        Fail "Failed creating role ${RoleName}: $($result.StdOut)"
    }
}

function Ensure-RolePolicyAttachment {
    param(
        [string]$RoleName,
        [string]$PolicyArn
    )

    if ($DryRun) {
        Write-Info "Ensuring policy attachment (dry-run): $RoleName <- $PolicyArn"
        Invoke-BootstrapAws -Arguments @("iam", "attach-role-policy", "--role-name", $RoleName, "--policy-arn", $PolicyArn) | Out-Null
        return
    }

    $query = "AttachedPolicies[?PolicyArn=='$PolicyArn'] | length(@)"
    $check = Invoke-BootstrapAws -Arguments @("iam", "list-attached-role-policies", "--role-name", $RoleName, "--query", $query, "--output", "text")
    if (-not $check.Success) {
        Fail "Failed reading policy attachments for ${RoleName}: $($check.StdOut)"
    }

    if ($check.StdOut -eq "1") {
        Write-Info "Role policy already attached: $RoleName <- $PolicyArn"
        return
    }

    Write-Info "Attaching role policy: $RoleName <- $PolicyArn"
    $attach = Invoke-BootstrapAws -Arguments @("iam", "attach-role-policy", "--role-name", $RoleName, "--policy-arn", $PolicyArn)
    if (-not $attach.Success) {
        Fail "Failed attaching ${PolicyArn} to ${RoleName}: $($attach.StdOut)"
    }
}

function Ensure-Group {
    param([string]$GroupName)

    if (Test-EntityExists -Arguments @("iam", "get-group", "--group-name", $GroupName)) {
        Write-Info "Group exists: $GroupName"
        return
    }

    Write-Info "Creating group: $GroupName"
    $create = Invoke-BootstrapAws -Arguments @("iam", "create-group", "--group-name", $GroupName)
    if (-not $create.Success) {
        Fail "Failed creating group ${GroupName}: $($create.StdOut)"
    }
}

function Ensure-BackendResources {
    $bucketName = "$Prefix-tf-state-$AccountId-$Region"
    $tableName = "$Prefix-terraform-locks"

    if ($DryRun) {
        Write-Info "Ensuring backend resources (dry-run)"
        Invoke-BootstrapAws -Arguments @("s3api", "create-bucket", "--bucket", $bucketName, "--region", $Region) | Out-Null
    }
    else {
        $exists = Invoke-BootstrapAws -Arguments @("s3api", "head-bucket", "--bucket", $bucketName)
        if ($exists.Success) {
            Write-Info "S3 backend bucket exists: $bucketName"
        }
        else {
            Write-Info "Creating S3 backend bucket: $bucketName"
            if ($Region -eq "us-east-1") {
                $createBucket = Invoke-BootstrapAws -Arguments @("s3api", "create-bucket", "--bucket", $bucketName, "--region", $Region)
            }
            else {
                $createBucket = Invoke-BootstrapAws -Arguments @("s3api", "create-bucket", "--bucket", $bucketName, "--region", $Region, "--create-bucket-configuration", "LocationConstraint=$Region")
            }

            if (-not $createBucket.Success) {
                Fail "Failed creating backend bucket ${bucketName}: $($createBucket.StdOut)"
            }
        }
    }

    foreach ($args in @(
        @("s3api", "put-bucket-versioning", "--bucket", $bucketName, "--versioning-configuration", "Status=Enabled"),
        @("s3api", "put-public-access-block", "--bucket", $bucketName, "--public-access-block-configuration", "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"),
        @("s3api", "put-bucket-encryption", "--bucket", $bucketName, "--server-side-encryption-configuration", '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}')
    )) {
        $result = Invoke-BootstrapAws -Arguments $args
        if (-not $result.Success) {
            Fail "Failed backend command: aws $($args -join ' ') -> $($result.StdOut)"
        }
    }

    if (Test-EntityExists -Arguments @("dynamodb", "describe-table", "--table-name", $tableName)) {
        Write-Info "DynamoDB lock table exists: $tableName"
        return
    }

    Write-Info "Creating DynamoDB lock table: $tableName"
    $table = Invoke-BootstrapAws -Arguments @(
        "dynamodb", "create-table",
        "--table-name", $tableName,
        "--attribute-definitions", "AttributeName=LockID,AttributeType=S",
        "--key-schema", "AttributeName=LockID,KeyType=HASH",
        "--billing-mode", "PAY_PER_REQUEST"
    )
    if (-not $table.Success) {
        Fail "Failed creating DynamoDB lock table ${tableName}: $($table.StdOut)"
    }
}

function Ensure-GitHubOidcProvider {
    if ($DryRun) {
        Write-Info "Ensuring GitHub OIDC provider (dry-run)"
        Invoke-BootstrapAws -Arguments @("iam", "create-open-id-connect-provider", "--url", "https://token.actions.githubusercontent.com", "--thumbprint-list", "6938fd4d98bab03faadb97b34396831e3780aea1", "--client-id-list", "sts.amazonaws.com") | Out-Null
        return
    }

    $list = Invoke-BootstrapAws -Arguments @("iam", "list-open-id-connect-providers", "--query", "OpenIDConnectProviderList[].Arn", "--output", "text")
    if (-not $list.Success) {
        Fail "Failed listing OIDC providers: $($list.StdOut)"
    }

    $providerExists = $false
    if (-not [string]::IsNullOrWhiteSpace($list.StdOut)) {
        foreach ($arn in $list.StdOut -split "\s+") {
            if ([string]::IsNullOrWhiteSpace($arn)) { continue }
            $provider = Invoke-BootstrapAws -Arguments @("iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", $arn, "--query", "Url", "--output", "text")
            if ($provider.Success -and $provider.StdOut -eq "token.actions.githubusercontent.com") {
                $clientIdCheck = Invoke-BootstrapAws -Arguments @("iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", $arn, "--query", "contains(ClientIDList, 'sts.amazonaws.com')", "--output", "text")
                $thumbprintCheck = Invoke-BootstrapAws -Arguments @("iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", $arn, "--query", "contains(ThumbprintList, '6938fd4d98bab03faadb97b34396831e3780aea1')", "--output", "text")
                if ($clientIdCheck.Success -and $thumbprintCheck.Success -and $clientIdCheck.StdOut -eq "True" -and $thumbprintCheck.StdOut -eq "True") {
                    Write-Info "GitHub OIDC provider exists and matches expected configuration: $arn"
                    $providerExists = $true
                    break
                }
                Fail "Existing GitHub OIDC provider has unexpected client ID list or thumbprints: $arn"
            }
        }
    }

    if ($providerExists) { return }

    Write-Info "Creating GitHub OIDC provider"
    $create = Invoke-BootstrapAws -Arguments @("iam", "create-open-id-connect-provider", "--url", "https://token.actions.githubusercontent.com", "--thumbprint-list", "6938fd4d98bab03faadb97b34396831e3780aea1", "--client-id-list", "sts.amazonaws.com")
    if (-not $create.Success) {
        Fail "Failed creating GitHub OIDC provider: $($create.StdOut)"
    }
}

function Write-RootGuardrails {
    Write-Warn "Root-account changes are intentionally NOT automated by this script."
    Write-Warn "Manual root checks required before Terraform apply:"
    Write-Warn "  1) Verify root MFA enabled."
    Write-Warn "  2) Verify no active root access keys."
    Write-Warn "  3) Verify alternate contacts and account alias."
}

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Fail "Required command not found: aws"
}

Assert-Value -Value $Region -Message "Missing AWS region. Use -Region or set AWS_REGION."
Assert-Value -Value $AccountId -Message "Missing AWS account id. Use -AccountId or set AWS_ACCOUNT_ID."
Assert-Value -Value $GitHubRepository -Message "Missing GitHub repository. Use -GitHubRepository or set GITHUB_REPOSITORY."
Assert-Value -Value $BootstrapAdminPrincipalArn -Message "Missing bootstrap admin principal ARN. Use -BootstrapAdminPrincipalArn or set BOOTSTRAP_ADMIN_PRINCIPAL_ARN."

Write-Info "Starting TF-0 AWS bootstrap (dry-run=$DryRun)"
Write-RootGuardrails

$bootstrapRoleName = "$Prefix-bootstrap-admin"
$planRoleName = "$Prefix-github-plan"
$applyRoleName = "$Prefix-github-apply"
$deployRoleName = "$Prefix-github-deploy"
$oidcProviderArn = "arn:aws:iam::${AccountId}:oidc-provider/token.actions.githubusercontent.com"

$planSub = "repo:${GitHubRepository}:pull_request"
$releaseSub = "repo:${GitHubRepository}:ref:refs/heads/release"

$bootstrapTrust = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "AWS": "$BootstrapAdminPrincipalArn" },
      "Action": "sts:AssumeRole"
    }
  ]
}
"@

$planTrust = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Principal": { "Federated": "$oidcProviderArn" },
      "Condition": {
        "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
        "StringLike": { "token.actions.githubusercontent.com:sub": "$planSub" }
      }
    }
  ]
}
"@

$releaseTrust = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Principal": { "Federated": "$oidcProviderArn" },
      "Condition": {
        "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
        "StringLike": { "token.actions.githubusercontent.com:sub": "$releaseSub" }
      }
    }
  ]
}
"@

if ($DryRun) {
    $bootstrapTrustPath = "/tmp/bootstrap-trust.json"
    $planTrustPath = "/tmp/plan-trust.json"
    $applyTrustPath = "/tmp/apply-trust.json"
    $deployTrustPath = "/tmp/deploy-trust.json"
}
else {
    $bootstrapTrustPath = [System.IO.Path]::GetTempFileName()
    $planTrustPath = [System.IO.Path]::GetTempFileName()
    $applyTrustPath = [System.IO.Path]::GetTempFileName()
    $deployTrustPath = [System.IO.Path]::GetTempFileName()

    Set-Content -Path $bootstrapTrustPath -Value $bootstrapTrust -Encoding UTF8
    Set-Content -Path $planTrustPath -Value $planTrust -Encoding UTF8
    Set-Content -Path $applyTrustPath -Value $releaseTrust -Encoding UTF8
    Set-Content -Path $deployTrustPath -Value $releaseTrust -Encoding UTF8
}

try {
    Ensure-Role -RoleName $bootstrapRoleName -Path $BootstrapRolePath -TrustFilePath $bootstrapTrustPath
    Ensure-RolePolicyAttachment -RoleName $bootstrapRoleName -PolicyArn "arn:aws:iam::aws:policy/AdministratorAccess"

    Ensure-BackendResources
    Ensure-GitHubOidcProvider

    Ensure-Role -RoleName $planRoleName -Path "/" -TrustFilePath $planTrustPath
    Ensure-Role -RoleName $applyRoleName -Path "/" -TrustFilePath $applyTrustPath
    Ensure-Role -RoleName $deployRoleName -Path "/" -TrustFilePath $deployTrustPath

    Ensure-RolePolicyAttachment -RoleName $planRoleName -PolicyArn "arn:aws:iam::aws:policy/ReadOnlyAccess"
    Ensure-RolePolicyAttachment -RoleName $applyRoleName -PolicyArn "arn:aws:iam::aws:policy/PowerUserAccess"
    Ensure-RolePolicyAttachment -RoleName $deployRoleName -PolicyArn "arn:aws:iam::aws:policy/PowerUserAccess"

    foreach ($groupName in @(
        "$Prefix-owners",
        "$Prefix-administrators",
        "$Prefix-viewers",
        "$Prefix-support-admins",
        "$Prefix-support-operators",
        "$Prefix-support-viewers",
        "$Prefix-breakglass"
    )) {
        Ensure-Group -GroupName $groupName
    }
}
finally {
    if (-not $DryRun) {
        foreach ($temp in @($bootstrapTrustPath, $planTrustPath, $applyTrustPath, $deployTrustPath)) {
            if ($temp -and (Test-Path -Path $temp)) {
                Remove-Item -Path $temp -Force
            }
        }
    }
}

Write-Info "Bootstrap complete."
