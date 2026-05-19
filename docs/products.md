# Catalyst product catalog

**Purpose:** the product catalog is a small, in-process registry of platform-shipped products that operators can deploy through the same Tier-2 onboard pipeline that backs `POST /services/onboard`. The first entry, `catalyst-api`, lets Catalyst deploy another Catalyst API instance — the meta-feature locked by CAT-3 ([#103](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/103)).

**Architectural decision:** Decision Log on [#103](https://github.com/Cloud-Byte-Consulting/Catalyst/issues/103) — Option A (API-driven self-onboard via product catalog), not Option B (separate Terraform root).

## Endpoint surface

| Method | Path | Purpose | RBAC |
|---|---|---|---|
| `GET` | `/products/catalog` | List all catalog entries | Any authenticated caller |
| `GET` | `/products/catalog/{product_id}` | Fetch a single catalog entry | Any authenticated caller; 404 on miss |
| `POST` | `/products/catalog/{product_id}/deploy` | Deploy a catalog product at a construct address | `catalyst-owners` OR `catalyst-administrators` |

The endpoints live in the BOTTOM section of [`services/catalyst-api/catalyst/main.py`](../services/catalyst-api/catalyst/main.py), inside a delimited comment block (`# Product-catalog endpoints (#103 — CAT-3 ...)`) so the registration block does not collide with the observability middleware near the top of the file (parallel work on #60). The paths are under `/products/catalog/*` so they coexist with the existing `/products` + `/products/deploy` + `/products/{tenant}/{project}/{app_name}` routes from #167, which back the per-tenant product-instance lifecycle.

## The catalog dict

The catalog is a single `PRODUCT_CATALOG` dict in [`services/catalyst-api/catalyst/products.py`](../services/catalyst-api/catalyst/products.py). Each entry follows this schema:

```python
PRODUCT_CATALOG = {
    "catalyst-api": {
        "name": "Catalyst API",
        "description": "Self-managed deployment of an additional Catalyst API instance.",
        "image_uri_env_var": "CATALYST_SELF_IMAGE_URI",
        "service_type": "web-service",
        "required_roles": frozenset({"owner", "administrator"}),
    },
}
```

Field reference:

| Field | Purpose |
|---|---|
| `name` | Display name surfaced in `GET /products/catalog` |
| `description` | Short tagline; appears in CLI/UI catalog listings |
| `image_uri_env_var` | Env var the operator sets to override the container image URI at deploy time; resolved by `_resolve_image_uri` (env override > `CATALYST_ECR_BASE` default > 500) |
| `service_type` | The `onboard.provision_app` service type; one of `web-service`, `worker`, `scheduled-job` |
| `required_roles` | `frozenset` of role strings (`owner`, `administrator`, etc. — output vocabulary of [`rbac._access_from_groups`](../services/catalyst-api/catalyst/rbac.py)) — the caller's role MUST be in this set to deploy |

## Adding a new product

1. Append a new entry to `PRODUCT_CATALOG`.
2. Document its image-URI env var (if any) in the operator runbook.
3. (Optional) extend `tests/test_products.py` with a happy-path + 403 test if the product has different RBAC than `catalyst-api`.

No new endpoint registration, no new route, no new test scaffolding — the existing `/products/catalog/*` family already serves every catalog entry, and the orchestration uses `service_type` to flow through the right `onboard.provision_app` path.

## RBAC enforcement

Two checks fire on the way through `deploy_product`:

1. **Product authorization** — `is_caller_authorized_for_product(access, product_id)` returns `True` iff `access.role` is in the product's `required_roles` set. Failures return `403 ScopeInsufficient`.
2. **Tenant boundary (scoped principals)** — if `access.role == "scoped"`, the construct address's tenant segment MUST be one the caller owns (`can_read_scope`). This is checked separately because scoped principals are never in `required_roles` by default; if a future product opts into scoped access, this layer enforces the tenant boundary.

The orchestration is short-circuit on RBAC failure: `onboard.provision_app` is NOT invoked when the deploy is denied. See the journey-07 test `test_self_deploy_viewer_403` for the boundary lock.

## Image-URI resolution

Resolution order, evaluated at deploy time (NOT at provision time — the image is referenced by the follow-up `service-cd.yml` pipeline, not Terraform state):

1. Read the product's `image_uri_env_var` (e.g. `CATALYST_SELF_IMAGE_URI`). If set, use it verbatim.
2. Otherwise, fall back to `f"{CATALYST_ECR_BASE}:{product_id}-latest"`.
3. If neither is configured, raise `HTTPException(500)` with a clear "image URI unresolvable" message — operators see this BEFORE the Terraform subprocess fires, so no partial-state cleanup is needed.

## Idempotency

The catalog deploy endpoint composes two idempotency layers:

* **Caller-supplied `idempotency_key`** — combined with `product_id` and `construct_address` into `product:{product_id}:{construct_address}:{key}` so reusing the same key against a DIFFERENT product does not collide. Replay returns the cached payload (same `deployment_id`, same ARNs) without re-invoking `onboard.provision_app`.
* **No idempotency key** — falls through to Terraform's own S3-state convergence. Each call mints a new `deployment_id` but the L4 state is the same, so the AWS-side resources are idempotent regardless.

## See also

- [`docs/onboarding/application.md` → "Self-deploying Catalyst"](onboarding/application.md#self-deploying-catalyst-103--cat-3) — the operator-facing one-liner
- [`services/catalyst-api/catalyst/products.py`](../services/catalyst-api/catalyst/products.py) — the catalog dict + deploy orchestration
- [`tests/e2e/test_journey_07_self_deploy.py`](../tests/e2e/test_journey_07_self_deploy.py) — end-to-end walkthrough (mock-mode)
- [ADR-014](ADR/ADR-014-services-onboard-provisioning-mode.md) + [ADR-015](ADR/ADR-015-terraform-state-partitioning.md) — the underlying onboard contract this layer wraps
