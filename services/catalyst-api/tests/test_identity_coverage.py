"""Coverage-completion tests for :mod:`catalyst.identity`.

These exercise the lazy-import + default-client branches in
``verify_presigned_identity`` and ``fetch_iam_groups`` and the edge
``_user_name_from_arn`` shape that returns ``None`` for an
``arn:aws:iam::.../user/`` ARN with a trailing slash (no user name).
"""

from __future__ import annotations

import sys
import types

import boto3
import pytest
from moto import mock_aws

from catalyst.identity import (
    IdentityVerificationError,
    fetch_iam_groups,
    verify_presigned_identity,
)


_VALID_BODY = """<GetCallerIdentityResponse>
  <GetCallerIdentityResult>
    <Arn>arn:aws:iam::123456789012:user/alice</Arn>
    <UserId>AIDAEXAMPLE</UserId>
    <Account>123456789012</Account>
  </GetCallerIdentityResult>
</GetCallerIdentityResponse>"""


def test_verify_presigned_identity_default_http_uses_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the caller omits ``http_get``, ``requests.get`` is imported
    lazily and used. We swap in a fake ``requests`` module so the test
    stays offline.
    """

    fake_requests = types.SimpleNamespace()

    captured: dict[str, object] = {}

    def fake_get(url: str, *, timeout: float):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["timeout"] = timeout
        return types.SimpleNamespace(status_code=200, text=_VALID_BODY)

    fake_requests.get = fake_get
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    identity = verify_presigned_identity(
        "https://sts.amazonaws.com/?Action=GetCallerIdentity",
        # http_get omitted => triggers the lazy-import branch
    )

    assert identity.arn == "arn:aws:iam::123456789012:user/alice"
    assert captured["url"].startswith("https://sts.amazonaws.com/")
    assert captured["timeout"] == 5.0  # default in signature


def test_verify_presigned_identity_status_is_none() -> None:
    """A response object that exposes no ``status_code`` attribute is
    treated as a rejection -- the error message echoes ``status=None``."""

    bad_response = types.SimpleNamespace()  # no status_code, no text
    with pytest.raises(IdentityVerificationError, match="status=None"):
        verify_presigned_identity(
            "https://sts.amazonaws.com/?x=1",
            http_get=lambda *a, **k: bad_response,
        )


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("AWS_REGION", "us-west-2")


def test_fetch_iam_groups_default_client_uses_boto3(aws_credentials: None) -> None:
    """When the caller omits ``iam_client``, the function falls back to
    ``boto3.client('iam')``. ``mock_aws()`` intercepts the call.
    """

    with mock_aws():
        iam = boto3.client("iam", region_name="us-west-2")
        iam.create_user(UserName="alice")
        iam.create_group(GroupName="catalyst-administrators")
        iam.add_user_to_group(GroupName="catalyst-administrators", UserName="alice")

        groups = fetch_iam_groups("arn:aws:iam::123456789012:user/alice")
        assert groups == ["catalyst-administrators"]


def test_fetch_iam_groups_empty_user_segment_returns_empty() -> None:
    """An ARN of the form ``...:user/`` (trailing slash, no user name) is
    not addressable in IAM. The helper must short-circuit instead of
    forwarding an empty UserName to ListGroupsForUser.
    """

    class Boom:
        def get_paginator(self, *_: object, **__: object) -> object:
            raise AssertionError("must not be called for empty user segment")

    assert fetch_iam_groups("arn:aws:iam::123:user/", iam_client=Boom()) == []
