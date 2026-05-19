"""Centralised error contract for the Catalyst control-plane API.

Issue #61 codifies the 4xx/5xx discipline for every handler in
``catalyst/main.py``. The mapping table lives here — not sprinkled across
handlers — so the response shape is uniform and so future endpoints get
the contract for free by raising one of the :class:`CatalystAPIError`
subclasses below.

Status-code matrix
------------------

* ``400`` / ``422`` — Pydantic / semantic validation failure
  (:class:`ValidationFailure`).
* ``401`` — auth missing or invalid (raised by ``rbac.access_dependency``;
  this module passes it through unchanged).
* ``403`` — scope insufficient (:class:`ScopeInsufficient`, or raised
  directly by ``rbac.require_write`` / ``rbac.can_read_scope``).
* ``404`` — resource not found (:class:`ResourceNotFound`).
* ``409`` — idempotency-key conflict (:class:`IdempotencyConflict`).
* ``429`` — boto3 ``ThrottlingException`` (mapped from
  :class:`botocore.exceptions.ClientError`).
* ``5xx`` — any unexpected AWS / repository failure
  (:class:`RepositoryFailure`, :class:`AWSTransientFailure`, raw
  ``ClientError``, or last-resort ``Exception``).

Response-body convention (single shape across the API)
------------------------------------------------------

::

    {
      "error": "<CatalystAPIError subclass name>",
      "correlation_id": "<uuid threaded from the X-Correlation-ID header>",
      "detail": "<hand-curated safe message; never the raw exception str>"
    }

The raw ``str(exc)`` is **never** included in the response — boto3
``ClientError`` messages routinely contain ARNs, account IDs, request
IDs, and occasionally credential fragments. Only the class name plus a
short, hand-curated detail string crosses the boundary; the full
exception is reserved for structured logs (where ADR-014 / ADR-015 already
specify the egress controls).

Retry/backoff on transient AWS failures is **out of scope** for #61 —
see the kaizen follow-up filed alongside this PR. For now,
``AWSTransientFailure`` and throttling map to ``503`` so a well-behaved
client backs off and retries on its own clock.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CatalystAPIError hierarchy — one subclass per failure mode.
#
# Subclassing :class:`Exception` (not :class:`HTTPException`) keeps the
# error type framework-agnostic: callers can raise a domain exception
# anywhere — repository, onboard helper, future RPC layer — and the
# boundary at the handler edge translates it to HTTP. This is the same
# pattern ``onboard.py`` already uses (it raises plain ``HTTPException``
# from a subprocess error); the hierarchy below lets every other handler
# express the failure as a domain concept first, mapping second.
# ---------------------------------------------------------------------------


class CatalystAPIError(Exception):
    """Base class for all Catalyst control-plane domain errors.

    ``detail`` is a hand-curated message safe to surface in API responses.
    It MUST NOT include raw boto3 / botocore exception text; pass any
    sensitive context via :attr:`context` (logged, not returned).
    """

    status_code: int = 500
    default_detail: str = "internal_error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.default_detail
        self.context = context or {}
        super().__init__(self.detail)


class ValidationFailure(CatalystAPIError):
    """Semantic validation failure (e.g. unknown landing-zone reference).

    Pydantic's own ``RequestValidationError`` continues to surface as 422
    via FastAPI's default handler — this class is for cross-field /
    cross-resource checks that don't fit a single Pydantic validator.
    """

    status_code = 422
    default_detail = "validation_failed"


class IdempotencyConflict(CatalystAPIError):
    """The same idempotency key was reused with a different payload.

    Distinct from the "replay returns the cached response" happy path,
    which is handled inline by ``_idempotent_response`` and is NOT an
    error. This subclass is reserved for the conflict case where a client
    has bound a key to two semantically different requests — surface a
    409 so the client knows to mint a new key.
    """

    status_code = 409
    default_detail = "idempotency_conflict"


class ResourceNotFound(CatalystAPIError):
    """A construct address / org tenant / product key has no record."""

    status_code = 404
    default_detail = "not_found"


class ScopeInsufficient(CatalystAPIError):
    """Caller authenticated but lacks the scope to perform the action.

    ``rbac.require_write`` / ``rbac.can_read_scope`` continue to raise
    ``HTTPException(403)`` directly; this class exists so a non-handler
    (e.g. a future repository-layer check) can express the same outcome
    in a framework-agnostic way and have the boundary translate it.
    """

    status_code = 403
    default_detail = "insufficient_permissions"


class RepositoryFailure(CatalystAPIError):
    """A repository write/read failed for reasons not in our control.

    Maps to 503 (Service Unavailable) so well-behaved clients retry with
    backoff; the underlying boto3 / DynamoDB exception is logged with the
    correlation id but never returned in the body.
    """

    status_code = 503
    default_detail = "repository_unavailable"


class AWSTransientFailure(CatalystAPIError):
    """A transient AWS error (throttling, capacity, retryable 5xx).

    Surface 503 + correlation_id and let the client back off. A
    retry/backoff sweep on the server side is tracked as a follow-up
    kaizen; #61 deliberately keeps this server-side dumb.
    """

    status_code = 503
    default_detail = "aws_transient_failure"


# ---------------------------------------------------------------------------
# botocore.ClientError handling.
#
# We import boto/botocore lazily so unit tests that don't have boto3
# installed (or unit tests that haven't initialised AWS plumbing) can
# still import :mod:`catalyst.errors`. Production paths always have
# botocore on sys.path because repository.py imports it directly.
# ---------------------------------------------------------------------------


def _classify_client_error_code(error_code: str) -> type[CatalystAPIError]:
    """Map a ``ClientError`` error-code string to a CatalystAPIError class.

    The mapping is deliberately small — #61 keeps the server side dumb
    and lets the client back off. Future kaizen can expand this table
    as we observe real-world failure modes in CloudWatch.
    """

    # Throttling / capacity → 503 (retryable).
    if error_code in {
        "ThrottlingException",
        "Throttling",
        "TooManyRequestsException",
        "RequestLimitExceeded",
        "ProvisionedThroughputExceededException",
        "ServiceUnavailable",
    }:
        return AWSTransientFailure

    # Resource-not-found-style codes → 404.
    if error_code in {
        "ResourceNotFoundException",
        "NoSuchEntity",
        "NotFoundException",
    }:
        return ResourceNotFound

    # Conditional-check / idempotency-collision → 409.
    if error_code in {"ConditionalCheckFailedException"}:
        return IdempotencyConflict

    # Everything else (5xx-ish AWS server errors, generic InternalError,
    # unknown codes) → 503 RepositoryFailure so a retry actually has a
    # chance to succeed without operator intervention.
    return RepositoryFailure


def _client_error_code(exc: Exception) -> str | None:
    """Return the AWS error code from a ``ClientError``, or ``None``."""

    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error")
    if not isinstance(error, dict):
        return None
    code = error.get("Code")
    return code if isinstance(code, str) else None


# ---------------------------------------------------------------------------
# The boundary translator: every handler wraps AWS / repo calls in a
# try/except that ends here. The function NEVER raises; it always
# returns an ``HTTPException`` ready to be re-raised, which keeps the
# handler-side boilerplate to two lines.
# ---------------------------------------------------------------------------


def to_http_exception(exc: Exception, correlation_id: str) -> HTTPException:
    """Translate ``exc`` into a uniformly-shaped ``HTTPException``.

    The response body always carries ``{error, correlation_id, detail}``.
    ``str(exc)`` is logged (so operators can debug from CloudWatch) but
    never returned — it may contain ARNs or credential fragments.

    Parameters
    ----------
    exc:
        The exception caught at the handler boundary. May be a
        :class:`CatalystAPIError` subclass, a raw
        :class:`botocore.exceptions.ClientError`, an ``HTTPException``
        we should pass through unchanged, or any other ``Exception``.
    correlation_id:
        The id minted by the per-request dependency (or passed through
        from the ``X-Correlation-ID`` header) — the same id that already
        appears in success-path responses and structured logs.
    """

    # ---- Pass-through: FastAPI / rbac may already have built an HTTPException
    # with a curated detail (e.g. the 401/403/422 paths in rbac.py). We add
    # the correlation_id to the body but leave the status untouched.
    if isinstance(exc, HTTPException):
        return _wrap_existing_http_exception(exc, correlation_id)

    # ---- Domain exceptions: status_code + default_detail come from the class.
    if isinstance(exc, CatalystAPIError):
        logger.error(
            "catalyst_api_error",
            extra={
                "error_class": type(exc).__name__,
                "correlation_id": correlation_id,
                "status_code": exc.status_code,
                "detail": exc.detail,
                "context": exc.context,
            },
        )
        return HTTPException(
            status_code=exc.status_code,
            detail={
                "error": type(exc).__name__,
                "correlation_id": correlation_id,
                "detail": exc.detail,
            },
        )

    # ---- botocore.ClientError: classify by error code.
    try:
        from botocore.exceptions import ClientError  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - botocore is optional at unit-test boundary
        ClientError = ()  # type: ignore[assignment]

    if ClientError and isinstance(exc, ClientError):  # type: ignore[arg-type]
        code = _client_error_code(exc) or "Unknown"
        target_class = _classify_client_error_code(code)
        logger.error(
            "aws_client_error",
            extra={
                "error_code": code,
                "correlation_id": correlation_id,
                "mapped_to": target_class.__name__,
                "raw": str(exc)[:1000],
            },
        )
        return HTTPException(
            status_code=target_class.status_code,
            detail={
                "error": target_class.__name__,
                "correlation_id": correlation_id,
                "detail": target_class.default_detail,
            },
        )

    # ---- Last resort: log the raw text, return an opaque 500.
    logger.exception(
        "catalyst_unexpected_error",
        extra={
            "error_class": type(exc).__name__,
            "correlation_id": correlation_id,
        },
    )
    return HTTPException(
        status_code=500,
        detail={
            "error": "InternalServerError",
            "correlation_id": correlation_id,
            "detail": "internal_error",
        },
    )


def _wrap_existing_http_exception(
    exc: HTTPException, correlation_id: str
) -> HTTPException:
    """Re-shape an existing :class:`HTTPException` to the canonical body.

    The existing ``detail`` becomes the ``detail`` field; the ``error``
    field is derived from the HTTP status (``ValidationError`` for 422,
    ``Unauthorized`` for 401, etc.) so the body stays parseable by
    clients that key on the ``error`` field rather than the status code.
    """

    # If we've already wrapped this exception once (e.g. nested boundaries),
    # don't double-wrap — return it unchanged.
    if isinstance(exc.detail, dict) and "correlation_id" in exc.detail:
        return exc

    error_name = _http_status_to_error_name(exc.status_code)
    detail_value = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error": error_name,
            "correlation_id": correlation_id,
            "detail": detail_value,
        },
        headers=exc.headers,
    )


def _http_status_to_error_name(status_code: int) -> str:
    """Map an HTTP status code to a short, stable error-class name."""

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
    }.get(status_code, "Error")
