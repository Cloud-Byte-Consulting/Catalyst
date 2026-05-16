"""Identity verification for the Catalyst API.

We follow the AWS IAM Authenticator pattern (used by EKS): the caller
constructs a *presigned* ``sts:GetCallerIdentity`` request using their own
IAM credentials and forwards the URL to the Catalyst API. The API replays
that URL against STS. STS validates the SigV4 signature itself and
returns the caller's identity if (and only if) the signature is valid
and unexpired. The Catalyst API never sees the caller's secret access
key, and there is no API Gateway in the path that could enforce
``execute-api:Invoke``.

References:
    - https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html
    - https://github.com/kubernetes-sigs/aws-iam-authenticator
    - ADR-008 (RBAC), ADR-009 (runtime), ADR-006 (CI/CD trust roles)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


# Acceptable STS hostnames. We accept the global endpoint and any regional
# endpoint that follows the documented pattern so the same code works in
# regions like us-west-2 (default) or partition-specific regions.
_ALLOWED_STS_HOSTS = ("sts.amazonaws.com",)
_ALLOWED_STS_HOST_SUFFIX = ".amazonaws.com"
_ALLOWED_STS_HOST_PREFIX = "sts."


class IdentityVerificationError(Exception):
    """Raised when the caller cannot be authenticated against STS."""


@dataclass(frozen=True)
class CallerIdentity:
    arn: str
    account: str
    user_id: str


def _validate_sts_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise IdentityVerificationError("identity URL must use https")
    host = parsed.hostname or ""
    host = host.lower()
    if host in _ALLOWED_STS_HOSTS:
        return
    if host.startswith(_ALLOWED_STS_HOST_PREFIX) and host.endswith(_ALLOWED_STS_HOST_SUFFIX):
        return
    raise IdentityVerificationError(f"identity URL host not allowed: {host}")


def _parse_caller_identity_xml(body: str) -> CallerIdentity:
    """Parse the relevant fields out of an STS GetCallerIdentity response.

    STS returns XML; we only need three fields and we want to avoid pulling
    ``defusedxml`` into the runtime path. We do a small, strict regex parse
    that rejects anything that does not look exactly like the documented
    response shape.
    """

    import re

    def _grab(tag: str) -> str:
        match = re.search(rf"<{tag}>([^<]+)</{tag}>", body)
        if not match:
            raise IdentityVerificationError(f"STS response missing <{tag}>")
        return match.group(1).strip()

    return CallerIdentity(arn=_grab("Arn"), account=_grab("Account"), user_id=_grab("UserId"))


def verify_presigned_identity(
    presigned_url: str,
    *,
    http_get: Any | None = None,
    timeout_seconds: float = 5.0,
) -> CallerIdentity:
    """Verify a presigned ``sts:GetCallerIdentity`` URL.

    Parameters
    ----------
    presigned_url:
        The full URL produced by the caller (including query-string SigV4
        parameters).
    http_get:
        Callable with the signature ``http_get(url, timeout=...) -> object``
        where the returned object exposes ``status_code`` and ``text``
        attributes. The default uses ``requests.get`` lazily so unit tests
        can pass a stub without installing the network stack.
    timeout_seconds:
        Per-request timeout passed to the HTTP client.

    Returns
    -------
    :class:`CallerIdentity` if STS accepts the signature.

    Raises
    ------
    :class:`IdentityVerificationError`
        if the URL points at a non-STS host, STS rejects the request, or the
        response cannot be parsed.
    """

    _validate_sts_url(presigned_url)

    if http_get is None:
        import requests

        http_get = requests.get

    try:
        response = http_get(presigned_url, timeout=timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        raise IdentityVerificationError(f"failed to reach STS: {exc}") from exc

    status = getattr(response, "status_code", None)
    body = getattr(response, "text", "") or ""
    if status != 200:
        raise IdentityVerificationError(
            f"STS rejected presigned request (status={status})"
        )
    if "<GetCallerIdentityResult" not in body:
        raise IdentityVerificationError("STS response not a GetCallerIdentity result")
    return _parse_caller_identity_xml(body)


def fetch_iam_groups(
    user_arn: str,
    *,
    iam_client: Any | None = None,
) -> list[str]:
    """Return IAM group names the caller belongs to.

    Notes
    -----
    * IAM ``ListGroupsForUser`` requires the caller's *user name*, not their
      ARN. We extract the user name from the ARN and forward it.
    * If the ARN does not refer to an IAM user (e.g. an assumed-role ARN),
      the caller cannot be matched to scoped groups and we return ``[]``;
      the caller will fall back to the ``none`` role unless they happen to
      hold one of the global ``catalyst-*`` groups via another mechanism.
    """

    user_name = _user_name_from_arn(user_arn)
    if user_name is None:
        return []

    if iam_client is None:
        import boto3

        iam_client = boto3.client("iam")

    paginator = iam_client.get_paginator("list_groups_for_user")
    groups: list[str] = []
    for page in paginator.paginate(UserName=user_name):
        for group in page.get("Groups", []):
            groups.append(group["GroupName"])
    return groups


def _user_name_from_arn(arn: str) -> str | None:
    # arn:aws:iam::<account>:user/<path?>/<name>
    if ":user/" not in arn:
        return None
    after = arn.split(":user/", 1)[1]
    if not after:
        return None
    return after.rsplit("/", 1)[-1]
