from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from mangum import Mangum
from pydantic import ValidationError

from .catalog import RESOURCE_CATALOG
from .constructs import ConstructAddress
from .errors import (
    ResourceNotFound,
    ValidationFailure,
    to_http_exception,
)
from .models import (
    ApplicationCreateRequest,
    EnvironmentCreateRequest,
    LandingZoneCreateRequest,
    OuCreateRequest,
    ProductDeploymentRecord,
    ProductDeploymentRequest,
    ServiceConfigRequest,
    ServiceDeployRequest,
    ServiceOnboardRequest,
)
from .observability import (
    caller_arn_var,
    correlation_id_var,
    endpoint_template,
    endpoint_var,
    metrics,
    request_var,
    tenant_var,
)
from .onboard import provision_app
from .rbac import AccessContext, access_dependency, can_read_scope, require_write
from .repository import Repository, get_repository

logger = logging.getLogger(__name__)

app = FastAPI(title="Catalyst API")


# ---------------------------------------------------------------------------
# Middleware registration (#60).
#
# FastAPI/Starlette middleware order: the LAST-added middleware runs
# FIRST on the request path (i.e. wraps every other middleware). We
# want the order on the wire to be:
#
#     request  -> observability_middleware -> correlation_id_middleware -> handler
#     response <- observability_middleware <- correlation_id_middleware <- handler
#
# So we add ``correlation_id_middleware`` FIRST (innermost) and
# ``observability_middleware`` SECOND (outermost). That way the
# observability layer can read ``request.state.correlation_id`` (set
# by the inner middleware) on the way out, and a single id threads
# every metric + log line.
# ---------------------------------------------------------------------------


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Thread ``X-Correlation-ID`` through every response, including errors.

    The per-handler ``correlation_id_dependency`` already sets the
    response header on success paths, but when a handler raises
    ``HTTPException`` FastAPI builds a fresh response from scratch — so
    the dependency-set header is lost. This middleware re-applies it
    unconditionally using the same id rule (request header if present,
    UUIDv4 otherwise) so a single id threads every response, success or
    failure.
    """

    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Per-request metrics + structured log emission (#60).

    Wraps every request — including those that fail with HTTPException
    via FastAPI's exception handler. For each request we:

        1. Compute the cardinality-bounded endpoint template (so a
           construct-address URL collapses to ``/services/{addr}``
           instead of exploding the CloudWatch dimension cap).
        2. Set the contextvars that :class:`JSONFormatter` reads so any
           ``logger.info(...)`` call inside the handler picks up the
           threaded fields.
        3. Call the downstream handler chain.
        4. Emit ``RequestCount`` + ``RequestDuration``.
        5. If ``status_code >= 400``, emit ``ErrorCount`` with the
           ``error_class`` set by :func:`catalyst.errors.to_http_exception`
           (falls back to a status-derived name if unset, which can
           happen for paths that raise a bare ``HTTPException`` without
           going through the boundary translator).
        6. Emit a ``request_complete`` structured log line.

    This middleware runs OUTSIDE ``correlation_id_middleware`` on the
    request path (added second per FastAPI's last-added-first-run rule)
    so the correlation id set by the inner middleware is visible on the
    response side here.

    Per #60: the Onboard-specific ``Catalyst/Onboard:OnboardDuration``
    metric stays as a load-bearing trip-wire — this generic
    ``Catalyst/API:RequestDuration`` fires alongside it for the same
    invocation, giving operators BOTH the Onboard-specific dimension
    and the generic per-endpoint duration in one alarm-able place.
    """

    method = request.method
    endpoint = endpoint_template(request.url.path)
    # Stash the resolved endpoint on request.state too so any code path
    # that walks the request (e.g. a future audit hook) can read it
    # without re-doing the template resolution.
    request.state.endpoint = endpoint

    # Populate the contextvars the JSON formatter reads. The correlation
    # id will have been set by ``correlation_id_middleware`` (which runs
    # before us on the request path); ``caller_arn`` may not be set yet
    # (it's resolved inside the rbac dependency at handler time), but
    # we set it from the request header eagerly so the request_complete
    # log line carries it for every request.
    correlation_id = getattr(request.state, "correlation_id", None) or (
        request.headers.get("X-Correlation-ID")
    )
    caller_arn = request.headers.get("x-caller-arn") or None

    endpoint_token = endpoint_var.set(endpoint)
    cid_token = correlation_id_var.set(correlation_id)
    arn_token = caller_arn_var.set(caller_arn)
    tenant_token = tenant_var.set(_extract_tenant_from_path(request.url.path))
    # Stash the current Request on a contextvar so ``to_http_exception``
    # can populate ``request.state.error_class`` even when the handler
    # raises without plumbing the request through. Reset under finally
    # below.
    request_token = request_var.set(request)

    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0

        # Per-request metric emissions. Each call is internally
        # swallow-on-failure so a CloudWatch outage cannot break the
        # request path — observability is best-effort.
        metrics.request_count(endpoint, method, status_code)
        metrics.request_duration(endpoint, method, duration_ms)
        if status_code >= 400:
            error_class = _resolve_error_class(request, status_code)
            metrics.error_count(endpoint, method, error_class)

        # Structured log line. Emitted at INFO for 2xx/3xx, WARNING for
        # 4xx (client-side miss), ERROR for 5xx (server-side fault) so
        # an operator filtering by level in CloudWatch Logs Insights
        # sees the same severity distinction the existing handler-side
        # logs use.
        log_level = logging.INFO
        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING

        logger.log(
            log_level,
            "request_complete",
            extra={
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 3),
                "correlation_id": correlation_id,
                "caller_arn": caller_arn,
            },
        )

        # Reset the contextvars so the next request on this asyncio
        # task starts clean. The reset MUST happen even on the
        # exception path, hence the ``finally`` placement.
        endpoint_var.reset(endpoint_token)
        correlation_id_var.reset(cid_token)
        caller_arn_var.reset(arn_token)
        tenant_var.reset(tenant_token)
        request_var.reset(request_token)


def _resolve_error_class(request: Request, status_code: int) -> str:
    """Return the error-class dimension value for ``ErrorCount``.

    Preference order:

        1. ``request.state.error_class`` — set by
           :func:`catalyst.errors.to_http_exception` when the error went
           through the boundary translator. This is the same class name
           that appears in the response body's ``error`` field.
        2. A status-derived name (``ValidationError`` for 422,
           ``Forbidden`` for 403, etc.) for paths that raise a bare
           ``HTTPException`` (e.g. FastAPI's own Pydantic 422 handler
           which never touches our translator).
        3. ``"Unknown"`` as a last-resort sentinel so the metric still
           fires with a bounded dimension value.
    """

    state = getattr(request, "state", None)
    if state is not None:
        explicit = getattr(state, "error_class", None)
        if isinstance(explicit, str) and explicit:
            return explicit

    # Inline copy of errors._http_status_to_error_name — duplicated here
    # to avoid a runtime import in the hot middleware path.
    return {
        400: "BadRequest",
        401: "Unauthorized",
        403: "Forbidden",
        404: "ResourceNotFound",
        409: "IdempotencyConflict",
        422: "ValidationError",
        429: "TooManyRequests",
        500: "InternalServerError",
        503: "RepositoryFailure",
    }.get(status_code, "Unknown")


def _extract_tenant_from_path(path: str) -> str | None:
    """Pull the ``{tenant}`` segment out of a path when present.

    Used by the structured-log threading so a log line emitted inside a
    handler that operates on a known tenant carries the tenant id even
    if the handler itself didn't think to add it. Returns ``None`` for
    routes that don't have a tenant segment (e.g. ``/health``,
    ``/catalog``, ``/services/onboard`` — the last carries a tenant
    inside the construct address body, not the path).
    """

    if not path:
        return None
    parts = path.lstrip("/").split("/")
    if len(parts) >= 2 and parts[0] == "orgs":
        return parts[1]
    if len(parts) >= 2 and parts[0] == "products" and parts[1] != "deploy":
        # /products/{tenant}/{project}/{app}
        return parts[1]
    return None


def repo_dependency() -> Repository:
    return get_repository()


# ---------------------------------------------------------------------------
# Correlation-ID propagation (#61).
#
# Every handler shares a single ``correlation_id`` produced by the
# :func:`correlation_id_dependency`. The id is taken from the
# ``X-Correlation-ID`` request header if present (so the CLI / GitHub
# Action can thread its own id through API calls) or minted as a fresh
# UUIDv4 otherwise. The id lands in:
#
#   * Every success-path response body (``correlation_id`` field — already
#     existed on most handlers; harmonised across all of them here)
#   * Every error-path response body (via ``errors.to_http_exception``)
#   * The ``X-Correlation-ID`` response header (so a CLI / curl client
#     can grep CloudWatch without parsing the JSON body)
#   * Every structured log line emitted by the wrapped handler
#
# A single id therefore threads the full request lifecycle: header in,
# log lines mid-request, body + header out.
# ---------------------------------------------------------------------------


def correlation_id_dependency(
    response: Response,
    request: Request,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> str:
    """Return the per-request correlation id used by the handler.

    ``correlation_id_middleware`` runs first and stashes the canonical id
    on ``request.state.correlation_id`` — we re-use that here so the
    middleware and the handler always agree on the id (otherwise a fresh
    UUID would be minted twice and the response header would disagree
    with the body).
    """

    cached = getattr(request.state, "correlation_id", None)
    correlation_id = cached or x_correlation_id or str(uuid.uuid4())
    response.headers["X-Correlation-ID"] = correlation_id
    request.state.correlation_id = correlation_id
    return correlation_id


def _idempotent_response(
    repo: Repository, idempotency_key: str | None, payload: dict, response: Response
) -> dict:
    if not idempotency_key:
        return payload
    cached = repo.get_idempotent(idempotency_key)
    if cached is not None:
        response.headers["X-Idempotent-Replay"] = "true"
        return cached
    repo.put_idempotent(idempotency_key, payload)
    return payload


def _parse_construct(
    value: str, correlation_id: str, request: Request | None = None
) -> ConstructAddress:
    """Parse + validate a construct address, raising the canonical 422 on miss."""

    try:
        return ConstructAddress(value=value)
    except ValidationError as exc:
        raise to_http_exception(
            ValidationFailure(
                "construct address must be tenant/env/lz/project/app",
                context={"raw": value, "pydantic": str(exc)},
            ),
            correlation_id,
            request=request,
        ) from exc


def _safe_call(
    correlation_id: str,
    fn: Callable[..., object],
    *args: object,
    request: Request | None = None,
    **kwargs: object,
):
    """Invoke ``fn(*args, **kwargs)`` inside the canonical error boundary.

    Repository / boto3 failures are caught here, classified by
    :func:`errors.to_http_exception`, and re-raised as ``HTTPException``
    with the canonical ``{error, correlation_id, detail}`` body. All
    handlers funnel AWS-side calls through this helper so the error
    shape is uniform without sprinkling try/except across every
    function body.

    The optional ``request`` parameter (keyword-only) is forwarded to
    :func:`to_http_exception` so the chosen error-class name lands on
    ``request.state.error_class`` — the observability middleware (#60)
    reads that to tag ``ErrorCount`` with the canonical class name.
    Existing call sites that omit ``request`` continue to work; the
    error-class dimension falls back to a status-derived name in that
    case.
    """

    try:
        return fn(*args, **kwargs)
    except HTTPException:
        # Don't double-wrap something the caller already shaped; pass through.
        raise
    except Exception as exc:  # noqa: BLE001 - boundary wrapper
        logger.error(
            "handler_boundary_error",
            extra={
                "correlation_id": correlation_id,
                "fn": getattr(fn, "__name__", repr(fn)),
                "error_class": type(exc).__name__,
            },
        )
        raise to_http_exception(exc, correlation_id, request=request) from exc


@app.get("/health")
def health(correlation_id: str = Depends(correlation_id_dependency)) -> dict:
    """Liveness probe; never wrapped because it has no AWS-side dependency."""

    return {"status": "ok", "correlation_id": correlation_id}


@app.get("/catalog")
def catalog(
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
) -> dict:
    return {
        "resources": [
            {"key": r.key, "category": r.category, "default_exposure": r.default_exposure}
            for r in RESOURCE_CATALOG
        ],
        "role": access.role,
        "correlation_id": correlation_id,
    }


@app.post("/orgs/{tenant}/ous")
def create_ou(
    tenant: str,
    request: OuCreateRequest,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier1")
    _safe_call(correlation_id, repo.append_org_record, tenant, "ous", request.name)
    return {
        "tenant": tenant,
        "ou_name": request.name,
        "correlation_id": correlation_id,
    }


@app.post("/orgs/{tenant}/landing-zones")
def create_landing_zone(
    tenant: str,
    request: LandingZoneCreateRequest,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    """Register a landing zone and return the #169 Gherkin AC payload.

    Response shape per scenario 1: ``landing_zone_id``, ``construct_address``,
    ``status: provisioned`` — plus the legacy ``landing_zone`` name field
    that existing callers already consume.
    """

    require_write(access, "tier1")
    _safe_call(
        correlation_id,
        repo.append_org_record,
        tenant,
        "landing_zones",
        request.name,
        attributes={
            "account_id": request.account_id,
            "compliance": request.compliance,
        },
    )
    landing_zone_id = f"{tenant}/{request.name}"
    return {
        "tenant": tenant,
        "landing_zone": request.name,
        "landing_zone_id": landing_zone_id,
        "construct_address": landing_zone_id,
        "account_id": request.account_id,
        "compliance": request.compliance,
        "status": "provisioned",
        "correlation_id": correlation_id,
    }


@app.post("/orgs/{tenant}/environments")
def create_environment(
    tenant: str,
    request: EnvironmentCreateRequest,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    """Register an environment under an existing landing zone.

    Validates that ``request.landing_zone`` resolves to a previously
    registered LZ on the same tenant — per #169 Gherkin scenario 3 the
    response is 422 with ``detail`` mentioning "unknown landing zone" when
    the reference does not exist.
    """

    require_write(access, "tier1")
    org = _safe_call(correlation_id, repo.get_organization, tenant)
    known_lzs = {lz["name"] for lz in org.get("landing_zones", [])}
    if request.landing_zone not in known_lzs:
        raise to_http_exception(
            ValidationFailure(f"unknown landing zone: {request.landing_zone}"),
            correlation_id,
        )
    _safe_call(
        correlation_id,
        repo.append_org_record,
        tenant,
        "environments",
        request.name,
        attributes={"landing_zone": request.landing_zone},
    )
    return {
        "tenant": tenant,
        "environment": request.name,
        "environment_id": f"{tenant}/{request.landing_zone}/{request.name}",
        "landing_zone": request.landing_zone,
        "status": "provisioned",
        "correlation_id": correlation_id,
    }


@app.post("/orgs/{tenant}/applications")
def create_application(
    tenant: str,
    request: ApplicationCreateRequest,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier1")
    _safe_call(
        correlation_id,
        repo.append_org_record,
        tenant,
        "applications",
        request.name,
        attributes={"project": request.project},
    )
    return {
        "tenant": tenant,
        "application": request.name,
        "project": request.project,
        "correlation_id": correlation_id,
    }


@app.get("/orgs/{tenant}")
def get_org(
    tenant: str,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    if not can_read_scope(access, tenant):
        raise to_http_exception(
            HTTPException(status_code=403, detail="insufficient_permissions"),
            correlation_id,
        )
    structure = _safe_call(correlation_id, repo.get_organization, tenant)
    return {
        "tenant": tenant,
        "structure": structure,
        "correlation_id": correlation_id,
    }


@app.post("/services/onboard")
def onboard_service(
    request: ServiceOnboardRequest,
    response: Response,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    """Tier 2 onboard: synchronously provision per-app AWS resources via Terraform.

    Replaces the v1 stubbed-ARN handler with the real ``terraform apply``
    flow committed in ADR-014. The L4 backend key is generated per
    invocation following ADR-015's state-key hierarchy
    (``catalyst/tenants/{tenant}/environments/{env}/apps/{app}.tfstate``)
    inside ``provision_app``.

    Idempotency continues to flow through the existing
    ``_idempotent_response`` wrapper — first call drives the Terraform
    apply, replay returns the cached payload without re-invoking
    ``provision_app`` (so Terraform's own S3-state convergence is only
    exercised on the first call within the 24h idempotency window).

    ``onboard.provision_app`` already implements the per-#61 boundary
    contract internally (catching ``CalledProcessError`` / ``TimeoutExpired``
    and raising ``HTTPException(500)`` with the correlation id). We
    re-raise those untouched so the curated message survives.
    """

    require_write(access, "tier2")
    construct = _parse_construct(request.construct_address, correlation_id)
    cached = _safe_call(correlation_id, repo.get_idempotent, request.idempotency_key)
    if cached is not None:
        response.headers["X-Idempotent-Replay"] = "true"
        return cached
    _safe_call(correlation_id, repo.init_service, construct.value)
    result = provision_app(
        construct.value,
        idempotency_key=request.idempotency_key,
        correlation_id=correlation_id,
        service_type=request.service_type,
    )
    payload = {
        "construct_address": result.construct_address,
        "ecr_uri": result.ecr_uri,
        "execution_role_arn": result.execution_role_arn,
        "log_group_name": result.log_group_name,
        "alb_listener_rule_arn": result.alb_listener_rule_arn,
        "catalog_record_key": result.catalog_record_key,
        "state_key": result.state_key,
        "status": "provisioned",
        "correlation_id": correlation_id,
    }
    return _idempotent_response(repo, request.idempotency_key, payload, response)


@app.post("/services/{construct_address:path}/deploy")
def deploy_service(
    construct_address: str,
    request: ServiceDeployRequest,
    response: Response,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier2")
    construct = _parse_construct(construct_address, correlation_id)
    service = _safe_call(correlation_id, repo.get_service, construct.value)
    if service is None:
        raise to_http_exception(
            ResourceNotFound("service_not_found"), correlation_id
        )
    event = {"image_tag": request.image_tag, "at": repo.now().isoformat()}
    _safe_call(correlation_id, repo.append_service_deployment, construct.value, event)
    payload = {
        "construct_address": construct.value,
        "deployed_image_tag": request.image_tag,
        "deployment_status": "stabilizing",
        "correlation_id": correlation_id,
    }
    return _idempotent_response(repo, request.idempotency_key, payload, response)


@app.get("/services/{construct_address:path}")
def service_status(
    construct_address: str,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    construct = _parse_construct(construct_address, correlation_id)
    tenant, _, _, project, _ = construct.value.split("/")
    if not can_read_scope(access, tenant, project):
        raise to_http_exception(
            HTTPException(status_code=403, detail="insufficient_permissions"),
            correlation_id,
        )
    service = _safe_call(correlation_id, repo.get_service, construct.value)
    if not service:
        raise to_http_exception(
            ResourceNotFound("service_not_found"), correlation_id
        )
    deployments = service["deployments"]
    latest = deployments[-1] if deployments else None
    return {
        "construct_address": construct.value,
        "current_image_tag": latest["image_tag"] if latest else "none",
        "running_task_count": 1 if latest else 0,
        "last_deploy_at": latest["at"] if latest else None,
        "correlation_id": correlation_id,
    }


@app.post("/services/{construct_address:path}/config")
def service_config(
    construct_address: str,
    request: ServiceConfigRequest,
    response: Response,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier2")
    construct = _parse_construct(construct_address, correlation_id)
    _safe_call(
        correlation_id, repo.update_service_config, construct.value, request.params
    )
    payload = {
        "construct_address": construct.value,
        "ssm_path_prefix": f"/catalyst/{construct.value}/config/",
        "param_count": len(request.params),
        "correlation_id": correlation_id,
    }
    return _idempotent_response(repo, request.idempotency_key, payload, response)


@app.get("/iam/groups")
def list_groups(
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
) -> dict:
    return {
        "groups": [
            "catalyst-owners",
            "catalyst-administrators",
            "catalyst-viewers",
            "catalyst-support-admins",
            "catalyst-support-operators",
            "catalyst-support-viewers",
            "catalyst-breakglass",
        ],
        "correlation_id": correlation_id,
    }


@app.post("/iam/groups/{group}/members")
def update_group_membership(
    group: str,
    user_arn: str = Header(...),
    action: str = Header(...),
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    if access.role != "owner":
        raise to_http_exception(
            HTTPException(status_code=403, detail="insufficient_permissions"),
            correlation_id,
        )
    _safe_call(correlation_id, repo.record_group_action, group, action, user_arn)
    return {"group": group, "action": action, "correlation_id": correlation_id}


@app.post("/products/deploy")
def deploy_product(
    request: ProductDeploymentRequest,
    response: Response,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier2")
    key = f"{request.tenant}/{request.project}/{request.app}"
    now = datetime.now(timezone.utc)
    record = ProductDeploymentRecord(
        tenant=request.tenant,
        project=request.project,
        app=request.app,
        lifecycle_state="planned",
        resources=[r.key for r in RESOURCE_CATALOG],
        updated_at=now,
    )
    _safe_call(correlation_id, repo.put_product, key, record.model_dump(mode="json"))
    product = _safe_call(correlation_id, repo.get_product, key)
    payload = {"product_instance": product, "correlation_id": correlation_id}
    return _idempotent_response(repo, request.idempotency_key, payload, response)


@app.get("/products")
def list_products(
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    records = _safe_call(correlation_id, repo.list_products)
    visible = []
    for record in records:
        if can_read_scope(access, record["tenant"], record["project"]):
            visible.append(record)
    return {
        "instances": visible,
        "count": len(visible),
        "correlation_id": correlation_id,
    }


@app.get("/products/{tenant}/{project}/{app_name}")
def get_product(
    tenant: str,
    project: str,
    app_name: str,
    correlation_id: str = Depends(correlation_id_dependency),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    if not can_read_scope(access, tenant, project):
        raise to_http_exception(
            HTTPException(status_code=403, detail="insufficient_permissions"),
            correlation_id,
        )
    key = f"{tenant}/{project}/{app_name}"
    record = _safe_call(correlation_id, repo.get_product, key)
    if record is None:
        raise to_http_exception(
            ResourceNotFound("product_not_found"), correlation_id
        )
    return {"product_instance": record, "correlation_id": correlation_id}


handler = Mangum(app)
