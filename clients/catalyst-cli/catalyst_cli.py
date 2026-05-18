"""Catalyst client CLI.

Wraps Catalyst API golden paths so consumers don't hand-craft HTTP requests.
Uses Microsoft `knack` per AGENTS.md.

### Auth strategies

`CATALYST_AUTH` selects the auth path:
  - `none` (default for tests / public endpoints)
  - `sigv4` — sign the API call with SigV4 against `execute-api`
  - `presigned-sts` — attach an `X-Amz-Security-Token` style presigned STS
    GetCallerIdentity URL header (consumed by the SigV4 RBAC path in
    `services/catalyst-api`, see ADR-008)

The HTTP layer is centralized in `_call` so tests can monkeypatch a single
seam.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import OrderedDict
from typing import Any

import requests
from knack import CLI, CLICommandsLoader
from knack.commands import CommandGroup

CONSTRUCT_RE = re.compile(
    r"^[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+$"
)


def _endpoint() -> str:
    return os.environ.get("CATALYST_API_ENDPOINT", "http://localhost:8000").rstrip("/")


def _auth_strategy() -> str:
    return os.environ.get("CATALYST_AUTH", "none").lower()


def _build_auth() -> Any:
    strategy = _auth_strategy()
    if strategy in ("none", ""):
        return None
    if strategy == "sigv4":
        try:
            import boto3
            from requests_aws4auth import AWS4Auth
        except ImportError as exc:
            raise SystemExit(
                "sigv4 auth requires boto3 + requests-aws4auth: "
                f"{exc}"
            ) from exc
        session = boto3.Session()
        creds = session.get_credentials()
        if creds is None:
            raise SystemExit("no AWS credentials available for sigv4 auth")
        creds = creds.get_frozen_credentials()
        region = session.region_name or os.environ.get("AWS_REGION", "us-west-2")
        return AWS4Auth(
            creds.access_key,
            creds.secret_key,
            region,
            "execute-api",
            session_token=creds.token,
        )
    if strategy == "presigned-sts":
        return None
    raise SystemExit(f"unknown CATALYST_AUTH value: {strategy}")


def generate_presigned_sts_url(
    *,
    region: str | None = None,
    expires_in: int = 60,
) -> str:
    """Construct a presigned ``sts:GetCallerIdentity`` URL using the caller's
    AWS credentials.

    The Catalyst API verifies the caller's identity by fetching this URL
    (see ``services/catalyst-api/catalyst/identity.py`` and ADR-008). The
    URL is sent in the ``x-catalyst-identity-url`` request header.

    Tested under ``moto.mock_aws`` — see ``test_catalyst_cli.py``.
    """
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - import guard
        raise SystemExit(
            f"presigned-sts auth requires boto3: {exc}"
        ) from exc
    session = boto3.Session()
    if session.get_credentials() is None:
        raise SystemExit("no AWS credentials available for presigned-sts auth")
    sts = session.client(
        "sts",
        region_name=region or session.region_name or os.environ.get("AWS_REGION", "us-east-1"),
    )
    return sts.generate_presigned_url(
        "get_caller_identity",
        Params={},
        ExpiresIn=expires_in,
        HttpMethod="GET",
    )


def _call(method: str, path: str, *, json_body: dict | None = None) -> dict:
    """Single HTTP seam — tests monkeypatch this function."""
    url = f"{_endpoint()}{path}"
    headers: dict[str, str] = {}
    if _auth_strategy() == "presigned-sts":
        token = os.environ.get("CATALYST_PRESIGNED_STS_URL")
        if not token:
            # Auto-generate when AWS creds are available; surfaces a clear
            # error when they aren't, instead of silently sending no header.
            token = generate_presigned_sts_url()
        # Header name MUST match `services/catalyst-api/catalyst/rbac.py:153`
        # (`x-catalyst-identity-url`). Earlier versions used a different
        # name (`X-Catalyst-Identity`); that was a bug — the API expects
        # the URL itself, not an opaque token, and the header name is
        # documented in `docs/smoke-tests.md` Tier 3.
        headers["x-catalyst-identity-url"] = token
    response = requests.request(
        method,
        url,
        json=json_body,
        auth=_build_auth(),
        headers=headers or None,
        timeout=30,
    )
    if response.status_code >= 400:
        raise SystemExit(
            f"request failed: {response.status_code} {response.text}"
        )
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return {"raw": response.text}


def _validate_construct(construct: str) -> None:
    if not CONSTRUCT_RE.match(construct):
        raise SystemExit(
            "invalid construct address - expected "
            "tenant/landing-zone/environment/project/app: "
            f"{construct!r}"
        )


def health_command() -> dict:
    """GET /health."""
    return _call("GET", "/health")


def catalog_list_command() -> dict:
    """GET /catalog."""
    return _call("GET", "/catalog")


def services_status_command(construct: str) -> dict:
    """GET /services/{construct}."""
    _validate_construct(construct)
    return _call("GET", f"/services/{construct}")


def services_onboard_command(
    construct: str,
    idempotency_key: str | None = None,
) -> dict:
    """POST /services/onboard."""
    _validate_construct(construct)
    body: dict[str, Any] = {"construct_address": construct}
    if idempotency_key:
        body["idempotency_key"] = idempotency_key
    return _call("POST", "/services/onboard", json_body=body)


def groups_list_command() -> dict:
    """GET /iam/groups."""
    return _call("GET", "/iam/groups")


class CatalystCommandsLoader(CLICommandsLoader):
    def load_command_table(self, args):
        with CommandGroup(self, "health", "__main__#{}") as g:
            g.command("check", "health_command")
        with CommandGroup(self, "catalog", "__main__#{}") as g:
            g.command("list", "catalog_list_command")
        with CommandGroup(self, "services", "__main__#{}") as g:
            g.command("status", "services_status_command")
            g.command("onboard", "services_onboard_command")
        with CommandGroup(self, "groups", "__main__#{}") as g:
            g.command("list", "groups_list_command")
        return OrderedDict(self.command_table)

    def load_arguments(self, command):
        super().load_arguments(command)


def cli_main(argv: list[str] | None = None) -> int:
    sys.modules["__main__"].health_command = health_command
    sys.modules["__main__"].catalog_list_command = catalog_list_command
    sys.modules["__main__"].services_status_command = services_status_command
    sys.modules["__main__"].services_onboard_command = services_onboard_command
    sys.modules["__main__"].groups_list_command = groups_list_command
    cli = CLI(cli_name="catalyst", commands_loader_cls=CatalystCommandsLoader)
    return cli.invoke(argv if argv is not None else sys.argv[1:])


def render(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(cli_main())
