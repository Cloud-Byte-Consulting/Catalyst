#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$PrintGitHubActionsRunnerPolicy,
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
        Invoke-BootstrapAws -Arguments @("iam", "create-open-id-connect-provider", "--url", "https://token.actions.githubusercontent.com", "--thumbprint-list", "6938fd4d98bab03faadb97b34396831e3780aea1", "22ff89586561fc2d52f77491e9f1eff1b80be33e", "--client-id-list", "sts.amazonaws.com") | Out-Null
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
                $thumbprintLegacy = Invoke-BootstrapAws -Arguments @("iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", $arn, "--query", "contains(ThumbprintList, '6938fd4d98bab03faadb97b34396831e3780aea1')", "--output", "text")
                $thumbprintModern = Invoke-BootstrapAws -Arguments @("iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", $arn, "--query", "contains(ThumbprintList, '22ff89586561fc2d52f77491e9f1eff1b80be33e')", "--output", "text")
                $thumbprintOk = ($thumbprintLegacy.Success -and $thumbprintLegacy.StdOut -eq "True") -or ($thumbprintModern.Success -and $thumbprintModern.StdOut -eq "True")
                if ($clientIdCheck.Success -and $clientIdCheck.StdOut -eq "True" -and $thumbprintOk) {
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
    $create = Invoke-BootstrapAws -Arguments @("iam", "create-open-id-connect-provider", "--url", "https://token.actions.githubusercontent.com", "--thumbprint-list", "6938fd4d98bab03faadb97b34396831e3780aea1", "22ff89586561fc2d52f77491e9f1eff1b80be33e", "--client-id-list", "sts.amazonaws.com")
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

function Assert-BootstrapAdminPrincipalArn {
    param([string]$PrincipalArn, [string]$AccountId)

    if ($PrincipalArn -notmatch '^arn:aws:iam::(\d{12}):(root|user/|role/)') {
        Fail "BOOTSTRAP_ADMIN_PRINCIPAL_ARN must be an IAM ARN like arn:aws:iam::123456789012:root, .../role/Name, or .../user/Name."
    }
    $principalAccount = $Matches[1]
    if ($principalAccount -eq "123456789012" -and $AccountId -ne "123456789012") {
        Fail "BOOTSTRAP_ADMIN_PRINCIPAL_ARN still uses the example account 123456789012 while AWS_ACCOUNT_ID is ${AccountId}. Set BOOTSTRAP_ADMIN_PRINCIPAL_ARN to a principal in this account (for example arn:aws:iam::${AccountId}:root for day-0 only, then replace with an admin role)."
    }
    if ($principalAccount -ne $AccountId) {
        Write-Warn "BOOTSTRAP_ADMIN_PRINCIPAL_ARN is in account ${principalAccount} but AWS_ACCOUNT_ID is ${AccountId} (cross-account trust). Ensure this is intentional."
    }
}

function Emit-GitHubActionsRunnerPolicy {
    param(
        [string]$AccountId,
        [string]$RegionName,
        [string]$Prefix,
        [string]$BootstrapPath
    )

    $trim = ($BootstrapPath.Trim("/"))
    $bucketName = "$Prefix-tf-state-$AccountId-$RegionName"
    $tableName = "$Prefix-terraform-locks"
    $planRole = "$Prefix-github-plan"
    $applyRole = "$Prefix-github-apply"
    $deployRole = "$Prefix-github-deploy"
    $bootstrapRoleGlob = "arn:aws:iam::${AccountId}:role/${trim}/*"

    $policy = [ordered]@{
        Version   = "2012-10-17"
        Statement = @(
            @{
                Sid      = "OIDCRead"
                Effect   = "Allow"
                Action   = @("iam:ListOpenIDConnectProviders", "iam:GetOpenIDConnectProvider")
                Resource = "*"
            },
            @{
                Sid      = "OIDCCreateIfMissing"
                Effect   = "Allow"
                Action   = "iam:CreateOpenIDConnectProvider"
                Resource = "*"
            },
            @{
                Sid       = "CreateBootstrapRoles"
                Effect    = "Allow"
                Action    = "iam:CreateRole"
                Resource  = "*"
                Condition = @{
                    StringLike = @{
                        "iam:RoleName" = "$Prefix-*"
                    }
                }
            },
            @{
                Sid      = "MutateBootstrapRoles"
                Effect   = "Allow"
                Action   = @(
                    "iam:GetRole", "iam:DeleteRole", "iam:AttachRolePolicy", "iam:DetachRolePolicy",
                    "iam:ListAttachedRolePolicies", "iam:ListRolePolicies", "iam:UpdateAssumeRolePolicy",
                    "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:TagRole",
                    "iam:UntagRole", "iam:PassRole"
                )
                Resource = @(
                    $bootstrapRoleGlob,
                    "arn:aws:iam::${AccountId}:role/${planRole}",
                    "arn:aws:iam::${AccountId}:role/${applyRole}",
                    "arn:aws:iam::${AccountId}:role/${deployRole}"
                )
            },
            @{
                Sid       = "CreateBootstrapGroups"
                Effect    = "Allow"
                Action    = "iam:CreateGroup"
                Resource  = "*"
                Condition = @{
                    StringLike = @{ "iam:GroupName" = "$Prefix-*" }
                }
            },
            @{
                Sid      = "ReadBootstrapGroups"
                Effect   = "Allow"
                Action   = "iam:GetGroup"
                Resource = "arn:aws:iam::${AccountId}:group/${Prefix}-*"
            },
            @{
                Sid      = "S3TerraformStateBucket"
                Effect   = "Allow"
                Action   = @(
                    "s3:CreateBucket", "s3:HeadBucket", "s3:PutBucketVersioning", "s3:PutBucketPublicAccessBlock",
                    "s3:PutEncryptionConfiguration", "s3:GetBucketEncryption", "s3:GetBucketVersioning",
                    "s3:GetBucketPublicAccessBlock", "s3:ListBucket"
                )
                Resource = @(
                    "arn:aws:s3:::${bucketName}",
                    "arn:aws:s3:::${bucketName}/*"
                )
            },
            @{
                Sid      = "DynamoTerraformLocks"
                Effect   = "Allow"
                Action   = @("dynamodb:CreateTable", "dynamodb:DescribeTable")
                Resource = "arn:aws:dynamodb:${RegionName}:${AccountId}:table/${tableName}"
            }
        )
    }

    ($policy | ConvertTo-Json -Depth 10)
}

if (-not $PrintGitHubActionsRunnerPolicy) {
    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
        Fail "Required command not found: aws"
    }
}

Assert-Value -Value $Region -Message "Missing AWS region. Use -Region or set AWS_REGION."
Assert-Value -Value $AccountId -Message "Missing AWS account id. Use -AccountId or set AWS_ACCOUNT_ID."

if ($PrintGitHubActionsRunnerPolicy) {
    Write-Output (Emit-GitHubActionsRunnerPolicy -AccountId $AccountId -RegionName $Region -Prefix $Prefix -BootstrapPath $BootstrapRolePath)
    exit 0
}

Assert-Value -Value $GitHubRepository -Message "Missing GitHub repository. Use -GitHubRepository or set GITHUB_REPOSITORY."
Assert-Value -Value $BootstrapAdminPrincipalArn -Message "Missing bootstrap admin principal ARN. Use -BootstrapAdminPrincipalArn or set BOOTSTRAP_ADMIN_PRINCIPAL_ARN."
Assert-BootstrapAdminPrincipalArn -PrincipalArn $BootstrapAdminPrincipalArn -AccountId $AccountId

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
