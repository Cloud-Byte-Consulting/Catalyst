# Catalyst CLI

Thin client over the Catalyst API. Built with Microsoft `knack` per AGENTS.md.

## Install

```bash
pip install -r clients/catalyst-cli/requirements.txt
```

## Configuration

| Env var | Purpose | Default |
|---|---|---|
| `CATALYST_API_ENDPOINT` | Base URL of the Catalyst API | `http://localhost:8000` |
| `CATALYST_AUTH` | `none` \| `sigv4` \| `presigned-sts` | `none` |
| `CATALYST_PRESIGNED_STS_URL` | Required when `CATALYST_AUTH=presigned-sts` | unset |
| `AWS_REGION` | Region used by `sigv4` auth | `us-west-2` |

## Golden-path commands

| Command | API call | Notes |
|---|---|---|
| `catalyst health check` | `GET /health` | No auth required. |
| `catalyst catalog list` | `GET /catalog` | Lists curated resources. |
| `catalyst services status <construct>` | `GET /services/{construct}` | Validates the construct address before calling the API. |
| `catalyst services onboard <construct> [--idempotency-key KEY]` | `POST /services/onboard` | Idempotent onboarding. |
| `catalyst groups list` | `GET /iam/groups` | Lists the seven global RBAC groups. |

The construct address must match `tenant/landing-zone/environment/project/app`
(per ADR-002 / `catalyst-{tenant}--{project}--{role}` delimiter), e.g.
`cloud-byte/dev/shared/platform/app1`.

## Examples

```bash
catalyst health check
catalyst catalog list
catalyst services status cloud-byte/dev/shared/platform/app1
catalyst services onboard cloud-byte/dev/shared/platform/app1 \
    --idempotency-key "$(uuidgen)"
catalyst groups list
```

## Tests

```bash
pip install -r clients/catalyst-cli/requirements-dev.txt
pytest clients/catalyst-cli/tests -v
```

The HTTP layer is centralized in `catalyst_cli._call`; tests monkeypatch that
single seam so the suite runs without an API or AWS credentials.

## Auth strategies

* `none` — no `Authorization` header. Use against a local dev API or for
  unauthenticated endpoints (`/health`, `/catalog`).
* `sigv4` — SigV4-sign the request with AWS4Auth using the active AWS
  session, suitable when API Gateway is configured with `auth_type = AWS_IAM`.
* `presigned-sts` — attaches a presigned STS `GetCallerIdentity` URL via the
  `X-Catalyst-Identity` header for the SigV4 RBAC path implemented in
  `services/catalyst-api/catalyst/identity.py` (see ADR-008).
