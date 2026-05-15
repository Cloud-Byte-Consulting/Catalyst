# `catalyst-api` GitHub Action

Composite action that invokes a Catalyst API operation from a workflow.
Belongs under issue #17 and complements the CLI from issue #16.

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `endpoint` | yes | — | Catalyst API base URL (no trailing slash). |
| `operation` | yes | — | Operation path appended to the endpoint, e.g. `services/onboard`. |
| `method` | no | `POST` | HTTP method. |
| `payload` | no | `{}` | JSON body. |

## Required environment variables

The composite action runs `aws-actions/configure-aws-credentials@v4` so the
calling workflow MUST set:

* `permissions.id-token: write` and `permissions.contents: read`
* `env.CATALYST_ACTION_ROLE_ARN` — IAM role ARN that the OIDC provider trusts
  (use the `deploy` role from `infrastructure/modules/iam`, e.g.
  `catalyst-github-deploy`).
* `env.AWS_REGION` (optional, defaults to `us-west-2`).

The action does not read or store long-lived AWS keys.

## Example workflow

```yaml
name: catalyst-onboard
on:
  workflow_dispatch:
    inputs:
      construct:
        description: tenant/landing-zone/environment/project/app
        required: true
permissions:
  id-token: write
  contents: read
env:
  AWS_REGION: us-west-2
  CATALYST_ACTION_ROLE_ARN: ${{ secrets.AWS_ROLE_DEPLOY_ARN }}
jobs:
  onboard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/catalyst-api
        with:
          endpoint: https://catalyst.example.com
          operation: services/onboard
          method: POST
          payload: '{"construct_address":"${{ inputs.construct }}"}'
```

A working version of the example lives at
[`examples/workflow.yml`](examples/workflow.yml).

## Validation

The action's metadata schema and the example workflow are linted by
`ci-smoke.yml` (`actionlint` + structural validator). Local check:

```bash
pip install pyyaml
python .github/scripts/validate_workflows.py
```

## Auth strategy notes

The composite obtains AWS short-lived credentials via OIDC and then issues a
`curl` against the Catalyst API. The API itself enforces RBAC via SigV4 +
STS GetCallerIdentity (ADR-008); when the API gateway in front of Catalyst is
configured with `auth_type = AWS_IAM`, those short-lived credentials reach
the API as a SigV4-signed request with no further configuration. Until that
gateway is in place, calls authenticate using the configured role's session
token but the API treats them as unauthenticated unless the operator has set
`CATALYST_AUTH_MODE=headers` for local validation (do **not** do this in
production).
