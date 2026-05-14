---
name: fastapi-control-plane
description: >-
  FastAPI service patterns for catalyst-api: router organization, pydantic v2
  request/response models, construct-scoped path design, IAM auth middleware,
  dependency injection, structured error responses, health endpoints, and
  OpenAPI generation. Use when building or modifying catalyst-api endpoints.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/fastapi-control-plane/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->


# FastAPI control plane

## Role

You guide the design and implementation of `catalyst-api`, the FastAPI control plane running on ECS Fargate. You enforce async-first patterns, construct-scoped routing, and API-lifecycle discipline per *Enterprise API Management* (Weir, Ch 7: API lifecycle) and *Platform Engineering for Architects* (Korbiacher et al., Ch 6: developer self-service, auth, tenancy). For thin routers, SOLID boundaries, and maintainable handler cores, invoke `@clean-python-code`.

## Instructions

1. **Router organization** — one router module per domain, mounted under versioned prefixes:

   ```
   services/catalyst-api/catalyst/
     routers/
       tenants.py          # /v1/tenants/...
       environments.py     # /v1/tenants/{t}/environments/...
       landing_zones.py    # /v1/tenants/{t}/environments/{e}/landing-zones/...
       projects.py         # /v1/.../projects/...
       applications.py     # /v1/.../applications/...
       deployments.py      # /v1/.../deployments/...
       services_catalog.py # /v1/.../services/...
       health.py           # /v1/health, /v1/openapi.json
     models/
       constructs.py       # ConstructAddress, Tenant, Environment, ...
       deployments.py      # DeployRequest, DeployStatus, ...
       common.py           # PaginatedResponse, ErrorResponse, ...
     middleware/
       auth.py             # IAM / OIDC token validation
       trace.py            # X-Ray trace_id + request_id injection
       error_handler.py    # Global exception → structured JSON
     dependencies/
       db.py               # Aurora connection pool (asyncpg via aioboto3 IAM auth)
       github.py           # GitHub App client (httpx)
       construct_scope.py  # Extract + validate construct address from path
   ```

2. **Construct-scoped paths** — the construct hierarchy embeds in the URL:

   ```
   /v1/tenants/{tenant_slug}
   /v1/tenants/{tenant_slug}/environments/{env_slug}
   /v1/tenants/{tenant_slug}/environments/{env_slug}/landing-zones/{lz_slug}
   .../{lz_slug}/projects/{project_slug}/applications/{app_slug}
   ```

   Use a shared `ConstructScope` dependency that parses the path params into a `ConstructAddress` pydantic model and validates the caller's permission at that scope level.

3. **Pydantic v2 models** — every request/response is typed:

   ```python
   from pydantic import BaseModel, Field, ConfigDict

   class TenantCreate(BaseModel):
       model_config = ConfigDict(strict=True)
       slug: str = Field(..., pattern=r"^[a-z0-9-]{2,40}$")
       display_name: str = Field(..., min_length=1, max_length=120)
       owner_email: str  # validated as email by a field_validator

   class TenantResponse(BaseModel):
       model_config = ConfigDict(from_attributes=True)
       slug: str
       display_name: str
       created_at: datetime
       construct_address: str  # e.g. "pharmacy"
   ```

   Per *Enterprise API Management* Ch 5 (CRUD service pattern): keep request models minimal (what the caller provides) and response models rich (what the system knows).

4. **Auth middleware** — two layers:

   - **Token validation**: OIDC JWT from GitHub Actions or API key from `catalyst` CLI; resolved to a principal with scoped permissions.
   - **Construct-scope check**: the `ConstructScope` dependency asserts the principal has the required verb (`read`, `create`, `deploy`, etc.) at the resolved construct level. Deny by default; 403 or 404 (hide existence) as appropriate.

   Per *Platform Engineering for Architects* Ch 6 (pp 207-217): authentication and tenancy are foundational — never optional, never deferred.

5. **Structured error responses** — all errors return consistent JSON:

   ```python
   class ErrorResponse(BaseModel):
       detail: str
       code: str          # e.g. "ILLEGAL_TRANSITION", "CONSTRUCT_NOT_FOUND"
       trace_id: str | None = None
       request_id: str | None = None

   # Register as exception handlers in main.py
   @app.exception_handler(ConstructNotFoundError)
   async def construct_not_found(request, exc):
       return JSONResponse(status_code=404, content=ErrorResponse(...).model_dump())
   ```

6. **Health and metadata endpoints**:

   ```
   GET /v1/health          → {"status": "ok", "version": "...", "aurora": "connected"}
   GET /v1/openapi.json    → generated OpenAPI 3.1 spec
   ```

   Health checks Aurora connectivity and returns degraded if the pool is exhausted. Per *Enterprise API Management* Ch 7 (Observe phase): observability starts at the health endpoint.

7. **Pagination** — cursor-based, not offset:

   ```python
   class PaginatedResponse(BaseModel, Generic[T]):
       items: list[T]
       next_cursor: str | None = None
       total_count: int | None = None  # only when cheap to compute
   ```

   Per *Enterprise API Management* Ch 5 (payload pagination, p130): cursor pagination scales; offset does not.

8. **Dependency injection** — use FastAPI `Depends()` for:
   - Database session (async context manager)
   - GitHub client (httpx.AsyncClient from app state)
   - Construct scope (parsed from path + validated)
   - Current principal (from auth middleware)
   - Structlog logger (bound with trace_id + request_id)

9. **Logging** — `structlog` only, never `print()`:

   ```python
   import structlog
   logger = structlog.get_logger()

   # In handlers:
   logger.info("deployment_created", deployment_id=dep.id,
               construct_address=str(scope.address), actor=principal.id)
   ```

   Every log line includes `trace_id` and `request_id` (injected by middleware).

10. **Design-first workflow** — per *Enterprise API Management* Ch 7 (API lifecycle, pp 206-231):
    - Write the OpenAPI spec (or let FastAPI generate from models) before implementing business logic.
    - Use `mock and try` (p217): stub endpoints return 501 with the expected response shape so consumers can develop in parallel.
    - Version routes (`/v1/...`); add `Sunset` header when deprecating.

## Output

When helping with catalyst-api:

- **New endpoint**: provide router code + pydantic models + dependency wiring + test stub
- **New model**: pydantic v2 with validators, `ConfigDict`, and example values
- **Auth question**: middleware pattern + construct-scope check + error response
- **Architecture question**: cite the relevant book chapter, link to `AGENTS.md` service inventory

## Guardrails

- No `requests` library — use `httpx` (async-first, modern TLS).
- No `print()` — log via `structlog`.
- No secrets in code, env files, or log output — source from Secrets Manager or SSM.
- No wildcard IAM — the task role for catalyst-api has explicit resource ARNs per `AGENTS.md` §7.
- No SQL with f-strings — use parameterized queries via asyncpg.
- No `datetime.utcnow()` — use `datetime.now(UTC)`.
- Endpoints that mutate state must be idempotent (use `Idempotency-Key` header or ULID-based dedup).
