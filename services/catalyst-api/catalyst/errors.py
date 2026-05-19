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
from contextvars import ContextVar
from typing import Any, Callable, TypeVar

from fastapi import HTTPException, Request
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    stop_after_delay,
    wait_random_exponential,
)

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


def to_http_exception(
    exc: Exception,
    correlation_id: str,
    *,
    request: Request | None = None,
) -> HTTPException:
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
    request:
        Optional FastAPI ``Request`` whose ``state.error_class`` will be
        set to the chosen error-class name. Used by the
        ``observability_middleware`` (#60) to tag ``ErrorCount`` with
        the canonical class name (the same name that appears in the
        response body's ``error`` field) rather than guessing from the
        status code alone. Older call sites that don't pass ``request``
        continue to work unchanged.
    """

    # ---- Pass-through: FastAPI / rbac may already have built an HTTPException
    # with a curated detail (e.g. the 401/403/422 paths in rbac.py). We add
    # the correlation_id to the body but leave the status untouched.
    if isinstance(exc, HTTPException):
        wrapped = _wrap_existing_http_exception(exc, correlation_id)
        _stash_error_class_on_request(request, _name_from_wrapped_detail(wrapped))
        return wrapped

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
        _stash_error_class_on_request(request, type(exc).__name__)
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
        _stash_error_class_on_request(request, target_class.__name__)
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
    _stash_error_class_on_request(request, "InternalServerError")
    return HTTPException(
        status_code=500,
        detail={
            "error": "InternalServerError",
            "correlation_id": correlation_id,
            "detail": "internal_error",
        },
    )


def _stash_error_class_on_request(request: Request | None, name: str) -> None:
    """Set ``request.state.error_class`` so the observability middleware
    can tag ``ErrorCount`` with the canonical name.

    If ``request`` is ``None`` we fall back to the ``request_var``
    contextvar set by ``observability_middleware`` — that way handlers
    that raise ``to_http_exception(...)`` WITHOUT plumbing the request
    through (every existing call site in :mod:`catalyst.main`) still
    populate ``error_class`` correctly. Tolerates a missing ``state``
    attribute defensively so a failure here can't break the error path.
    """

    if request is None:
        try:
            from .observability import request_var  # local import to avoid cycles

            request = request_var.get()
        except Exception:  # noqa: BLE001 - defensive; never fail error translation
            request = None

    if request is None:
        return
    state = getattr(request, "state", None)
    if state is None:
        return
    try:
        setattr(state, "error_class", name)
    except Exception:  # noqa: BLE001 - defensive; never fail error translation
        pass


def _name_from_wrapped_detail(wrapped: HTTPException) -> str:
    """Extract the ``error`` field from a wrapped HTTPException's detail.

    Used to populate ``request.state.error_class`` on the
    pass-through-existing-HTTPException branch. Falls back to a
    status-code-derived name when the detail is not in the canonical
    ``{error, correlation_id, detail}`` shape.
    """

    detail = wrapped.detail
    if isinstance(detail, dict):
        name = detail.get("error")
        if isinstance(name, str):
            return name
    return _http_status_to_error_name(wrapped.status_code)


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


# ---------------------------------------------------------------------------
# #205 — server-side retry + exponential backoff for transient AWS failures.
#
# The retry layer fires BEFORE the exception bubbles up to
# ``_safe_call``'s 503 conversion. Only the codes listed in
# :data:`RETRYABLE_AWS_CODES` trigger a retry; everything else (404-style
# misses, conditional-check conflicts, validation errors) raises on the
# first attempt so the boundary translator can map it to the right status.
#
# Retry budget — locked in the Decision Log on #205:
#
#   * ``stop_after_attempt(3)`` AND ``stop_after_delay(30)`` (whichever
#     fires first) — 3 attempts max, 30 s wall-clock cap below the
#     Lambda timeout.
#   * ``wait_random_exponential(multiplier=0.5, max=8)`` — exponential
#     backoff with full jitter capped at 8 s so the 30 s budget stays
#     intact even on the worst-case ladder (≤ 0.5 + 1 + 2 + 4 + 8 = 15.5
#     s of sleep across 3 attempts).
#   * ``retry_if_exception(is_retryable_aws_error)`` — only ClientError
#     with a code in :data:`RETRYABLE_AWS_CODES` retries; ANY other
#     exception (including non-retryable ClientError codes) escapes the
#     decorator on the first throw and gets the existing 4xx/5xx mapping.
#   * ``before_sleep`` hook — emit a structured log line so operators can
#     see retries in CloudWatch and distinguish a transient blip from a
#     real capacity issue masquerading as success.
# ---------------------------------------------------------------------------


#: AWS error-code strings that warrant a server-side retry. Anything not
#: in this set bubbles up on the first throw — including codes that map
#: to non-2xx but non-transient outcomes (404, 409, etc.).
RETRYABLE_AWS_CODES: frozenset[str] = frozenset(
    {
        "ThrottlingException",
        "Throttling",
        "ProvisionedThroughputExceededException",
        "ServiceUnavailable",
        "TooManyRequestsException",
        "RequestLimitExceeded",
    }
)


#: Per-request context populated by the handler/test boundary. The retry
#: decorator pulls these into its structured-log line. They default to
#: ``None`` so the decorator stays usable without any caller plumbing —
#: callers that DO have the values (every catalyst handler does, via
#: ``correlation_id_dependency``) ``token = retry_correlation_id.set(...)``
#: and ``retry_correlation_id.reset(token)`` around the call.
#:
#: Contextvars (not function args) because the wrapped functions are
#: existing repository methods whose signatures must stay stable — this
#: kaizen explicitly forbids signature changes. Contextvars also survive
#: across async/sync boundaries cleanly, which keeps the seam working
#: when handlers eventually become async.
retry_correlation_id: ContextVar[str | None] = ContextVar(
    "retry_correlation_id", default=None
)
retry_endpoint: ContextVar[str | None] = ContextVar(
    "retry_endpoint", default=None
)


F = TypeVar("F", bound=Callable[..., Any])


def is_retryable_aws_error(exc: BaseException) -> bool:
    """Return ``True`` iff ``exc`` is a ``ClientError`` we should retry.

    Used both by the :func:`with_aws_retry` decorator's
    ``retry_if_exception`` predicate and by unit tests that want to
    assert classification independently of the tenacity machinery.

    Any non-``ClientError`` exception returns ``False`` so unrelated
    failure modes (network errors handled lower in botocore, plain
    ``RuntimeError`` from a misbehaving fake, etc.) bubble up immediately.
    """

    try:
        from botocore.exceptions import (  # type: ignore[import-not-found]
            ClientError,
        )
    except Exception:  # noqa: BLE001 - botocore optional at unit-test boundary
        return False

    if not isinstance(exc, ClientError):
        return False

    code = _client_error_code(exc)
    return code in RETRYABLE_AWS_CODES


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """``before_sleep`` hook: emit a structured log line + custom metric.

    Fields required by the #205 Decision Log:

        * ``endpoint`` — resolved from :data:`retry_endpoint` contextvar
          (handler sets it via the dependency); ``None`` if unset.
        * ``correlation_id`` — resolved from :data:`retry_correlation_id`
          contextvar; ``None`` if unset.
        * ``attempt`` — the 1-based attempt number that just failed
          (tenacity counts attempts pre-sleep, so this is the attempt
          we're about to retry after).
        * ``error_code`` — the AWS error code that triggered the retry.

    Per #60, this hook ALSO emits ``Catalyst/API:RetryAttempt`` so the
    retry pressure is alarmable from CloudWatch — a transient
    ThrottlingException that successfully retries shows up as a real
    retry attempt instead of being invisible at the metric layer.

    Failure inside this hook is swallowed — observability MUST NOT mask
    a genuine retry. ``MetricsEmitter._put`` already swallows internally
    so a CloudWatch outage cannot break the retry path either.
    """

    outcome = retry_state.outcome
    exc = outcome.exception() if outcome is not None else None
    code = _client_error_code(exc) if exc is not None else None
    endpoint = retry_endpoint.get()
    logger.warning(
        "aws_retry_attempt",
        extra={
            "endpoint": endpoint,
            "correlation_id": retry_correlation_id.get(),
            "attempt": retry_state.attempt_number,
            "error_code": code,
        },
    )
    # #60 — emit the RetryAttempt metric in the same hook. Lazy-import the
    # observability module so the circular dependency between
    # ``errors`` (which observability imports) and ``observability``
    # (which we'd import here) stays one-directional at import time.
    try:
        from .observability import metrics  # local import: avoid cycle at module load

        metrics.retry_attempt(endpoint or "unknown", code or "Unknown")
    except Exception:  # noqa: BLE001 - observability MUST NOT mask the retry path
        pass


def with_aws_retry() -> Callable[[F], F]:
    """Decorator: retry ``ClientError`` with retryable code, up to budget.

    Wraps the bare boto3 call sites in :mod:`catalyst.repository` and
    :mod:`catalyst.onboard` so transient throttling/capacity errors get a
    chance to succeed without the client having to retry on its own
    clock.

    The decorator is parameter-free on purpose — the retry budget is a
    project-wide policy (Decision Log on #205), not a per-call knob.

    Returns
    -------
    Callable
        A decorator that returns a wrapper with the same call signature
        as ``fn``. The wrapper raises the SAME exception ``fn`` raised on
        the last attempt — there is no re-wrapping, so the existing
        boundary translator (:func:`to_http_exception`) sees the bare
        ``ClientError`` and classifies it normally on exhaustion.
    """

    def decorator(fn: F) -> F:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            retrying = Retrying(
                retry=retry_if_exception(is_retryable_aws_error),
                stop=(stop_after_attempt(3) | stop_after_delay(30)),
                wait=wait_random_exponential(multiplier=0.5, max=8),
                before_sleep=_log_retry_attempt,
                reraise=True,
            )
            return retrying(fn, *args, **kwargs)

        wrapped.__name__ = getattr(fn, "__name__", "wrapped")
        wrapped.__doc__ = fn.__doc__
        wrapped.__wrapped__ = fn  # type: ignore[attr-defined]
        return wrapped  # type: ignore[return-value]

    return decorator
