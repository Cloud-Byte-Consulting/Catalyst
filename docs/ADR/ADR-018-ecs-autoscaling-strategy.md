# ADR-018 — ECS Application Autoscaling Strategy

**Status**: Accepted - 2026-05-19
**Related**: [ADR-009](ADR-009-runtime-strategy.md) (Lambda vs ECS runtime choice), [ADR-014](ADR-014-services-onboard-provisioning-mode.md) (observability trip-wire), [ADR-016](ADR-016-cmk-key-strategy.md) (CMK strategy)
**Issue**: [#230](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/230)
**Closes brief gap**: Option 1 §autoscaling

---

## Context

The challenge brief's Option 1 ("Digging deeper") calls for **autoscaling** explicitly. The 2026-05-18 Option-1 audit flagged this as MISSING: no `aws_appautoscaling_target`, no target-tracking policies anywhere in the repo. ECS task count was statically provisioned (the ECS service from #62's task definition has whatever `desired_count` the CD pipeline registers and never moves).

This ADR records the strategy decisions for the `modules/ecs-autoscaling` sub-module shipped under #230.

## Decision

### 1. Use App Autoscaling target tracking (not step scaling)

Two AWS-provided primitives can drive ECS task count from CloudWatch metrics:

| Primitive | Knob | When it fits |
|---|---|---|
| **Target tracking** | `target_value` only (operator names a steady-state target; AWS picks thresholds + cool-downs) | Most workloads — declarative, low-tuning, ergonomic |
| **Step scaling** | Operator names threshold bands + scale deltas + cool-downs | When the steady-state target is wrong (e.g. for batch-spike workloads) |

We pick **target tracking** for both policies. The operator says "average CPU should be 60%" and AWS handles the scale-out/scale-in alarms internally. Step scaling would require us to maintain four threshold values per metric, which is brittle for a demo workload where the right thresholds are not known in advance.

### 2. Two metrics: CPU + ALBRequestCountPerTarget

CPU alone is insufficient. Many FastAPI handlers in Catalyst block on AWS API round trips (`provision_app`, `boto3.client('dynamodb').put_item`) and never pin CPU even at high request load. A CPU-only policy would under-scale.

| Policy | Predefined metric | Target | Catches |
|---|---|---|---|
| `cpu_target_tracking` | `ECSServiceAverageCPUUtilization` | 60% | Runaway compute (parsing-heavy paths, retry storms) |
| `request_count_per_target` | `ALBRequestCountPerTarget` | 50 RPM/task | Request flood not gated on CPU (AWS-API-bound handlers) |

Both run concurrently. App Autoscaling picks the higher of the two scale-out signals.

### 3. `min_capacity = 1` (cost) vs `min_capacity = 2` (HA) — explicit trade-off

The default is **`min_capacity = 1`**. The demo target is cost-conscious: a single Fargate task at 0.5 vCPU / 1 GiB runs ~$0.02/hour. Holding two tasks doubles that for HA the demo audience won't witness.

The HA cost: a single-task service has a **brief window of unavailability** during:
- Task replacement (ECS rolls a new task; ALB takes ~30s to swap)
- Task crash + restart (~60s ECS-managed recovery)
- AZ outage (the task is in one AZ; ALB cross-AZ load balancing only helps if multiple tasks exist)

Production deployments that require HA **must** override `ecs_autoscaling_min_capacity = 2` (or higher) per-deployment. This is a per-deployment variable so it can be set differently per environment without forking the module. ADR-014's trip-wire on `OnboardDuration` p95 > 10 min surfaces if HA-driven scaling lag becomes a real signal.

### 4. Supplemental CloudWatch alarms wired to the #63 SNS topic

AWS's target-tracking policies auto-emit CloudWatch alarms (one for scale-out, one for scale-in, per policy). These alarms are NOT routed to SNS by default — they exist only to drive the scaling action. Operators looking at the dashboard from #63 see no autoscaling signal.

The module emits three **supplemental** alarms wired to the shared `catalyst-alerts` SNS topic:

| Alarm | Trigger | What it means |
|---|---|---|
| `cpu-high` | CPU > 80% for 5 min | Scale-out is lagging behind sustained load — investigate runaway compute |
| `rpt-high` | RPT > 100 for 5 min | Request flood beyond target-tracking capacity — likely upstream incident |
| `at-max-capacity` | DesiredTaskCount ≥ max_capacity for 15 min | The service is pinned at the ceiling — raise `max_capacity` or fix the underlying load |

These are **complements**, not replacements, for AWS's internal scaling alarms. The supplemental set gives operators visibility on the same SNS topic as the rest of the #63 alarm fan-out.

When `ecs_autoscaling_sns_topic_arn` is empty, the supplemental alarms are skipped. Autoscaling itself still works — only the SNS visibility is degraded. This makes the module deployable in environments without the shared SNS topic (e.g. local Terraform testing).

## Consequences

### Positive

- Operator declares intent (`60% CPU`, `50 RPM/task`) without picking threshold magic numbers
- Two metrics catch both compute-bound and IO-bound scaling needs
- Supplemental alarms preserve operator visibility on the shared SNS topic
- `min_capacity = 1` keeps demo cost minimal; production override is one variable

### Negative

- AWS's default 3-minute scale-in cool-down means the service holds extra capacity for ~3 min after load drops. Acceptable for demo workloads; not for spiky cost-sensitive workloads. Not tunable via target-tracking — would require step scaling to change.
- `at-max-capacity` alarm fires when the service is correctly running at the upper bound under sustained load. Operators must treat this as "investigate and possibly raise the ceiling," not "scale-out failed." The alarm description states this explicitly.
- The ECS service itself is provisioned outside the module (by the CD pipeline that consumes the #62 task definition). The composite caller must pass cluster/service/ALB/TG identifiers as bare strings rather than reading them from `module.ecs_runtime` outputs.

### Follow-ups (out of scope for #230)

- **Lambda concurrency scaling**: Lambda already scales by default. If sustained traffic patterns demand reserved concurrency tuning, file a follow-up.
- **Custom-metric scaling on `Catalyst/API`**: the namespace from #60 could drive an autoscaling target on, e.g., `RequestDuration` p99. Defer until a real need surfaces.
- **Scheduled scaling**: for known demo-period traffic, an `aws_appautoscaling_scheduled_action` could pre-scale. Out of scope for the as-needed default.

## Verification

Per the Gherkin acceptance criteria on #230:

```gherkin
Scenario: Autoscaling target is registered
  Given the ECS catalyst-api service is deployed
  When aws application-autoscaling describe-scalable-targets --service-namespace ecs is called
  Then a target exists for the service with min=1 max=6

Scenario: Both policies attached
  Given the autoscaling target exists
  When aws application-autoscaling describe-scaling-policies --service-namespace ecs is called
  Then two TargetTrackingScaling policies exist
  And one tracks ECSServiceAverageCPUUtilization at 60
  And one tracks ALBRequestCountPerTarget at 50

Scenario: Scaling alarms wired to SNS
  Given the policies are deployed
  When aws cloudwatch describe-alarms --alarm-names <policy-alarms> is called
  Then their AlarmActions include the catalyst-alerts SNS topic ARN
```

`infrastructure/tests/ecs-autoscaling.tftest.hcl` enforces the first two scenarios at plan time. Operator-side verification (`aws application-autoscaling describe-*`) is documented in `docs/onboarding/platform.md` §Autoscaling.

## References

- Brief: `docs/references/challenge-brief.md` §Digging deeper Option 1
- #63 SNS topic — the `catalyst-alerts` topic this module's supplemental alarms publish to
- #62 task definition — provides the ECS task this autoscaling target scales
- [AWS Application Auto Scaling docs — Predefined metrics](https://docs.aws.amazon.com/autoscaling/application/userguide/application-auto-scaling-target-tracking.html)
- [AWS Application Auto Scaling docs — ALBRequestCountPerTarget resource_label format](https://docs.aws.amazon.com/autoscaling/application/APIReference/API_PredefinedMetricSpecification.html)
