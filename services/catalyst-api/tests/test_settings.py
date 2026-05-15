"""Settings resolution tests covering env / SSM / Secrets Manager paths."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from catalyst.settings import (
    Settings,
    SettingsResolutionError,
    get_settings,
    reset_settings,
)


@pytest.fixture(autouse=True)
def _reset_after_each() -> "object":
    yield
    reset_settings()


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("AWS_REGION", "us-west-2")


def test_defaults_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "CATALYST_REPOSITORY",
        "CATALYST_AUTH_MODE",
        "CATALYST_DYNAMODB_TABLE",
        "CATALYST_DYNAMODB_TABLE_PARAMETER",
        "CATALYST_RUNTIME_ROLE_ARN",
        "CATALYST_RUNTIME_ROLE_ARN_PARAMETER",
        "CATALYST_GROUP_CACHE_TTL",
    ]:
        monkeypatch.delenv(key, raising=False)
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.repository_backend == "memory"
    assert settings.auth_mode == "headers"
    assert settings.dynamodb_table_name is None


def test_env_overrides_take_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALYST_REPOSITORY", "dynamodb")
    monkeypatch.setenv("CATALYST_AUTH_MODE", "sigv4")
    monkeypatch.setenv("CATALYST_DYNAMODB_TABLE", "my-table")
    monkeypatch.setenv("CATALYST_RUNTIME_ROLE_ARN", "arn:aws:iam::123:role/r")
    monkeypatch.setenv("CATALYST_GROUP_CACHE_TTL", "600")
    settings = get_settings()
    assert settings.repository_backend == "dynamodb"
    assert settings.auth_mode == "sigv4"
    assert settings.dynamodb_table_name == "my-table"
    assert settings.iam_role_arn == "arn:aws:iam::123:role/r"
    assert settings.iam_group_cache_ttl_seconds == 600


def test_ssm_parameter_resolves_table(aws_credentials: None, monkeypatch: pytest.MonkeyPatch) -> None:
    with mock_aws():
        ssm = boto3.client("ssm", region_name="us-west-2")
        ssm.put_parameter(
            Name="/catalyst/shared/dynamodb/platform-state/table-name",
            Type="String",
            Value="catalyst-platform-state",
        )
        monkeypatch.delenv("CATALYST_DYNAMODB_TABLE", raising=False)
        monkeypatch.setenv(
            "CATALYST_DYNAMODB_TABLE_PARAMETER",
            "/catalyst/shared/dynamodb/platform-state/table-name",
        )
        settings = get_settings()
        assert settings.dynamodb_table_name == "catalyst-platform-state"


def test_secret_resolves_runtime_value(aws_credentials: None, monkeypatch: pytest.MonkeyPatch) -> None:
    with mock_aws():
        sm = boto3.client("secretsmanager", region_name="us-west-2")
        sm.create_secret(Name="catalyst/runtime/api-key", SecretString="super-secret")
        monkeypatch.setenv(
            "CATALYST_RUNTIME_SECRET_API_KEY_SECRET", "catalyst/runtime/api-key"
        )
        settings = get_settings()
        assert settings.runtime_secrets["API_KEY"] == "super-secret"


def test_ssm_resolution_failure_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    class BoomSSM:
        def get_parameter(self, **_: object) -> dict:
            raise RuntimeError("denied")

    monkeypatch.delenv("CATALYST_DYNAMODB_TABLE", raising=False)
    monkeypatch.setenv("CATALYST_DYNAMODB_TABLE_PARAMETER", "/missing")
    with pytest.raises(SettingsResolutionError):
        get_settings(ssm_client=BoomSSM())


def test_secret_resolution_failure_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    class BoomSecrets:
        def get_secret_value(self, **_: object) -> dict:
            raise RuntimeError("denied")

    monkeypatch.setenv("CATALYST_RUNTIME_SECRET_X_SECRET", "missing")
    with pytest.raises(SettingsResolutionError):
        get_settings(secrets_client=BoomSecrets())


def test_get_settings_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALYST_REPOSITORY", "memory")
    first = get_settings()
    monkeypatch.setenv("CATALYST_REPOSITORY", "dynamodb")
    second = get_settings()
    assert second is first  # cache hit; no re-resolution


def test_refresh_bypasses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALYST_REPOSITORY", "memory")
    first = get_settings()
    monkeypatch.setenv("CATALYST_REPOSITORY", "dynamodb")
    monkeypatch.setenv("CATALYST_DYNAMODB_TABLE", "x")
    second = get_settings(refresh=True)
    assert second is not first
    assert second.repository_backend == "dynamodb"
