# ADR-019 — Aurora Serverless v2 with IAM authentication for catalyst-api

**Status**: Accepted - 2026-05-18
**Related**: [ADR-007](ADR-007-catalyst-api-golden-paths.md) - [ADR-008](ADR-008-catalyst-api-rbac.md) - [ADR-010](ADR-010-egress-control.md) - [ADR-015](ADR-015-terraform-state-partitioning.md) - [ADR-016](ADR-016-cmk-key-strategy.md)
**Supersedes**: none
**Issue**: [#229](https://github.com/Cloud-Byte-Consulting/cAtalyst/issues/229) (stacked on [#228](https://github.com/Cloud-Byte-Consulting/Catalyst/pull/234))

> Numbering note: this ADR is 019, not 017. PR #233 (homelab/Gitea ADRs)
> introduced files for 016/017/018 in parallel; ADR-019 skips that range to
> sidestep a numbering collision rather than create a merge-time renumber.

---

## Context

Catalyst's challenge-brief Option 1 ("Dig deeper") calls out **serverless RDS queried by the app** as a deliverable, and Option 3 references **IAM authentication to Postgres** as a dev-skills extension. The 2026-05-18 audit on issue #229 confirmed neither was present: the catalyst-api persisted exclusively to DynamoDB, there was no Aurora module under `infrastructure/modules/`, and the runtime carried no DB client code path.

Delivering both together gave us:

- a serverless data plane (right-sized scaling, on-demand cost shape) on the IaC side, and
- a credential-less query path (no long-lived DB password env var, audited via CloudTrail's `rds-db:connect`) on the app side.

This ADR settles the shape of the Aurora module (`infrastructure/modules/aurora-serverless/`), the IAM-auth client (`services/catalyst-api/catalyst/rds_repository.py`), the bootstrap path that creates the `catalyst` database + `catalyst_app` IAM-mapped role, and the dual-write contract between DynamoDB and Aurora.

The module consumes the `catalyst_data_key` CMK from ADR-016 (#228, unmerged at the time of writing) so a single key revocation blackholes the full data plane (DynamoDB + Aurora) for an app.

---

## Decision

We will provision a per-app **Aurora Serverless v2 (PostgreSQL 16)** cluster from a new `infrastructure/modules/aurora-serverless/` module, gated by an opt-in flag (`enable_aurora_serverless`) on the `catalyst-app` composite. Apps that don't need RDS keep DynamoDB-only persistence and pay zero RDS cost.

The cluster is encrypted at rest with the `catalyst_data_key` CMK (ADR-016), has `iam_database_authentication_enabled = true`, and accepts ingress on 5432 ONLY from the runtime SGs (ECS task / Lambda VPC). A break-glass master password is stored in Secrets Manager but **never used by app traffic** — the app authenticates via `boto3.client('rds').generate_db_auth_token(...)` and a fresh 15-minute token on every connection.

A new `RDSRepository` class implements:

- `record_deployment` (INSERT into `deployment_history`),
- `list_deployments` (SELECT with optional product_id + tenant filters), and
- `health_check` (SELECT 1).

The `GET /deployment-history` endpoint reads from Aurora; the existing `POST /products/catalog/{id}/deploy` performs a **dual-write** — DynamoDB first (source of truth), then a best-effort Aurora write (failure logged + `RDSWriteFailure` metric emitted, but does NOT roll back DynamoDB).

---

## Consequences

- **Good** — Serverless v2 right-sizes for the demo (0.5 ACU min, 2 ACU max); idle cost is minimal but non-zero (scaling to 0 ACU is intentionally not enabled — see Alternatives). The 16-line engine has native `rds_iam` extension support, so IAM auth is built-in (no driver-level patching).
- **Good** — Per-connection auth tokens have a 15-minute TTL. We deliberately do NOT cache them. In Lambda's stateless invocation model and short-lived ECS task lifecycle, a cached token cannot be reliably invalidated on rotation events; per-connection generation is the simpler safe default.
- **Good** — The `rds-db:connect` IAM policy resource ARN — `arn:aws:rds-db:${region}:${account}:dbuser:${cluster_resource_id}/catalyst_app` — is scoped to a single dbuser. Even a fully compromised runtime role can only authenticate as `catalyst_app`, which has `SELECT, INSERT` on `deployment_history` only (no UPDATE / DELETE / TRUNCATE — the history is append-only).
- **Good** — `enabled_cloudwatch_logs_exports = ["postgresql"]` + `log_statement = "ddl"` + `log_min_duration_statement = 1000` captures schema drift and slow queries in CloudWatch Logs without the firehose volume of `log_statement = "all"`.
- **Good** — `rds.force_ssl = 1` at the parameter-group level + `sslmode = "require"` on the Python side. The TLS requirement is enforced server-side and client-side; neither side alone is sufficient.
- **Trade-off** — We added a `psycopg[binary]>=3.1` dependency (≈8 MB compiled binary). The `[binary]` distribution avoids needing libpq at build time, which keeps the Lambda layer simple at the cost of the binary footprint.
- **Trade-off** — The bootstrap step is a `null_resource` + `local-exec` calling `psql` (Approach A in the Decision Log on #229). It requires `psql` on the apply host (the CI ubuntu-latest runner has it). It cannot drift-detect — if someone hand-edits the role outside the script, Terraform won't notice. The follow-up to adopt the `cyrilgdn/postgresql` provider is documented in Alternatives.
- **Trade-off** — The break-glass Secrets Manager secret currently uses the AWS-managed `aws/secretsmanager` key, NOT the `catalyst_data_key` CMK. Wiring a Secrets-Manager CMK is a separate follow-up that pairs with the secret-rotation Lambda; it was deliberately deferred from this PR to keep the scope tight.
- **Risk** — A psycopg / boto3 transient failure during dual-write must NOT block the primary deploy path. **Mitigation**: the helper `products._dual_write_rds` wraps the RDS write in a swallow-and-log boundary that emits a `RDSWriteFailure` metric. The DynamoDB write is the source of truth.
- **Risk** — Connection pooling is not implemented in v1. Lambda's stateless invocation model and the short-lived ECS task lifecycle make a process-local pool brittle (idle connections get reaped, tokens expire). **Mitigation**: the v1 demo path generates a fresh token per connection. If real load surfaces, RDS Proxy or a dedicated PgBouncer side-car is the documented next step.

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| **Aurora Serverless v1** (`engine_mode = "serverless"`) | AWS has signalled deprecation; v1 lacks per-second billing, has higher cold-start latency, and the `rds_iam` extension is not first-class. v2 with `engine_mode = "provisioned"` + `serverlessv2_scaling_configuration` is the AWS-blessed serverless shape. |
| **Provisioned (non-serverless) Aurora** | The challenge brief explicitly asks for serverless. The fixed-instance cost (~$50/mo minimum for a `db.t4g.medium`) is unjustifiable for an audit-grade demo. |
| **Scale Serverless v2 to 0 ACU** | Available in AWS but introduces cold-start latency (~15s) on first request after a scale-down. The demo's pause-between-runs would land on a cold start; smoother demo UX justifies the 0.5-ACU floor. |
| **Static DB password in Secrets Manager (no IAM auth)** | The brief's Option 3 explicitly calls out IAM-auth-Postgres. Even ignoring the brief: a static password creates a long-lived credential the app must rotate or risk leaking. IAM auth shifts the trust anchor to the runtime role, where ADR-008's RBAC contract already governs the blast radius. |
| **`cyrilgdn/postgresql` Terraform provider for bootstrap** | More elegant (declarative role / database / grant management) but adds a third-party provider with its own auth dance, and the bootstrap is exactly three SQL statements. The `null_resource` + `psql` script is narrower, ships in CI's `ubuntu-latest`, and the SQL is version-controlled in `bootstrap.sql.tftpl`. Re-evaluate if the bootstrap grows beyond ~20 SQL lines. |
| **Migrate existing DynamoDB data to Postgres** | The brief asks the app to *query* serverless RDS, not migrate. DynamoDB stays the source of truth; the dual-write proves the pattern. Migration is a much larger change with its own backfill / cutover / consistency story — out of scope for #229. |
| **RDS Proxy in front of the cluster** | Useful for Lambda connection pooling but adds a ~$20/mo idle cost. v1 generates a fresh token per connection; if pooling becomes load-bearing, RDS Proxy is the right next step. |
| **pgvector extension** | Out of scope. The catalog deployment history has no embedding workload; pgvector would be over-engineering for #229. |
| **Cross-region read replicas** | The brief's audit scope is single-region. Cross-region replication adds complexity (latency tolerance, conflict resolution) that doesn't pay off for the demo. |
| **Connection pooling in `rds_repository.py`** | Generating a fresh token per connection has a measurable cost (≈30ms per `generate_db_auth_token` call) but the token TTL (15min) doesn't compose cleanly with a Lambda's "warm-then-recycled" lifecycle. Per-connection generation is simpler and we don't have a load profile yet that justifies the complexity. |
| **Scale to 0 + RDS Data API instead of psycopg** | The Data API is HTTP-shaped (no persistent connection), which would dodge the pooling question. It does NOT support IAM database auth — auth is via a Secrets Manager ARN, which is the static-password shape we explicitly want to avoid. |

---

## Operational notes

### Bootstrap idempotency

The bootstrap script uses `CREATE ... IF NOT EXISTS` + `DO $$ ... $$` blocks for every statement, so a re-run (e.g. when the SQL hash trigger changes) is a no-op rather than an error. The `null_resource` trigger keys on `(cluster_arn, secret_arn, sql_hash)` — a change to any of the three re-runs the bootstrap, but the SQL itself is idempotent.

### Disaster recovery

- Automated backups: 7-day retention by default (`backup_retention_days`).
- `skip_final_snapshot = true` for the demo to keep `terraform destroy` clean. **In production, flip to false** and accept the snapshot cost — the `final_snapshot_identifier` is name-spaced per cluster + timestamp.
- Master credentials in Secrets Manager: `recovery_window_in_days = 7` so an accidental delete is recoverable within a week.

### Cost shape (us-west-2 list, ACU pricing)

| Component | Idle (0.5 ACU) | Burst (2 ACU) |
|---|---|---|
| Aurora ACUs | ~$43/mo | ~$172/mo |
| Storage | $0.10 / GB-mo | (linear) |
| Backup storage | $0.021 / GB-mo (after retention) | (linear) |
| Performance Insights | free at 7-day retention | (paid at longer retention) |

A typical demo run (low write volume, 1 ACU average) lands around $80/mo — well within the audit's cost-bound expectations.
