"""Tests for GET /deployment-history (#229 / ADR-019).

The endpoint reads from Aurora via :class:`RDSRepository`; tests mock
the repo dependency through FastAPI's :attr:`app.dependency_overrides`
so the test surface never touches real boto3 / psycopg / RDS.

Covered behaviours:

* 200 — happy path returns the rows the repo emits.
* 503 — RDSRepository unwired (CATALYST_AURORA_ENDPOINT unset) surfaces
  as 503 ``rds_unwired`` per the handler contract.
* RBAC — scoped callers get tenant-filtered server-side. A scoped
  caller asking for someone else's tenant is 403.
* Tenant-wide callers (owner / administrator / viewer) see everything
  (no implicit tenant filter).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from catalyst.main import app, rds_repo_dependency


client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(
    groups: str,
    caller: str = "arn:aws:iam::123456789012:user/x",
) -> dict[str, str]:
    return {"x-caller-arn": caller, "x-iam-groups": groups}


def _fake_repo(rows: list[dict] | None = None) -> MagicMock:
    """Build a MagicMock that quacks like RDSRepository for the endpoint path."""

    repo = MagicMock()
    repo.list_deployments.return_value = rows or []
    return repo


@pytest.fixture
def install_repo() -> Any:
    """Install a fake RDSRepository on app.dependency_overrides for the test."""

    repos: list[MagicMock] = []

    def _install(rows: list[dict] | None = None) -> MagicMock:
        repo = _fake_repo(rows=rows)
        app.dependency_overrides[rds_repo_dependency] = lambda: repo
        repos.append(repo)
        return repo

    yield _install

    app.dependency_overrides.pop(rds_repo_dependency, None)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_returns_503_when_rds_unwired() -> None:
    """No repo installed => the dependency returns None (env-unwired) => 503."""

    # Force the dependency to return None — simulates CATALYST_AURORA_ENDPOINT
    # unset in production.
    app.dependency_overrides[rds_repo_dependency] = lambda: None
    try:
        response = client.get(
            "/deployment-history",
            headers=_headers("catalyst-owners"),
        )
    finally:
        app.dependency_overrides.pop(rds_repo_dependency, None)

    assert response.status_code == 503
    body = response.json()
    # The errors.to_http_exception wrapper renders detail as the original
    # HTTPException.detail string; we substring-match because the wrapper
    # may decorate it (e.g. with correlation_id) but never strips the seed.
    assert "rds_unwired" in str(body)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_owner_sees_all_rows_no_tenant_filter(install_repo) -> None:
    rows = [
        {
            "deployment_id": "dep-1",
            "product_id": "catalyst-api",
            "tenant": "acme",
            "construct_address": "acme/dev/shared/p1/a1",
            "caller_arn": "arn:1",
            "created_at": "2026-05-18T12:00:00+00:00",
        },
        {
            "deployment_id": "dep-2",
            "product_id": "catalyst-api",
            "tenant": "globex",
            "construct_address": "globex/dev/shared/p1/a1",
            "caller_arn": "arn:2",
            "created_at": "2026-05-18T12:01:00+00:00",
        },
    ]
    repo = install_repo(rows=rows)

    response = client.get(
        "/deployment-history",
        headers=_headers("catalyst-owners"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["deployments"] == rows
    assert body["filters"]["tenant"] is None
    # Owner => no implicit tenant filter forwarded to the repo.
    repo.list_deployments.assert_called_once_with(
        product_id=None, tenant=None, limit=100
    )


def test_product_id_filter_forwards_to_repo(install_repo) -> None:
    repo = install_repo(rows=[])

    response = client.get(
        "/deployment-history?product_id=catalyst-api&limit=10",
        headers=_headers("catalyst-administrators"),
    )

    assert response.status_code == 200
    repo.list_deployments.assert_called_once_with(
        product_id="catalyst-api", tenant=None, limit=10
    )


# ---------------------------------------------------------------------------
# RBAC / tenant-scoping
# ---------------------------------------------------------------------------


def test_scoped_caller_gets_their_own_tenant_filter_implicitly(
    install_repo,
) -> None:
    """A scoped caller without an explicit ?tenant= still gets server-side filtering."""

    repo = install_repo(rows=[])

    response = client.get(
        "/deployment-history",
        headers=_headers("catalyst-acme--p1--admins"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filters"]["tenant"] == "acme"
    repo.list_deployments.assert_called_once_with(
        product_id=None, tenant="acme", limit=100
    )


def test_scoped_caller_cannot_query_other_tenant(install_repo) -> None:
    """An explicit tenant query that differs from the caller's scope => 403."""

    install_repo(rows=[])

    response = client.get(
        "/deployment-history?tenant=globex",
        headers=_headers("catalyst-acme--p1--admins"),
    )

    assert response.status_code == 403
    body = response.json()
    # FastAPI wraps the to_http_exception payload as {"detail": {...}};
    # the inner dict carries the canonical {error, correlation_id, detail}.
    inner = body["detail"]
    assert inner["detail"] == "insufficient_permissions"
    assert inner["error"] == "Forbidden"


def test_scoped_caller_explicit_same_tenant_allowed(install_repo) -> None:
    """Explicit ?tenant= matching the scope is OK."""

    repo = install_repo(rows=[])

    response = client.get(
        "/deployment-history?tenant=acme",
        headers=_headers("catalyst-acme--p1--admins"),
    )

    assert response.status_code == 200
    repo.list_deployments.assert_called_once_with(
        product_id=None, tenant="acme", limit=100
    )


def test_administrator_can_query_explicit_tenant(install_repo) -> None:
    """Tenant-wide roles can pass ?tenant= explicitly."""

    repo = install_repo(rows=[])

    response = client.get(
        "/deployment-history?tenant=acme",
        headers=_headers("catalyst-administrators"),
    )

    assert response.status_code == 200
    repo.list_deployments.assert_called_once_with(
        product_id=None, tenant="acme", limit=100
    )
