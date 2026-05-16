"""Runtime configuration for the Catalyst API.

Configuration is resolved with the following precedence per value:

    1. Direct environment variables (e.g. ``CATALYST_DYNAMODB_TABLE``)
    2. SSM Parameter Store, when ``CATALYST_*_PARAMETER`` is set
    3. Secrets Manager, when ``CATALYST_*_SECRET`` is set
    4. Hard-coded defaults (only for non-sensitive knobs)

The module is intentionally small. It exposes a single ``get_settings()``
factory that caches the resolved values for the life of the process so
SSM/Secrets reads happen once on cold start, not on every request.

Resolution failures raise :class:`SettingsResolutionError` so the issue
shows up in CloudWatch on the very first request rather than as a
delayed AccessDenied / ResourceNotFound deep inside a handler.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


class SettingsResolutionError(RuntimeError):
    """Raised when a required setting cannot be resolved from env/SSM/Secrets."""


@dataclass(frozen=True)
class Settings:
    repository_backend: str
    auth_mode: str
    aws_region: str
    dynamodb_table_name: str | None
    dynamodb_table_parameter: str | None
    sts_endpoint: str
    iam_group_cache_ttl_seconds: int
    iam_role_arn: str | None
    runtime_secrets: dict[str, str] = field(default_factory=dict)


def _read_ssm_parameter(name: str, *, region: str, client: Any | None = None) -> str:
    if client is None:
        import boto3

        client = boto3.client("ssm", region_name=region)
    response = client.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]


def _read_secret(name: str, *, region: str, client: Any | None = None) -> str:
    if client is None:
        import boto3

        client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=name)
    if "SecretString" in response:
        return response["SecretString"]
    return response["SecretBinary"].decode("utf-8")


def _resolve_env_or_ssm(env_var: str, *, region: str, ssm_client: Any | None = None) -> str | None:
    """Return env value if present, else read from SSM if ``<env_var>_PARAMETER`` is set."""

    direct = os.environ.get(env_var)
    if direct:
        return direct
    parameter_name = os.environ.get(f"{env_var}_PARAMETER")
    if parameter_name:
        try:
            return _read_ssm_parameter(parameter_name, region=region, client=ssm_client)
        except Exception as exc:  # noqa: BLE001 - rewrap with caller context
            raise SettingsResolutionError(
                f"failed to resolve {env_var} via SSM parameter {parameter_name}: {exc}"
            ) from exc
    return None


def _resolve_secret(env_var: str, *, region: str, secrets_client: Any | None = None) -> str | None:
    """Return env value if present, else read from Secrets Manager if ``<env_var>_SECRET`` is set."""

    direct = os.environ.get(env_var)
    if direct:
        return direct
    secret_name = os.environ.get(f"{env_var}_SECRET")
    if secret_name:
        try:
            return _read_secret(secret_name, region=region, client=secrets_client)
        except Exception as exc:  # noqa: BLE001
            raise SettingsResolutionError(
                f"failed to resolve {env_var} via secret {secret_name}: {exc}"
            ) from exc
    return None


_settings_lock = Lock()
_settings_cache: Settings | None = None


def _resolve_settings(
    *,
    ssm_client: Any | None = None,
    secrets_client: Any | None = None,
) -> Settings:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-west-2"

    backend = os.environ.get("CATALYST_REPOSITORY", "memory").strip().lower()
    auth_mode = os.environ.get("CATALYST_AUTH_MODE", "headers").strip().lower()
    sts_endpoint = os.environ.get("CATALYST_STS_ENDPOINT", f"https://sts.{region}.amazonaws.com")
    cache_ttl = int(os.environ.get("CATALYST_GROUP_CACHE_TTL", "300"))

    table_name = _resolve_env_or_ssm(
        "CATALYST_DYNAMODB_TABLE", region=region, ssm_client=ssm_client
    )
    table_parameter = os.environ.get("CATALYST_DYNAMODB_TABLE_PARAMETER")
    iam_role_arn = _resolve_env_or_ssm(
        "CATALYST_RUNTIME_ROLE_ARN", region=region, ssm_client=ssm_client
    )

    secret_keys = [
        key.removesuffix("_SECRET")
        for key in os.environ
        if key.startswith("CATALYST_RUNTIME_SECRET_") and key.endswith("_SECRET")
    ]
    runtime_secrets: dict[str, str] = {}
    for key in secret_keys:
        value = _resolve_secret(key, region=region, secrets_client=secrets_client)
        if value is not None:
            short = key.removeprefix("CATALYST_RUNTIME_SECRET_")
            runtime_secrets[short] = value

    return Settings(
        repository_backend=backend,
        auth_mode=auth_mode,
        aws_region=region,
        dynamodb_table_name=table_name,
        dynamodb_table_parameter=table_parameter,
        sts_endpoint=sts_endpoint,
        iam_group_cache_ttl_seconds=cache_ttl,
        iam_role_arn=iam_role_arn,
        runtime_secrets=runtime_secrets,
    )


def get_settings(
    *,
    ssm_client: Any | None = None,
    secrets_client: Any | None = None,
    refresh: bool = False,
) -> Settings:
    """Return cached settings, resolving from env/SSM/Secrets on first call."""

    global _settings_cache
    if _settings_cache is not None and not refresh:
        return _settings_cache
    with _settings_lock:
        if _settings_cache is not None and not refresh:
            return _settings_cache
        _settings_cache = _resolve_settings(ssm_client=ssm_client, secrets_client=secrets_client)
        return _settings_cache


def reset_settings() -> None:
    """Drop the cached settings (test helper / cold-restart hook)."""

    global _settings_cache
    with _settings_lock:
        _settings_cache = None
