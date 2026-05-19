<!-- AUTO-GENERATED from skills/score-translator/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
---
name: score-translator
description: >-
  Score spec validation and translation: parsing score.yaml (apiVersion
  score.dev/v1b1), validating against the pinned schema at ../spec/,
  translating workload descriptions into Terraform variable maps, and
  enforcing construct address context. Use when implementing Score validation
  in catalyst-api or the catalyst CLI.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/score-translator/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Score translator

## Role

You guide the validation and translation of **Score** workload descriptions (`score.yaml`, `apiVersion: score.dev/v1b1`) into platform-internal representations. Score is the **only** customer-authored workload schema in Catalyst — customers never write Terraform or raw AWS resource definitions. You enforce repository-configured spec validation (sibling `../spec/` checkout) and the construct address requirement from `docs/ADR/ADR-002-construct-hierarchy.md`.

## Instructions

### 1. What Score is

Score (https://score.dev) is an open, platform-agnostic workload specification. A `score.yaml` describes **what** a workload needs (containers, resources, routes) without dictating **how** the platform provisions them.

```yaml
apiVersion: score.dev/v1b1
metadata:
  name: order-service
containers:
  main:
    image: .   # built by CI
    variables:
      DB_HOST: "${resources.db.host}"
      DB_PORT: "${resources.db.port}"
resources:
  db:
    type: postgres
  queue:
    type: sqs
  dns:
    type: dns
    params:
      prefix: orders
```

### 2. Validation against configured spec root

Per repository convention and the sibling-spec expectation:

- The JSON Schema for Score lives in the sibling checkout at `../spec/` (clone `https://github.com/BittahCriminal/spec`).
- Both the **catalyst CLI** (Bun/TypeScript) and **catalyst-api** (Python) validate against this schema.
- **Never** validate against a runtime-fetched schema — the pinned checkout is the authority.

```python
import json
import os
from pathlib import Path
from jsonschema import validate, ValidationError

SPEC_ROOT = Path(
    os.environ.get("CATALYST_SCORE_SPEC_ROOT", str(Path.cwd().parent / "spec"))
)
SCORE_SCHEMA_PATH = SPEC_ROOT / "score-v1b1.json"

def load_score_schema() -> dict:
    """Load the pinned Score JSON Schema from ../spec/."""
    if not SCORE_SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Score spec not found at {SCORE_SCHEMA_PATH}. "
            "Clone https://github.com/BittahCriminal/spec into the workspace parent."
        )
    return json.loads(SCORE_SCHEMA_PATH.read_text())

def validate_score(score_data: dict) -> None:
    """Validate a parsed score.yaml against the pinned schema."""
    schema = load_score_schema()
    try:
        validate(instance=score_data, schema=schema)
    except ValidationError as e:
        raise ScoreValidationError(
            field=".".join(str(p) for p in e.absolute_path),
            message=e.message,
        )
```

### 3. Construct address binding

Every Score submission is bound to a construct address:

```
<tenant>/<env>/<lz>/<project>/<app>
```

The address comes from:
- **GitHub Action**: repo labels or workflow inputs
- **catalyst CLI**: `--tenant`, `--env`, etc. flags or `catalyst.toml`
- **catalyst-api**: path parameters in the URL

The `metadata.name` in `score.yaml` must match the `<app>` component of the construct address, or the API rejects the submission.

### 4. Translation to Terraform variable maps

Score describes intent; Catalyst translates to Terraform inputs:

```python
from pydantic import BaseModel

class TerraformVarMap(BaseModel):
    """Variables passed to the Terraform root module for an application."""
    app_name: str
    construct_address: str
    container_image: str
    container_port: int = 8080
    resource_requests: dict[str, ResourceSpec]
    environment_variables: dict[str, str]
    dns_prefix: str | None = None

class ResourceSpec(BaseModel):
    resource_type: str  # "postgres", "sqs", "s3", "dns", etc.
    params: dict[str, str] = {}

def translate_score_to_tfvars(
    score: dict,
    address: ConstructAddress,
    image_tag: str,
) -> TerraformVarMap:
    """
    Translate validated score.yaml + construct address into a Terraform
    variable map. The output feeds into the root module graph via
    terraform.tfvars.json.
    """
    containers = score.get("containers", {})
    main = containers.get("main", {})
    resources = score.get("resources", {})

    resource_specs = {
        name: ResourceSpec(
            resource_type=res["type"],
            params=res.get("params", {}),
        )
        for name, res in resources.items()
    }

    return TerraformVarMap(
        app_name=score["metadata"]["name"],
        construct_address=str(address),
        container_image=f"{ecr_repo(address)}:{image_tag}",
        container_port=int(main.get("variables", {}).get("PORT", 8080)),
        resource_requests=resource_specs,
        environment_variables=resolve_variables(main.get("variables", {}), resources),
        dns_prefix=resources.get("dns", {}).get("params", {}).get("prefix"),
    )
```

### 5. Variable resolution

Score variables use `${resources.<name>.<property>}` syntax. These resolve **at plan time** to Terraform references (not literal values):

```python
import re

RESOURCE_VAR_PATTERN = re.compile(r"\$\{resources\.(\w+)\.(\w+)\}")

def resolve_variables(
    variables: dict[str, str],
    resources: dict[str, dict],
) -> dict[str, str]:
    """
    Replace Score resource references with Terraform output references.
    E.g., ${resources.db.host} → module.postgres.endpoint
    """
    resolved = {}
    for key, value in variables.items():
        match = RESOURCE_VAR_PATTERN.match(value)
        if match:
            resource_name, prop = match.groups()
            if resource_name not in resources:
                raise ScoreValidationError(
                    field=f"containers.main.variables.{key}",
                    message=f"references undefined resource '{resource_name}'",
                )
            resolved[key] = f"${{module.{resource_name}.{prop}}}"
        else:
            resolved[key] = value
    return resolved
```

### 6. CLI integration (Bun/TypeScript)

The `catalyst` CLI validates Score client-side before submitting:

```
catalyst validate --score ./score.yaml
catalyst submit ./score.yaml --tenant pharmacy --env prod --lz clinical --project rx-fulfillment
```

The CLI loads the same JSON Schema from `SPEC_ROOT` (bundled at build time via `bun build`) and performs identical validation. The API re-validates server-side as defense-in-depth.

### 7. Supported resource types (initial set)

| Score `type` | Terraform module | AWS resource |
|-------------|-----------------|-------------|
| `postgres` | `composite/aurora-serverless-v2` | Aurora SLv2 cluster (shared, schema per app) |
| `sqs` | `leaf/sqs-queue` (to create) | SQS Standard or FIFO queue |
| `s3` | `leaf/s3-secure-bucket` | S3 bucket with BPA + KMS |
| `dns` | Output of `composite/cloudfront-fronted-alb` | Route 53 record + ALB target group |
| `redis` | `composite/elasticache-redis` (future) | ElastiCache Redis cluster |

## Output

- **Validation code**: schema loading + validate function + error model
- **Translation code**: Score → TerraformVarMap + resource resolution
- **CLI integration**: validation command structure + build-time schema bundling

## Guardrails

- **Never skip validation** — both CLI and API validate; the API is authoritative.
- **Never invent resource types** not in the supported set without an ADR.
- **Never embed AWS-specific details in score.yaml** — Score is platform-agnostic; the translation layer handles AWS specifics.
- **Never hardcode the spec path** — derive from `CATALYST_SCORE_SPEC_ROOT` or runtime config.
- **Score file is always explicitly passed** — no magic discovery of YAML files per `AGENTS.md`.
