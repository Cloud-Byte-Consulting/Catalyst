"""IAM-authenticated Aurora Serverless v2 (PostgreSQL) client (#229 / ADR-019).

This module is the application-side counterpart to ``modules/aurora-serverless``.
It holds a small repository class (:class:`RDSRepository`) that:

* Generates a fresh RDS IAM auth token on EVERY connection via
  ``boto3.client('rds').generate_db_auth_token(...)``. Tokens are valid for
  15 minutes; we deliberately do NOT cache them — the catalyst-api runs in
  a stateless Lambda / short-lived ECS context where a cached token cannot
  be reliably invalidated on rotation events. Per-connection generation is
  the simpler, safer default; if a real load profile motivates pooling
  later it becomes an explicit follow-up (documented in ADR-019).
* Opens a TLS-required ``psycopg`` connection using the auth token as the
  password (``sslmode='require'``). The connection is returned as a
  context manager so callers can compose it with ``with`` blocks; the
  connection is closed deterministically on context exit.
* Implements three methods:

    * :meth:`record_deployment`  — INSERT a row into the
      ``deployment_history`` table created by the cluster bootstrap. Called
      from ``products.deploy_product`` as a best-effort dual-write AFTER
      the DynamoDB write succeeds; failures here are logged + emit a
      ``RDSWriteFailure`` metric but do NOT roll back DynamoDB.
    * :meth:`list_deployments`   — SELECT with optional ``product_id`` and
      ``tenant`` filters. The tenant filter mirrors the existing RBAC
      tenant-scoping contract from :func:`catalyst.rbac.can_read_scope`:
      callers without a tenant-wide role only see rows for their own
      tenant.
    * :meth:`health_check`       — ``SELECT 1`` against the cluster;
      returns False on any exception (used by :func:`catalyst.main.health`
      to surface DB connectivity to liveness probes).

The repository takes its config via the constructor (no env-var reads)
so unit tests can spin one up against a mock without touching the
process environment. The companion factory :func:`get_rds_repository`
reads ``CATALYST_AURORA_*`` env vars and is mocked in tests via
:func:`set_rds_repository`.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL statements.
#
# Kept as module-level constants so unit tests can assert on the exact
# string sent to psycopg's ``cursor.execute``. The schema mirrors the
# bootstrap script in ``modules/aurora-serverless/bootstrap.sql.tftpl``:
#
#   deployment_history (
#       deployment_id      TEXT PRIMARY KEY,
#       product_id         TEXT,
#       tenant             TEXT,
#       construct_address  TEXT,
#       caller_arn         TEXT,
#       created_at         TIMESTAMPTZ
#   )
# ---------------------------------------------------------------------------

_INSERT_DEPLOYMENT_SQL = (
    "INSERT INTO deployment_history "
    "(deployment_id, product_id, tenant, construct_address, caller_arn) "
    "VALUES (%s, %s, %s, %s, %s)"
)

_SELECT_DEPLOYMENTS_BASE = (
    "SELECT deployment_id, product_id, tenant, construct_address, "
    "caller_arn, created_at FROM deployment_history"
)

_SELECT_ORDER_BY = " ORDER BY created_at DESC"

_HEALTH_CHECK_SQL = "SELECT 1"


class RDSRepository:
    """IAM-auth PostgreSQL repository for deployment history.

    Parameters
    ----------
    cluster_endpoint:
        Aurora cluster writer endpoint hostname (output
        ``aurora_cluster_endpoint`` from the composite).
    region:
        AWS region for the RDS IAM auth-token signer. Required because
        ``generate_db_auth_token`` signs the request with a region-specific
        SigV4; signing in the wrong region yields a token AWS will reject.
    port:
        PostgreSQL port; default 5432.
    db_name:
        Database name; default ``catalyst``.
    db_user:
        PostgreSQL role mapped to IAM auth; default ``catalyst_app``.
    boto3_client:
        Optional pre-built boto3 RDS client (test seam). When None, a
        client is lazily constructed on first :meth:`_get_auth_token`.
    psycopg_connect:
        Optional callable matching ``psycopg.connect`` (test seam). When
        None, the real ``psycopg.connect`` is imported lazily.
    """

    def __init__(
        self,
        cluster_endpoint: str,
        region: str,
        *,
        port: int = 5432,
        db_name: str = "catalyst",
        db_user: str = "catalyst_app",
        boto3_client: Any | None = None,
        psycopg_connect: Any | None = None,
    ) -> None:
        if not cluster_endpoint:
            raise ValueError("cluster_endpoint is required")
        if not region:
            raise ValueError("region is required")
        self._cluster_endpoint = cluster_endpoint
        self._region = region
        self._port = port
        self._db_name = db_name
        self._db_user = db_user
        self._boto3_client = boto3_client
        self._psycopg_connect = psycopg_connect

    # ----- internal helpers -------------------------------------------------

    def _rds_client(self) -> Any:
        """Return the boto3 RDS client, creating on first access.

        Lazy so importing this module doesn't pull boto3 into the import
        path; tests inject a fake via the constructor.
        """

        if self._boto3_client is None:
            import boto3

            self._boto3_client = boto3.client("rds", region_name=self._region)
        return self._boto3_client

    def _connect_fn(self) -> Any:
        """Return the ``psycopg.connect`` callable (or the test override)."""

        if self._psycopg_connect is not None:
            return self._psycopg_connect
        import psycopg  # imported lazily so the module import is cheap

        return psycopg.connect

    def _get_auth_token(self) -> str:
        """Generate a fresh RDS IAM auth token.

        Called on EVERY :meth:`_get_connection` (no caching) — see module
        docstring for the rationale. The token is a signed URL whose
        body, when passed as the PostgreSQL password, authenticates the
        connection as ``self._db_user`` if (and only if) the caller's
        IAM identity has ``rds-db:connect`` for the matching dbuser ARN.
        """

        return self._rds_client().generate_db_auth_token(
            DBHostname=self._cluster_endpoint,
            Port=self._port,
            DBUsername=self._db_user,
            Region=self._region,
        )

    @contextmanager
    def _get_connection(self) -> Iterator[Any]:
        """Open a TLS-required connection using a fresh auth token.

        Yields the psycopg connection; closes deterministically on
        context exit (even on exception). Caller wraps individual
        statements in their own try/except — this helper deliberately
        does NOT swallow errors so a connection-time failure surfaces
        to the boundary handler.
        """

        token = self._get_auth_token()
        connect = self._connect_fn()
        conn = connect(
            host=self._cluster_endpoint,
            port=self._port,
            dbname=self._db_name,
            user=self._db_user,
            password=token,
            sslmode="require",
        )
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - close errors are non-fatal
                logger.warning("rds_connection_close_failed", exc_info=True)

    # ----- public methods ---------------------------------------------------

    def record_deployment(
        self,
        *,
        deployment_id: str,
        product_id: str,
        tenant: str,
        construct_address: str,
        caller_arn: str,
    ) -> None:
        """INSERT a deployment row.

        Raises on any psycopg error so :mod:`catalyst.products` can decide
        whether to roll back its own state (it doesn't — DynamoDB stays
        the source of truth; see ADR-019 §Dual-write).
        """

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_DEPLOYMENT_SQL,
                    (
                        deployment_id,
                        product_id,
                        tenant,
                        construct_address,
                        caller_arn,
                    ),
                )
            conn.commit()

    def list_deployments(
        self,
        *,
        product_id: str | None = None,
        tenant: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """SELECT deployment rows with optional filters.

        Tenant-scoping is the caller's responsibility — the FastAPI
        handler in :mod:`catalyst.main` resolves the caller's
        :class:`catalyst.rbac.AccessContext` and forwards ``tenant`` only
        when the caller is tenant-scoped (per
        :func:`catalyst.rbac.can_read_scope`). When the caller is a
        tenant-wide role (owner / administrator / viewer) the handler
        forwards ``tenant=None`` and the full list is returned.

        Parameters
        ----------
        product_id:
            Optional product filter (e.g. ``catalyst-api``).
        tenant:
            Optional tenant filter; the handler enforces RBAC.
        limit:
            Hard upper bound on rows returned (defaults to 100). Prevents
            an unbounded SELECT from blowing memory.
        """

        clauses: list[str] = []
        params: list[Any] = []
        if product_id is not None:
            clauses.append("product_id = %s")
            params.append(product_id)
        if tenant is not None:
            clauses.append("tenant = %s")
            params.append(tenant)

        sql = _SELECT_DEPLOYMENTS_BASE
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += _SELECT_ORDER_BY + " LIMIT %s"
        params.append(limit)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()

        return [
            {
                "deployment_id": row[0],
                "product_id": row[1],
                "tenant": row[2],
                "construct_address": row[3],
                "caller_arn": row[4],
                "created_at": row[5].isoformat() if row[5] is not None else None,
            }
            for row in rows
        ]

    def health_check(self) -> bool:
        """Run ``SELECT 1`` against the cluster.

        Returns True iff the query succeeds. Any exception (connection,
        auth-token, TLS, query) returns False — the caller (the ``/health``
        endpoint) treats this as a soft signal, not a hard failure.
        """

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(_HEALTH_CHECK_SQL)
                    cur.fetchone()
            return True
        except Exception as exc:  # noqa: BLE001 - health probe MUST NOT raise
            logger.warning(
                "rds_health_check_failed",
                extra={"error_class": type(exc).__name__},
            )
            return False


# ---------------------------------------------------------------------------
# Process-wide repository singleton + test seams.
#
# Production: :func:`get_rds_repository` reads CATALYST_AURORA_ENDPOINT /
# CATALYST_AURORA_REGION / CATALYST_AURORA_DB_NAME / CATALYST_AURORA_DB_USER
# (only the first two are required) and constructs the repository on first
# call. Subsequent calls return the cached instance.
#
# Tests: :func:`set_rds_repository` replaces the cache with a mock and
# :func:`reset_rds_repository` drops the cache so the next call re-resolves.
# ---------------------------------------------------------------------------

_repo_singleton: RDSRepository | None = None


def get_rds_repository() -> RDSRepository | None:
    """Return the process-wide :class:`RDSRepository`, or None when unwired.

    The repository is OPT-IN: callers that haven't enabled Aurora
    (``CATALYST_AURORA_ENDPOINT`` unset) get ``None``, and consumers like
    the dual-write path in :mod:`catalyst.products` short-circuit
    gracefully. This is the runtime mirror of the Terraform-side
    ``enable_aurora_serverless`` opt-in.
    """

    global _repo_singleton
    if _repo_singleton is not None:
        return _repo_singleton

    import os

    endpoint = os.environ.get("CATALYST_AURORA_ENDPOINT", "").strip()
    region = os.environ.get("CATALYST_AURORA_REGION", "").strip()
    if not endpoint or not region:
        return None

    db_name = os.environ.get("CATALYST_AURORA_DB_NAME", "catalyst").strip() or "catalyst"
    db_user = (
        os.environ.get("CATALYST_AURORA_DB_USER", "catalyst_app").strip()
        or "catalyst_app"
    )

    _repo_singleton = RDSRepository(
        cluster_endpoint=endpoint,
        region=region,
        db_name=db_name,
        db_user=db_user,
    )
    return _repo_singleton


def set_rds_repository(repository: RDSRepository | None) -> None:
    """Override the process-wide repository (test seam)."""

    global _repo_singleton
    _repo_singleton = repository


def reset_rds_repository() -> None:
    """Drop the cached repository so the next ``get_rds_repository`` re-resolves."""

    global _repo_singleton
    _repo_singleton = None
