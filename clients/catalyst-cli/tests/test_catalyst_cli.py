"""Golden-path tests for the Catalyst CLI.

The HTTP seam is `catalyst_cli._call`; tests monkeypatch it so the CLI runs
without an API or AWS credentials. Each scenario maps to a Gherkin AC from
issue #16.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CLI_DIR = Path(__file__).resolve().parent.parent
if str(CLI_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_DIR))

import catalyst_cli  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.setenv("CATALYST_AUTH", "none")
    monkeypatch.setenv("CATALYST_API_ENDPOINT", "http://test.local")
    yield


@pytest.fixture
def fake_call(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    response_map: dict[tuple[str, str], dict] = {}

    def _fake(method: str, path: str, *, json_body: dict | None = None) -> dict:
        calls.append((method, path, json_body))
        return response_map.get((method, path), {"ok": True, "method": method, "path": path})

    monkeypatch.setattr(catalyst_cli, "_call", _fake)
    return calls, response_map


def test_health_calls_get_health(fake_call):
    calls, _ = fake_call
    payload = catalyst_cli.health_command()
    assert calls == [("GET", "/health", None)]
    assert payload["method"] == "GET"


def test_catalog_list_calls_get_catalog(fake_call):
    calls, response_map = fake_call
    response_map[("GET", "/catalog")] = {"resources": [{"key": "ecr-repo"}], "role": "viewer"}
    payload = catalyst_cli.catalog_list_command()
    assert calls == [("GET", "/catalog", None)]
    assert payload["resources"][0]["key"] == "ecr-repo"


def test_services_status_calls_correct_path(fake_call):
    calls, _ = fake_call
    construct = "cloud-byte/dev/shared/platform/app1"
    catalyst_cli.services_status_command(construct)
    assert calls == [("GET", f"/services/{construct}", None)]


def test_services_onboard_posts_body(fake_call):
    calls, _ = fake_call
    construct = "cloud-byte/dev/shared/platform/app1"
    catalyst_cli.services_onboard_command(construct, idempotency_key="abc-123")
    assert calls == [
        (
            "POST",
            "/services/onboard",
            {"construct_address": construct, "idempotency_key": "abc-123"},
        )
    ]


def test_groups_list_calls_iam_groups(fake_call):
    calls, _ = fake_call
    catalyst_cli.groups_list_command()
    assert calls == [("GET", "/iam/groups", None)]


# ---------------------------------------------------------------------------
# Tier 1 orgs commands (#169)
# ---------------------------------------------------------------------------


def test_orgs_get_calls_correct_path(fake_call):
    calls, response_map = fake_call
    response_map[("GET", "/orgs/cloud-byte")] = {
        "tenant": "cloud-byte",
        "landing_zones": [],
        "environments": [],
    }
    payload = catalyst_cli.orgs_get_command("cloud-byte")
    assert calls == [("GET", "/orgs/cloud-byte", None)]
    assert payload["tenant"] == "cloud-byte"


def test_orgs_landing_zones_create_posts_body(fake_call):
    calls, _ = fake_call
    catalyst_cli.orgs_landing_zones_create_command(
        tenant="cloud-byte",
        name="shared",
        account_id="123456789012",
        compliance="standard",
        idempotency_key="lz-001",
    )
    assert calls == [
        (
            "POST",
            "/orgs/cloud-byte/landing-zones",
            {
                "tenant": "cloud-byte",
                "name": "shared",
                "account_id": "123456789012",
                "compliance": "standard",
                "idempotency_key": "lz-001",
            },
        )
    ]


def test_orgs_environments_create_posts_body(fake_call):
    calls, _ = fake_call
    catalyst_cli.orgs_environments_create_command(
        tenant="cloud-byte",
        name="dev",
        landing_zone="shared",
        idempotency_key="env-dev-001",
    )
    assert calls == [
        (
            "POST",
            "/orgs/cloud-byte/environments",
            {
                "tenant": "cloud-byte",
                "name": "dev",
                "landing_zone": "shared",
                "idempotency_key": "env-dev-001",
            },
        )
    ]


def test_orgs_ous_create_posts_body(fake_call):
    calls, _ = fake_call
    catalyst_cli.orgs_ous_create_command(
        tenant="cloud-byte", name="engineering"
    )
    assert calls == [
        ("POST", "/orgs/cloud-byte/ous", {"tenant": "cloud-byte", "name": "engineering"})
    ]


def test_orgs_applications_create_posts_body(fake_call):
    calls, _ = fake_call
    catalyst_cli.orgs_applications_create_command(
        tenant="cloud-byte",
        project="my-project",
        name="my-app",
        idempotency_key="app-001",
    )
    assert calls == [
        (
            "POST",
            "/orgs/cloud-byte/applications",
            {
                "tenant": "cloud-byte",
                "project": "my-project",
                "name": "my-app",
                "idempotency_key": "app-001",
            },
        )
    ]


def test_orgs_get_rejects_empty_tenant(fake_call):
    calls, _ = fake_call
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.orgs_get_command("")
    assert "tenant is required" in str(exc.value)
    assert calls == []


def test_orgs_landing_zones_create_rejects_missing_account(fake_call):
    calls, _ = fake_call
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.orgs_landing_zones_create_command(
            tenant="cloud-byte", name="shared", account_id=""
        )
    assert "account_id are required" in str(exc.value) or "required" in str(exc.value)
    assert calls == []


def test_orgs_environments_create_rejects_missing_landing_zone(fake_call):
    calls, _ = fake_call
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.orgs_environments_create_command(
            tenant="cloud-byte", name="dev", landing_zone=""
        )
    assert "required" in str(exc.value)
    assert calls == []


def test_orgs_ous_create_rejects_missing_name(fake_call):
    calls, _ = fake_call
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.orgs_ous_create_command(tenant="cloud-byte", name="")
    assert "required" in str(exc.value)
    assert calls == []


def test_orgs_applications_create_rejects_missing_project(fake_call):
    calls, _ = fake_call
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.orgs_applications_create_command(
            tenant="cloud-byte", project="", name="my-app"
        )
    assert "required" in str(exc.value)
    assert calls == []


def test_orgs_landing_zones_create_surfaces_4xx_detail(monkeypatch):
    """Gherkin AC scenario 2: CLI surfaces the same 4xx error detail the API
    returns. Tier 1 orgs commands go through the same _call seam as Tier 2,
    so a 422 with body.detail propagates verbatim into the SystemExit message.
    """
    monkeypatch.setenv("CATALYST_AUTH", "none")

    class _R:
        status_code = 422
        text = '{"detail":"unknown landing zone parent"}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"detail": "unknown landing zone parent"}

    monkeypatch.setattr(catalyst_cli.requests, "request", lambda *a, **kw: _R())
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.orgs_landing_zones_create_command(
            tenant="cloud-byte",
            name="shared",
            account_id="123456789012",
        )
    msg = str(exc.value)
    assert "request failed: 422" in msg
    assert "unknown landing zone parent" in msg


def test_invalid_construct_raises_before_http(fake_call, monkeypatch):
    calls, _ = fake_call
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.services_status_command("not-a-valid-address")
    assert "invalid construct address" in str(exc.value)
    assert calls == []


def test_endpoint_env_var_used(monkeypatch):
    monkeypatch.setenv("CATALYST_API_ENDPOINT", "https://api.example.com/")
    assert catalyst_cli._endpoint() == "https://api.example.com"


def test_auth_strategy_none(monkeypatch):
    monkeypatch.setenv("CATALYST_AUTH", "none")
    assert catalyst_cli._build_auth() is None


def test_auth_strategy_unknown_raises(monkeypatch):
    monkeypatch.setenv("CATALYST_AUTH", "totally-bogus")
    with pytest.raises(SystemExit) as exc:
        catalyst_cli._build_auth()
    assert "unknown CATALYST_AUTH" in str(exc.value)


def test_presigned_sts_requires_credentials_when_token_absent(monkeypatch):
    """When CATALYST_PRESIGNED_STS_URL is unset, the CLI auto-generates via
    boto3. If no AWS credentials are available either, it fails clean —
    surfacing a precise error rather than silently sending no auth header.
    """
    monkeypatch.setenv("CATALYST_AUTH", "presigned-sts")
    monkeypatch.delenv("CATALYST_PRESIGNED_STS_URL", raising=False)
    # Clear any AWS creds in the test environment to force the no-creds path.
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
              "AWS_PROFILE", "AWS_DEFAULT_REGION", "AWS_REGION"):
        monkeypatch.delenv(k, raising=False)
    # Force the boto3 credential chain to return None deterministically
    # (some operator machines have an aws-cli `login_session` profile that
    # otherwise raises MissingDependencyException from botocore).
    import boto3
    monkeypatch.setattr(boto3.Session, "get_credentials", lambda self: None)

    def _fake_request(method, url, **kwargs):
        raise AssertionError("HTTP request must not happen when creds missing")

    monkeypatch.setattr(catalyst_cli.requests, "request", _fake_request)
    with pytest.raises(SystemExit) as exc:
        catalyst_cli._call("GET", "/health")
    assert "no AWS credentials" in str(exc.value)


def test_render_emits_stable_json():
    out = catalyst_cli.render({"b": 2, "a": 1})
    assert out == '{\n  "a": 1,\n  "b": 2\n}'


def test_call_raises_on_4xx(monkeypatch):
    class _R:
        status_code = 422
        text = "{\"detail\":\"bad\"}"
        headers = {"content-type": "application/json"}

        def json(self):
            return {"detail": "bad"}

    monkeypatch.setattr(catalyst_cli.requests, "request", lambda *a, **kw: _R())
    with pytest.raises(SystemExit) as exc:
        catalyst_cli._call("GET", "/services/x")
    assert "request failed: 422" in str(exc.value)


def test_call_returns_json_for_2xx(monkeypatch):
    class _R:
        status_code = 200
        text = "{\"status\":\"ok\"}"
        headers = {"content-type": "application/json"}

        def json(self):
            return {"status": "ok"}

    monkeypatch.setattr(catalyst_cli.requests, "request", lambda *a, **kw: _R())
    result = catalyst_cli._call("GET", "/health")
    assert result == {"status": "ok"}


# ---------------------------------------------------------------------------
# Product-catalog commands (#103 — CAT-3 self-deploy)
# ---------------------------------------------------------------------------


def test_products_list_calls_catalog_endpoint(fake_call):
    calls, response_map = fake_call
    response_map[("GET", "/products/catalog")] = {
        "products": [{"product_id": "catalyst-api", "name": "Catalyst API"}],
    }
    payload = catalyst_cli.products_list_command()
    assert calls == [("GET", "/products/catalog", None)]
    assert payload["products"][0]["product_id"] == "catalyst-api"


def test_products_get_calls_catalog_endpoint(fake_call):
    calls, response_map = fake_call
    response_map[("GET", "/products/catalog/catalyst-api")] = {
        "product": {"product_id": "catalyst-api", "service_type": "web-service"},
    }
    payload = catalyst_cli.products_get_command("catalyst-api")
    assert calls == [("GET", "/products/catalog/catalyst-api", None)]
    assert payload["product"]["product_id"] == "catalyst-api"


def test_products_get_rejects_empty_id(fake_call):
    calls, _ = fake_call
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.products_get_command("")
    assert "product_id is required" in str(exc.value)
    assert calls == []


def test_products_deploy_posts_body(fake_call):
    calls, _ = fake_call
    construct = "acme/dev/shared/catalyst-meta/v2"
    catalyst_cli.products_deploy_command(
        product_id="catalyst-api",
        construct=construct,
        idempotency_key="deploy-001",
    )
    assert calls == [
        (
            "POST",
            "/products/catalog/catalyst-api/deploy",
            {"construct_address": construct, "idempotency_key": "deploy-001"},
        )
    ]


def test_products_deploy_without_idempotency_key(fake_call):
    """idempotency_key is optional — the field is omitted when not supplied."""

    calls, _ = fake_call
    construct = "acme/dev/shared/catalyst-meta/v2"
    catalyst_cli.products_deploy_command(
        product_id="catalyst-api", construct=construct
    )
    assert calls == [
        (
            "POST",
            "/products/catalog/catalyst-api/deploy",
            {"construct_address": construct},
        )
    ]


def test_products_deploy_rejects_empty_product_id(fake_call):
    calls, _ = fake_call
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.products_deploy_command(
            product_id="", construct="acme/dev/shared/catalyst-meta/v2"
        )
    assert "product_id is required" in str(exc.value)
    assert calls == []


def test_products_deploy_validates_construct(fake_call):
    """Bad construct address fails client-side before hitting HTTP."""

    calls, _ = fake_call
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.products_deploy_command(
            product_id="catalyst-api", construct="bad-address"
        )
    assert "invalid construct address" in str(exc.value)
    assert calls == []
