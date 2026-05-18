"""Pytest fixtures for the Catalyst CLI test suite.

Adds the CLI source directory to sys.path so tests can import
``catalyst_cli`` directly. Provides reusable AWS-credential and
moto-STS fixtures consumed by the integration tests (#156).
"""
from __future__ import annotations

import os
import sys

import pytest

CLI_ROOT = os.path.dirname(os.path.abspath(__file__))
if CLI_ROOT not in sys.path:
    sys.path.insert(0, CLI_ROOT)


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub AWS credentials and region so boto3 / moto don't reach for the
    operator's real `~/.aws/credentials`. Scoped — undone on test exit.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "TESTTESTTESTTESTTESTTESTTESTTESTTESTTEST")
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def sts_client(aws_credentials):
    """A boto3 STS client with stub credentials — use inside ``@mock_aws``."""
    import boto3

    return boto3.client("sts", region_name="us-east-1")
