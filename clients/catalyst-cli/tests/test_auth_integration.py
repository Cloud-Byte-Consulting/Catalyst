"""Integration tests for the Catalyst CLI auth flow under moto-mocked AWS.

Covers issue #156 (CLI-TEST-moto): exercise the real boto3 STS interaction
without touching live AWS. Validates the presigned URL pattern documented
in ADR-008 + ``services/catalyst-api/catalyst/identity.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

CLI_DIR = Path(__file__).resolve().parent.parent
if str(CLI_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_DIR))

# moto is opt-in (declared in requirements-dev.txt). Skip the module cleanly
# if it isn't installed — keeps the suite green for slim install paths.
moto = pytest.importorskip("moto")
mock_aws = moto.mock_aws

import catalyst_cli  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.setenv("CATALYST_AUTH", "presigned-sts")
    monkeypatch.setenv("CATALYST_API_ENDPOINT", "http://test.local")
    monkeypatch.delenv("CATALYST_PRESIGNED_STS_URL", raising=False)


@mock_aws
def test_generate_presigned_sts_url_returns_signed_url(aws_credentials):
    """The helper produces a URL signed against sts.amazonaws.com with the
    GetCallerIdentity action and the four expected SigV4 query params.
    """
    url = catalyst_cli.generate_presigned_sts_url()
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "sts.amazonaws.com" or parsed.netloc.startswith("sts.")
    qs = parse_qs(parsed.query)
    assert qs.get("Action") == ["GetCallerIdentity"]
    for required in ("X-Amz-Algorithm", "X-Amz-Credential", "X-Amz-Date", "X-Amz-Signature"):
        assert required in qs, f"missing SigV4 param: {required}"


@mock_aws
def test_generate_presigned_sts_url_honors_expires_in(aws_credentials):
    """`ExpiresIn` round-trips into the X-Amz-Expires query parameter."""
    url = catalyst_cli.generate_presigned_sts_url(expires_in=120)
    qs = parse_qs(urlparse(url).query)
    assert qs.get("X-Amz-Expires") == ["120"]


@mock_aws
def test_generate_presigned_sts_url_uses_region(monkeypatch, aws_credentials):
    """Explicit region is passed to the boto3 STS client.

    We don't assert on the URL's credential scope here: STS global endpoint
    (sts.amazonaws.com) always signs with us-east-1 regardless of
    region_name. The test verifies our helper *forwards* the region to
    boto3 — boto3's signing behavior is upstream and not our contract.
    """
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    captured_region: dict = {}
    import boto3
    real_client = boto3.Session.client

    def _spy_client(self, service_name, **kwargs):
        if service_name == "sts":
            captured_region["region"] = kwargs.get("region_name")
        return real_client(self, service_name, **kwargs)

    monkeypatch.setattr(boto3.Session, "client", _spy_client)
    url = catalyst_cli.generate_presigned_sts_url(region="eu-west-1")
    assert captured_region.get("region") == "eu-west-1", (
        f"helper should forward explicit region to boto3.client(); "
        f"got region_name={captured_region.get('region')!r}"
    )
    # URL itself is still well-formed.
    assert url.startswith("https://"), url


def test_generate_presigned_sts_url_errors_when_no_credentials(monkeypatch):
    """No AWS creds + no env-supplied URL → SystemExit with a clear message
    rather than a silent unauthenticated request.
    """
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
              "AWS_PROFILE", "AWS_DEFAULT_REGION", "AWS_REGION"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(
        "boto3.Session.get_credentials",
        lambda self: None,
    )
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.generate_presigned_sts_url()
    assert "no AWS credentials" in str(exc.value)


@mock_aws
def test_call_attaches_presigned_url_header(monkeypatch, aws_credentials):
    """End-to-end: when presigned-sts is selected and AWS creds are available,
    ``_call`` auto-generates the URL and attaches it under the
    ``x-catalyst-identity-url`` header (canonical name per rbac.py:153).
    """
    captured: dict = {}

    class _R:
        status_code = 200
        text = "{}"
        headers = {"content-type": "application/json"}

        def json(self):
            return {}

    def _fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = kwargs.get("headers") or {}
        return _R()

    monkeypatch.setattr(catalyst_cli.requests, "request", _fake_request)
    catalyst_cli._call("GET", "/health")
    headers = captured["headers"]
    assert "x-catalyst-identity-url" in headers, (
        f"expected x-catalyst-identity-url header (matches rbac.py:153); "
        f"got headers={headers!r}"
    )
    token = headers["x-catalyst-identity-url"]
    parsed = urlparse(token)
    assert parsed.scheme == "https"
    qs = parse_qs(parsed.query)
    assert qs.get("Action") == ["GetCallerIdentity"]


@mock_aws
def test_sigv4_build_auth_returns_aws4auth(monkeypatch, aws_credentials):
    """When CATALYST_AUTH=sigv4, _build_auth() resolves credentials via boto3
    and returns a requests_aws4auth.AWS4Auth signer (used by requests).
    """
    monkeypatch.setenv("CATALYST_AUTH", "sigv4")
    from requests_aws4auth import AWS4Auth
    auth = catalyst_cli._build_auth()
    assert isinstance(auth, AWS4Auth)
    # AWS4Auth exposes the service and region it was bound to.
    assert auth.service == "execute-api"
    assert auth.region == "us-east-1"


def test_sigv4_build_auth_raises_without_credentials(monkeypatch):
    """No AWS creds + sigv4 strategy → SystemExit, never silently no-auth."""
    monkeypatch.setenv("CATALYST_AUTH", "sigv4")
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
              "AWS_PROFILE", "AWS_DEFAULT_REGION", "AWS_REGION"):
        monkeypatch.delenv(k, raising=False)
    import boto3
    monkeypatch.setattr(boto3.Session, "get_credentials", lambda self: None)
    with pytest.raises(SystemExit) as exc:
        catalyst_cli._build_auth()
    assert "no AWS credentials" in str(exc.value)


@mock_aws
def test_sigv4_build_auth_uses_aws_region_env_fallback(monkeypatch, aws_credentials):
    """When session has no region, AWS_REGION env is the fallback."""
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setenv("CATALYST_AUTH", "sigv4")
    # Force session.region_name to None so the env fallback is exercised.
    import boto3
    monkeypatch.setattr(
        boto3.Session, "region_name", property(lambda self: None)
    )
    auth = catalyst_cli._build_auth()
    assert auth.region == "ap-southeast-2"


def test_call_returns_raw_text_for_non_json_response(monkeypatch):
    """Non-JSON response (e.g. text/plain health probe) returns {"raw": text}
    instead of attempting json() parse.
    """
    monkeypatch.setenv("CATALYST_AUTH", "none")

    class _R:
        status_code = 200
        text = "OK"
        headers = {"content-type": "text/plain"}

        def json(self):  # pragma: no cover - must not be called
            raise AssertionError("json() should not be called for text/plain")

    monkeypatch.setattr(catalyst_cli.requests, "request", lambda *a, **kw: _R())
    assert catalyst_cli._call("GET", "/health") == {"raw": "OK"}


def test_cli_main_invokes_command_through_knack(monkeypatch):
    """End-to-end smoke: cli_main wires the command table and dispatches to
    health_command via knack. We monkeypatch _call to keep the test offline.
    """
    monkeypatch.setenv("CATALYST_AUTH", "none")
    monkeypatch.setenv("CATALYST_API_ENDPOINT", "http://test.local")
    calls: list[tuple[str, str]] = []

    def _fake_call(method, path, *, json_body=None):
        calls.append((method, path))
        return {"status": "ok"}

    monkeypatch.setattr(catalyst_cli, "_call", _fake_call)
    rc = catalyst_cli.cli_main(["health", "check"])
    assert rc == 0
    assert ("GET", "/health") in calls


@mock_aws
def test_orgs_landing_zones_create_attaches_presigned_url_header(monkeypatch, aws_credentials):
    """Tier 1 orgs commands (#169) flow through the same _call seam as Tier 2,
    so the auto-generated x-catalyst-identity-url header should be attached
    on outbound POST requests when CATALYST_AUTH=presigned-sts.
    """
    captured: dict = {}

    class _R:
        status_code = 201
        text = '{"landing_zone_id":"lz-1","construct_address":"cloud-byte/shared"}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"landing_zone_id": "lz-1", "construct_address": "cloud-byte/shared"}

    def _fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = kwargs.get("headers") or {}
        captured["json_body"] = kwargs.get("json")
        return _R()

    monkeypatch.setattr(catalyst_cli.requests, "request", _fake_request)
    catalyst_cli.orgs_landing_zones_create_command(
        tenant="cloud-byte",
        name="shared",
        account_id="061051223073",
        compliance="standard",
        idempotency_key="lz-integration-001",
    )
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/orgs/cloud-byte/landing-zones")
    assert "x-catalyst-identity-url" in captured["headers"], (
        f"expected x-catalyst-identity-url header (matches rbac.py:153); "
        f"got headers={captured['headers']!r}"
    )
    token = captured["headers"]["x-catalyst-identity-url"]
    assert urlparse(token).scheme == "https"
    qs = parse_qs(urlparse(token).query)
    assert qs.get("Action") == ["GetCallerIdentity"]
    # Body sanity-check — confirms the command serialized correctly.
    assert captured["json_body"]["tenant"] == "cloud-byte"
    assert captured["json_body"]["compliance"] == "standard"
    assert captured["json_body"]["idempotency_key"] == "lz-integration-001"


@mock_aws
def test_call_respects_env_supplied_url(monkeypatch, aws_credentials):
    """When CATALYST_PRESIGNED_STS_URL is set explicitly, the CLI forwards it
    verbatim — does not regenerate. Useful when the caller has already
    generated a URL out-of-band (e.g. from a workflow secret).
    """
    explicit = "https://sts.amazonaws.com/?Action=GetCallerIdentity&pre=baked"
    monkeypatch.setenv("CATALYST_PRESIGNED_STS_URL", explicit)
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
    assert captured["headers"].get("x-catalyst-identity-url") == explicit
