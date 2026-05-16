"""End-to-end tests for the SigV4 RBAC path through the FastAPI app.

The presigned-URL is mocked through the FastAPI ``app.state`` test seam so we
exercise the full request -> dependency -> identity -> group resolution
pipeline without standing up STS or IAM.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from catalyst.identity import CallerIdentity
from catalyst.main import app
from catalyst.rbac import _clear_cache
from catalyst.repository import InMemoryRepository, set_repository
from catalyst import settings as settings_module


@pytest.fixture(autouse=True)
def _wire_sigv4_mode(monkeypatch: pytest.MonkeyPatch) -> "object":
    monkeypatch.setenv("CATALYST_AUTH_MODE", "sigv4")
    settings_module.reset_settings()
    set_repository(InMemoryRepository())
    _clear_cache()
    app.state.identity_verifier = lambda url: CallerIdentity(
        arn="arn:aws:iam::123456789012:user/alice", account="123456789012", user_id="AIDA"
    )
    app.state.group_lookup = lambda arn: ["catalyst-administrators"]
    yield
    settings_module.reset_settings()
    app.state.identity_verifier = None
    app.state.group_lookup = None


def _client() -> TestClient:
    return TestClient(app)


def test_sigv4_path_authorises_with_admin_group() -> None:
    response = _client().get(
        "/orgs/cloud-byte",
        headers={"x-catalyst-identity-url": "https://sts.us-west-2.amazonaws.com/?x=1"},
    )
    assert response.status_code == 200


def test_sigv4_path_rejects_missing_url() -> None:
    response = _client().get("/orgs/cloud-byte")
    assert response.status_code == 401
    assert "x-catalyst-identity-url" in response.json()["detail"]


def test_sigv4_path_rejects_failed_verification() -> None:
    def boom(url: str) -> CallerIdentity:
        raise RuntimeError("expired signature")

    app.state.identity_verifier = boom
    response = _client().get(
        "/orgs/cloud-byte",
        headers={"x-catalyst-identity-url": "https://sts.us-west-2.amazonaws.com/?x=1"},
    )
    assert response.status_code == 401
    assert "identity_verification_failed" in response.json()["detail"]


def test_sigv4_path_rejects_failed_group_lookup() -> None:
    def boom(arn: str) -> list[str]:
        raise RuntimeError("AccessDenied")

    app.state.group_lookup = boom
    response = _client().get(
        "/orgs/cloud-byte",
        headers={"x-catalyst-identity-url": "https://sts.us-west-2.amazonaws.com/?x=1"},
    )
    assert response.status_code == 500
    assert "group_lookup_failed" in response.json()["detail"]


def test_sigv4_path_caches_group_lookup_per_caller() -> None:
    calls: list[str] = []

    def counting_lookup(arn: str) -> list[str]:
        calls.append(arn)
        return ["catalyst-administrators"]

    app.state.group_lookup = counting_lookup

    headers = {"x-catalyst-identity-url": "https://sts.us-west-2.amazonaws.com/?x=1"}
    for _ in range(3):
        assert _client().get("/orgs/cloud-byte", headers=headers).status_code == 200

    assert len(calls) == 1


def test_sigv4_path_with_no_groups_returns_403_on_writes() -> None:
    app.state.group_lookup = lambda arn: []
    response = _client().post(
        "/orgs/cloud-byte/environments",
        json={"tenant": "cloud-byte", "name": "prod"},
        headers={"x-catalyst-identity-url": "https://sts.us-west-2.amazonaws.com/?x=1"},
    )
    assert response.status_code == 403
