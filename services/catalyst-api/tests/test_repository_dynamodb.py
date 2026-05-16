"""Integration tests for :class:`DynamoDBRepository`.

Uses ``moto`` v5 ``mock_aws()`` to simulate DynamoDB; no real AWS calls.
The schema mirrors ``infrastructure/modules/dynamodb`` so a regression in
either module surfaces here.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from catalyst.repository import DynamoDBRepository


TABLE = "catalyst-platform-state"


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


def test_idempotency_round_trip(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    assert repo.get_idempotent("k1") is None
    repo.put_idempotent("k1", {"answer": 42})
    assert repo.get_idempotent("k1") == {"answer": 42}
    # passing None must short-circuit and never read DynamoDB
    assert repo.get_idempotent(None) is None


def test_idempotency_writes_ttl(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    repo.put_idempotent("k2", {"x": 1})
    raw = ddb_table.get_item(Key={"pk": "IDEM#k2", "sk": "RESULT"})["Item"]
    assert "expires_at" in raw
    assert raw["expires_at"] > 0


def test_org_records_accumulate_per_kind(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    repo.append_org_record("acme", "environments", "dev")
    repo.append_org_record("acme", "environments", "prod")
    repo.append_org_record("acme", "applications", "billing")

    org = repo.get_organization("acme")
    assert [e["name"] for e in org["environments"]] == ["dev", "prod"]
    assert [a["name"] for a in org["applications"]] == ["billing"]
    assert org["ous"] == []
    assert org["landing_zones"] == []


def test_get_organization_unknown_tenant_is_empty(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    assert repo.get_organization("missing") == {}


def test_org_record_rejects_unknown_kind(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    with pytest.raises(ValueError):
        repo.append_org_record("acme", "made_up", "x")


def test_service_lifecycle(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    construct = "cloud-byte/dev/shared/platform/app1"

    assert repo.get_service(construct) is None

    repo.init_service(construct)
    repo.append_service_deployment(construct, {"image_tag": "v1", "at": "2026-05-15T10:00:00Z"})
    repo.append_service_deployment(construct, {"image_tag": "v2", "at": "2026-05-15T11:00:00Z"})
    repo.update_service_config(construct, {"FEATURE_X": "on", "LOG_LEVEL": "info"})
    repo.update_service_config(construct, {"LOG_LEVEL": "debug"})

    service = repo.get_service(construct)
    assert service is not None
    assert [d["image_tag"] for d in service["deployments"]] == ["v1", "v2"]
    assert service["config"] == {"FEATURE_X": "on", "LOG_LEVEL": "debug"}


def test_init_service_is_idempotent(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    construct = "cloud-byte/dev/shared/platform/app1"
    repo.init_service(construct)
    repo.update_service_config(construct, {"K": "v"})
    repo.init_service(construct)  # second call must NOT clobber config
    service = repo.get_service(construct)
    assert service is not None
    assert service["config"] == {"K": "v"}


def test_product_inventory(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    record = {"tenant": "acme", "project": "billing", "app": "ledger", "lifecycle_state": "planned"}
    repo.put_product("acme/billing/ledger", record)
    repo.put_product(
        "acme/billing/invoices",
        {"tenant": "acme", "project": "billing", "app": "invoices", "lifecycle_state": "active"},
    )

    assert repo.get_product("acme/billing/ledger") == record
    assert repo.get_product("missing") is None
    products = repo.list_products()
    assert {p["app"] for p in products} == {"ledger", "invoices"}


def test_group_action_audit_trail(ddb_table) -> None:  # type: ignore[no-untyped-def]
    repo = _make_repo(ddb_table)
    repo.record_group_action("catalyst-support-admins", "add", "arn:aws:iam::123:user/alice")
    repo.record_group_action("catalyst-support-admins", "remove", "arn:aws:iam::123:user/bob")
    actions = repo.list_group_actions("catalyst-support-admins")
    assert actions == [
        "add:arn:aws:iam::123:user/alice",
        "remove:arn:aws:iam::123:user/bob",
    ]
    assert repo.list_group_actions("catalyst-owners") == []


def test_constructor_requires_table_name() -> None:
    with pytest.raises(ValueError):
        DynamoDBRepository("")
