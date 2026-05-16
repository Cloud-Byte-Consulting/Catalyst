from __future__ import annotations

import json
import os

import requests
from knack import CLI
from knack.arguments import ArgumentsContext
from requests_aws4auth import AWS4Auth


def _auth() -> AWS4Auth:
    import boto3

    session = boto3.Session()
    creds = session.get_credentials().get_frozen_credentials()
    region = session.region_name or os.environ.get("AWS_REGION", "us-west-2")
    return AWS4Auth(creds.access_key, creds.secret_key, region, "execute-api", session_token=creds.token)


def status_command(construct: str) -> None:
    endpoint = os.environ.get("CATALYST_API_ENDPOINT", "http://localhost:8000")
    response = requests.get(f"{endpoint}/services/{construct}", auth=_auth(), timeout=30)
    if response.status_code >= 400:
        raise SystemExit(f"request failed: {response.status_code} {response.text}")
    print(json.dumps(response.json(), indent=2))


def cli_main() -> int:
    cli = CLI(cli_name="catalyst")
    with ArgumentsContext(cli, "services status") as ac:
        ac.argument("construct")
    cli.invocation.commands_loader.command_table["services status"] = status_command
    return cli.invoke()


if __name__ == "__main__":
    raise SystemExit(cli_main())
