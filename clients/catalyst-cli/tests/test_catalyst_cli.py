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


def test_presigned_sts_requires_token(monkeypatch):
    monkeypatch.setenv("CATALYST_AUTH", "presigned-sts")
    monkeypatch.delenv("CATALYST_PRESIGNED_STS_URL", raising=False)

    def _fake_request(method, url, **kwargs):
        raise AssertionError("HTTP request must not happen when token missing")

    monkeypatch.setattr(catalyst_cli.requests, "request", _fake_request)
    with pytest.raises(SystemExit) as exc:
        catalyst_cli._call("GET", "/health")
    assert "presigned-sts auth requires CATALYST_PRESIGNED_STS_URL" in str(exc.value)


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
