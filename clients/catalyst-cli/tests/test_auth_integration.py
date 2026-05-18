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
