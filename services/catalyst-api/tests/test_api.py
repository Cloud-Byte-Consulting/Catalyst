from fastapi.testclient import TestClient

from catalyst.main import app
from catalyst.repository import repo


client = TestClient(app)


def _headers(groups: str = "catalyst-owners", caller: str = "arn:aws:iam::123456789012:user/test") -> dict:
    return {
        "x-caller-arn": caller,
        "x-iam-groups": groups,
    }


def setup_function() -> None:
    repo.organizations.clear()
    repo.services.clear()
    repo.idempotency.clear()
    repo.product_instances.clear()
    repo.groups.clear()


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalog_returns_resources() -> None:
    response = client.get("/catalog", headers=_headers("catalyst-support-viewers"))
    assert response.status_code == 200
    assert any(item["key"] == "network" for item in response.json()["resources"])


def test_tier1_writes_and_read() -> None:
    payload = {"tenant": "cloud-byte", "name": "prod", "idempotency_key": "org-1"}
    create = client.post("/orgs/cloud-byte/environments", json=payload, headers=_headers("catalyst-owners"))
    read = client.get("/orgs/cloud-byte", headers=_headers("catalyst-support-viewers"))
    assert create.status_code == 200
    assert read.status_code == 200
    assert read.json()["structure"]["environments"][0]["name"] == "prod"


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
