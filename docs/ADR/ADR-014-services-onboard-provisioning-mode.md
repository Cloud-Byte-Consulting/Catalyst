# ADR-014 — `POST /services/onboard` provisioning mode: synchronous Terraform-in-Lambda (v2)

**Status**: Accepted · 2026-05-18
**Related**: [ADR-007](ADR-007-catalyst-api-golden-paths.md) · [ADR-009](ADR-009-runtime-strategy.md) · [ADR-012](ADR-012-onboarding-experience.md)

---

## Context

[ADR-007](ADR-007-catalyst-api-golden-paths.md) defines `POST /services/onboard` as the Tier 2 golden path that provisions ECR, IAM roles, ALB listener rules, CloudWatch log groups, and a DynamoDB idempotency record for a new application service. The v1 implementation in `services/catalyst-api/catalyst/main.py:129-148` returns **stubbed ARNs** synthesised from the construct address; no AWS resources are created. Both ADR-007 §Consequences and [ADR-012](ADR-012-onboarding-experience.md) §Consequences acknowledge this as temporary debt.

Issue [#167](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/167) replaces the stub with real provisioning that consumes the `tenant-onboarding` composite Terraform module from [#168](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/168). Two architectural shapes were viable:

- **Option A — synchronous Terraform-in-Lambda.** The API handler shells out to a bundled `terraform` binary, runs `init/plan/apply` against the S3 remote backend, blocks until the apply settles, and returns real ARNs in the response.
- **Option B — asynchronous job pipeline.** The API enqueues a job on SQS, returns `202 Accepted` with a `job_id`, a separate runner-Lambda drains the queue and executes Terraform, and a status table (DynamoDB) is polled via a new `GET /services/{construct_address}/onboard-status` endpoint.

The onboarding-followup risk register ([`docs/plans/onboarding-followup-plan.md`](../plans/onboarding-followup-plan.md) §Risks + watchpoints) explicitly time-boxes this decision: **one day of design, otherwise ship A and file v3 for B**. The runtime constraint from [ADR-009](ADR-009-runtime-strategy.md) — Lambda container, 15-minute hard cap, scale-to-zero — bounds Option A's headroom but does not eliminate it for current onboard workloads (composite module apply estimated at 2–5 minutes wall clock).

This ADR is a **precursor** to #167's implementation PR; it captures the architectural choice so the implementation PR can be reviewed against a frozen decision rather than re-arguing the trade-off inline.

---

## Decision

**Adopt Option A — synchronous Terraform-in-Lambda — as the v2 implementation of `POST /services/onboard`.**

### Rationale

- **Time-box discipline.** The risk register ships A when A vs B is not unambiguously decided within one day. Empirically, expected apply runtime (2–5 min p50) sits well inside Lambda's 15-min ceiling, and no caller has yet asked for sub-second onboard latency. Choosing A defers SQS + runner-Lambda + status-table complexity until measured demand justifies it.
- **S3-state idempotency for free.** The composite module from #168 reads/writes the existing Terraform remote backend (`{prefix}-tf-state-{account}-{region}`) with the existing DynamoDB lock table. Re-invoking onboard with the same construct address converges to the same state by Terraform's normal contract. Option B would require a separate `idempotency_keys` table reconciled against the live SQS queue and the job-status table — three sources of truth for what S3 already serialises.
- **No new AWS surface.** Option A adds zero new resources beyond what #168 already provisions. Option B adds an SQS queue, a runner-Lambda (image, role, log group, DLQ), a status DynamoDB table, IAM glue between all three, and a new API route. That is 2–3× the code surface for a benefit (latency hiding) that is not currently requested.
- **Lambda runtime bound is acceptable today.** [ADR-009](ADR-009-runtime-strategy.md) selects Lambda as the default runtime; its 15-min hard cap is the only architectural constraint Option A trips against. Composite-module apply runtime is monitored from day one (see Consequences) so we know when this ceiling becomes load-bearing.
- **Cold-start cost is one-time per container.** The `terraform` binary ships inside the Lambda container image (per ADR-009's container-image deployment model); install happens at image build, not per-invocation. Cold-start adds binary-resident-set page-in latency but not download time.

### Deferred to v3 (Option B)

Option B is **not dismissed**. It is filed as a deferred direction with an explicit trip-wire metric (see Consequences). If onboard runtime p95 crosses the threshold, Option B is the next evolution — not a redesign.

---

## Option comparison

| Dimension | Option A — sync Terraform-in-Lambda (v2) | Option B — async SQS + runner-Lambda + status table (v3) |
|---|---|---|
| **Caller latency** | Blocking, 2–5 min p50 expected; 15-min hard ceiling | Sub-second 202; eventual completion via status polling |
| **Failure modes** | Lambda timeout → caller sees 504; Terraform error → caller sees 5xx with `correlation_id`; partial apply visible in S3 state | Queue producer failure → caller sees 5xx; runner failure → status row marks `failed`; partial apply still visible in S3 state. More failure surfaces, more end-to-end retry semantics |
| **Idempotency** | S3 remote state + DynamoDB lock table (existing infrastructure); `idempotency_key` field maps to the DynamoDB idempotency record from ADR-007 | Same S3/lock backing **plus** a status table keyed on `job_id` **plus** a reconciliation pass against the queue. Three-way consistency required |
| **Blast radius** | Same Lambda execution role + composite-module IAM scope; one principal touches AWS | API Lambda role (enqueue only) + runner-Lambda role (full provisioning IAM); two principals to audit |
| **Dev/test ergonomics** | `moto` + `terraform` binary in test container; pytest blocks; deterministic ordering | `moto` + queue mocking + status-table mocking; eventual-consistency assertions; slower test feedback |
| **Observability** | One CloudWatch log group per invocation; correlation ID threads `init → plan → apply`; progress opaque to caller | Producer log group + runner log group + status table state; richer telemetry but split across three surfaces |
| **Cost (steady-state)** | Lambda invocation duration only; no idle resources | Lambda invocations (both) + SQS + DynamoDB read/write per status poll; small but nonzero idle floor |
| **Code surface** | ~1 module (`catalyst/onboard.py`), ~1 handler edit, moto-mocked tests | ~3 modules (producer, consumer, status) + new route + 2 IAM roles + DLQ + tests for each surface |
| **Time to land** | ≤2 days behind #168 (per #167 estimate) | 1+ week; new infrastructure module + runtime integration + status polling client + docs |
| **Caps and ceilings** | Lambda 15-min hard cap (per ADR-009) | None at the per-job level; SQS retention (14 days max) and DynamoDB row TTL bound durability |

---

## Consequences

### Positive

- **Smaller PR.** #167 stays single-purpose and reviewable; reviewers compare actual vs stubbed ARNs, not also a queue topology.
- **Existing idempotency contract honoured.** The ADR-007 `idempotency_key` field and the existing DynamoDB idempotency table remain the only caller-visible mechanism; no second key (`job_id`) leaks into the API surface.
- **No new infrastructure to operate.** No SQS DLQ to monitor, no runner-Lambda to size, no status table to TTL. The platform team's day-2 burden does not grow with this change.
- **Direct error surface.** Provisioning failures land on the calling request with the correlation ID already in scope. Callers do not need to correlate `job_id` against a separate status endpoint to learn what went wrong.

### Negative / trade-offs

- **Caller blocks 2–5 minutes.** Onboard becomes a long-running synchronous call. CLI clients ([`clients/catalyst-cli/`](../../clients/catalyst-cli/)) must extend their default request timeout for the `services onboard` command; the cap follows Lambda's 15-min ceiling. The CLI timeout-extension and the Lambda-cap note are to be documented in [`docs/onboarding/application.md`](../onboarding/application.md) as part of #167's implementation PR (not yet present in the runbook).
- **No progress signal.** The caller sees nothing between request and response. If apply gets stuck at 10 minutes, the client cannot tell whether the system is healthy or hung until Lambda times out.
- **Lambda 15-min cap is now a product constraint.** If the composite module grows (e.g. cross-region replication, multi-account vending), onboard runtime can approach the ceiling. The trip-wire below catches this before users do.
- **Cold-start binary page-in.** First invocation after idle pays for paging the `terraform` binary into RAM. Acceptable today; mitigated by ADR-009's provisioned-concurrency option if it becomes a complaint.

### Deferred — Option B as v3

Option B is filed as the planned next evolution. **Trip-wire metric:** if `POST /services/onboard` end-to-end runtime p95 exceeds **10 minutes over a rolling 30-day window**, open a v3 epic to ship the async pipeline. Implementation: the onboard handler emits a custom CloudWatch metric on each invocation via `PutMetricData` (namespace `Catalyst/Onboard`, metric `OnboardDuration`, dimensions `Endpoint=services_onboard` + `Result=success|failure`); a CloudWatch alarm on the `p95` statistic of that metric drives the trip-wire. The built-in `AWS/Lambda` `Duration` metric is function-scoped (not per-endpoint) and cannot be filtered post-hoc by log fields, so a handler-emitted custom metric is the right surface. CloudWatch Logs Insights over the structured onboard log lines is the secondary verification path.

Threshold rationale: 10 minutes leaves 5 minutes of headroom under Lambda's 15-min hard cap — enough to ship v3 before user-visible timeouts. p95 over 30 days smooths out single noisy applies (e.g. a one-off VPC endpoint backfill) and catches sustained drift.

A v3 implementation note is preserved here so the future agent does not re-derive the design:

- Producer: the existing onboard handler validates, enqueues an SQS message with `construct_address`, `idempotency_key`, `actor`, and returns `202` with `{ "job_id", "status_url" }`.
- Consumer: a runner-Lambda subscribed to the queue (visibility timeout ≥ Lambda max) executes Terraform with the same composite module #167 calls in v2.
- Status: a DynamoDB table keyed on `job_id` (with GSI on `idempotency_key`) records `pending | running | succeeded | failed`, the apply log location, and the eventual ARN payload.
- New route: `GET /services/{construct_address}/onboard-status?job_id=…` reads the status table. Polling cadence is documented (suggest 5 s, jittered).
- Idempotency: reconcile the existing DynamoDB `idempotency_keys` row with the status table on enqueue; replay returns the existing `job_id`.

This deferred direction is **not** a commitment to ship Option B; it is the design that ships **if and only if** the trip-wire fires.

**Trip-wire alarm now exists.** The CloudWatch alarm encoding this trip-wire is provisioned by [`infrastructure/modules/observability/`](../../infrastructure/modules/observability/README.md) (`aws_cloudwatch_metric_alarm.onboard_p95_latency`, alarm name `${name_prefix}-onboard-p95-latency`). It computes p95 of `Catalyst/Onboard:OnboardDuration` on a 1-day period over 30 evaluation periods — the 30-day rolling window — and fires when the value crosses 600,000 ms (10 min) into the `${name_prefix}-alarms` SNS topic. Until SVC-9 reaches the operator-subscriber wiring step (out-of-band; see [`docs/onboarding/platform.md`](../onboarding/platform.md) §"Operator alerts"), the alarm is computed but the page is not delivered.

---

## Compliance

- Synchronous Terraform execution MUST run as the existing Lambda execution role; no new principals introduced by this ADR.
- The composite module from #168 MUST be invoked via the Terraform remote backend (S3 + DynamoDB lock) — never with local state. The backend `key` MUST follow the L4 convention in [ADR-015](ADR-015-terraform-state-partitioning.md) (`catalyst/tenants/{tenant}/environments/{env}/apps/{app}.tfstate`), generated at apply time via `-backend-config="key=…"`.
- Onboard responses MUST continue to honour the ADR-007 `idempotency_key` contract and return `X-Idempotent-Replay: true` on replay.
- CLI default request timeout MUST be set to cover the Lambda 15-min ceiling (with a small margin) and MUST be documented at the call site.
- Onboard handler MUST emit a structured log line with `endpoint=services_onboard` and `correlation_id=…` on entry and exit, and MUST call `PutMetricData` once per invocation in namespace `Catalyst/Onboard` (metric `OnboardDuration`, unit `Milliseconds`, dimensions `Endpoint=services_onboard` + `Result=success|failure`) so the v3 trip-wire alarm is computable from a first-class metric — not from log filtering after the fact.

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| **Option B — async SQS + runner-Lambda + status table (now)** | 2–3× the code surface, three new failure modes, and a second AWS principal — for a benefit (latency hiding) that no caller has yet requested. Captured as the deferred v3 with a measurable trip-wire so this is reopened on data, not opinion. |
| **Step Functions Express orchestration** | Would solve the long-runtime concern but introduces a second control-plane (Step Functions state machine) that callers and the CLI would have to learn. The v2 use case has no branching workflow — it is a linear `init → plan → apply`. Step Functions complexity is unjustified at one stage. |
| **Move onboard off Lambda to ECS Fargate** | Solves the 15-min cap, but [ADR-009](ADR-009-runtime-strategy.md) explicitly chose Lambda as default because the API is request-pattern light and scale-to-zero is desirable. Splitting one handler onto ECS while the rest stays on Lambda creates a runtime fork with no upside until sustained load arrives. |
| **Defer #167 entirely and keep the v1 stub** | The stub is a production-blocking lie: it returns fake ARNs that callers cannot use. Both ADR-007 §Consequences and ADR-012 §Consequences flag this as temporary. Continuing to defer is a worse outcome than shipping a synchronous-but-real implementation. |
| **EventBridge Pipes between API and runner** | Same async pattern as Option B but with a different transport. Inherits the same multi-principal, multi-surface cost; the queue technology is not the design's load-bearing element. Not separately evaluated. |

---

## References

- [ADR-007 — Catalyst API golden paths (v1)](ADR-007-catalyst-api-golden-paths.md) §Consequences — original acknowledgment of the v1 stub and the polling-vs-async-202 question this ADR resolves
- [ADR-009 — Catalyst API runtime strategy](ADR-009-runtime-strategy.md) — Lambda container default and the 15-min runtime ceiling that bounds Option A
- [ADR-012 — Onboarding into Catalyst: three audience-sliced tracks](ADR-012-onboarding-experience.md) §Consequences — "Service onboard latency remains high until async / Terraform-backed provisioning replaces the v1 stub responses"
- [`docs/plans/onboarding-followup-plan.md`](../plans/onboarding-followup-plan.md) §Risks + watchpoints — the time-box guidance (ship A, file v3 for B) this ADR executes
- [`services/catalyst-api/catalyst/main.py:129-148`](../../services/catalyst-api/catalyst/main.py) — the current stubbed onboard handler this ADR sets up the replacement for
- Tracking issue: [#167](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/167) — Terraform-backed `POST /services/onboard` implementation
- Upstream dependency: [#168](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/168) — tenant-onboarding composite Terraform module
- ADR-014 tracking issue: [#183](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/183)
