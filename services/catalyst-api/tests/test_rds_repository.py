"""Unit tests for :mod:`catalyst.rds_repository` (#229 / ADR-019).

Strategy: mock at the boto3 and psycopg boundaries — DO NOT use
testcontainers-postgres. The Decision Log on #229 explicitly rejected
Docker-in-CI for this surface; mocking the two boundaries is enough to
cover the SQL shape + token-rotation contract.

Coverage targets:

* Token generation — fresh token on EVERY :meth:`_get_connection` (no
  caching). Asserted by calling list_deployments twice and checking the
  boto3 mock got two calls.
* SQL shape — :meth:`record_deployment` issues the canonical INSERT with
  positional params in the documented order.
* SQL shape — :meth:`list_deployments` issues SELECT + ORDER BY +
  LIMIT, with optional WHERE clauses for product_id / tenant.
* Health check — returns True on success, False on
  ``psycopg.OperationalError``.
* Auth-token plumbing — the boto3 ``generate_db_auth_token`` is called
  with the configured DBHostname / Port / DBUsername / Region.
* TLS — the connect call includes ``sslmode="require"``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from catalyst.rds_repository import (
    RDSRepository,
    get_rds_repository,
    reset_rds_repository,
    set_rds_repository,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Minimal psycopg cursor double — records execute calls + canned rows."""

    def __init__(self, rows: list[tuple] | None = None) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._rows = rows or []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def fetchall(self) -> list[tuple]:
        return self._rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else (1,)

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_exc) -> None:
        return None


class _FakeConnection:
    """Minimal psycopg connection double — exposes cursor + commit/close."""

    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *_exc) -> None:
        return None


def _make_repo(
    *,
    rows: list[tuple] | None = None,
    connect_raises: Exception | None = None,
    token_value: str = "fake-iam-auth-token",
) -> tuple[RDSRepository, MagicMock, MagicMock, _FakeConnection]:
    """Build an RDSRepository with mocked boto3 + psycopg seams.

    Returns the repo plus the boto3 client mock, the psycopg.connect mock,
    and the fake connection — so tests can assert on call args/counts on
    any of the three.
    """

    cursor = _FakeCursor(rows=rows)
    conn = _FakeConnection(cursor)

    boto = MagicMock()
    boto.generate_db_auth_token.return_value = token_value

    connect = MagicMock()
    if connect_raises is not None:
        connect.side_effect = connect_raises
    else:
        connect.return_value = conn

    repo = RDSRepository(
        cluster_endpoint="aurora.example.amazonaws.com",
        region="us-west-2",
        boto3_client=boto,
        psycopg_connect=connect,
    )
    return repo, boto, connect, conn


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------


def test_auth_token_called_with_configured_inputs() -> None:
    """generate_db_auth_token is signed with the configured host/port/user/region."""

    repo, boto, _connect, _conn = _make_repo(rows=[(1,)])

    repo.health_check()

    boto.generate_db_auth_token.assert_called_once_with(
        DBHostname="aurora.example.amazonaws.com",
        Port=5432,
        DBUsername="catalyst_app",
        Region="us-west-2",
    )


def test_token_is_generated_per_connection_not_cached() -> None:
    """Two SELECTs => two token generations (no caching, per ADR-019)."""

    repo, boto, _connect, _conn = _make_repo(rows=[])

    repo.list_deployments()
    repo.list_deployments()

    assert boto.generate_db_auth_token.call_count == 2


# ---------------------------------------------------------------------------
# Connection plumbing
# ---------------------------------------------------------------------------


def test_connection_uses_sslmode_require_and_token_password() -> None:
    """psycopg.connect is called with sslmode='require' and the token as password."""

    repo, _boto, connect, _conn = _make_repo(rows=[])

    repo.list_deployments()

    connect.assert_called_once()
    kwargs = connect.call_args.kwargs
    assert kwargs["host"] == "aurora.example.amazonaws.com"
    assert kwargs["port"] == 5432
    assert kwargs["dbname"] == "catalyst"
    assert kwargs["user"] == "catalyst_app"
    assert kwargs["password"] == "fake-iam-auth-token"
    assert kwargs["sslmode"] == "require"


def test_connection_is_closed_even_on_inner_error() -> None:
    """The context manager closes the connection on the exception path too."""

    repo, _boto, _connect, conn = _make_repo(rows=[])
    # Force the cursor.execute to raise; the connection should still close.
    conn._cursor.execute = MagicMock(side_effect=RuntimeError("query exploded"))

    with pytest.raises(RuntimeError):
        repo.list_deployments()

    assert conn.closed is True


# ---------------------------------------------------------------------------
# record_deployment
# ---------------------------------------------------------------------------


def test_record_deployment_issues_canonical_insert() -> None:
    """The INSERT statement + positional params match the documented contract."""

    repo, _boto, _connect, conn = _make_repo()

    repo.record_deployment(
        deployment_id="dep-1",
        product_id="catalyst-api",
        tenant="acme",
        construct_address="acme/dev/shared/p1/a1",
        caller_arn="arn:aws:iam::123:user/x",
    )

    assert len(conn._cursor.executed) == 1
    sql, params = conn._cursor.executed[0]
    assert "INSERT INTO deployment_history" in sql
    assert "deployment_id, product_id, tenant, construct_address, caller_arn" in sql
    assert "VALUES (%s, %s, %s, %s, %s)" in sql
    assert params == (
        "dep-1",
        "catalyst-api",
        "acme",
        "acme/dev/shared/p1/a1",
        "arn:aws:iam::123:user/x",
    )
    assert conn.committed is True


# ---------------------------------------------------------------------------
# list_deployments — SQL shape + filtering
# ---------------------------------------------------------------------------


def test_list_deployments_no_filters_emits_base_select_with_limit() -> None:
    """No filters => SELECT ... FROM deployment_history ORDER BY created_at DESC LIMIT %s."""

    repo, _boto, _connect, conn = _make_repo(rows=[])

    repo.list_deployments(limit=42)

    sql, params = conn._cursor.executed[0]
    assert "SELECT deployment_id, product_id, tenant, construct_address" in sql
    assert "FROM deployment_history" in sql
    assert "WHERE" not in sql
    assert "ORDER BY created_at DESC" in sql
    assert "LIMIT %s" in sql
    assert params == (42,)


def test_list_deployments_with_product_id_filter() -> None:
    """product_id filter => WHERE product_id = %s clause + matching param."""

    repo, _boto, _connect, conn = _make_repo(rows=[])

    repo.list_deployments(product_id="catalyst-api")

    sql, params = conn._cursor.executed[0]
    assert "WHERE product_id = %s" in sql
    assert params == ("catalyst-api", 100)


def test_list_deployments_with_tenant_filter() -> None:
    """tenant filter => WHERE tenant = %s clause + matching param."""

    repo, _boto, _connect, conn = _make_repo(rows=[])

    repo.list_deployments(tenant="acme")

    sql, params = conn._cursor.executed[0]
    assert "WHERE tenant = %s" in sql
    assert params == ("acme", 100)


def test_list_deployments_with_both_filters_uses_and_clause() -> None:
    """Both filters => WHERE product_id = %s AND tenant = %s + both params."""

    repo, _boto, _connect, conn = _make_repo(rows=[])

    repo.list_deployments(product_id="catalyst-api", tenant="acme")

    sql, params = conn._cursor.executed[0]
    assert "WHERE product_id = %s AND tenant = %s" in sql
    assert params == ("catalyst-api", "acme", 100)


def test_list_deployments_returns_dict_rows_in_documented_shape() -> None:
    """The fetched rows are rendered as the documented per-row dict."""

    when = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)
    repo, _boto, _connect, _conn = _make_repo(
        rows=[
            ("dep-1", "catalyst-api", "acme", "acme/dev/shared/p1/a1", "arn:1", when),
        ]
    )

    rows = repo.list_deployments()

    assert rows == [
        {
            "deployment_id": "dep-1",
            "product_id": "catalyst-api",
            "tenant": "acme",
            "construct_address": "acme/dev/shared/p1/a1",
            "caller_arn": "arn:1",
            "created_at": "2026-05-18T12:00:00+00:00",
        }
    ]


def test_list_deployments_renders_null_created_at_as_none() -> None:
    """Defensive: a NULL created_at column does not blow up the renderer."""

    repo, _boto, _connect, _conn = _make_repo(
        rows=[("dep-2", "catalyst-api", "acme", "acme/dev/shared/p1/a1", "arn:1", None)]
    )

    rows = repo.list_deployments()

    assert rows[0]["created_at"] is None


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


def test_health_check_returns_true_on_success() -> None:
    repo, _boto, _connect, _conn = _make_repo(rows=[(1,)])

    assert repo.health_check() is True


def test_health_check_returns_false_on_connect_error() -> None:
    """Connection failure (psycopg.OperationalError) returns False, not raise."""

    repo, _boto, _connect, _conn = _make_repo(
        connect_raises=RuntimeError("simulated psycopg.OperationalError")
    )

    assert repo.health_check() is False


def test_health_check_returns_false_on_query_error() -> None:
    """A cursor.execute failure returns False as well — both branches matter."""

    repo, _boto, _connect, conn = _make_repo()
    conn._cursor.execute = MagicMock(side_effect=RuntimeError("query failed"))

    assert repo.health_check() is False


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_constructor_requires_endpoint() -> None:
    with pytest.raises(ValueError, match="cluster_endpoint is required"):
        RDSRepository(cluster_endpoint="", region="us-west-2")


def test_constructor_requires_region() -> None:
    with pytest.raises(ValueError, match="region is required"):
        RDSRepository(cluster_endpoint="aurora.example.com", region="")


# ---------------------------------------------------------------------------
# Module-level cache / factory
# ---------------------------------------------------------------------------


def test_get_rds_repository_returns_none_when_env_unwired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No CATALYST_AURORA_ENDPOINT => None (OPT-IN semantics)."""

    reset_rds_repository()
    monkeypatch.delenv("CATALYST_AURORA_ENDPOINT", raising=False)
    monkeypatch.delenv("CATALYST_AURORA_REGION", raising=False)

    assert get_rds_repository() is None


def test_get_rds_repository_resolves_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env vars set => factory constructs a real RDSRepository instance."""

    reset_rds_repository()
    monkeypatch.setenv("CATALYST_AURORA_ENDPOINT", "aurora.example.amazonaws.com")
    monkeypatch.setenv("CATALYST_AURORA_REGION", "us-west-2")

    repo = get_rds_repository()
    try:
        assert isinstance(repo, RDSRepository)
        assert repo._cluster_endpoint == "aurora.example.amazonaws.com"
        assert repo._region == "us-west-2"
        assert repo._db_name == "catalyst"
        assert repo._db_user == "catalyst_app"
    finally:
        reset_rds_repository()


def test_set_rds_repository_overrides_singleton() -> None:
    """The test-seam override replaces the cached repo."""

    sentinel = RDSRepository(
        cluster_endpoint="x", region="us-west-2", boto3_client=MagicMock(),
        psycopg_connect=MagicMock(),
    )
    set_rds_repository(sentinel)
    try:
        assert get_rds_repository() is sentinel
    finally:
        reset_rds_repository()


# ---------------------------------------------------------------------------
# Dual-write contract (products._dual_write_rds)
#
# DynamoDB is the source of truth; the RDS write is best-effort and MUST NOT
# raise (per ADR-019 §Dual-write). These tests exercise the helper directly
# so the failure-handling branches are covered without driving the full
# /products/catalog/{id}/deploy path.
# ---------------------------------------------------------------------------


def test_dual_write_no_op_when_repo_unwired() -> None:
    """When get_rds_repository returns None, the helper is a silent no-op."""

    from catalyst import products as products_module

    set_rds_repository(None)
    try:
        # Should NOT raise even with no repo configured.
        products_module._dual_write_rds(
            product_id="catalyst-api",
            deployment_id="dep-1",
            construct_address="acme/dev/shared/p1/a1",
            tenant="acme",
            caller_arn="arn:1",
            correlation_id="cid-1",
        )
    finally:
        reset_rds_repository()


def test_dual_write_swallows_repo_failure() -> None:
    """A raising record_deployment is logged + swallowed (no exception leaks)."""

    from catalyst import products as products_module

    fake = MagicMock(spec=RDSRepository)
    fake.record_deployment.side_effect = RuntimeError("boom")
    set_rds_repository(fake)
    try:
        # MUST NOT raise — DynamoDB write is the source of truth.
        products_module._dual_write_rds(
            product_id="catalyst-api",
            deployment_id="dep-1",
            construct_address="acme/dev/shared/p1/a1",
            tenant="acme",
            caller_arn="arn:1",
            correlation_id="cid-1",
        )
        # The repo was called with the right args even though it raised.
        fake.record_deployment.assert_called_once_with(
            deployment_id="dep-1",
            product_id="catalyst-api",
            tenant="acme",
            construct_address="acme/dev/shared/p1/a1",
            caller_arn="arn:1",
        )
    finally:
        reset_rds_repository()


def test_dual_write_happy_path_forwards_args() -> None:
    """Happy path: repo.record_deployment is called with the documented kwargs."""

    from catalyst import products as products_module

    fake = MagicMock(spec=RDSRepository)
    set_rds_repository(fake)
    try:
        products_module._dual_write_rds(
            product_id="catalyst-api",
            deployment_id="dep-1",
            construct_address="acme/dev/shared/p1/a1",
            tenant="acme",
            caller_arn="arn:1",
            correlation_id="cid-1",
        )
        fake.record_deployment.assert_called_once_with(
            deployment_id="dep-1",
            product_id="catalyst-api",
            tenant="acme",
            construct_address="acme/dev/shared/p1/a1",
            caller_arn="arn:1",
        )
    finally:
        reset_rds_repository()
