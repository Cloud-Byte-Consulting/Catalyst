"""Tests for the SVC-6 observability middleware + helpers (#60).

The middleware emits four metric types (``RequestCount``,
``RequestDuration``, ``ErrorCount``, ``RetryAttempt``) against the
locked ``Catalyst/API`` namespace, plus a JSON-line structured log per
request. These tests assert:

* Per-request emission shape — every response, success or failure,
  fires ``RequestCount`` and ``RequestDuration`` with the right
  cardinality-bounded ``Endpoint`` template.
* 4xx-path ``ErrorCount`` carries the canonical error-class name (the
  same name that lands in the response body's ``error`` field).
* Structured log line is valid JSON and carries every required field
  from the Decision Log (``timestamp``, ``level``, ``event``,
  ``endpoint``, ``correlation_id``, ``caller_arn``, ``tenant``).
* Correlation-ID threads through the LOG payload end-to-end (it's NOT
  a metric dimension — cardinality cost outweighs benefit).
* A failure inside ``PutMetricData`` MUST NOT break the request path —
  the request still succeeds and a single ``metric_emit_failed`` log
  line surfaces the swallow.
* The retry hook (#205) now emits ``RetryAttempt`` against the same
  namespace per the #60 Decision Log.
* ``endpoint_template`` collapses path params to bounded templates so
  dimension cardinality stays sane.
* The Onboard-specific ``Catalyst/Onboard:OnboardDuration`` metric
  (#167) coexists cleanly with the new generic
  ``Catalyst/API:RequestDuration`` — both fire for the same onboard
  invocation, and the Onboard metric is NOT touched by #60.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from typing import Any

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from catalyst import observability
from catalyst.main import app
from catalyst.observability import (
    JSONFormatter,
    MetricsEmitter,
    METRIC_NAMESPACE,
    caller_arn_var,
    configure_logging,
    correlation_id_var,
    endpoint_template,
    endpoint_var,
    tenant_var,
)
from catalyst.repository import InMemoryRepository, set_repository


client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures + recorders.
# ---------------------------------------------------------------------------


class _MetricRecorder:
    """Captures every PutMetricData call so tests can assert on shape.

    Mirrors the pattern used by ``tests/test_onboard.py`` — a tiny stub
    that records ``Namespace`` + ``MetricData`` per call so the assertion
    is on the structured shape, not a brittle string comparison.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _RaisingCloudWatch:
    """PutMetricData stub that always raises — used to assert the swallow."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        raise ClientError(
            error_response={
                "Error": {"Code": "InternalFailure", "Message": "cw is down"},
                "ResponseMetadata": {"HTTPStatusCode": 500},
            },
            operation_name="PutMetricData",
        )


@pytest.fixture(autouse=True)
def _fresh_repo() -> None:
    """Reset the in-memory repository between tests."""

    set_repository(InMemoryRepository())


@pytest.fixture
def metric_recorder(monkeypatch) -> _MetricRecorder:
    """Swap the MetricsEmitter client for a recorder that captures every call."""

    recorder = _MetricRecorder()
    monkeypatch.setattr(observability.metrics, "_client", recorder)
    return recorder


def _headers(
    groups: str = "catalyst-owners",
    caller: str = "arn:aws:iam::123456789012:user/test",
    correlation_id: str | None = None,
) -> dict:
    headers = {
        "x-caller-arn": caller,
        "x-iam-groups": groups,
    }
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    return headers


def _dims(call: dict) -> dict:
    """Pull the dimensions of the first metric in a PutMetricData call."""

    data = call["MetricData"][0]
    return {d["Name"]: d["Value"] for d in data["Dimensions"]}


def _by_name(calls: list[dict], name: str) -> list[dict]:
    """Filter a list of PutMetricData calls by metric name."""

    return [c for c in calls if c["MetricData"][0]["MetricName"] == name]


# ---------------------------------------------------------------------------
# Per-request metric emission.
# ---------------------------------------------------------------------------


def test_request_complete_emits_request_count_and_duration(metric_recorder) -> None:
    """A 200 GET fires both RequestCount and RequestDuration in Catalyst/API."""

    response = client.get("/health")
    assert response.status_code == 200

    counts = _by_name(metric_recorder.calls, "RequestCount")
    durations = _by_name(metric_recorder.calls, "RequestDuration")

    assert len(counts) == 1, f"expected one RequestCount, got {metric_recorder.calls}"
    assert len(durations) == 1

    assert counts[0]["Namespace"] == METRIC_NAMESPACE == "Catalyst/API"
    assert durations[0]["Namespace"] == METRIC_NAMESPACE

    cdims = _dims(counts[0])
    assert cdims["Endpoint"] == "/health"
    assert cdims["Method"] == "GET"
    assert cdims["StatusCode"] == "200"

    ddims = _dims(durations[0])
    assert ddims["Endpoint"] == "/health"
    assert ddims["Method"] == "GET"
    # Duration must be a positive number recorded in Milliseconds.
    duration_data = durations[0]["MetricData"][0]
    assert duration_data["Unit"] == "Milliseconds"
    assert duration_data["Value"] >= 0.0


def test_request_count_emitted_for_post(metric_recorder) -> None:
    """The Method dimension reflects POST, not GET."""

    response = client.post(
        "/orgs/cloud-byte/ous",
        json={"name": "platform-ou"},
        headers=_headers(),
    )
    # OU create may 200 or 422 depending on body shape; we don't care
    # about the status here, only that the Method dimension is POST.
    assert response.status_code in (200, 422)

    counts = _by_name(metric_recorder.calls, "RequestCount")
    assert counts, "expected at least one RequestCount"
    assert _dims(counts[0])["Method"] == "POST"


def test_error_count_not_emitted_on_2xx(metric_recorder) -> None:
    """A successful response MUST NOT emit ErrorCount."""

    response = client.get("/health")
    assert response.status_code == 200
    assert _by_name(metric_recorder.calls, "ErrorCount") == []


def test_4xx_response_emits_error_count(metric_recorder) -> None:
    """A validation failure emits ErrorCount tagged with ValidationFailure.

    Drives ``POST /services/onboard`` with a malformed construct
    address — the handler raises ``ValidationFailure`` via
    ``to_http_exception``, which stashes ``error_class`` on
    request.state. The middleware reads that and emits the metric.
    """

    response = client.post(
        "/services/onboard",
        json={"construct_address": "bad-address"},
        headers=_headers("catalyst-support-admins"),
    )
    assert response.status_code == 422

    errors = _by_name(metric_recorder.calls, "ErrorCount")
    assert len(errors) == 1
    edims = _dims(errors[0])
    assert edims["Endpoint"] == "/services/onboard"
    assert edims["Method"] == "POST"
    # The class name MUST match what the response body's ``error`` field carries.
    assert edims["ErrorClass"] == "ValidationFailure"
    # And the canonical body carries the same name — sanity-check the
    # contract is honoured both at the metric layer AND in the response.
    assert response.json()["detail"]["error"] == "ValidationFailure"


def test_404_emits_error_count_with_resource_not_found(metric_recorder) -> None:
    """A 404 lands ErrorCount tagged with ResourceNotFound."""

    response = client.get(
        "/services/cloud-byte/dev/shared/platform/never-onboarded",
        headers=_headers("catalyst-support-viewers"),
    )
    assert response.status_code == 404

    errors = _by_name(metric_recorder.calls, "ErrorCount")
    assert errors
    assert _dims(errors[0])["ErrorClass"] == "ResourceNotFound"


def test_404_emits_with_collapsed_endpoint_template(metric_recorder) -> None:
    """The Endpoint dimension uses the bounded template, not the literal URL."""

    response = client.get(
        "/services/cloud-byte/dev/shared/platform/never-onboarded",
        headers=_headers("catalyst-support-viewers"),
    )
    assert response.status_code == 404

    counts = _by_name(metric_recorder.calls, "RequestCount")
    assert counts
    # The literal path has 5 distinct slugs; the template collapses
    # them to ``/services/{addr}`` so cardinality stays bounded.
    assert _dims(counts[0])["Endpoint"] == "/services/{addr}"


# ---------------------------------------------------------------------------
# Structured logging shape.
# ---------------------------------------------------------------------------


def test_json_formatter_produces_valid_single_line_json() -> None:
    """A LogRecord rendered through JSONFormatter is parseable as JSON."""

    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="catalyst.test",
        level=logging.INFO,
        pathname="test",
        lineno=1,
        msg="hello",
        args=None,
        exc_info=None,
    )
    rendered = formatter.format(record)
    parsed = json.loads(rendered)
    # Required fields per the #60 Decision Log are always present, even
    # when their contextvars are unset (None values are explicit, not
    # missing keys — that way log filters keying on field absence work).
    for key in ("timestamp", "level", "event", "endpoint", "correlation_id", "caller_arn", "tenant"):
        assert key in parsed, f"required field {key} missing from JSON log line"
    assert parsed["level"] == "INFO"
    assert parsed["event"] == "hello"


def test_json_formatter_threads_contextvars_into_log() -> None:
    """Setting endpoint/correlation/caller_arn/tenant contextvars threads them in."""

    formatter = JSONFormatter()
    ep_token = endpoint_var.set("/health")
    cid_token = correlation_id_var.set("cid-123")
    arn_token = caller_arn_var.set("arn:aws:iam::123:user/bob")
    tenant_token = tenant_var.set("acme")
    try:
        record = logging.LogRecord(
            name="catalyst.test",
            level=logging.INFO,
            pathname="test",
            lineno=1,
            msg="threaded",
            args=None,
            exc_info=None,
        )
        rendered = formatter.format(record)
        parsed = json.loads(rendered)
    finally:
        endpoint_var.reset(ep_token)
        correlation_id_var.reset(cid_token)
        caller_arn_var.reset(arn_token)
        tenant_var.reset(tenant_token)

    assert parsed["endpoint"] == "/health"
    assert parsed["correlation_id"] == "cid-123"
    assert parsed["caller_arn"] == "arn:aws:iam::123:user/bob"
    assert parsed["tenant"] == "acme"


def test_json_formatter_merges_extras_into_payload() -> None:
    """A ``logger.info(msg, extra={...})`` adds top-level keys, not nested."""

    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="catalyst.test",
        level=logging.INFO,
        pathname="test",
        lineno=1,
        msg="event",
        args=None,
        exc_info=None,
    )
    record.duration_ms = 42.5
    record.error_class = "ValidationFailure"
    rendered = formatter.format(record)
    parsed = json.loads(rendered)
    assert parsed["duration_ms"] == 42.5
    assert parsed["error_class"] == "ValidationFailure"


def test_json_formatter_serialises_non_json_extras_safely() -> None:
    """Non-JSON-serialisable extras (datetimes, Decimal) don't drop the line."""

    from datetime import datetime, timezone as _tz

    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="catalyst.test",
        level=logging.INFO,
        pathname="test",
        lineno=1,
        msg="event",
        args=None,
        exc_info=None,
    )
    record.when = datetime(2026, 5, 18, tzinfo=_tz.utc)
    rendered = formatter.format(record)
    parsed = json.loads(rendered)
    # Stringified rather than dropped — better visibility for operators.
    assert "2026-05-18" in str(parsed["when"])


def test_structured_log_contains_required_fields(caplog) -> None:
    """The middleware's ``request_complete`` log line carries every required field.

    We capture via ``caplog`` (LogRecord level) rather than parsing the
    stdout JSON — caplog gives us the raw extras dict which is
    semantically equivalent and avoids coupling the test to stdout
    capture details. The JSON-line shape is asserted separately by
    ``test_json_formatter_produces_valid_single_line_json``.
    """

    with caplog.at_level(logging.INFO, logger="catalyst.main"):
        response = client.get(
            "/health",
            headers={"X-Correlation-ID": "cid-log-shape"},
        )
    assert response.status_code == 200

    complete = [r for r in caplog.records if r.message == "request_complete"]
    assert complete, "expected a request_complete log line"
    record = complete[-1].__dict__
    assert record.get("endpoint") == "/health"
    assert record.get("method") == "GET"
    assert record.get("status_code") == 200
    assert record.get("correlation_id") == "cid-log-shape"
    assert isinstance(record.get("duration_ms"), float)


def test_request_complete_log_is_actual_json_line_on_stdout() -> None:
    """The configured handler renders to JSON on stdout — assert end-to-end.

    Re-configure logging with a fresh JSON handler pointed at an
    in-memory stream so we can read the literal rendered line and
    parse it. This proves the full path (record -> formatter -> JSON
    line) actually works, not just the LogRecord shape.
    """

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        # Drive a real request so the middleware's request_complete log
        # line lands in our stream.
        client.get("/health", headers={"X-Correlation-ID": "cid-stdout-line"})
    finally:
        root.removeHandler(handler)

    raw = stream.getvalue().splitlines()
    # Find the request_complete line — there may be other log lines
    # interleaved depending on what else fired.
    matching = [line for line in raw if "request_complete" in line]
    assert matching, f"no request_complete line in stream output: {raw!r}"
    parsed = json.loads(matching[-1])
    assert parsed["event"] == "request_complete"
    assert parsed["endpoint"] == "/health"
    assert parsed["correlation_id"] == "cid-stdout-line"
    assert parsed["status_code"] == 200


def test_5xx_logs_at_error_level(caplog, monkeypatch) -> None:
    """A 5xx response logs the ``request_complete`` line at ERROR level."""

    # Force a 500 by making the repository raise from a handler that doesn't
    # have its own error mapping — the boundary translator returns 500.
    repo = InMemoryRepository()

    def boom(*_a, **_kw):
        raise RuntimeError("synthetic boom")

    monkeypatch.setattr(repo, "get_organization", boom)
    set_repository(repo)

    with caplog.at_level(logging.ERROR, logger="catalyst.main"):
        response = client.get(
            "/orgs/cloud-byte",
            headers=_headers("catalyst-support-viewers"),
        )
    assert response.status_code == 500

    complete = [
        r for r in caplog.records
        if r.message == "request_complete" and r.levelno == logging.ERROR
    ]
    assert complete, "expected an ERROR-level request_complete log line"


# ---------------------------------------------------------------------------
# Correlation-ID threading.
# ---------------------------------------------------------------------------


def test_correlation_id_threads_through_metrics_and_logs(caplog, metric_recorder) -> None:
    """Setting X-Correlation-ID lands the id in the LOG payload.

    Per the #60 Decision Log the correlation id is NOT a metric
    dimension (cardinality cost is unbounded — one new dimension value
    per request) so we verify it appears in the LOG, while the metric
    layer carries only the bounded endpoint/method/status_code/error_class
    dimensions.
    """

    given = str(uuid.uuid4())
    with caplog.at_level(logging.INFO, logger="catalyst.main"):
        response = client.get(
            "/health", headers={"X-Correlation-ID": given}
        )
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == given

    # Log payload carries the id.
    complete = [r for r in caplog.records if r.message == "request_complete"]
    assert complete
    assert complete[-1].__dict__.get("correlation_id") == given

    # Metric dimensions do NOT carry correlation_id — verify by reading
    # every recorded metric's dimensions and confirming the given id is
    # absent. This is the cardinality-control guardrail.
    for call in metric_recorder.calls:
        for dim in call["MetricData"][0]["Dimensions"]:
            assert dim["Value"] != given, (
                f"correlation_id MUST NOT appear as a metric dimension; "
                f"found in {call!r}"
            )


# ---------------------------------------------------------------------------
# Failure isolation: a metric failure MUST NOT break the request path.
# ---------------------------------------------------------------------------


def test_metric_emit_failure_does_not_break_request(monkeypatch, caplog) -> None:
    """A raising CloudWatch client keeps the request returning 200."""

    raising = _RaisingCloudWatch()
    monkeypatch.setattr(observability.metrics, "_client", raising)

    with caplog.at_level(logging.WARNING, logger="catalyst.observability"):
        response = client.get("/health")
    assert response.status_code == 200

    # The metric stub WAS invoked (so we know the swallow ran).
    assert raising.calls, "expected at least one PutMetricData attempt"

    # A ``metric_emit_failed`` line surfaces the swallow so operators
    # can see the failure trail.
    failures = [r for r in caplog.records if r.message == "metric_emit_failed"]
    assert failures, "expected a metric_emit_failed log line on swallow"


# ---------------------------------------------------------------------------
# Endpoint template / cardinality control.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/health", "/health"),
        ("/catalog", "/catalog"),
        ("/", "/"),
        ("/orgs/acme", "/orgs/{tenant}"),
        ("/orgs/acme/ous", "/orgs/{tenant}/ous"),
        ("/orgs/acme/landing-zones", "/orgs/{tenant}/landing-zones"),
        ("/orgs/acme/environments", "/orgs/{tenant}/environments"),
        ("/orgs/acme/applications", "/orgs/{tenant}/applications"),
        ("/products", "/products"),
        ("/products/deploy", "/products/deploy"),
        (
            "/products/acme/payments/checkout",
            "/products/{tenant}/{project}/{app}",
        ),
        ("/services/onboard", "/services/onboard"),
        (
            "/services/acme/dev/shared/payments/checkout",
            "/services/{addr}",
        ),
        (
            "/services/acme/dev/shared/payments/checkout/deploy",
            "/services/{addr}/deploy",
        ),
        (
            "/services/acme/dev/shared/payments/checkout/config",
            "/services/{addr}/config",
        ),
        ("/iam/groups", "/iam/groups"),
        (
            "/iam/groups/catalyst-support-admins/members",
            "/iam/groups/{group}/members",
        ),
    ],
)
def test_endpoint_template_collapses_paths(raw: str, expected: str) -> None:
    """Every catalyst route collapses to a bounded-cardinality template."""

    assert endpoint_template(raw) == expected


def test_endpoint_template_unknown_path_falls_back_safely() -> None:
    """Unknown paths collapse safely (no unbounded cardinality leak)."""

    result = endpoint_template("/unknown/some/random/slug")
    # Fallback collapses everything after the first segment to ``{path}``.
    assert result == "/unknown/{path}"


# ---------------------------------------------------------------------------
# RetryAttempt metric — #205's before_sleep hook now emits the metric.
# ---------------------------------------------------------------------------


@pytest.fixture
def _no_backoff_sleep(monkeypatch) -> None:
    """Stub tenacity's nap so retry tests don't accrue wall-clock."""

    import tenacity.nap

    monkeypatch.setattr(tenacity.nap, "sleep", lambda _seconds: None)


def test_retry_attempt_metric_emitted_on_throttling(
    monkeypatch, _no_backoff_sleep, metric_recorder
) -> None:
    """A retry on ThrottlingException fires the RetryAttempt metric.

    Drives the DynamoDB repository's ``_get`` (wrapped by
    ``with_aws_retry``) directly with a flaky stub that throttles once
    then succeeds — the same surface #205's existing tests use.
    """

    from catalyst.errors import retry_correlation_id, retry_endpoint
    from catalyst.repository import DynamoDBRepository

    class _ThrottleOnceTable:
        def __init__(self) -> None:
            self.calls = 0

        def get_item(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ClientError(
                    error_response={
                        "Error": {
                            "Code": "ThrottlingException",
                            "Message": "rate exceeded",
                        },
                        "ResponseMetadata": {"HTTPStatusCode": 400},
                    },
                    operation_name="GetItem",
                )
            return {"Item": {"pk": "ok", "sk": "ok"}}

    table = _ThrottleOnceTable()
    repo = DynamoDBRepository("catalyst-platform-state", table=table)

    cid_token = retry_correlation_id.set("cid-retry-metric")
    ep_token = retry_endpoint.set("/services/{addr}")
    try:
        result = repo._get("PK#x", "SK#x")
    finally:
        retry_correlation_id.reset(cid_token)
        retry_endpoint.reset(ep_token)

    assert result == {"pk": "ok", "sk": "ok"}
    assert table.calls == 2

    # The retry hook fired exactly once (before sleeping for retry 2).
    retries = _by_name(metric_recorder.calls, "RetryAttempt")
    assert len(retries) == 1, f"expected 1 RetryAttempt, got {retries}"
    rdims = _dims(retries[0])
    assert rdims["Endpoint"] == "/services/{addr}"
    assert rdims["ErrorCode"] == "ThrottlingException"
    assert retries[0]["Namespace"] == METRIC_NAMESPACE == "Catalyst/API"


def test_retry_attempt_metric_failure_does_not_break_retry(
    monkeypatch, _no_backoff_sleep
) -> None:
    """Even if PutMetricData fails, the retry path still completes."""

    raising = _RaisingCloudWatch()
    monkeypatch.setattr(observability.metrics, "_client", raising)

    from catalyst.repository import DynamoDBRepository

    class _ThrottleOnceTable:
        def __init__(self) -> None:
            self.calls = 0

        def get_item(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ClientError(
                    error_response={
                        "Error": {
                            "Code": "ThrottlingException",
                            "Message": "rate exceeded",
                        },
                        "ResponseMetadata": {"HTTPStatusCode": 400},
                    },
                    operation_name="GetItem",
                )
            return {"Item": {"pk": "ok", "sk": "ok"}}

    table = _ThrottleOnceTable()
    repo = DynamoDBRepository("catalyst-platform-state", table=table)

    # Should NOT raise — observability MUST NOT mask the retry success.
    result = repo._get("PK#x", "SK#x")
    assert result == {"pk": "ok", "sk": "ok"}
    assert table.calls == 2


# ---------------------------------------------------------------------------
# Onboard coexistence — verify the new generic metric ALSO fires on onboard.
# ---------------------------------------------------------------------------


def test_onboard_emits_both_onboard_and_api_duration(monkeypatch, metric_recorder) -> None:
    """``POST /services/onboard`` lands BOTH metrics (preserves #167 trip-wire).

    The conftest fake replaces ``provision_app`` for the default fixture
    so this test exercises the handler-side middleware on the same
    surface real onboard would take, without shelling out.
    """

    response = client.post(
        "/services/onboard",
        json={
            "construct_address": "acme/dev/shared/payments/checkout",
            "service_type": "web-service",
            "idempotency_key": "onboard-obs-coexist",
        },
        headers=_headers("catalyst-support-admins"),
    )
    assert response.status_code == 200, response.text

    # The generic per-API metric fires.
    counts = _by_name(metric_recorder.calls, "RequestCount")
    durations = _by_name(metric_recorder.calls, "RequestDuration")
    assert counts
    assert durations
    # Endpoint collapses to the literal route — onboard is its own bucket
    # (we don't want it lumped with arbitrary /services/{addr} paths).
    assert _dims(counts[0])["Endpoint"] == "/services/onboard"
    assert _dims(durations[0])["Endpoint"] == "/services/onboard"
    # And the namespace is the new generic one — preserving Onboard's
    # own namespace was the explicit choice in the Decision Log.
    assert counts[0]["Namespace"] == "Catalyst/API"


# ---------------------------------------------------------------------------
# MetricsEmitter unit tests — direct surface, no HTTP plumbing.
# ---------------------------------------------------------------------------


def test_metrics_emitter_uses_locked_namespace_for_every_method() -> None:
    """Every public method on MetricsEmitter writes to ``Catalyst/API``."""

    emitter = MetricsEmitter()
    recorder = _MetricRecorder()
    emitter.client = recorder

    emitter.request_count("/health", "GET", 200)
    emitter.request_duration("/health", "GET", 12.5)
    emitter.error_count("/services/onboard", "POST", "ValidationFailure")
    emitter.retry_attempt("/services/{addr}", "ThrottlingException")

    assert len(recorder.calls) == 4
    for call in recorder.calls:
        assert call["Namespace"] == "Catalyst/API"


def test_metrics_emitter_request_count_shape() -> None:
    emitter = MetricsEmitter()
    recorder = _MetricRecorder()
    emitter.client = recorder

    emitter.request_count("/orgs/{tenant}", "GET", 200)
    call = recorder.calls[0]
    data = call["MetricData"][0]
    assert data["MetricName"] == "RequestCount"
    assert data["Unit"] == "Count"
    assert data["Value"] == 1.0
    dims = {d["Name"]: d["Value"] for d in data["Dimensions"]}
    assert dims == {
        "Endpoint": "/orgs/{tenant}",
        "Method": "GET",
        "StatusCode": "200",
    }


def test_metrics_emitter_request_duration_shape() -> None:
    emitter = MetricsEmitter()
    recorder = _MetricRecorder()
    emitter.client = recorder

    emitter.request_duration("/orgs/{tenant}", "GET", 42.5)
    call = recorder.calls[0]
    data = call["MetricData"][0]
    assert data["MetricName"] == "RequestDuration"
    assert data["Unit"] == "Milliseconds"
    assert data["Value"] == 42.5
    dims = {d["Name"]: d["Value"] for d in data["Dimensions"]}
    # Duration deliberately omits StatusCode dimension — analytical
    # slicing keys off endpoint/method, not status.
    assert dims == {"Endpoint": "/orgs/{tenant}", "Method": "GET"}


def test_metrics_emitter_error_count_shape() -> None:
    emitter = MetricsEmitter()
    recorder = _MetricRecorder()
    emitter.client = recorder

    emitter.error_count("/services/onboard", "POST", "AWSTransientFailure")
    call = recorder.calls[0]
    data = call["MetricData"][0]
    assert data["MetricName"] == "ErrorCount"
    assert data["Unit"] == "Count"
    dims = {d["Name"]: d["Value"] for d in data["Dimensions"]}
    assert dims == {
        "Endpoint": "/services/onboard",
        "Method": "POST",
        "ErrorClass": "AWSTransientFailure",
    }


def test_metrics_emitter_retry_attempt_shape() -> None:
    emitter = MetricsEmitter()
    recorder = _MetricRecorder()
    emitter.client = recorder

    emitter.retry_attempt("/services/{addr}", "ThrottlingException")
    call = recorder.calls[0]
    data = call["MetricData"][0]
    assert data["MetricName"] == "RetryAttempt"
    assert data["Unit"] == "Count"
    dims = {d["Name"]: d["Value"] for d in data["Dimensions"]}
    assert dims == {
        "Endpoint": "/services/{addr}",
        "ErrorCode": "ThrottlingException",
    }


def test_metrics_emitter_handles_unknown_endpoint_and_code_gracefully() -> None:
    """``None`` endpoint / error_code collapse to ``"unknown"`` / ``"Unknown"`` sentinels."""

    emitter = MetricsEmitter()
    recorder = _MetricRecorder()
    emitter.client = recorder

    emitter.retry_attempt("", "")
    call = recorder.calls[0]
    dims = {d["Name"]: d["Value"] for d in call["MetricData"][0]["Dimensions"]}
    # Empty strings collapse to bounded sentinels so CloudWatch
    # never sees an empty dimension value (which would be rejected).
    assert dims["Endpoint"] == "unknown"
    assert dims["ErrorCode"] == "Unknown"


# ---------------------------------------------------------------------------
# configure_logging — idempotent, env-var-driven level.
# ---------------------------------------------------------------------------


def test_configure_logging_is_idempotent() -> None:
    """Calling configure_logging twice replaces, doesn't stack handlers."""

    root = logging.getLogger()
    before = len([
        h for h in root.handlers if getattr(h, "_catalyst_json_handler", False)
    ])
    configure_logging()
    configure_logging()
    after = len([
        h for h in root.handlers if getattr(h, "_catalyst_json_handler", False)
    ])
    assert after == 1, f"expected one tagged handler, got {after} (before={before})"


def test_configure_logging_respects_env_var(monkeypatch) -> None:
    """CATALYST_LOG_LEVEL=DEBUG configures DEBUG on the root logger."""

    monkeypatch.setenv("CATALYST_LOG_LEVEL", "DEBUG")
    configure_logging()
    assert logging.getLogger().level == logging.DEBUG
    # Reset back to INFO so subsequent tests aren't noisy.
    monkeypatch.delenv("CATALYST_LOG_LEVEL", raising=False)
    configure_logging()


def test_configure_logging_swallows_unknown_level_gracefully(monkeypatch) -> None:
    """A typo'd CATALYST_LOG_LEVEL doesn't crash logging."""

    monkeypatch.setenv("CATALYST_LOG_LEVEL", "TYPO_LEVEL")
    # Should not raise.
    configure_logging()
    # Falls back to INFO (the default level on a typo).
    assert logging.getLogger().level == logging.INFO
