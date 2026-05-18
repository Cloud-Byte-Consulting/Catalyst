# Catalyst control-plane architecture

Source diagram for the Catalyst Internal Developer Platform control plane. Rendered inline by GitHub. Aligned with ADR-006 (CI/CD), ADR-007 (golden paths), ADR-008 (RBAC), ADR-009 (runtime), ADR-010 (egress).

## Request path

```mermaid
flowchart TB
    Caller["Caller<br/>(operator / agent / CLI / GitHub Action)"]
    ALB["ALB :443<br/>(public, allowlisted CIDRs)"]
    Lambda["Lambda function<br/>catalyst-api<br/>(FastAPI + Mangum)"]
    STS["AWS STS<br/>GetCallerIdentity"]
    IAM["AWS IAM<br/>ListGroupsForUser<br/>(5 min cache)"]
    DDB[("DynamoDB<br/>catalyst-platform-state")]
    SSM[("SSM Parameter Store<br/>/catalyst/shared/*")]
    Sec[("Secrets Manager<br/>(optional per-key)")]
    OIDC["GitHub OIDC<br/>Identity Provider"]
    Plan["catalyst-github-plan<br/>(pull_request trust)"]
    Apply["catalyst-github-apply<br/>(ref:release trust)"]
    Deploy["catalyst-github-deploy<br/>(ref:release trust)"]
    Drift["catalyst-github-drift<br/>(ref:release trust)"]

    Caller -->|SigV4 signed request| ALB
    ALB --> Lambda
    Lambda --> STS
    Lambda --> IAM
    Lambda --> DDB
    Lambda --> SSM
    Lambda -.->|optional| Sec

    GHA["GitHub Actions workflows<br/>terraform.yml / service-cd.yml<br/>tf-drift.yml / teardown.yml"]
    GHA -->|sts:AssumeRoleWithWebIdentity| OIDC
    OIDC --> Plan
    OIDC --> Apply
    OIDC --> Deploy
    OIDC --> Drift
```

## Provisioning tiers

```mermaid
flowchart LR
    subgraph Bootstrap["Bootstrap tier — cost $0, survives teardown"]
        BAdmin["catalyst-bootstrap-admin<br/>(local op only)"]
        OIDCProv["GitHub OIDC provider"]
        BootRoles["catalyst-github-{plan,apply,deploy,drift}"]
        Groups["IAM Groups<br/>owners / administrators / viewers"]
        StateBkt[("S3 catalyst-tf-state-*")]
        Locks[("DynamoDB catalyst-terraform-locks")]
    end

    subgraph Pipeline["Pipeline tier — destroyed on teardown"]
        VPC["VPC + subnets + NAT"]
        SG["Security groups<br/>(ALB ingress allowlist)"]
        ECR[("ECR catalyst-api")]
        ECS["ECS cluster + ALB + TG"]
        LambdaMod["Lambda module<br/>(gated by lambda_image_seeded)"]
        DDBPlatform[("DynamoDB platform-state")]
        FW["Network Firewall<br/>(conditional, off by default)"]
    end

    Bootstrap -->|writes| TFState[("Terraform state in StateBkt")]
    Pipeline -->|writes outputs| SSMOut[("SSM /catalyst/shared/*")]
    SSMOut -->|read by| ServiceCD["service-cd.yml<br/>(phase gate)"]
```

## Phase ordering enforcement (ADR-006)

```mermaid
sequenceDiagram
    participant Op as Operator
    participant Bootstrap as scripts/bootstrap-aws-account.sh
    participant TF as terraform.yml
    participant CD as service-cd.yml
    participant Drift as tf-drift.yml

    Op->>Bootstrap: one-time, root creds
    Bootstrap-->>Op: OIDC provider, 4 roles, state bucket, lock table
    Op->>TF: gh workflow run terraform.yml
    TF->>TF: plan + apply (lambda gate=OFF)
    TF-->>SSMOut: VPC, SG, ECR, ECS-ALB, DDB
    Op->>CD: gh workflow run service-cd.yml
    CD->>CD: build image, push ECR :SHA + :latest
    Op->>Op: gh variable set CATALYST_LAMBDA_IMAGE_SEEDED true
    Op->>TF: gh workflow run terraform.yml (lambda gate=ON)
    TF-->>SSMOut: Lambda function ARN
    Note over Drift: daily 06:00 UTC<br/>read-only plan
```

See [ADR-006](../docs/ADR/ADR-006-cicd-pipeline-architecture.md) §"Phase ordering (hard constraint)" for the original mermaid this is derived from.
