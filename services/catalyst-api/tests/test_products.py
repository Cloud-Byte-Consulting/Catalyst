"""Tests for the product-catalog endpoints + orchestration (#103 — CAT-3).

The new endpoints live under ``/products/catalog/*`` so they coexist with
the existing ``/products`` + ``/products/deploy`` + ``/products/{tenant}/
{project}/{app_name}`` routes from #167 (per the path-collision strategy
documented in main.py's bottom comment block).

Three behaviours under test:

* **Catalog surface** — GET endpoints expose the in-process
  :data:`PRODUCT_CATALOG` dict; unknown product_id → 404.
* **RBAC contract** — owner / administrator OK, viewer 403, scoped
  caller outside the tenant 403 (Decision Log on #103).
* **Deploy orchestration** — the underlying ``onboard.provision_app``
  is called exactly once on the happy path; idempotency replay returns
  the cached payload without re-invoking onboard.

The tests do NOT exercise the real Terraform subprocess; ``provision_app``
is monkeypatched per test to a fake that returns a deterministic
:class:`OnboardResult`. Real subprocess coverage lives in
``tests/test_onboard.py`` and ``tests/e2e/test_journey_07_self_deploy.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from catalyst import products as products_module
from catalyst.main import app
from catalyst.onboard import OnboardResult
from catalyst.repository import InMemoryRepository, set_repository


client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


def _headers(
    groups: str = "catalyst-owners",
    caller: str = "arn:aws:iam::123456789012:user/owner",
) -> dict:
    return {"x-caller-arn": caller, "x-iam-groups": groups}


@pytest.fixture(autouse=True)
def _reset_repo() -> None:
    set_repository(InMemoryRepository())


@pytest.fixture(autouse=True)
def _image_uri_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the image-URI env so deploys resolve without needing CATALYST_ECR_BASE."""

    monkeypatch.setenv(
        "CATALYST_SELF_IMAGE_URI",
        "123456789012.dkr.ecr.us-west-2.amazonaws.com/catalyst-api:latest",
    )


@pytest.fixture
def fake_provision_app(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace onboard.provision_app with a MagicMock that returns a canned result.

    Yields the mock so tests can assert call args / count.
    """

    mock = MagicMock(
        return_value=OnboardResult(
            construct_address="acme/dev/shared/catalyst-meta/v2",
            ecr_uri="555555555555.dkr.ecr.us-west-2.amazonaws.com/acme-catalyst-meta-v2",
            execution_role_arn="arn:aws:iam::555555555555:role/acme-catalyst-meta-v2-exec",
            log_group_name="/aws/catalyst/acme/dev/catalyst-meta/v2",
            alb_listener_rule_arn=(
                "arn:aws:elasticloadbalancing:us-west-2:555555555555:"
                "listener-rule/app/catalyst-alb/aaaa/bbbb/cccc"
            ),
            catalog_record_key="APP#acme/dev/shared/catalyst-meta/v2|META",
            correlation_id="test-corr-id",
            state_key="catalyst/tenants/acme/environments/dev/apps/v2.tfstate",
        )
    )
    # Patch at both call sites — the products module imports the symbol
    # directly (`from .onboard import provision_app`), so we patch THAT
    # reference, not catalyst.onboard.provision_app.
    monkeypatch.setattr(products_module, "provision_app", mock)
    return mock


# ---------------------------------------------------------------------------
# GET /products/catalog
# ---------------------------------------------------------------------------


def test_list_products_returns_catalyst_api() -> None:
    """GET /products/catalog surfaces the catalyst-api catalog entry."""

    response = client.get("/products/catalog", headers=_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    products = body["products"]
    ids = {p["product_id"] for p in products}
    assert "catalyst-api" in ids
    entry = next(p for p in products if p["product_id"] == "catalyst-api")
    assert entry["name"] == "Catalyst API"
    assert entry["service_type"] == "web-service"
    assert entry["image_uri_env_var"] == "CATALYST_SELF_IMAGE_URI"
    # frozenset serialised as a sorted list — stable order in JSON.
    assert entry["required_roles"] == ["administrator", "owner"]
    assert body["correlation_id"]


def test_list_products_requires_auth_but_open_to_viewer() -> None:
    """Listing the catalog does NOT require write access."""

    response = client.get(
        "/products/catalog", headers=_headers("catalyst-support-viewers", "arn:...:user/v")
    )
    assert response.status_code == 200
    assert {p["product_id"] for p in response.json()["products"]} == {"catalyst-api"}


# ---------------------------------------------------------------------------
# GET /products/catalog/{product_id}
# ---------------------------------------------------------------------------


def test_get_product_returns_metadata() -> None:
    response = client.get("/products/catalog/catalyst-api", headers=_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["product"]["product_id"] == "catalyst-api"
    assert body["product"]["service_type"] == "web-service"
    assert "Self-managed" in body["product"]["description"]


def test_unknown_product_returns_404() -> None:
    response = client.get("/products/catalog/nonsense-product", headers=_headers())
    assert response.status_code == 404, response.text
    body = response.json()["detail"]
    assert isinstance(body, dict)
    assert body["error"] == "ResourceNotFound"
    assert "nonsense-product" in body["detail"]


# ---------------------------------------------------------------------------
# POST /products/catalog/{product_id}/deploy — happy path
# ---------------------------------------------------------------------------


def test_deploy_product_happy_path(fake_provision_app: MagicMock) -> None:
    """Owner deploys catalyst-api; onboard.provision_app called once with right args."""

    response = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=_headers(),
        json={
            "construct_address": "acme/dev/shared/catalyst-meta/v2",
            "idempotency_key": "test-deploy-001",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["product_id"] == "catalyst-api"
    assert body["construct_address"] == "acme/dev/shared/catalyst-meta/v2"
    assert body["status"] == "provisioned"
    # Real ARN shapes from the fake — NOT the v1 stubbed 123456789012 prefix.
    assert body["ecr_uri"].startswith("555555555555.dkr.ecr.us-west-2.amazonaws.com/")
    assert body["execution_role_arn"].startswith("arn:aws:iam::555555555555:role/")
    assert body["log_group_name"] == "/aws/catalyst/acme/dev/catalyst-meta/v2"
    assert body["alb_listener_rule_arn"].startswith("arn:aws:elasticloadbalancing:")
    assert body["state_key"] == "catalyst/tenants/acme/environments/dev/apps/v2.tfstate"
    assert body["image_uri"] == (
        "123456789012.dkr.ecr.us-west-2.amazonaws.com/catalyst-api:latest"
    )
    assert body["deployment_id"]  # UUID hex, no dashes
    assert len(body["deployment_id"]) == 32

    # provision_app called exactly once, with the construct address and the
    # product's service_type (catalyst-api → web-service).
    assert fake_provision_app.call_count == 1
    call = fake_provision_app.call_args
    assert call.args[0] == "acme/dev/shared/catalyst-meta/v2"
    assert call.kwargs["service_type"] == "web-service"
    assert call.kwargs["idempotency_key"] == "test-deploy-001"


def test_deploy_admin_role_allowed(fake_provision_app: MagicMock) -> None:
    """administrator role (catalyst-support-admins) is in required_roles."""

    response = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
        json={"construct_address": "acme/dev/shared/catalyst-meta/v2"},
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# POST /products/catalog/{product_id}/deploy — RBAC + scope failures
# ---------------------------------------------------------------------------


def test_deploy_product_viewer_403(fake_provision_app: MagicMock) -> None:
    """Viewer cannot deploy; provision_app must NOT be called."""

    response = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=_headers("catalyst-support-viewers", "arn:...:user/viewer"),
        json={"construct_address": "acme/dev/shared/catalyst-meta/v2"},
    )
    assert response.status_code == 403, response.text
    body = response.json()["detail"]
    assert body["error"] == "ScopeInsufficient"
    # Onboard MUST NOT have been called — RBAC short-circuits.
    assert fake_provision_app.call_count == 0


def test_deploy_product_scoped_tenant_403_outside_their_tenant(
    fake_provision_app: MagicMock,
) -> None:
    """Scoped principal can't deploy onto a tenant they don't own."""

    response = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=_headers(
            "catalyst-acme--payments--admins", "arn:...:user/scoped"
        ),
        json={"construct_address": "other-tenant/dev/shared/catalyst-meta/v2"},
    )
    # `scoped` is not in required_roles, so the role check fires first
    # and returns 403 before we even parse the construct address.
    assert response.status_code == 403, response.text
    assert fake_provision_app.call_count == 0


def test_deploy_unauth_no_groups_403(fake_provision_app: MagicMock) -> None:
    """No IAM groups → role is "none" → 403."""

    response = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers={"x-caller-arn": "arn:...:user/anon", "x-iam-groups": ""},
        json={"construct_address": "acme/dev/shared/catalyst-meta/v2"},
    )
    assert response.status_code == 403
    assert fake_provision_app.call_count == 0


# ---------------------------------------------------------------------------
# POST /products/catalog/{product_id}/deploy — idempotency
# ---------------------------------------------------------------------------


def test_deploy_product_idempotent_replay(fake_provision_app: MagicMock) -> None:
    """Same idempotency_key returns same deployment_id without re-invoking onboard."""

    payload = {
        "construct_address": "acme/dev/shared/catalyst-meta/v2",
        "idempotency_key": "replay-test-001",
    }
    first = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=_headers(),
        json=payload,
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    deployment_id = first_body["deployment_id"]

    second = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=_headers(),
        json=payload,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()

    # Replay returns the SAME deployment_id (idempotency works) ...
    assert second_body["deployment_id"] == deployment_id
    # ... AND the rest of the payload matches.
    assert second_body["ecr_uri"] == first_body["ecr_uri"]
    assert second_body["construct_address"] == first_body["construct_address"]

    # provision_app called exactly once — replay short-circuits the orchestration.
    assert fake_provision_app.call_count == 1


def test_deploy_different_idem_keys_yield_different_deployments(
    fake_provision_app: MagicMock,
) -> None:
    """Different keys against same construct produce distinct deployment_ids."""

    payload_a = {
        "construct_address": "acme/dev/shared/catalyst-meta/v2",
        "idempotency_key": "deploy-a",
    }
    payload_b = {
        "construct_address": "acme/dev/shared/catalyst-meta/v2",
        "idempotency_key": "deploy-b",
    }
    a = client.post("/products/catalog/catalyst-api/deploy", headers=_headers(), json=payload_a)
    b = client.post("/products/catalog/catalyst-api/deploy", headers=_headers(), json=payload_b)
    assert a.status_code == 200
    assert b.status_code == 200
    assert a.json()["deployment_id"] != b.json()["deployment_id"]
    # Both calls actually went through provision_app.
    assert fake_provision_app.call_count == 2


# ---------------------------------------------------------------------------
# POST /products/catalog/{product_id}/deploy — error paths
# ---------------------------------------------------------------------------


def test_deploy_unknown_product_404(fake_provision_app: MagicMock) -> None:
    response = client.post(
        "/products/catalog/nonsense-product/deploy",
        headers=_headers(),
        json={"construct_address": "acme/dev/shared/catalyst-meta/v2"},
    )
    assert response.status_code == 404, response.text
    body = response.json()["detail"]
    assert body["error"] == "ResourceNotFound"
    assert fake_provision_app.call_count == 0


def test_deploy_invalid_construct_address_422(fake_provision_app: MagicMock) -> None:
    response = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=_headers(),
        json={"construct_address": "not-a-valid-construct"},
    )
    assert response.status_code == 422, response.text
    assert fake_provision_app.call_count == 0


def test_deploy_extra_field_rejected_by_extra_forbid(
    fake_provision_app: MagicMock,
) -> None:
    """``extra="forbid"`` proves drift fails loudly (per #199 / #177)."""

    response = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=_headers(),
        json={
            "construct_address": "acme/dev/shared/catalyst-meta/v2",
            "rogue_field": "should-422",
        },
    )
    assert response.status_code == 422
    assert fake_provision_app.call_count == 0


# ---------------------------------------------------------------------------
# Image-URI resolution
# ---------------------------------------------------------------------------


def test_image_uri_uses_env_override_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """CATALYST_SELF_IMAGE_URI takes precedence over the default."""

    monkeypatch.setenv("CATALYST_SELF_IMAGE_URI", "registry.example.com/catalyst-api:v999")
    resolved = products_module._resolve_image_uri(
        "catalyst-api", products_module.get_product("catalyst-api")
    )
    assert resolved == "registry.example.com/catalyst-api:v999"


def test_image_uri_falls_back_to_ecr_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CATALYST_SELF_IMAGE_URI", raising=False)
    monkeypatch.setenv(
        "CATALYST_ECR_BASE", "123456789012.dkr.ecr.us-west-2.amazonaws.com/catalyst"
    )
    resolved = products_module._resolve_image_uri(
        "catalyst-api", products_module.get_product("catalyst-api")
    )
    assert resolved == "123456789012.dkr.ecr.us-west-2.amazonaws.com/catalyst:catalyst-api-latest"


def test_image_uri_raises_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CATALYST_SELF_IMAGE_URI", raising=False)
    monkeypatch.delenv("CATALYST_ECR_BASE", raising=False)
    with pytest.raises(Exception) as exc_info:
        products_module._resolve_image_uri(
            "catalyst-api", products_module.get_product("catalyst-api")
        )
    # The raised HTTPException carries a curated message.
    assert "image URI unresolvable" in str(exc_info.value.detail)


def test_deploy_returns_500_when_image_uri_unresolvable(
    monkeypatch: pytest.MonkeyPatch, fake_provision_app: MagicMock
) -> None:
    """Unresolvable image URI 500s BEFORE invoking onboard."""

    monkeypatch.delenv("CATALYST_SELF_IMAGE_URI", raising=False)
    monkeypatch.delenv("CATALYST_ECR_BASE", raising=False)
    response = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=_headers(),
        json={"construct_address": "acme/dev/shared/catalyst-meta/v2"},
    )
    assert response.status_code == 500, response.text
    # onboard MUST NOT have been invoked; image-URI resolution short-circuits.
    assert fake_provision_app.call_count == 0


# ---------------------------------------------------------------------------
# Unit-level functions
# ---------------------------------------------------------------------------


def test_get_product_returns_none_for_unknown() -> None:
    assert products_module.get_product("totally-bogus") is None


def test_list_products_serialises_frozenset_to_sorted_list() -> None:
    products = products_module.list_products()
    assert len(products) >= 1
    for entry in products:
        assert isinstance(entry["required_roles"], list)
        assert entry["required_roles"] == sorted(entry["required_roles"])


def test_is_caller_authorized_for_unknown_product_returns_false() -> None:
    from catalyst.rbac import AccessContext

    access = AccessContext(role="owner", scopes=[("*", "*")], caller_arn="arn:owner")
    assert (
        products_module.is_caller_authorized_for_product(access, "unknown") is False
    )


def test_is_caller_authorized_admin_yes_viewer_no() -> None:
    from catalyst.rbac import AccessContext

    admin = AccessContext(role="administrator", scopes=[("*", "*")], caller_arn="arn:a")
    viewer = AccessContext(role="viewer", scopes=[("*", "*")], caller_arn="arn:v")
    assert (
        products_module.is_caller_authorized_for_product(admin, "catalyst-api") is True
    )
    assert (
        products_module.is_caller_authorized_for_product(viewer, "catalyst-api") is False
    )


def test_deployment_idempotency_key_namespaces_per_product() -> None:
    """The composite key prevents a key reused against a different product from colliding."""

    a = products_module._deployment_idempotency_key(
        "catalyst-api", "acme/dev/shared/x/y", "shared-key"
    )
    b = products_module._deployment_idempotency_key(
        "other-product", "acme/dev/shared/x/y", "shared-key"
    )
    assert a is not None and b is not None
    assert a != b
    assert "catalyst-api" in a
    assert "other-product" in b


def test_deployment_idempotency_key_none_when_no_key() -> None:
    assert (
        products_module._deployment_idempotency_key(
            "catalyst-api", "acme/dev/shared/x/y", None
        )
        is None
    )


def test_repository_records_and_lists_deployments() -> None:
    repo = InMemoryRepository()
    repo.record_product_deployment(
        product_id="catalyst-api",
        construct_address="acme/dev/shared/catalyst-meta/v2",
        deployment_id="dep-1",
        idempotency_key="idem-1",
        payload={"product_id": "catalyst-api", "deployment_id": "dep-1"},
        created_at="2026-05-18T00:00:00Z",
    )
    repo.record_product_deployment(
        product_id="catalyst-api",
        construct_address="acme/dev/shared/catalyst-meta/v3",
        deployment_id="dep-2",
        idempotency_key=None,
        payload={"product_id": "catalyst-api", "deployment_id": "dep-2"},
        created_at="2026-05-18T00:00:01Z",
    )
    assert repo.get_product_deployment("dep-1")["deployment_id"] == "dep-1"
    assert repo.get_product_deployment("dep-missing") is None
    assert (
        repo.get_product_deployment_by_idem_key("idem-1")["deployment_id"] == "dep-1"
    )
    assert repo.get_product_deployment_by_idem_key("not-set") is None
    assert {d["deployment_id"] for d in repo.list_product_deployments("catalyst-api")} == {
        "dep-1",
        "dep-2",
    }
    assert repo.list_product_deployments("other") == []
