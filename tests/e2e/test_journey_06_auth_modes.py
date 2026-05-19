"""Journey 06 — Auth modes (presigned-STS ↔ SigV4).

Asserts the asymmetric naming documented in ADR-008 § "Naming asymmetry
between client and server":

* **Client** side selects the production auth flow via
  ``CATALYST_AUTH=presigned-sts``. The CLI presigns
  ``sts:GetCallerIdentity`` with the caller's own AWS credentials and
  forwards the URL in the ``x-catalyst-identity-url`` header.
* **Server** side reads ``CATALYST_AUTH_MODE=sigv4``. The
  ``access_dependency`` notices the env var, pulls the
  ``x-catalyst-identity-url`` header, runs the URL through the
  app-state-injectable ``identity_verifier``, and finally looks up the
  caller's IAM groups via ``group_lookup``. Both seams live on
  ``app.state`` so tests can drive the full pipeline without standing
  up STS or IAM.

This journey would catch a regression in any of:

* the client-side ``x-catalyst-identity-url`` header name changing
  (renames break ADR-008's stable contract)
* the server-side ``CATALYST_AUTH_MODE=sigv4`` branch falling out of
  the dependency
* the missing-URL error path collapsing from 401 to 403 (loses the
  distinction between unauthenticated and unauthorised)

Live mode is skipped because it requires real STS credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


# ``catalyst_cli`` is needed to drive the presigned-URL generation. Path is
# inserted by conftest, but we re-assert here so this file can be moved.
CLI_DIR = Path(__file__).resolve().parents[2] / "clients" / "catalyst-cli"
if str(CLI_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_DIR))


pytestmark = pytest.mark.filterwarnings("default")


def _skip_live(mode: str) -> None:
    if mode == "live":
        pytest.skip(
            "journey 06 (auth modes) is mock-only: requires moto STS + the "
            "FastAPI app.state seams. Live mode requires real STS credentials."
        )


def test_client_side_presigned_sts_attaches_identity_url_header(monkeypatch, mode):
    """Client side: ``CATALYST_AUTH=presigned-sts`` → URL in ``x-catalyst-identity-url``."""

    _skip_live(mode)

    moto = pytest.importorskip("moto")
    mock_aws = moto.mock_aws

    # Stub AWS creds so boto3 can sign the URL under moto.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("CATALYST_AUTH", "presigned-sts")
    monkeypatch.setenv("CATALYST_API_ENDPOINT", "http://test.local")

    import catalyst_cli

    with mock_aws():
        captured: dict = {}

        class _R:
            status_code = 200
            text = "{}"
            headers = {"content-type": "application/json"}

            def json(self):
                return {}

        def _fake_request(method, url, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}
            return _R()

        monkeypatch.setattr(catalyst_cli.requests, "request", _fake_request)
        catalyst_cli._call("GET", "/health")

    token = captured["headers"].get("x-catalyst-identity-url")
    assert token, (
        f"client-side presigned-sts must attach x-catalyst-identity-url; "
        f"saw: {sorted(captured['headers'])}"
    )
    parsed = urlparse(token)
    assert parsed.scheme == "https"
    qs = parse_qs(parsed.query)
    # The URL is a real presigned STS GetCallerIdentity URL.
    assert qs.get("Action") == ["GetCallerIdentity"]
    for required in ("X-Amz-Algorithm", "X-Amz-Credential", "X-Amz-Date", "X-Amz-Signature"):
        assert required in qs, f"missing SigV4 param: {required}"


def test_server_side_sigv4_mode_resolves_groups_via_state_seams(monkeypatch, mode):
    """Server side: ``CATALYST_AUTH_MODE=sigv4`` + ``x-catalyst-identity-url``.

    Drives the full ``access_dependency`` pipeline via the FastAPI
    ``app.state.identity_verifier`` / ``app.state.group_lookup`` seams
    (the same hook ``tests/test_rbac_sigv4.py`` uses). Asserts that a
    well-formed presigned-URL header gets resolved into an
    administrator role and authorises a ``GET /orgs/{tenant}``.
    """

    _skip_live(mode)

    # Lazy imports so live-mode collection doesn't drag in the API package
    # when CATALYST_E2E_LIVE=1 (in that case the journey is skipped).
    from fastapi.testclient import TestClient

    from catalyst import settings as settings_module
    from catalyst.identity import CallerIdentity
    from catalyst.main import app
    from catalyst.rbac import _clear_cache
    from catalyst.repository import InMemoryRepository, set_repository

    monkeypatch.setenv("CATALYST_AUTH_MODE", "sigv4")
    settings_module.reset_settings()
    set_repository(InMemoryRepository())
    _clear_cache()

    app.state.identity_verifier = lambda url: CallerIdentity(
        arn="arn:aws:iam::123456789012:user/alice",
        account="123456789012",
        user_id="AIDA",
    )
    app.state.group_lookup = lambda arn: ["catalyst-administrators"]
    try:
        local_client = TestClient(app)
        response = local_client.get(
            "/orgs/cloud-byte",
            headers={
                "x-catalyst-identity-url": (
                    "https://sts.us-west-2.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15"
                ),
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["tenant"] == "cloud-byte"
    finally:
        app.state.identity_verifier = None
        app.state.group_lookup = None
        settings_module.reset_settings()


def test_server_side_sigv4_mode_rejects_missing_identity_url_with_401(
    monkeypatch, mode
):
    """Server side: ``CATALYST_AUTH_MODE=sigv4`` + no identity header → 401.

    This is the 401 path the journey-05 sub-case 5 docstring references.
    A 401 (not a 403) preserves the unauthenticated-vs-unauthorised
    distinction operators rely on when triaging CloudWatch logs.
    """

    _skip_live(mode)

    from fastapi.testclient import TestClient

    from catalyst import settings as settings_module
    from catalyst.main import app
    from catalyst.rbac import _clear_cache
    from catalyst.repository import InMemoryRepository, set_repository

    monkeypatch.setenv("CATALYST_AUTH_MODE", "sigv4")
    settings_module.reset_settings()
    set_repository(InMemoryRepository())
    _clear_cache()
    try:
        local_client = TestClient(app)
        # No ``x-catalyst-identity-url`` header.
        response = local_client.get("/orgs/cloud-byte")
        assert response.status_code == 401, response.text
        assert "x-catalyst-identity-url" in response.json()["detail"]
    finally:
        settings_module.reset_settings()
