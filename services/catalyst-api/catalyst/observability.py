"""Cross-cutting observability primitives for the Catalyst control-plane API.

Issue #60 codifies the SVC-6 service-observability contract: every request
through the FastAPI surface gets structured JSON logs + custom CloudWatch
metrics + correlation-ID propagation, implemented as cross-cutting
middleware so per-handler boilerplate stays out of the handler bodies.

The module hosts three concerns:

1. **JSONFormatter** — formats every log record as a single JSON line with
   the required fields (``timestamp``, ``level``, ``event``, ``endpoint``,
   ``correlation_id``, ``caller_arn``, ``tenant``) plus any per-event
   extras the caller supplied via ``logger.<level>(msg, extra={...})``.
2. **MetricsEmitter** — wraps ``boto3 cloudwatch:PutMetricData`` calls for
   the four locked metric names in the ``Catalyst/API`` namespace
   (``RequestCount``, ``RequestDuration``, ``ErrorCount``,
   ``RetryAttempt``). The exact names + namespace are referenced by #63's
   alarms — DO NOT rename without coordinating with that PR.
3. **Module-level singletons** — ``metrics`` is the process-wide emitter
   used by the middleware + retry hook. Tests swap the underlying boto3
   client via the ``client`` property.

The metric namespace + names below are LOCKED by the Decision Log on #60
and referenced by #63 (parallel sister PR). Any rename here breaks #63's
alarms. The structured-log fields are LOCKED for the same reason —
operators query CloudWatch Logs Insights by these names.

All ``PutMetricData`` calls are best-effort: failures are caught, logged
as ``metric_emit_failed``, and swallowed so observability infrastructure
never breaks the request path. This mirrors the same swallow-semantics
the existing ``onboard._emit_metric`` already uses (Onboard's specific
trip-wire metric stays untouched by #60).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


#: The CloudWatch metric namespace for ALL generic per-request metrics
#: emitted by the FastAPI middleware. LOCKED by the Decision Log on #60
#: and referenced by #63's alarms — DO NOT rename.
METRIC_NAMESPACE = "Catalyst/API"


#: Per-request context populated by the observability middleware. The
#: JSONFormatter pulls these values into every log record so a caller
#: invoking ``logger.info("...")`` from within a handler automatically
#: gets ``endpoint``/``correlation_id``/``caller_arn``/``tenant`` threaded
#: into the JSON line without having to plumb them through every call.
#:
#: Contextvars (not module globals) because Lambda invocations are
#: per-request and FastAPI handlers may run concurrently under uvicorn —
#: a module global would leak request state across concurrent requests.
endpoint_var: ContextVar[str | None] = ContextVar("endpoint_var", default=None)
correlation_id_var: ContextVar[str | None] = ContextVar(
    "correlation_id_var", default=None
)
caller_arn_var: ContextVar[str | None] = ContextVar("caller_arn_var", default=None)
tenant_var: ContextVar[str | None] = ContextVar("tenant_var", default=None)


# ---------------------------------------------------------------------------
# Structured JSON logging.
# ---------------------------------------------------------------------------


#: Standard LogRecord attribute names — every key on a ``LogRecord``
#: that is NOT in this set is a caller-supplied ``extra=`` field and
#: should be merged into the JSON payload. We compute this once at import
#: time so the per-record path stays cheap.
_STANDARD_LOG_RECORD_KEYS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
        "taskName",  # 3.12+
    }
)


class JSONFormatter(logging.Formatter):
    """Format every ``LogRecord`` as a single JSON line.

    Required fields per the #60 Decision Log:

        * ``timestamp`` — ISO 8601 UTC, microseconds, ``Z`` suffix.
        * ``level`` — the record level name (``INFO``, ``WARNING``, etc.).
        * ``event`` — the record's primary message (``record.getMessage()``).
        * ``endpoint`` — pulled from the :data:`endpoint_var` contextvar
          (the middleware sets it on request entry); ``None`` if unset.
        * ``correlation_id`` — pulled from :data:`correlation_id_var`;
          ``None`` if unset.
        * ``caller_arn`` — pulled from :data:`caller_arn_var`; ``None`` if
          unset.
        * ``tenant`` — pulled from :data:`tenant_var`; ``None`` if unset.

    Any ``extra=`` keys passed to ``logger.<level>(...)`` are merged into
    the JSON payload at the top level (they override the contextvar
    values for the same key, which lets a caller pass an explicit
    ``endpoint`` for a non-request-bound log line). Standard
    ``LogRecord`` attributes are filtered out so they don't bloat every
    line.

    Exception info (when ``logger.exception(...)`` is used or
    ``exc_info=True`` is passed) lands in the ``exc_info`` field as a
    pre-formatted traceback string so a single ``aws logs filter`` call
    sees the full stack without parsing nested JSON.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render ``record`` as a single JSON-line string."""

        # Base fields — required by #60 Decision Log. Pull the contextvars
        # first, then let any caller-supplied extras override them.
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "event": record.getMessage(),
            "endpoint": endpoint_var.get(),
            "correlation_id": correlation_id_var.get(),
            "caller_arn": caller_arn_var.get(),
            "tenant": tenant_var.get(),
            "logger": record.name,
        }

        # Merge caller-supplied ``extra=`` keys. ``LogRecord`` flattens
        # extras into the record __dict__ alongside the standard
        # attributes; we filter the standard set out and copy the rest.
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_KEYS:
                continue
            if key.startswith("_"):
                continue
            payload[key] = value

        # Exception tracebacks (when ``logger.exception(...)`` was used)
        # — render once and attach as a string so downstream JSON parsers
        # don't choke on nested newlines.
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # ``default=str`` to keep the formatter robust against
        # non-serialisable extras (datetimes, Decimal, etc.) — better to
        # surface a stringified value than to drop the whole log line.
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install :class:`JSONFormatter` on the root logger.

    Idempotent: calling this twice replaces the handler rather than
    stacking two. The default level is ``INFO`` which matches the
    existing handler-side ``logger.info(...)`` call sites; the runtime
    can override via ``CATALYST_LOG_LEVEL=DEBUG`` if needed.

    Writes to ``sys.stdout`` (not the default ``stderr``) so the AWS
    Lambda runtime captures the lines via the standard stdout drain
    rather than the stderr error channel — matching the existing
    onboard log path.
    """

    env_level = os.environ.get("CATALYST_LOG_LEVEL")
    if env_level:
        try:
            level = getattr(logging, env_level.upper())
        except AttributeError:
            # Don't fail logging configuration on a typo in an env var —
            # fall back to the default and emit a single startup line.
            level = logging.INFO

    root = logging.getLogger()
    # Remove any handlers we previously installed so re-configuration
    # (e.g. a test calling configure_logging() repeatedly) doesn't pile
    # up duplicate handlers each emitting the same line.
    for handler in list(root.handlers):
        if getattr(handler, "_catalyst_json_handler", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    handler.setLevel(level)
    # Tag the handler so the cleanup loop above can find it on re-config.
    handler._catalyst_json_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)


# ---------------------------------------------------------------------------
# CloudWatch metrics emission.
# ---------------------------------------------------------------------------


class MetricsEmitter:
    """boto3 wrapper for the four locked ``Catalyst/API`` metrics.

    The four metric names + dimension sets below match the Decision Log
    on #60 EXACTLY — they are referenced by #63's alarms and a rename
    here will silently break those alarms (alarms fire on nothing). DO
    NOT rename without coordinating with #63.

    All ``PutMetricData`` calls are wrapped in try/except. On failure we
    emit a ``metric_emit_failed`` log line and continue — observability
    infrastructure MUST NOT fail the request path. This mirrors the
    same swallow-semantics ``onboard._emit_metric`` uses for the
    existing ``Catalyst/Onboard:OnboardDuration`` metric.

    The underlying boto3 client is lazily created on first use so unit
    tests that don't drive a real boto3 call don't need AWS credentials.
    Tests can swap the client via the :attr:`client` setter.
    """

    def __init__(self, namespace: str = METRIC_NAMESPACE) -> None:
        self._namespace = namespace
        self._client: Any | None = None
        # The structured log emitted on failure uses this logger; it is
        # named so unit tests can use ``caplog`` to assert on the failure
        # log line specifically.
        self._logger = logging.getLogger("catalyst.observability")

    @property
    def client(self) -> Any:
        """Return the boto3 CloudWatch client, creating on first access.

        Lazy so importing :mod:`catalyst.observability` does not pull
        boto3 into the import path — the unit test surface and any
        non-AWS callers stay cheap.
        """

        if self._client is None:
            import boto3

            region = os.environ.get("AWS_REGION") or os.environ.get(
                "AWS_DEFAULT_REGION"
            )
            if region:
                self._client = boto3.client("cloudwatch", region_name=region)
            else:
                self._client = boto3.client("cloudwatch")
        return self._client

    @client.setter
    def client(self, value: Any) -> None:
        """Override the underlying CloudWatch client (test seam)."""

        self._client = value

    @property
    def namespace(self) -> str:
        return self._namespace

    def _put(self, metric_name: str, value: float, unit: str, dimensions: list[dict]) -> None:
        """Best-effort ``PutMetricData`` wrapper — never raises.

        Every public ``request_count`` / ``request_duration`` /
        ``error_count`` / ``retry_attempt`` call funnels through here so
        the swallow-and-log semantics live in exactly one place.
        """

        try:
            self.client.put_metric_data(
                Namespace=self._namespace,
                MetricData=[
                    {
                        "MetricName": metric_name,
                        "Value": float(value),
                        "Unit": unit,
                        "Dimensions": dimensions,
                    }
                ],
            )
        except Exception as exc:  # noqa: BLE001 - observability MUST NOT fail the request
            self._logger.warning(
                "metric_emit_failed",
                extra={
                    "metric_name": metric_name,
                    "namespace": self._namespace,
                    "error_class": type(exc).__name__,
                },
            )

    def request_count(
        self, endpoint: str, method: str, status_code: int
    ) -> None:
        """Emit ``RequestCount`` (one count per response).

        Dimensions match the Decision Log: ``Endpoint``, ``Method``,
        ``StatusCode``. The status code is stringified for CloudWatch —
        dimension values are always strings in PutMetricData.
        """

        self._put(
            "RequestCount",
            1,
            "Count",
            [
                {"Name": "Endpoint", "Value": endpoint},
                {"Name": "Method", "Value": method},
                {"Name": "StatusCode", "Value": str(status_code)},
            ],
        )

    def request_duration(
        self, endpoint: str, method: str, duration_ms: float
    ) -> None:
        """Emit ``RequestDuration`` (wall-clock per response, ms).

        Dimensions: ``Endpoint``, ``Method``. We deliberately omit
        ``StatusCode`` from the duration dimension set because the
        cardinality cost outweighs the analytical benefit — operators
        slice latency by endpoint/method, not by status, and #63's
        latency alarms key off the endpoint/method aggregate.
        """

        self._put(
            "RequestDuration",
            duration_ms,
            "Milliseconds",
            [
                {"Name": "Endpoint", "Value": endpoint},
                {"Name": "Method", "Value": method},
            ],
        )

    def error_count(
        self, endpoint: str, method: str, error_class: str
    ) -> None:
        """Emit ``ErrorCount`` (one count per 4xx/5xx response).

        Dimensions: ``Endpoint``, ``Method``, ``ErrorClass``. The
        ``error_class`` comes from ``request.state.error_class`` (set by
        :func:`catalyst.errors.to_http_exception`) so the same class
        names that appear in the response body (``ValidationFailure``,
        ``ResourceNotFound``, ``AWSTransientFailure``, etc.) are the
        ones that surface in the dimension — which lets a single
        CloudWatch alarm key off the class name an operator already
        knows from reading the error contract docs.
        """

        self._put(
            "ErrorCount",
            1,
            "Count",
            [
                {"Name": "Endpoint", "Value": endpoint},
                {"Name": "Method", "Value": method},
                {"Name": "ErrorClass", "Value": error_class},
            ],
        )

    def retry_attempt(self, endpoint: str, error_code: str) -> None:
        """Emit ``RetryAttempt`` (one count per ``with_aws_retry`` retry).

        Dimensions: ``Endpoint``, ``ErrorCode``. Fired from the
        ``before_sleep`` hook in :func:`catalyst.errors._log_retry_attempt`
        so a transient ThrottlingException that successfully retries
        still shows up as a real retry attempt — without this metric
        the only visibility into retry pressure is the log line, which
        is harder to alarm on.
        """

        self._put(
            "RetryAttempt",
            1,
            "Count",
            [
                {"Name": "Endpoint", "Value": endpoint or "unknown"},
                {"Name": "ErrorCode", "Value": error_code or "Unknown"},
            ],
        )


#: Process-wide singleton used by the middleware + retry hook. Tests
#: that want to assert on emission patterns swap ``metrics.client`` to
#: a fake recorder; tests that want to verify a clean instance per test
#: can construct their own :class:`MetricsEmitter` and inject it via a
#: monkeypatch on this module attribute.
metrics = MetricsEmitter()


# ---------------------------------------------------------------------------
# Endpoint-template helper.
# ---------------------------------------------------------------------------


def endpoint_template(path: str) -> str:
    """Collapse a request path to a cardinality-bounded endpoint template.

    CloudWatch dimensions explode the metric cardinality if we use the
    raw path — a unique construct address per onboard request would
    create one ``Endpoint`` value per app, blowing the 30-dimension cap
    in a single tenant. The middleware sends every request through this
    function first so the dimension value is the bounded *template*
    (e.g. ``/services/{addr}``) instead of the literal slug-bearing
    path.

    The set of templates below mirrors the route declarations in
    :mod:`catalyst.main` — when a new route is added there, add the
    matching template here so its observability metric is bounded.
    """

    # Order matters: longer / more-specific prefixes MUST come first so
    # a path like ``/services/{addr}/deploy`` doesn't match the bare
    # ``/services/{addr}`` template.
    if not path or path == "/":
        return "/"

    # Strip any trailing slash for a canonical match.
    canonical = path.rstrip("/") or "/"

    if canonical == "/health":
        return "/health"
    if canonical == "/catalog":
        return "/catalog"
    if canonical == "/products":
        return "/products"
    if canonical == "/products/deploy":
        return "/products/deploy"
    if canonical == "/services/onboard":
        return "/services/onboard"
    if canonical == "/iam/groups":
        return "/iam/groups"

    parts = canonical.lstrip("/").split("/")

    # /orgs/{tenant}/ous, /orgs/{tenant}/landing-zones, /orgs/{tenant}/environments,
    # /orgs/{tenant}/applications -> /orgs/{tenant}/<kind>
    if len(parts) == 3 and parts[0] == "orgs":
        kind = parts[2]
        return f"/orgs/{{tenant}}/{kind}"

    # /orgs/{tenant}
    if len(parts) == 2 and parts[0] == "orgs":
        return "/orgs/{tenant}"

    # /products/{tenant}/{project}/{app} (3-segment after /products)
    if len(parts) == 4 and parts[0] == "products":
        return "/products/{tenant}/{project}/{app}"

    # /iam/groups/{group}/members
    if len(parts) == 4 and parts[0] == "iam" and parts[1] == "groups" and parts[3] == "members":
        return "/iam/groups/{group}/members"

    # /services/{addr}/deploy, /services/{addr}/config — the addr is the
    # 5-segment construct path, so we look for the trailing literal
    # ("deploy" or "config") and template everything else.
    if parts and parts[0] == "services" and parts[-1] in {"deploy", "config"}:
        return f"/services/{{addr}}/{parts[-1]}"

    # /services/{addr} — any other path under /services/ collapses here.
    if parts and parts[0] == "services":
        return "/services/{addr}"

    # Fallback: collapse path params we can't recognise. Better to lose
    # specificity than to leak unbounded cardinality into CloudWatch.
    return "/" + "/".join(parts[:1]) + "/{path}"


# Configure logging once at import time so the JSON-line format is in
# place before any handler runs. ``main.py`` imports this module at app
# init time, which guarantees the formatter is wired by the time the
# first request lands. Idempotent against re-import.
configure_logging()
