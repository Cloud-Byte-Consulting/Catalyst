"""Catalyst product catalog + self-deploy orchestration (#103 — CAT-3).

This module backs the new ``GET /products/catalog`` and
``POST /products/catalog/{product_id}/deploy`` endpoints in
:mod:`catalyst.main`. The endpoint family is the meta-feature for CAT-3:
Catalyst uses its own onboard contract to deploy another Catalyst API
instance, proving the platform deploys its own products (not just
arbitrary apps).

Architecture (Option A in the Decision Log on #103)
---------------------------------------------------

A small in-process :data:`PRODUCT_CATALOG` dict maps stable product IDs
(``catalyst-api`` for now) to product metadata (display name, image-URI
env var, RBAC required-roles set, default service type). Deploys go
through :func:`deploy_product`, which:

  1. Validates the product exists in the catalog.
  2. Validates the caller's :class:`AccessContext` role is in the
     product's ``required_roles`` frozenset.
  3. Validates the construct address against the canonical
     :class:`ConstructAddress` pattern (delegated to the underlying
     ``onboard.provision_app`` so the contract stays single-sourced).
  4. Replays the idempotency key against the per-product
     deployment-record store (so the same key returns the same record
     without re-invoking Terraform).
  5. Calls ``onboard.provision_app`` to actually run the L4 Terraform
     composite (same path Tier 2 app onboards take, per ADR-014/ADR-015).
  6. Records a ``product_deployment`` row keyed by ``(product_id,
     construct_address, idempotency_key)`` so a future call with the
     same triple hits the idempotent-replay branch.
  7. Returns the standard onboard ARN payload plus ``product_id`` and
     ``deployment_id`` so the caller can correlate the catalog deploy
     with the Tier 2 record produced under the hood.

Image-URI resolution
--------------------

The product metadata carries an ``image_uri_env_var`` name (e.g.
``CATALYST_SELF_IMAGE_URI``). At deploy time, :func:`_resolve_image_uri`
looks up the env var; if unset it falls back to a sensible default
keyed off ``CATALYST_ECR_BASE`` (the same ECR registry the Catalyst
runtime uses). If both are missing the function raises a 500 via
:class:`HTTPException` — the operator MUST configure one or the other
to deploy a product. The image URI is **not** baked into Terraform
state at provision time; it's used by the subsequent ``service-cd.yml``
pipeline to update the runtime to the right tag.

RBAC contract (Decision Log on #103)
-----------------------------------

``required_roles`` is a frozenset of strings drawn from
:func:`rbac._access_from_groups`'s output vocabulary:

  * ``owner``         — ``catalyst-owners`` / ``catalyst-breakglass``
  * ``administrator`` — ``catalyst-support-admins`` / ``catalyst-administrators``
  * ``viewer``        — read-only roles (never in ``required_roles`` for a deploy)
  * ``scoped``        — tenant/project-scoped (must additionally own
    the tenant in the construct address; checked separately)

A caller whose ``access.role`` is in ``required_roles`` is allowed; a
scoped caller's tenant ownership is checked separately by the handler
(via the existing ``can_read_scope`` / construct parsing logic) since
the catalog deploy must additionally pass the construct-address
tenant boundary.

Coordination with #167
----------------------

This module is a thin orchestrator over ``onboard.provision_app``; we
neither replace nor fork it. The ``service_type`` argument flows
through cleanly (Catalyst API itself is a ``web-service``), so no
internal helper was needed. If the onboard contract evolves in
parallel work, this module continues to compose because we depend on
the public function signature, not internals.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from pydantic import ValidationError

from .constructs import ConstructAddress
from .errors import (
    ResourceNotFound,
    ScopeInsufficient,
    ValidationFailure,
    to_http_exception,
)
from .onboard import provision_app
from .rbac import AccessContext, can_read_scope

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PRODUCT_CATALOG — the single source of truth for platform-shipped products.
#
# Adding a new product is a single-line change: register its metadata here
# and the GET /products/catalog endpoint exposes it automatically.
#
# Schema (each value is a dict):
#
#   name:                 human-readable display name
#   description:          short tagline for catalog UIs / CLIs
#   image_uri_env_var:    env var the operator sets to override the default
#                         image URI at deploy time (resolved by
#                         :func:`_resolve_image_uri`)
#   service_type:         the ``onboard.provision_app`` service_type to use
#                         (``web-service``, ``worker``, ``scheduled-job``)
#   required_roles:       frozenset of role strings the caller must hold.
#                         See module docstring for the role vocabulary.
# ---------------------------------------------------------------------------


PRODUCT_CATALOG: dict[str, dict[str, Any]] = {
    "catalyst-api": {
        "name": "Catalyst API",
        "description": (
            "Self-managed deployment of an additional Catalyst API instance. "
            "Exercises the platform's own onboard contract to prove Catalyst "
            "deploys its own products, not just arbitrary apps (CAT-3)."
        ),
        # The image URI is resolved at deploy time from this env var; the
        # default (if missing) is f"{ECR_BASE}:catalyst-api-latest" — see
        # _resolve_image_uri below.
        "image_uri_env_var": "CATALYST_SELF_IMAGE_URI",
        "service_type": "web-service",
        # Decision Log §RBAC contract — owner OR administrator can deploy.
        # Scoped principals are handled separately by the handler (they must
        # additionally own the tenant segment of the construct address).
        "required_roles": frozenset({"owner", "administrator"}),
    },
}


# ---------------------------------------------------------------------------
# Public read accessors. Both are tiny but the API surface goes through
# them (not bare dict.get calls) so future enrichment — e.g. dynamic
# catalog from a Parameter Store path — can replace the dict without
# touching every call site.
# ---------------------------------------------------------------------------


def get_product(product_id: str) -> dict[str, Any] | None:
    """Return the catalog entry for ``product_id`` or ``None`` if missing."""

    return PRODUCT_CATALOG.get(product_id)


def list_products() -> list[dict[str, Any]]:
    """Return all catalog entries, each enriched with its ``product_id`` key.

    The dict is normalised to JSON-friendly types — ``frozenset`` becomes a
    sorted ``list`` so FastAPI's default encoder can serialise it without
    a custom encoder.
    """

    return [_serialise_product(pid, meta) for pid, meta in PRODUCT_CATALOG.items()]


def _serialise_product(product_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Render a catalog entry for the API response.

    The internal ``required_roles`` field is a frozenset; we convert to a
    sorted list so the JSON body is stable across runs (a frozenset's
    iteration order is implementation-defined).
    """

    return {
        "product_id": product_id,
        "name": meta["name"],
        "description": meta["description"],
        "service_type": meta["service_type"],
        "image_uri_env_var": meta["image_uri_env_var"],
        "required_roles": sorted(meta["required_roles"]),
    }


# ---------------------------------------------------------------------------
# RBAC check — a separate function so unit tests can exercise the matrix
# without standing up a TestClient. The handler calls this BEFORE invoking
# deploy_product so a 403 returns without touching the repo.
# ---------------------------------------------------------------------------


def is_caller_authorized_for_product(
    access: AccessContext, product_id: str
) -> bool:
    """Return True if ``access.role`` is in the product's required-roles set.

    For ``scoped`` callers, this returns ``True`` if and only if the
    product explicitly lists ``scoped`` in its required-roles set — by
    default products do NOT allow scoped callers because a scoped caller
    can only act inside their own tenant boundary, and a meta-deploy of
    Catalyst itself should be an owner/administrator action. The handler
    still does the tenant-membership check on the construct address.

    Returns ``False`` for unknown products so a misrouted call surfaces
    as 403 rather than 200 (defence in depth — the caller path SHOULD
    short-circuit on ``get_product is None`` first).
    """

    product = get_product(product_id)
    if product is None:
        return False
    return access.role in product["required_roles"]


# ---------------------------------------------------------------------------
# Image-URI resolution.
#
# Resolution order (deploy time, not provision time):
#   1. Read the product's image_uri_env_var; if set, use it verbatim.
#   2. Fall back to f"{CATALYST_ECR_BASE}:{product_id}-latest".
#   3. If neither is available, raise HTTPException(500) so the operator
#      sees a clear configuration error instead of a half-provisioned
#      product.
#
# The image URI is returned alongside the ARN payload so a follow-up
# service-cd.yml run can pick it up. This module does NOT push the image
# to ECR — that's the platform-build pipeline's job.
# ---------------------------------------------------------------------------


def _resolve_image_uri(product_id: str, product: dict[str, Any]) -> str:
    """Resolve the container image URI for ``product_id``.

    Raises
    ------
    HTTPException
        500 if neither the per-product env var nor ``CATALYST_ECR_BASE``
        is set — the operator MUST configure one to deploy a product.
    """

    env_var = product["image_uri_env_var"]
    override = os.environ.get(env_var, "").strip()
    if override:
        return override

    ecr_base = os.environ.get("CATALYST_ECR_BASE", "").strip()
    if not ecr_base:
        raise HTTPException(
            status_code=500,
            detail=(
                f"product image URI unresolvable: set {env_var} or "
                f"CATALYST_ECR_BASE in the Catalyst API environment"
            ),
        )
    return f"{ecr_base}:{product_id}-latest"


# ---------------------------------------------------------------------------
# Deploy orchestration.
#
# The handler in main.py wraps this call inside the existing _safe_call
# / to_http_exception boundary so AWS-side failures map to the canonical
# 4xx/5xx contract from #61 without sprinkling try/except here.
# ---------------------------------------------------------------------------


def _make_deployment_id() -> str:
    """Mint a deployment-id (UUIDv4 hex, no dashes).

    Pulled into its own function so unit tests can monkeypatch it for
    deterministic assertions on the response payload.
    """

    return uuid.uuid4().hex


def _deployment_idempotency_key(
    product_id: str, construct_address: str, idempotency_key: str | None
) -> str | None:
    """Compose the per-deployment idempotency key.

    Two semantics here:

    * **caller-supplied idempotency_key** — combined with product_id +
      construct_address so the same key reused against a DIFFERENT product
      doesn't collide.
    * **no idempotency_key** — returns ``None`` so the repo layer skips
      the idempotent-replay branch and the caller relies on Terraform's
      own S3-state convergence (which is idempotent for the same construct
      address) per the Decision Log.
    """

    if not idempotency_key:
        return None
    return f"product:{product_id}:{construct_address}:{idempotency_key}"


def deploy_product(
    product_id: str,
    construct_address: str,
    idempotency_key: str | None,
    access: AccessContext,
    repo: Any,
    correlation_id: str,
) -> dict[str, Any]:
    """Deploy a catalog product at ``construct_address``.

    Parameters
    ----------
    product_id:
        Catalog key (e.g. ``catalyst-api``).
    construct_address:
        ``tenant/env/lz/project/app`` — same shape Tier 2 onboard takes.
    idempotency_key:
        Optional client idempotency key. When provided, the per-product
        deployment record is looked up by ``(product_id, construct_address,
        idempotency_key)``; a hit returns the cached payload without
        re-invoking onboard.
    access:
        Resolved :class:`AccessContext` for the caller. RBAC is enforced
        on the way in.
    repo:
        Repository instance (interface from :mod:`catalyst.repository`).
    correlation_id:
        Per-request correlation id from the handler boundary.

    Returns
    -------
    dict
        ``product_id``, ``deployment_id``, ``construct_address``,
        ``status``, plus the standard onboard ARN payload.

    Raises
    ------
    HTTPException
        404 if the product is unknown; 403 if RBAC fails; 422 if the
        construct address is malformed; 500 if image-URI resolution
        fails; bubbles other onboard failures from ``provision_app``.
    """

    product = get_product(product_id)
    if product is None:
        raise to_http_exception(
            ResourceNotFound(f"unknown product: {product_id}"),
            correlation_id,
        )

    if not is_caller_authorized_for_product(access, product_id):
        raise to_http_exception(
            ScopeInsufficient(
                "insufficient_permissions",
                context={
                    "product_id": product_id,
                    "role": access.role,
                    "required_roles": sorted(product["required_roles"]),
                },
            ),
            correlation_id,
        )

    # Validate the construct address shape early — provision_app will do
    # this too, but doing it here lets us return a 422 BEFORE we even
    # touch the repo or image-URI resolution.
    try:
        parsed = ConstructAddress(value=construct_address)
    except ValidationError as exc:
        raise to_http_exception(
            ValidationFailure(
                "construct address must be tenant/env/lz/project/app",
                context={"raw": construct_address, "pydantic": str(exc)},
            ),
            correlation_id,
        ) from exc

    # Scoped callers (per ADR-008) must additionally own the tenant
    # segment of the construct address. We piggyback on can_read_scope
    # because it already encodes the tenant-wide / scoped-project rules.
    tenant, _env, _lz, project, _app = parsed.value.split("/")
    if access.role == "scoped" and not can_read_scope(access, tenant, project):
        raise to_http_exception(
            ScopeInsufficient(
                "insufficient_permissions",
                context={
                    "product_id": product_id,
                    "construct_tenant": tenant,
                    "construct_project": project,
                },
            ),
            correlation_id,
        )

    deploy_idem_key = _deployment_idempotency_key(
        product_id, construct_address, idempotency_key
    )

    # Idempotent-replay check — first hit wins. This is keyed on the
    # composite (product_id + construct_address + idempotency_key) so
    # reuse of the same idempotency_key against a different product
    # doesn't collide.
    if deploy_idem_key is not None:
        existing = repo.get_product_deployment_by_idem_key(deploy_idem_key)
        if existing is not None:
            logger.info(
                "product_deploy_idempotent_replay",
                extra={
                    "correlation_id": correlation_id,
                    "product_id": product_id,
                    "deployment_id": existing.get("deployment_id"),
                },
            )
            return existing

    # Resolve the image URI BEFORE invoking onboard. If the resolution
    # fails we want to fail fast — provision_app spawns a Terraform
    # subprocess on the first line, and we don't want to leave an
    # orphan state if the image URI is broken.
    image_uri = _resolve_image_uri(product_id, product)

    # Mint a deployment id BEFORE invoking onboard so a partial failure
    # (e.g. Terraform fails halfway) still leaves a record we can grep
    # for in CloudWatch.
    deployment_id = _make_deployment_id()

    logger.info(
        "product_deploy_invoke_onboard",
        extra={
            "correlation_id": correlation_id,
            "product_id": product_id,
            "deployment_id": deployment_id,
            "construct_address": construct_address,
            "service_type": product["service_type"],
            "image_uri": image_uri,
        },
    )

    onboard_result = provision_app(
        construct_address,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        service_type=product["service_type"],
    )

    payload: dict[str, Any] = {
        "product_id": product_id,
        "deployment_id": deployment_id,
        "construct_address": onboard_result.construct_address,
        "status": "provisioned",
        "ecr_uri": onboard_result.ecr_uri,
        "execution_role_arn": onboard_result.execution_role_arn,
        "log_group_name": onboard_result.log_group_name,
        "alb_listener_rule_arn": onboard_result.alb_listener_rule_arn,
        "catalog_record_key": onboard_result.catalog_record_key,
        "state_key": onboard_result.state_key,
        "image_uri": image_uri,
        "correlation_id": correlation_id,
    }

    # Persist the product-deployment record. Both branches (caller-supplied
    # key and no-key) record the row so list/get queries can surface
    # deployment history; only the keyed branch participates in replay.
    repo.record_product_deployment(
        product_id=product_id,
        construct_address=onboard_result.construct_address,
        deployment_id=deployment_id,
        idempotency_key=deploy_idem_key,
        payload=payload,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # Dual-write to Aurora (best-effort, #229 / ADR-019). DynamoDB above
    # is the source of truth; the RDS write is a secondary read path
    # that backs `GET /deployment-history`. Failure here MUST NOT roll
    # back DynamoDB — we log a warning + emit a `RDSWriteFailure` metric
    # so an operator can spot RDS-side issues without breaking the
    # primary deploy flow. The repo getter returns None when Aurora
    # isn't wired (CATALYST_AURORA_ENDPOINT unset), in which case the
    # dual-write is a no-op.
    _dual_write_rds(
        product_id=product_id,
        deployment_id=deployment_id,
        construct_address=onboard_result.construct_address,
        tenant=tenant,
        caller_arn=access.caller_arn or "",
        correlation_id=correlation_id,
    )

    return payload


def _dual_write_rds(
    *,
    product_id: str,
    deployment_id: str,
    construct_address: str,
    tenant: str,
    caller_arn: str,
    correlation_id: str,
) -> None:
    """Best-effort INSERT to Aurora's deployment_history table (#229).

    Pulled into a helper so :func:`deploy_product` stays narrow and tests
    can monkeypatch one symbol to drive the failure branch. Failures are
    swallowed (logged + metric emitted) — the DynamoDB write is the
    source of truth.
    """

    try:
        from .rds_repository import get_rds_repository

        rds_repo = get_rds_repository()
        if rds_repo is None:
            # Aurora not wired — nothing to do. This is the steady-state
            # for callers that haven't flipped `enable_aurora_serverless`
            # on the composite, so don't log loudly.
            return
        rds_repo.record_deployment(
            deployment_id=deployment_id,
            product_id=product_id,
            tenant=tenant,
            construct_address=construct_address,
            caller_arn=caller_arn,
        )
    except Exception as exc:  # noqa: BLE001 - dual-write MUST NOT raise
        logger.warning(
            "rds_dual_write_failed",
            extra={
                "correlation_id": correlation_id,
                "product_id": product_id,
                "deployment_id": deployment_id,
                "error_class": type(exc).__name__,
            },
        )
        # Best-effort metric — observability MUST NOT raise on its own
        # failure either, so wrap in its own try/except.
        try:
            from .observability import metrics

            metrics._put(  # noqa: SLF001 - intentional cross-module hook
                "RDSWriteFailure",
                1,
                "Count",
                [
                    {"Name": "ProductId", "Value": product_id},
                    {"Name": "ErrorClass", "Value": type(exc).__name__},
                ],
            )
        except Exception:  # noqa: BLE001
            logger.debug("rds_write_failure_metric_emit_failed", exc_info=True)
