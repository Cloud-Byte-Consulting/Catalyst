# Catalyst GitOps workflow

Every change to Catalyst — infrastructure, service code, configuration — flows through a Pull Request against `release`. The pipeline encodes the contract in ADR-006: plan visible before apply, OIDC trust scoped per role, drift detection daily.

## End-to-end flow

```mermaid
flowchart LR
    Dev["Developer / Agent"] -->|"branch + commit"| Push["push to feature branch"]
    Push -->|"opens PR"| PR["Pull Request<br/>against release"]

    PR --> Quality["pr-checks.yml<br/>(fmt, validate, tflint,<br/>tfsec, checkov, pytest)"]
    PR --> Plan["terraform.yml plan<br/>(role: catalyst-github-plan)"]
    PR --> Smoke["ci-smoke.yml<br/>(actionlint + structural)"]
    PR --> Policy["validate-policies.yml<br/>(conftest)"]

    Plan -->|"sticky plan comment"| PR
    Quality --> PR
    Smoke --> PR
    Policy --> PR

    PR --> Review["Human review +<br/>Copilot review +<br/>peer-review sub-agent<br/>(AGENTS.md gate)"]

    Review --> Decision{"Approve?"}
    Decision -->|"changes requested"| Dev
    Decision -->|"approved + merge"| Merge["merge to release"]

    Merge --> Apply["terraform.yml apply<br/>(role: catalyst-github-apply)"]
    Apply --> SSM[("SSM Parameter Store<br/>/catalyst/shared/*<br/>(written by TF outputs)")]
    Apply --> StateBkt[("S3 catalyst-tf-state")]

    SSM --> CD["service-cd.yml<br/>(role: catalyst-github-deploy)<br/>SSM phase gate"]
    CD --> ECR[("ECR push :SHA + :latest")]
    CD --> Runtime["Lambda update-function-code<br/>OR ECS update-service"]

    Runtime --> Andon["Andon signal<br/>CloudWatch metrics + SNS"]

    subgraph Continuous["Continuous"]
        Drift["tf-drift.yml<br/>(daily 06:00 UTC)<br/>role: catalyst-github-drift"]
        DriftCheck{"plan exit code"}
        Drift --> DriftCheck
        DriftCheck -->|"0 / no drift"| Pass["silent pass"]
        DriftCheck -->|"2 / drift detected"| SNS["SNS CatalystDrift"]
        DriftCheck -->|"1 / plan error"| Page["SNS page on-call"]
        SNS --> Kaizen["GitHub Issue<br/>state/pending<br/>type/kaizen"]
    end
```

## Role separation (ADR-006 §IAM roles per pipeline)

| Pipeline phase | OIDC role | Trust subject | Permissions |
|---|---|---|---|
| Plan (PR validation) | `catalyst-github-plan` | `repo:Cloud-Byte-Consulting/Catalyst:pull_request` | Read-only on managed resources |
| Apply (release merge) | `catalyst-github-apply` | `repo:Cloud-Byte-Consulting/Catalyst:ref:refs/heads/release` | Full write on managed resources |
| Service deploy | `catalyst-github-deploy` | `repo:Cloud-Byte-Consulting/Catalyst:ref:refs/heads/release` | ECR push + Lambda/ECS update + SSM get |
| Drift detection | `catalyst-github-drift` | `repo:Cloud-Byte-Consulting/Catalyst:ref:refs/heads/release` | ReadOnlyAccess |

No long-lived AWS credentials anywhere. The bootstrap script (`scripts/bootstrap-aws-account.sh`) is the only step that requires human AWS credentials, and it runs once per account.

## Andon signal — drift becomes a tracked issue

```mermaid
sequenceDiagram
    participant Cron as scheduled trigger (06:00 UTC)
    participant Drift as tf-drift.yml
    participant TF as terraform plan
    participant SNS as SNS CatalystDrift
    participant GH as GitHub Issues

    Cron->>Drift: schedule fires
    Drift->>TF: terraform plan -detailed-exitcode
    alt exit code 0
        TF-->>Drift: no drift
        Drift-->>Cron: pass silently
    else exit code 2
        TF-->>Drift: drift summary
        Drift->>SNS: publish drift summary
        Drift->>GH: create issue<br/>(state/pending + type/kaizen)
        GH-->>Drift: issue URL in job summary
    else exit code 1
        TF-->>Drift: plan error
        Drift->>SNS: page on-call
    end
```

This is the **andon cord** for the Catalyst platform — drift detected at 06:00 UTC enters the same state machine (ADR-001) that every other change goes through. An agent can pick it up by querying `gh issue list --label state/pending --label type/kaizen`.

See [ADR-001](../docs/ADR/ADR-001-github-issues-as-state-machine.md) for the durable state machine + audit trail design.
See [ADR-006](../docs/ADR/ADR-006-cicd-pipeline-architecture.md) for the consolidated workflow architecture.
