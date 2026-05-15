"""SigV4-presigned-STS verification tests for :mod:`catalyst.identity`."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from catalyst.identity import (
    CallerIdentity,
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


class _FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


def test_verify_presigned_identity_returns_identity() -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, *, timeout: float) -> _FakeResponse:
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResponse(200, _VALID_BODY)

    identity = verify_presigned_identity(
        "https://sts.us-west-2.amazonaws.com/?Action=GetCallerIdentity&X-Amz-Signature=abc",
        http_get=fake_get,
        timeout_seconds=2.5,
    )

    assert identity == CallerIdentity(
        arn="arn:aws:iam::123456789012:user/alice",
        account="123456789012",
        user_id="AIDAEXAMPLE",
    )
    assert captured["timeout"] == 2.5


def test_verify_rejects_non_https() -> None:
    with pytest.raises(IdentityVerificationError):
        verify_presigned_identity(
            "http://sts.amazonaws.com/?x=1",
            http_get=lambda *a, **k: _FakeResponse(200, _VALID_BODY),
        )


def test_verify_rejects_unknown_host() -> None:
    with pytest.raises(IdentityVerificationError):
        verify_presigned_identity(
            "https://attacker.example.com/?x=1",
            http_get=lambda *a, **k: _FakeResponse(200, _VALID_BODY),
        )


def test_verify_rejects_global_sts_lookalike() -> None:
    # We accept the canonical sts.amazonaws.com but not look-alikes
    with pytest.raises(IdentityVerificationError):
        verify_presigned_identity(
            "https://sts-amazonaws.com.evil.io/?x=1",
            http_get=lambda *a, **k: _FakeResponse(200, _VALID_BODY),
        )


def test_verify_accepts_global_endpoint() -> None:
    identity = verify_presigned_identity(
        "https://sts.amazonaws.com/?Action=GetCallerIdentity",
        http_get=lambda *a, **k: _FakeResponse(200, _VALID_BODY),
    )
    assert identity.account == "123456789012"


def test_verify_surfaces_non_200() -> None:
    def fake_get(url: str, *, timeout: float) -> _FakeResponse:
        return _FakeResponse(403, "<Error/>")

    with pytest.raises(IdentityVerificationError, match="status=403"):
        verify_presigned_identity(
            "https://sts.us-west-2.amazonaws.com/?x=1",
            http_get=fake_get,
        )


def test_verify_rejects_unexpected_body() -> None:
    def fake_get(url: str, *, timeout: float) -> _FakeResponse:
        return _FakeResponse(200, "<NotWhatYouThink/>")

    with pytest.raises(IdentityVerificationError):
        verify_presigned_identity(
            "https://sts.us-west-2.amazonaws.com/?x=1",
            http_get=fake_get,
        )


def test_verify_wraps_transport_errors() -> None:
    def fake_get(url: str, *, timeout: float) -> _FakeResponse:
        raise OSError("connection refused")

    with pytest.raises(IdentityVerificationError, match="failed to reach STS"):
        verify_presigned_identity(
            "https://sts.us-west-2.amazonaws.com/?x=1",
            http_get=fake_get,
        )


def test_verify_rejects_partial_body() -> None:
    body = "<GetCallerIdentityResult><Arn>arn:aws:iam::1:user/x</Arn></GetCallerIdentityResult>"

    def fake_get(url: str, *, timeout: float) -> _FakeResponse:
        return _FakeResponse(200, body)

    with pytest.raises(IdentityVerificationError, match="missing"):
        verify_presigned_identity(
            "https://sts.us-west-2.amazonaws.com/?x=1",
            http_get=fake_get,
        )


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("AWS_REGION", "us-west-2")


def test_fetch_iam_groups_uses_user_name(aws_credentials: None) -> None:
    with mock_aws():
        iam = boto3.client("iam", region_name="us-west-2")
        iam.create_user(UserName="alice")
        iam.create_group(GroupName="catalyst-administrators")
        iam.create_group(GroupName="catalyst-cloud-byte--payments--admins")
        iam.add_user_to_group(GroupName="catalyst-administrators", UserName="alice")
        iam.add_user_to_group(GroupName="catalyst-cloud-byte--payments--admins", UserName="alice")

        groups = fetch_iam_groups(
            "arn:aws:iam::123456789012:user/alice", iam_client=iam
        )
        assert sorted(groups) == [
            "catalyst-administrators",
            "catalyst-cloud-byte--payments--admins",
        ]


def test_fetch_iam_groups_returns_empty_for_role_arn() -> None:
    class Boom:
        def get_paginator(self, *_: object, **__: object) -> object:
            raise AssertionError("must not be called for non-user ARN")

    groups = fetch_iam_groups(
        "arn:aws:iam::123:role/some-role",
        iam_client=Boom(),
    )
    assert groups == []


def test_fetch_iam_groups_with_path(aws_credentials: None) -> None:
    with mock_aws():
        iam = boto3.client("iam", region_name="us-west-2")
        iam.create_user(UserName="bob", Path="/teams/")
        iam.create_group(GroupName="catalyst-viewers")
        iam.add_user_to_group(GroupName="catalyst-viewers", UserName="bob")
        groups = fetch_iam_groups(
            "arn:aws:iam::123456789012:user/teams/bob", iam_client=iam
        )
        assert groups == ["catalyst-viewers"]
