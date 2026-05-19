"""Shared fixtures for the Catalyst end-to-end regression suite (#207).

The same six journey files run in two modes, selected at fixture-resolution
time by ``CATALYST_E2E_LIVE``:

* **Mock mode (default).** ``client`` is a
  :class:`fastapi.testclient.TestClient` wrapping the in-process
  ``catalyst.main.app``. ``InMemoryRepository`` is reset on every test so
  state never bleeds between tests. The ``terraform`` subprocess chain
  the onboard journey would otherwise invoke is replaced via the
  ``_SubprocessRecorder`` pattern (see ``test_journey_03_app_onboard``).
* **Live mode.** ``CATALYST_E2E_LIVE=1`` plus
  ``CATALYST_API_ENDPOINT=https://...`` swaps in a
  :class:`requests.Session` pointed at the real ALB. Tests that cannot
  run live (real Terraform applies, moto-only STS) skip cleanly.

The same ``client`` object exposes a ``.get/.post`` surface in both
modes — journey tests only branch on mode for behaviour-level
assertions (idempotency replay, real-vs-mock ARN shapes, etc.).

Three project-rooted ``sys.path`` insertions live at the top of the file
so ``from catalyst.main import app`` resolves without a project-level
``pyproject.toml`` — same pattern the per-component ``conftest.py``
files use today.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Iterator

import pytest

# ---------------------------------------------------------------------------
# sys.path wiring — exposes ``catalyst`` (API) and ``catalyst_cli`` (CLI)
# without requiring an editable install. Matches the per-component conftests.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "catalyst-api"
CLI_ROOT = REPO_ROOT / "clients" / "catalyst-cli"
for path in (API_ROOT, CLI_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


# ---------------------------------------------------------------------------
# Mode toggle
# ---------------------------------------------------------------------------


def _live_mode_enabled() -> bool:
    """True when both ``CATALYST_E2E_LIVE`` and ``CATALYST_API_ENDPOINT`` are set."""

    if os.environ.get("CATALYST_E2E_LIVE", "").strip() not in ("1", "true", "True"):
        return False
    return bool(os.environ.get("CATALYST_API_ENDPOINT", "").strip())


@pytest.fixture(scope="session")
def mode() -> str:
    """Return ``"live"`` or ``"mock"`` for the whole session.

    Single source of truth so journey tests can ``if mode == "live": ...``
    without re-reading env vars. Session-scoped because the mode never
    changes mid-suite.
    """

    return "live" if _live_mode_enabled() else "mock"


# ---------------------------------------------------------------------------
# Mock-mode plumbing — reset state on every test and ensure the API can
# resolve its dependencies without real AWS.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_api_state(mode: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Wipe the in-process API state between tests in mock mode.

    Live mode leaves the real stack untouched — operators must clean up
    their own seed data per ``docs/e2e-testing.md``.
    """

    if mode == "live":
        yield
        return

    # Force the headers-based auth path (the e2e RBAC journey explicitly
    # overrides this to ``sigv4`` for one sub-case) and a memory repo so
    # tests are hermetic.
    monkeypatch.setenv("CATALYST_AUTH_MODE", "headers")
    monkeypatch.setenv("CATALYST_REPOSITORY", "memory")

    from catalyst import settings as settings_module
    from catalyst.rbac import _clear_cache
    from catalyst.repository import InMemoryRepository, set_repository

    settings_module.reset_settings()
    set_repository(InMemoryRepository())
    _clear_cache()
    yield
    settings_module.reset_settings()
    _clear_cache()


# ---------------------------------------------------------------------------
# The ``client`` fixture — surface a uniform .get/.post in both modes.
# ---------------------------------------------------------------------------


class _LiveClient:
    """Thin requests.Session wrapper that mimics the bits of TestClient we use.

    Returns objects whose ``.status_code``, ``.headers``, and ``.json()``
    match TestClient's contract so journey tests don't need a branch
    every time they read a response.
    """

    def __init__(self, base_url: str) -> None:
        import requests

        self._session = requests.Session()
        self._base = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return self._base + path if path.startswith("/") else f"{self._base}/{path}"

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._session.get(self._url(path), timeout=30, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self._session.post(self._url(path), timeout=30, **kwargs)


@pytest.fixture
def client(mode: str):
    """Return a TestClient (mock) or a requests-backed shim (live).

    Both expose the .get/.post(path, headers=, json=) surface; journey
    tests should treat the returned object as opaque and call
    ``.status_code`` / ``.headers`` / ``.json()`` on the response.
    """

    if mode == "live":
        endpoint = os.environ["CATALYST_API_ENDPOINT"]
        return _LiveClient(endpoint)

    # Lazy import so the CLI test environment (which doesn't ship fastapi)
    # doesn't choke on collection.
    from fastapi.testclient import TestClient

    from catalyst.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def correlation_id_header() -> dict[str, str]:
    """Return a fresh ``X-Correlation-ID`` header dict.

    Validates the #61 middleware: the value is a UUIDv4 the journey can
    grep for in ``response.headers["X-Correlation-ID"]`` and
    ``response.json()["correlation_id"]``.
    """

    return {"X-Correlation-ID": str(uuid.uuid4())}


def _iam_groups_header(groups: str, caller: str) -> dict[str, str]:
    """Return the canonical RBAC headers used by every API test today.

    Matches ``services/catalyst-api/tests/test_api.py``'s ``_headers()``.
    """

    return {
        "x-caller-arn": caller,
        "x-iam-groups": groups,
    }


@pytest.fixture
def owner_headers(correlation_id_header: dict[str, str]) -> dict[str, str]:
    return {
        **_iam_groups_header(
            "catalyst-owners", "arn:aws:iam::123456789012:user/e2e-owner"
        ),
        **correlation_id_header,
    }


@pytest.fixture
def admin_headers(correlation_id_header: dict[str, str]) -> dict[str, str]:
    return {
        **_iam_groups_header(
            "catalyst-support-admins", "arn:aws:iam::123456789012:user/e2e-admin"
        ),
        **correlation_id_header,
    }


@pytest.fixture
def viewer_headers(correlation_id_header: dict[str, str]) -> dict[str, str]:
    return {
        **_iam_groups_header(
            "catalyst-support-viewers", "arn:aws:iam::123456789012:user/e2e-viewer"
        ),
        **correlation_id_header,
    }


# ---------------------------------------------------------------------------
# Per-test tenant slug — deterministic-but-unique so a re-run on a live
# stack does not collide with the previous run's seed data.
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_slug(request: pytest.FixtureRequest) -> str:
    """Per-test tenant slug, e.g. ``e2e-journey-02-a1b2c3d4``.

    Deterministic on the test node id so a flaky test can grep CloudWatch
    for its own slug, but suffixed with a short UUID so successive runs
    don't reuse the same tenant key in the real DynamoDB table.
    """

    base = request.node.name.replace("test_", "").replace("_", "-").lower()
    if len(base) > 30:
        base = base[:30]
    return f"e2e-{base}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Subprocess-fake for the onboard journey — re-uses the proven
# ``_SubprocessRecorder`` pattern from
# ``services/catalyst-api/tests/test_onboard.py``. The class + factory
# live in ``_terraform_fakes.py`` so journey test modules can import
# them without depending on conftest discovery semantics.
# ---------------------------------------------------------------------------

# The helpers live alongside ``conftest.py`` and are imported by journey
# tests as ``from _terraform_fakes import ...`` (the e2e directory is on
# sys.path because pytest's rootdir-as-conftest behaviour adds it).


@pytest.fixture
def onboard_env(monkeypatch: pytest.MonkeyPatch, mode: str) -> Iterator[None]:
    """Configure the env vars the onboard handler requires.

    Mock-mode only — live mode talks to the deployed Lambda whose env
    is already set. Mirrors ``test_onboard.py::env_setup``.
    """

    if mode == "live":
        yield
        return

    monkeypatch.setenv(
        "CATALYST_STATE_BUCKET", "catalyst-tf-state-123456789012-us-west-2"
    )
    monkeypatch.setenv(
        "CATALYST_LOCK_TABLE", "catalyst-tf-lock-123456789012-us-west-2"
    )
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("CATALYST_ALB_LISTENER_ARN", "")
    monkeypatch.setenv("CATALYST_ALB_TARGET_GROUP_ARN", "")
    yield


@pytest.fixture
def patch_boto3_cloudwatch(monkeypatch: pytest.MonkeyPatch, mode: str) -> Iterator[Any]:
    """Stub out the boto3 CloudWatch client the onboard handler uses for metrics.

    Yields the recorder so journey tests can introspect calls. Mock-mode
    only.
    """

    if mode == "live":
        yield None
        return

    class _MetricRecorder:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def put_metric_data(self, **kwargs: Any) -> None:
            self.calls.append(kwargs)

    recorder = _MetricRecorder()

    def cw_factory(client_name: str, region_name: str | None = None) -> Any:  # noqa: ARG001
        return recorder

    import boto3

    monkeypatch.setattr(boto3, "client", cw_factory)
    yield recorder
