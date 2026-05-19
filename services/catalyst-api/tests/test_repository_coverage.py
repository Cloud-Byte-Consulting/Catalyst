"""Coverage-completion tests for :mod:`catalyst.repository`.

These tests close the per-module gaps surfaced by the #40 coverage audit
that the existing :mod:`tests.test_repository_dynamodb` suite does not
exercise: product-catalog deployment writes/queries (#103 paths) on
DynamoDB, the ``_scan_pk_prefix`` pagination loop, attribute-passthrough
on ``append_org_record``, and the in-memory ``clear()`` / singleton
resolution surfaces.

The tests are behavior-oriented: each one asserts an observable outcome
(``get_*`` returns the expected payload, the audit row is written, the
singleton is replaced) rather than just running the code path.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from catalyst.repository import (
    DynamoDBRepository,
    InMemoryRepository,
    Repository,
    get_repository,
    reset_repository,
    set_repository,
)


TABLE = "catalyst-platform-state-cov"


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("AWS_REGION", "us-west-2")


@pytest.fixture
def ddb_table(aws_credentials: None):  # type: ignore[no-untyped-def]
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-west-2")
        client.create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        )
        client.get_waiter("table_exists").wait(TableName=TABLE)
        resource = boto3.resource("dynamodb", region_name="us-west-2")
        yield resource.Table(TABLE)


def _make_repo(table) -> DynamoDBRepository:  # type: ignore[no-untyped-def]
    return DynamoDBRepository(TABLE, table=table)


# -- DynamoDB product-deployment paths (#103) ------------------------------


def test_product_deployment_round_trip_with_idem_key(ddb_table) -> None:  # type: ignore[no-untyped-def]
    """record + lookup by deployment_id + lookup by idempotency key."""

    repo = _make_repo(ddb_table)
    repo.record_product_deployment(
        product_id="grafana",
        construct_address="acme/dev/shared/observability/grafana",
        deployment_id="dep-001",
        idempotency_key="idem-abc",
        payload={"status": "queued", "deployment_id": "dep-001"},
        created_at="2026-05-18T12:00:00Z",
    )

    # Direct lookup by deployment_id (scan path)
    record = repo.get_product_deployment("dep-001")
    assert record is not None
    assert record["product_id"] == "grafana"
    assert record["construct_address"] == "acme/dev/shared/observability/grafana"
    assert record["idempotency_key"] == "idem-abc"
    assert record["payload"] == {"status": "queued", "deployment_id": "dep-001"}

    # Replay lookup by idempotency key returns the cached payload verbatim.
    replay = repo.get_product_deployment_by_idem_key("idem-abc")
    assert replay == {"status": "queued", "deployment_id": "dep-001"}


def test_product_deployment_without_idem_key_skips_sidecar(ddb_table) -> None:  # type: ignore[no-untyped-def]
    """No idempotency key => no PRODDEP_IDEM# sidecar row gets written."""

    repo = _make_repo(ddb_table)
    repo.record_product_deployment(
        product_id="grafana",
        construct_address="acme/dev/shared/observability/grafana",
        deployment_id="dep-002",
        idempotency_key=None,
        payload={"status": "queued"},
        created_at="2026-05-18T13:00:00Z",
    )

    assert repo.get_product_deployment("dep-002") is not None
    # No idem key => replay lookup MUST return None even if we ask for the
    # empty string sentinel.
    assert repo.get_product_deployment_by_idem_key("") is None


def test_product_deployment_unknown_idem_key_is_none(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    assert repo.get_product_deployment_by_idem_key("never-seen") is None


def test_product_deployment_unknown_id_is_none(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    assert repo.get_product_deployment("never-recorded") is None


def test_list_product_deployments_returns_only_matching_product(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    for i, product in enumerate(("grafana", "grafana", "loki")):
        repo.record_product_deployment(
            product_id=product,
            construct_address=f"acme/dev/shared/obs/{product}",
            deployment_id=f"dep-{product}-{i}",
            idempotency_key=None,
            payload={"deployment_id": f"dep-{product}-{i}"},
            created_at=f"2026-05-18T1{i}:00:00Z",
        )

    grafana = repo.list_product_deployments("grafana")
    assert {r["deployment_id"] for r in grafana} == {"dep-grafana-0", "dep-grafana-1"}

    loki = repo.list_product_deployments("loki")
    assert len(loki) == 1 and loki[0]["product_id"] == "loki"

    # Unknown product -> empty list (not error)
    assert repo.list_product_deployments("tempo") == []


def test_scan_pk_prefix_paginates(ddb_table) -> None:  # type: ignore[no-untyped-def]
    """``_scan_pk_prefix`` keeps paginating until ``LastEvaluatedKey`` is absent.

    Moto returns everything in one page by default, so we drive the loop
    by wrapping the table's ``scan`` method to inject a synthetic
    ``LastEvaluatedKey`` exactly once.
    """

    repo = _make_repo(ddb_table)
    repo.put_product("k1", {"app": "ledger"})
    repo.put_product("k2", {"app": "invoices"})

    original_scan = repo._table.scan
    call_count = {"n": 0}

    def paginating_scan(**kwargs):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        response = original_scan(**kwargs)
        if call_count["n"] == 1:
            # Force a second iteration by claiming there's more data; the
            # second call will see ``ExclusiveStartKey`` and moto will
            # produce an empty page without ``LastEvaluatedKey``.
            response = dict(response)
            response["LastEvaluatedKey"] = {"pk": "PROD#k2", "sk": "INSTANCE"}
        return response

    repo._table.scan = paginating_scan  # type: ignore[method-assign]
    try:
        products = repo.list_products()
    finally:
        repo._table.scan = original_scan  # type: ignore[method-assign]

    assert call_count["n"] >= 2, "pagination loop must call scan more than once"
    assert {p["app"] for p in products} == {"ledger", "invoices"}


def test_append_org_record_passes_through_attributes(ddb_table) -> None:  # type: ignore[no-untyped-def]
    """Attribute pass-through with name/created_at injection-guard.

    The DynamoDB path mirrors the in-memory path: caller-supplied
    ``name``/``created_at`` keys are filtered so an attacker cannot
    rewrite the record header, but other fields are preserved verbatim.
    """

    repo = _make_repo(ddb_table)
    repo.append_org_record(
        "acme",
        "environments",
        "dev",
        attributes={
            "account_id": "111111111111",
            "region": "us-west-2",
            # These two MUST be filtered out -- the record's own
            # name/created_at wins.
            "name": "EVIL",
            "created_at": "1970-01-01T00:00:00Z",
        },
    )

    org = repo.get_organization("acme")
    [env] = org["environments"]
    assert env["name"] == "dev"
    assert env["created_at"] != "1970-01-01T00:00:00Z"
    assert env["account_id"] == "111111111111"
    assert env["region"] == "us-west-2"


def test_dynamodb_default_table_resource_path(aws_credentials: None) -> None:  # type: ignore[no-untyped-def]
    """When ``table=`` is omitted, the constructor falls back to
    ``boto3.resource('dynamodb')``. The mock_aws context ensures we don't
    hit real AWS even if the lazy import succeeds.
    """

    with mock_aws():
        # Create the table so the implicit resource has something to bind
        # to (the binding is lazy until first use, but exercising the
        # constructor is the goal here).
        client = boto3.client("dynamodb", region_name="us-west-2")
        client.create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        )
        client.get_waiter("table_exists").wait(TableName=TABLE)

        repo = DynamoDBRepository(TABLE)
        assert repo.table_name == TABLE
        # And it actually works end-to-end:
        repo.put_idempotent("ping", {"ok": True})
        assert repo.get_idempotent("ping") == {"ok": True}


# -- InMemoryRepository corner cases ---------------------------------------


def test_in_memory_clear_drops_every_collection() -> None:
    repo = InMemoryRepository()
    repo.put_idempotent("k", {"v": 1})
    repo.append_org_record("acme", "environments", "dev")
    repo.init_service("acme/dev/shared/p/a")
    repo.record_group_action("catalyst-owners", "add", "arn:aws:iam::1:user/x")
    repo.put_product("acme/p/a", {"app": "a"})
    repo.record_product_deployment(
        product_id="grafana",
        construct_address="acme/dev/shared/obs/grafana",
        deployment_id="dep-x",
        idempotency_key="i-x",
        payload={"status": "queued"},
        created_at="2026-05-18T00:00:00Z",
    )

    repo.clear()

    assert repo.get_idempotent("k") is None
    assert repo.get_organization("acme") == {}
    assert repo.get_service("acme/dev/shared/p/a") is None
    assert repo.list_group_actions("catalyst-owners") == []
    assert repo.list_products() == []
    assert repo.get_product_deployment("dep-x") is None
    assert repo.get_product_deployment_by_idem_key("i-x") is None
    assert repo.list_product_deployments("grafana") == []


def test_in_memory_product_deployment_isolates_payload_replay() -> None:
    repo = InMemoryRepository()
    repo.record_product_deployment(
        product_id="grafana",
        construct_address="acme/dev/shared/obs/grafana",
        deployment_id="dep-1",
        idempotency_key="idem-1",
        payload={"status": "queued"},
        created_at="2026-05-18T00:00:00Z",
    )
    # The idem-keyed lookup returns the cached payload directly (NOT the
    # full record envelope) so the replay path can echo what the caller
    # saw the first time.
    assert repo.get_product_deployment_by_idem_key("idem-1") == {"status": "queued"}
    # Without an idem key the sidecar is not written.
    repo.record_product_deployment(
        product_id="grafana",
        construct_address="acme/dev/shared/obs/grafana",
        deployment_id="dep-2",
        idempotency_key=None,
        payload={"status": "queued"},
        created_at="2026-05-18T01:00:00Z",
    )
    assert repo.get_product_deployment_by_idem_key("dep-2") is None


# -- Singleton resolution --------------------------------------------------


def test_set_and_reset_repository_round_trip() -> None:
    custom = InMemoryRepository()
    set_repository(custom)
    assert get_repository() is custom

    reset_repository()
    # After reset, the next call must materialise a fresh instance (NOT
    # return the previously-injected one).
    fresh = get_repository()
    assert fresh is not custom
    assert isinstance(fresh, Repository)


def test_get_repository_dynamodb_branch_requires_table_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_repository()`` raises a clear error if asked for DynamoDB
    without a resolved table name.

    Drives ``CATALYST_REPOSITORY=dynamodb`` with no table env vars set,
    which is the operator-error path that must NOT silently fall back to
    the in-memory backend.
    """

    monkeypatch.setenv("CATALYST_REPOSITORY", "dynamodb")
    monkeypatch.delenv("CATALYST_DYNAMODB_TABLE", raising=False)
    monkeypatch.delenv("CATALYST_DYNAMODB_TABLE_PARAMETER", raising=False)

    from catalyst import settings as settings_module

    settings_module.reset_settings()
    reset_repository()
    try:
        with pytest.raises(RuntimeError, match="DynamoDB repository requested"):
            get_repository()
    finally:
        reset_repository()
        settings_module.reset_settings()
