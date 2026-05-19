<!-- AUTO-GENERATED from skills/deployment-strategies/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: deployment-strategies
description: >
  Blue/green ECS via CodeDeploy, Lambda weighted alias shifting (canary),
  rollback triggers (alarm-based), pre/post traffic hooks, bake periods, and
  the deploy-orchestrator Step Functions state machine. Use when implementing
  or reviewing deployment automation.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/deployment-strategies/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

## Role

Deployment engineer designing safe, observable, and automatically recoverable
release strategies for the Catalyst IDP. Every deployment is a state machine
transition — never a fire-and-forget push.

## Instructions

### 1. Blue/green ECS with CodeDeploy

Configure CodeDeploy deployment group with:
- Deployment type: `BLUE_GREEN`
- ECS service: `catalyst-api` (Fargate, min 2 tasks)
- Load balancer: ALB with production and test listeners
- Traffic routing: `TimeBasedLinear` — 10% every 5 minutes
- Appspec (`appspec.yml`) defines `TaskDefinition` and `ContainerName/Port`
- Pre-traffic hook Lambda validates health endpoint returns 200
- Post-traffic hook Lambda runs smoke tests against test listener
- Original task set termination wait: 30 minutes (bake period)

Terraform resources: `aws_codedeploy_app`, `aws_codedeploy_deployment_group`
with `blue_green_deployment_config` and `ecs_service` blocks.

### 2. Lambda alias canary

For deploy-orchestrator and other Lambda services:
- Create a `live` alias pointing to the latest published version
- Use `aws_lambda_alias` with `routing_config` for weighted shifting
- Deployment preference: `Canary10Percent5Minutes` (10% for 5 min, then 100%)
- CodeDeploy Lambda deployment group triggers rollback on alarm

### 3. Auto-rollback on CloudWatch alarm triggers

Every deployment group configures `auto_rollback_configuration`:
- `enabled = true`
- `events = ["DEPLOYMENT_FAILURE", "DEPLOYMENT_STOP_ON_ALARM"]`

Alarm-based triggers (in `alarm_configuration`):
- ECS: `catalyst-api-error-rate`, `catalyst-api-latency`
- Lambda: per-function `Errors` metric alarm

If any alarm enters ALARM state during traffic shifting, CodeDeploy
automatically rolls back to the previous task set or alias version.

### 4. Bake period monitoring

After traffic shifting completes (100% on new target):
- 30-minute bake period with active alarm monitoring
- During bake: error rate, latency p99, and DLQ depth are watched
- If alarm fires during bake: manual rollback triggered via Step Functions
- Post-bake: original (blue) task set terminated, deployment marked complete

### 5. Deploy state machine (Step Functions)

The `deploy-orchestrator` Step Functions state machine manages the lifecycle:

```
StartDeploy → ValidatePlan → ShiftTraffic → BakePeriod → Complete
                    │               │              │
                    ▼               ▼              ▼
                 Rollback       Rollback       Rollback
```

States:
- `StartDeploy` — record deployment in DDB, open GitHub Issue
- `ValidatePlan` — confirm Terraform plan matches expected changes
- `ShiftTraffic` — invoke CodeDeploy, begin canary/linear shift
- `BakePeriod` — wait 30 min, poll alarms via CloudWatch API
- `Complete` — update DDB, close Issue, notify SNS
- `Rollback` — trigger CodeDeploy rollback, update Issue with failure reason

### 6. GitHub Issue state transitions for deploys

Deployments are tracked as GitHub Issues with labels:
- `state/pending` — deployment requested, awaiting approval
- `state/agent-working` — deploy-orchestrator actively shifting traffic
- `state/done` — deployment complete, bake passed
- `state/rolled-back` — rollback executed, requires follow-up review

Transitions are managed by the deploy-orchestrator Lambda calling the GitHub
API (via OIDC-authenticated `catalyst-api`). Each transition adds a timeline
comment with deployment metadata (task definition ARN, commit SHA, duration).

### 7. Deployment as the last mile (CI/CD Design Patterns)

Per Bajpai et al: deployment is not a separate concern but the final stage of
the pipeline. The same artifact (container image SHA or Lambda zip hash) that
passed all CI gates is the artifact that deploys — no rebuild. Image tags use
the git commit SHA, never `:latest`. The deploy step consumes the artifact
reference from the CI output, ensuring provenance.

## Output

- Terraform deployment modules under the repository's active IaC path
- Step Functions ASL definition under the repository's deploy-orchestrator path
- Appspec templates under the service deploy path
- Hook Lambda source under the deploy-orchestrator hooks path

## Guardrails

- Never deploy without at least one alarm configured as a rollback trigger.
- Never use `AllAtOnce` traffic routing for production ECS services.
- Never skip the bake period — it is the final proving check before the
  blue task set is terminated.
- Never hardcode image tags — always reference the SHA-tagged artifact from CI.
- Never allow deployments from branches other than `main` to production.
- Always ensure the deploy state machine records start/end timestamps and
  outcome in DynamoDB for audit trail.
