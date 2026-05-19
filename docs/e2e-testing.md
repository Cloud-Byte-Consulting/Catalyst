# Catalyst end-to-end testing

A single regression suite under `tests/e2e/` exercises the six Catalyst
golden paths in one go. Same suite runs in two modes:

| Mode | Trigger | What it talks to |
|---|---|---|
| Mock (default) | plain `pytest tests/e2e/` | in-process `catalyst.main.app` via `fastapi.testclient.TestClient` |
| Live (opt-in) | `CATALYST_E2E_LIVE=1` + `CATALYST_API_ENDPOINT=https://...` | the real ALB at `$CATALYST_API_ENDPOINT` |

Mock mode runs in under a few seconds; the suite's contractual budget
is **under 60 seconds** (issue #207 Gherkin AC scenario 1). Live mode
adds network latency; budget it at a few minutes against a warm Lambda.

Tracking issue: [#207](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/207).

## The six journeys

One file per journey under `tests/e2e/`:

1. **`test_journey_01_operator_bootstrap.py`** — Track A. `GET /health`
   + `GET /iam/groups` + correlation-id (#61) round-trip.
2. **`test_journey_02_tenant_register.py`** — Track B. Tier 1 write
   surface: landing-zone → environment → application → `GET
   /orgs/{tenant}` returns the full hierarchy with the #199 widened
   fields (`account_id`, `compliance`, `landing_zone`, `project`).
3. **`test_journey_03_app_onboard.py`** — Track C. `POST
   /services/onboard` returns real ARN shapes from the L4 composite
   (not the v1 stub) and the ADR-015 state key.
4. **`test_journey_04_idempotency_replay.py`** — Same `idempotency_key`
   on a second `POST /services/onboard` returns the cached payload
   with `X-Idempotent-Replay: true` and does **not** re-invoke
   terraform.
5. **`test_journey_05_rbac_paths.py`** — Five sub-cases: viewer can
   read, viewer cannot write, tenant-scoped owner can write tier 2,
   tenant-scoped owner cannot read other tenants, missing headers are
   denied.
6. **`test_journey_06_auth_modes.py`** — Client-side
   `CATALYST_AUTH=presigned-sts` ↔ server-side
   `CATALYST_AUTH_MODE=sigv4` per ADR-008 § "Naming asymmetry".

## Running

### Mock mode (default; what CI runs)

```powershell
pytest tests/e2e/ -v
```

No env vars required. The suite fakes the Terraform subprocess chain
and uses `InMemoryRepository`, so it does not need AWS credentials and
does not modify any real state.

### Live mode (opt-in; post-deploy)

```powershell
$env:CATALYST_E2E_LIVE = "1"
$env:CATALYST_API_ENDPOINT = "http://catalyst-alb-XXXX.us-east-1.elb.amazonaws.com"
pytest tests/e2e/ -v
```

Two extra requirements for live mode:

- The caller's egress IP must be on `CATALYST_API_INGRESS_ALLOWLIST`
  (see `docs/smoke-tests.md` § Prerequisites).
- For journey 02/05 writes, the operator should clean up seed data
  afterwards — the `tenant_slug` fixture stamps a UUID suffix so re-
  runs do not collide, but DynamoDB rows accumulate indefinitely.

Journeys 03, 04, and 06 auto-skip in live mode (real Terraform applies
take minutes; real STS credentials are out-of-scope per #207's Scope
§Out). The four live-eligible tests cover the API contracts that can be
exercised non-destructively (health, iam/groups, tenant read,
correlation-id, viewer/RBAC reads).

## When to add a new journey

Not every endpoint needs an e2e test. Add one when:

- The contract crosses **two or more components** (CLI ↔ API, API ↔
  Terraform, API ↔ IAM / STS). Within-component coverage belongs in
  `services/catalyst-api/tests/` or `clients/catalyst-cli/tests/`.
- A previous regression escaped through to deploy because per-PR unit
  tests passed but the integration boundary broke (this suite was born
  exactly to catch that pattern).
- The journey is documented in an ADR or the issue tracker as a
  "golden path".

Do **not** add a journey for:

- Pure single-handler edge cases (use `services/catalyst-api/tests/`).
- Performance / load (separate kaizen).
- UI behaviour (no UI exists today).

## Deliberate-regression verification procedure

Per the #207 Verification section: "one follow-up PR introduces a
deliberate regression in a handler to confirm the e2e test catches it
(then revert)". The procedure:

1. Pick a handler the e2e suite covers (e.g. `onboard_service` in
   `services/catalyst-api/catalyst/main.py`).
2. Introduce a regression: rename a response field
   (`execution_role_arn` → `task_role_arn`), or hard-code an ARN
   prefix (return `"123456789012.dkr.ecr…"` regardless of input).
3. Run `pytest tests/e2e/ -v`. The corresponding journey **must
   fail** with an assertion that points at the boundary that broke —
   not a generic 500 / connection error.
4. Capture the failure output as evidence on the kaizen PR, then
   revert the deliberate regression.
5. Confirm `pytest tests/e2e/ -v` is green again before merge.

Run this procedure at least once per quarter (or any time a major new
journey lands) so the suite's fail-loud guarantee stays accurate.

## CI integration

- **`.github/workflows/pr-checks.yml` → `python-tests` job:** runs
  `pytest tests/e2e/` on every PR alongside the API unit suite.
  Mock-mode only.
- **`.github/workflows/ci-smoke.yml`:** opt-in via `workflow_dispatch`
  input `run_e2e_live`. Sets `CATALYST_E2E_LIVE=1` +
  `CATALYST_API_ENDPOINT=<dispatch input>` and runs the suite against
  a real ALB. Use this after a deploy to validate the integration
  surface against the live stack.

Cross-link: `docs/smoke-tests.md` covers the manual operator
runbook (Tier 1 AWS reads, Tier 2 curl probes). This page covers the
automated regression suite. Use both: smoke-tests catches "stack is
alive" failures, e2e catches "stack is alive but a contract has
drifted" failures.
