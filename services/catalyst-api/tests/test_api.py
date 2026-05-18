from fastapi.testclient import TestClient

from catalyst.main import app
from catalyst.repository import InMemoryRepository, set_repository


client = TestClient(app)


def _headers(groups: str = "catalyst-owners", caller: str = "arn:aws:iam::123456789012:user/test") -> dict:
    return {
        "x-caller-arn": caller,
        "x-iam-groups": groups,
    }


def setup_function() -> None:
    set_repository(InMemoryRepository())


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalog_returns_resources() -> None:
    response = client.get("/catalog", headers=_headers("catalyst-support-viewers"))
    assert response.status_code == 200
    assert any(item["key"] == "network" for item in response.json()["resources"])


def test_tier1_writes_and_read() -> None:
    """Happy path: create a landing zone, then an environment under it."""

    lz_payload = {
        "tenant": "cloud-byte",
        "name": "shared",
        "account_id": "061051223073",
        "compliance": "standard",
        "idempotency_key": "lz-1",
    }
    lz_create = client.post(
        "/orgs/cloud-byte/landing-zones", json=lz_payload, headers=_headers("catalyst-owners")
    )
    assert lz_create.status_code == 200

    env_payload = {
        "tenant": "cloud-byte",
        "name": "prod",
        "landing_zone": "shared",
        "idempotency_key": "env-1",
    }
    env_create = client.post(
        "/orgs/cloud-byte/environments", json=env_payload, headers=_headers("catalyst-owners")
    )
    assert env_create.status_code == 200

    read = client.get("/orgs/cloud-byte", headers=_headers("catalyst-support-viewers"))
    assert read.status_code == 200
    assert read.json()["structure"]["environments"][0]["name"] == "prod"


# ---------------------------------------------------------------------------
# #177 — Tier 1 widened-contract coverage
#
# Every endpoint asserts three properties:
#  1. The CLI's full field set is accepted (no 422 on the canonical body)
#  2. The new fields land in the persisted record (read back via GET /orgs)
#  3. ``extra="forbid"`` is wired — an unknown field returns 422
# ---------------------------------------------------------------------------


def test_landing_zone_persists_account_id_and_compliance() -> None:
    payload = {
        "tenant": "cloud-byte",
        "name": "shared",
        "account_id": "061051223073",
        "compliance": "hipaa",
        "idempotency_key": "lz-acct",
    }
    create = client.post(
        "/orgs/cloud-byte/landing-zones", json=payload, headers=_headers("catalyst-owners")
    )
    assert create.status_code == 200
    body = create.json()
    # #169 Gherkin AC scenario 1 — response must surface these fields.
    assert body["landing_zone_id"] == "cloud-byte/shared"
    assert body["construct_address"] == "cloud-byte/shared"
    assert body["status"] == "provisioned"
    assert body["account_id"] == "061051223073"
    assert body["compliance"] == "hipaa"

    read = client.get("/orgs/cloud-byte", headers=_headers("catalyst-support-viewers"))
    persisted = read.json()["structure"]["landing_zones"][0]
    assert persisted["name"] == "shared"
    assert persisted["account_id"] == "061051223073"
    assert persisted["compliance"] == "hipaa"


def test_landing_zone_rejects_non_twelve_digit_account_id() -> None:
    payload = {
        "tenant": "cloud-byte",
        "name": "shared",
        "account_id": "not-an-id",
        "compliance": "standard",
    }
    response = client.post(
        "/orgs/cloud-byte/landing-zones", json=payload, headers=_headers("catalyst-owners")
    )
    assert response.status_code == 422


def test_landing_zone_rejects_unknown_compliance() -> None:
    payload = {
        "tenant": "cloud-byte",
        "name": "shared",
        "account_id": "061051223073",
        "compliance": "soc2-but-make-it-up",
    }
    response = client.post(
        "/orgs/cloud-byte/landing-zones", json=payload, headers=_headers("catalyst-owners")
    )
    assert response.status_code == 422


def test_landing_zone_rejects_unknown_extra_field() -> None:
    """``extra="forbid"`` proof — drift fails loudly instead of being dropped."""

    payload = {
        "tenant": "cloud-byte",
        "name": "shared",
        "account_id": "061051223073",
        "compliance": "standard",
        "region": "us-west-2",  # not in the model — must 422
    }
    response = client.post(
        "/orgs/cloud-byte/landing-zones", json=payload, headers=_headers("catalyst-owners")
    )
    assert response.status_code == 422


def test_environment_persists_landing_zone_reference() -> None:
    client.post(
        "/orgs/cloud-byte/landing-zones",
        json={
            "tenant": "cloud-byte",
            "name": "shared",
            "account_id": "061051223073",
            "compliance": "standard",
        },
        headers=_headers("catalyst-owners"),
    )
    env_payload = {
        "tenant": "cloud-byte",
        "name": "prod",
        "landing_zone": "shared",
        "idempotency_key": "env-1",
    }
    create = client.post(
        "/orgs/cloud-byte/environments", json=env_payload, headers=_headers("catalyst-owners")
    )
    assert create.status_code == 200
    body = create.json()
    assert body["environment_id"] == "cloud-byte/shared/prod"
    assert body["landing_zone"] == "shared"
    assert body["status"] == "provisioned"

    read = client.get("/orgs/cloud-byte", headers=_headers("catalyst-support-viewers"))
    persisted = read.json()["structure"]["environments"][0]
    assert persisted["name"] == "prod"
    assert persisted["landing_zone"] == "shared"


def test_environment_unknown_landing_zone_returns_422() -> None:
    """#169 Gherkin AC scenario 3 — unknown LZ reference is a 422."""

    payload = {
        "tenant": "cloud-byte",
        "name": "prod",
        "landing_zone": "does-not-exist",
    }
    response = client.post(
        "/orgs/cloud-byte/environments", json=payload, headers=_headers("catalyst-owners")
    )
    assert response.status_code == 422
    assert "unknown landing zone" in response.json()["detail"]


def test_environment_rejects_unknown_extra_field() -> None:
    client.post(
        "/orgs/cloud-byte/landing-zones",
        json={
            "tenant": "cloud-byte",
            "name": "shared",
            "account_id": "061051223073",
            "compliance": "standard",
        },
        headers=_headers("catalyst-owners"),
    )
    payload = {
        "tenant": "cloud-byte",
        "name": "prod",
        "landing_zone": "shared",
        "region": "us-west-2",  # drift — must 422
    }
    response = client.post(
        "/orgs/cloud-byte/environments", json=payload, headers=_headers("catalyst-owners")
    )
    assert response.status_code == 422


def test_ou_create_happy_path_and_rejects_extras() -> None:
    payload = {"tenant": "cloud-byte", "name": "platform-ou", "idempotency_key": "ou-1"}
    response = client.post(
        "/orgs/cloud-byte/ous", json=payload, headers=_headers("catalyst-owners")
    )
    assert response.status_code == 200
    assert response.json()["ou_name"] == "platform-ou"

    drift = client.post(
        "/orgs/cloud-byte/ous",
        json={**payload, "parent_ou_id": "ou-abc123"},
        headers=_headers("catalyst-owners"),
    )
    assert drift.status_code == 422


def test_application_persists_project() -> None:
    payload = {
        "tenant": "cloud-byte",
        "project": "payments",
        "name": "checkout",
        "idempotency_key": "app-1",
    }
    create = client.post(
        "/orgs/cloud-byte/applications", json=payload, headers=_headers("catalyst-owners")
    )
    assert create.status_code == 200
    body = create.json()
    assert body["application"] == "checkout"
    assert body["project"] == "payments"

    read = client.get("/orgs/cloud-byte", headers=_headers("catalyst-support-viewers"))
    persisted = read.json()["structure"]["applications"][0]
    assert persisted["name"] == "checkout"
    assert persisted["project"] == "payments"


def test_application_rejects_unknown_extra_field() -> None:
    payload = {
        "tenant": "cloud-byte",
        "project": "payments",
        "name": "checkout",
        "runtime": "nodejs20",  # drift — must 422
    }
    response = client.post(
        "/orgs/cloud-byte/applications", json=payload, headers=_headers("catalyst-owners")
    )
    assert response.status_code == 422


def test_service_onboard_idempotent_replay() -> None:
    payload = {
        "construct_address": "cloud-byte/dev/shared/platform/app1",
        "service_type": "web-service",
        "port": 8000,
        "idempotency_key": "idem-1",
    }
    first = client.post("/services/onboard", json=payload, headers=_headers("catalyst-support-admins", "arn:...:user/admin"))
    second = client.post("/services/onboard", json=payload, headers=_headers("catalyst-support-admins", "arn:...:user/admin"))
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers.get("X-Idempotent-Replay") == "true"


def test_service_deploy_and_status() -> None:
    onboard_payload = {
        "construct_address": "cloud-byte/dev/shared/platform/app1",
        "service_type": "web-service",
        "port": 8000,
    }
    client.post("/services/onboard", json=onboard_payload, headers=_headers("catalyst-support-admins", "arn:...:user/admin"))
    deploy = client.post(
        "/services/cloud-byte/dev/shared/platform/app1/deploy",
        json={"image_tag": "v1.2.3", "idempotency_key": "dep-1"},
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
    )
    status = client.get("/services/cloud-byte/dev/shared/platform/app1", headers=_headers("catalyst-support-viewers"))
    assert deploy.status_code == 200
    assert status.status_code == 200
    assert status.json()["current_image_tag"] == "v1.2.3"


def test_service_config_updates() -> None:
    client.post(
        "/services/onboard",
        json={"construct_address": "cloud-byte/dev/shared/platform/app2", "service_type": "worker", "port": 9000},
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
    )
    config = client.post(
        "/services/cloud-byte/dev/shared/platform/app2/config",
        json={"params": {"A": "1", "B": "2"}, "idempotency_key": "cfg-1"},
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
    )
    assert config.status_code == 200
    assert config.json()["param_count"] == 2


def test_scoped_group_filters_products() -> None:
    deploy = {
        "tenant": "cloud-byte",
        "project": "payments",
        "app": "checkout",
        "idempotency_key": "p1",
    }
    client.post("/products/deploy", json=deploy, headers=_headers("catalyst-support-admins", "arn:...:user/admin"))

    scoped_view = client.get("/products", headers=_headers("catalyst-cloud-byte--payments--viewers", "arn:...:user/scoped"))
    assert scoped_view.status_code == 200
    assert scoped_view.json()["count"] == 1

    denied_view = client.get("/products", headers=_headers("catalyst-acme--billing--viewers", "arn:...:user/other"))
    assert denied_view.status_code == 200
    assert denied_view.json()["count"] == 0


def test_get_product_scoped_permissions() -> None:
    client.post(
        "/products/deploy",
        json={"tenant": "cloud-byte", "project": "payments", "app": "checkout", "idempotency_key": "p1"},
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
    )
    allowed = client.get("/products/cloud-byte/payments/checkout", headers=_headers("catalyst-cloud-byte--payments--admins"))
    denied = client.get("/products/cloud-byte/payments/checkout", headers=_headers("catalyst-acme--billing--admins"))
    assert allowed.status_code == 200
    assert denied.status_code == 403


def test_legacy_scoped_group_compatibility() -> None:
    client.post(
        "/products/deploy",
        json={"tenant": "cloud-byte", "project": "payments", "app": "legacy", "idempotency_key": "legacy-1"},
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
    )
    legacy = client.get("/products", headers=_headers("catalyst-cloud-byte-payments-viewers", "arn:...:user/legacy"))
    assert legacy.status_code == 200
    assert legacy.json()["count"] == 1


def test_viewer_cannot_post() -> None:
    payload = {"construct_address": "cloud-byte/dev/shared/platform/app2", "service_type": "worker", "port": 9000}
    response = client.post("/services/onboard", json=payload, headers=_headers("catalyst-support-viewers"))
    assert response.status_code == 403


def test_owner_can_manage_group_members() -> None:
    response = client.post(
        "/iam/groups/catalyst-support-admins/members",
        headers={
            **_headers("catalyst-owners", "arn:...:user/owner"),
            "user-arn": "arn:aws:iam::123456789012:user/alice",
            "action": "add",
        },
    )
    assert response.status_code == 200


def test_non_owner_cannot_manage_group_members() -> None:
    response = client.post(
        "/iam/groups/catalyst-support-admins/members",
        headers={
            **_headers("catalyst-support-admins", "arn:...:user/admin"),
            "user-arn": "arn:aws:iam::123456789012:user/alice",
            "action": "add",
        },
    )
    assert response.status_code == 403


def test_missing_service_status_returns_404() -> None:
    response = client.get("/services/cloud-byte/dev/shared/platform/missing", headers=_headers("catalyst-support-viewers"))
    assert response.status_code == 404


def test_invalid_construct_returns_422() -> None:
    response = client.post(
        "/services/onboard",
        json={"construct_address": "bad-address", "service_type": "worker", "port": 9000},
        headers=_headers("catalyst-support-admins"),
    )
    assert response.status_code == 422
