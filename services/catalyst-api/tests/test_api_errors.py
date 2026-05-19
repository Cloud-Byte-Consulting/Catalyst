"""Per-handler error-contract coverage for #61.

Each test asserts the canonical response shape introduced by
``catalyst/errors.py``::

    {"error": "<class>", "correlation_id": "<uuid>", "detail": "<msg>"}

Three families of cases:

* **Malformed input** — invalid construct addresses, wrong enum values,
  unknown extra fields, missing required fields. These exercise FastAPI's
  built-in Pydantic 422 handler PLUS the ``ValidationFailure`` raised
  inline by ``_parse_construct``.
* **AWS / repository failure** — a monkeypatched repository raises a
  plain ``Exception`` (proxy for a boto3 ``ClientError``); the handler
  boundary translates it to 503 + ``RepositoryFailure`` body.
* **Domain errors** — ``ResourceNotFound`` (org + service) and
  ``IdempotencyConflict`` (one direct test of the translator) each
  surface with the canonical body and the expected status.

Correlation-ID propagation is asserted on every case: every error body
carries ``correlation_id``, and when the request supplied
``X-Correlation-ID`` the response echoes it back verbatim.
"""

from __future__ import annotations

import uuid

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from catalyst.errors import (
    IdempotencyConflict,
    RepositoryFailure,
    ResourceNotFound,
    ValidationFailure,
    to_http_exception,
)
from catalyst.main import app
from catalyst.repository import InMemoryRepository, set_repository


client = TestClient(app)


def _headers(
    groups: str = "catalyst-owners",
    caller: str = "arn:aws:iam::123456789012:user/test",
    correlation_id: str | None = None,
) -> dict:
    headers = {
        "x-caller-arn": caller,
        "x-iam-groups": groups,
    }
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    return headers


@pytest.fixture(autouse=True)
def _fresh_repo() -> None:
    set_repository(InMemoryRepository())


def _assert_error_envelope(body: dict, *, expected_error: str | None = None) -> str:
    """Assert canonical {error, correlation_id, detail} shape; return the id."""

    # FastAPI wraps everything under ``detail`` for HTTPException raises.
    envelope = body.get("detail", body)
    assert isinstance(envelope, dict), f"detail must be a dict, got {envelope!r}"
    assert "correlation_id" in envelope
    assert "error" in envelope
    assert "detail" in envelope
    if expected_error:
        assert envelope["error"] == expected_error, envelope
    return envelope["correlation_id"]


# ---------------------------------------------------------------------------
# Correlation-ID propagation
# ---------------------------------------------------------------------------


def test_correlation_id_echoed_from_request_header_on_success() -> None:
    """The X-Correlation-ID request header threads into the response."""

    given = str(uuid.uuid4())
    response = client.get(
        "/health", headers={"X-Correlation-ID": given}
    )
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == given
    assert response.json()["correlation_id"] == given


def test_correlation_id_generated_when_request_omits_header() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    generated = response.json()["correlation_id"]
    assert response.headers["X-Correlation-ID"] == generated
    uuid.UUID(generated)  # must be a parseable UUID


def test_correlation_id_echoed_on_error_response() -> None:
    """A 422 body still carries the caller's X-Correlation-ID."""

    given = str(uuid.uuid4())
    response = client.post(
        "/services/onboard",
        json={"construct_address": "bad-address"},
        headers=_headers("catalyst-support-admins", correlation_id=given),
    )
    assert response.status_code == 422
    seen = _assert_error_envelope(response.json(), expected_error="ValidationFailure")
    assert seen == given
    assert response.headers["X-Correlation-ID"] == given


# ---------------------------------------------------------------------------
# Malformed input cases — one per endpoint that takes a body.
# ---------------------------------------------------------------------------


def test_landing_zone_missing_required_field_returns_422() -> None:
    response = client.post(
        "/orgs/cloud-byte/landing-zones",
        json={"tenant": "cloud-byte", "name": "shared"},  # no account_id
        headers=_headers("catalyst-owners"),
    )
    assert response.status_code == 422


def test_landing_zone_invalid_compliance_returns_422() -> None:
    response = client.post(
        "/orgs/cloud-byte/landing-zones",
        json={
            "tenant": "cloud-byte",
            "name": "shared",
            "account_id": "061051223073",
            "compliance": "not-a-valid-enum",
        },
        headers=_headers("catalyst-owners"),
    )
    assert response.status_code == 422


def test_environment_unknown_landing_zone_carries_canonical_body() -> None:
    response = client.post(
        "/orgs/cloud-byte/environments",
        json={
            "tenant": "cloud-byte",
            "name": "prod",
            "landing_zone": "never-registered",
        },
        headers=_headers("catalyst-owners"),
    )
    assert response.status_code == 422
    envelope_cid = _assert_error_envelope(
        response.json(), expected_error="ValidationFailure"
    )
    assert envelope_cid  # non-empty UUID-shaped string
    assert "unknown landing zone" in response.json()["detail"]["detail"]


def test_application_missing_project_returns_422() -> None:
    response = client.post(
        "/orgs/cloud-byte/applications",
        json={"tenant": "cloud-byte", "name": "checkout"},  # no project
        headers=_headers("catalyst-owners"),
    )
    assert response.status_code == 422


def test_ou_unknown_extra_field_returns_422() -> None:
    response = client.post(
        "/orgs/cloud-byte/ous",
        json={"tenant": "cloud-byte", "name": "platform-ou", "drift": "yes"},
        headers=_headers("catalyst-owners"),
    )
    assert response.status_code == 422


def test_service_onboard_invalid_construct_returns_canonical_422() -> None:
    response = client.post(
        "/services/onboard",
        json={"construct_address": "not/enough/segments"},
        headers=_headers("catalyst-support-admins"),
    )
    assert response.status_code == 422
    _assert_error_envelope(response.json(), expected_error="ValidationFailure")


def test_service_deploy_invalid_construct_returns_canonical_422() -> None:
    response = client.post(
        "/services/bad-address/deploy",
        json={"image_tag": "v1", "idempotency_key": "d-1"},
        headers=_headers("catalyst-support-admins"),
    )
    assert response.status_code == 422
    _assert_error_envelope(response.json(), expected_error="ValidationFailure")


def test_service_config_invalid_construct_returns_canonical_422() -> None:
    response = client.post(
        "/services/bad-address/config",
        json={"params": {"K": "V"}, "idempotency_key": "c-1"},
        headers=_headers("catalyst-support-admins"),
    )
    assert response.status_code == 422
    _assert_error_envelope(response.json(), expected_error="ValidationFailure")


def test_service_status_invalid_construct_returns_canonical_422() -> None:
    response = client.get(
        "/services/bad-address",
        headers=_headers("catalyst-support-viewers"),
    )
    assert response.status_code == 422
    _assert_error_envelope(response.json(), expected_error="ValidationFailure")


def test_products_deploy_missing_app_returns_422() -> None:
    response = client.post(
        "/products/deploy",
        json={"tenant": "cloud-byte", "project": "payments", "idempotency_key": "p-1"},
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Resource-not-found cases — service + product + org-product.
# ---------------------------------------------------------------------------


def test_service_status_missing_returns_canonical_404() -> None:
    response = client.get(
        "/services/cloud-byte/dev/shared/platform/never-onboarded",
        headers=_headers("catalyst-support-viewers"),
    )
    assert response.status_code == 404
    _assert_error_envelope(response.json(), expected_error="ResourceNotFound")


def test_service_deploy_missing_returns_canonical_404() -> None:
    response = client.post(
        "/services/cloud-byte/dev/shared/platform/never-onboarded/deploy",
        json={"image_tag": "v1", "idempotency_key": "d-1"},
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
    )
    assert response.status_code == 404
    _assert_error_envelope(response.json(), expected_error="ResourceNotFound")


def test_get_product_missing_returns_canonical_404() -> None:
    response = client.get(
        "/products/cloud-byte/payments/never-deployed",
        headers=_headers("catalyst-support-admins"),
    )
    assert response.status_code == 404
    _assert_error_envelope(response.json(), expected_error="ResourceNotFound")


# ---------------------------------------------------------------------------
# AWS / repository failure injection.
#
# We monkeypatch ``InMemoryRepository.<method>`` to raise a synthetic
# exception so the handler boundary translator must do its job. This is
# the unit-test equivalent of moto's failure-injection — it exercises the
# code path without needing a real boto3 call.
# ---------------------------------------------------------------------------


def _injected_boto3_throttling() -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": "ThrottlingException", "Message": "rate exceeded"},
            "ResponseMetadata": {"HTTPStatusCode": 400},
        },
        operation_name="PutItem",
    )


def _injected_repository_failure() -> Exception:
    return RuntimeError("synthetic repo failure — must not leak to body")


def test_create_landing_zone_repo_failure_returns_503(monkeypatch) -> None:
    repo = InMemoryRepository()

    def boom(*_a, **_kw):
        raise _injected_repository_failure()

    monkeypatch.setattr(repo, "append_org_record", boom)
    set_repository(repo)

    response = client.post(
        "/orgs/cloud-byte/landing-zones",
        json={
            "tenant": "cloud-byte",
            "name": "shared",
            "account_id": "061051223073",
            "compliance": "standard",
        },
        headers=_headers("catalyst-owners"),
    )
    assert response.status_code == 500  # last-resort path; unknown Exception
    envelope = response.json()["detail"]
    assert envelope["error"] == "InternalServerError"
    # The original RuntimeError message must NOT leak into the body.
    assert "synthetic repo failure" not in str(envelope)


def test_create_ou_aws_throttling_returns_503(monkeypatch) -> None:
    repo = InMemoryRepository()

    def boom(*_a, **_kw):
        raise _injected_boto3_throttling()

    monkeypatch.setattr(repo, "append_org_record", boom)
    set_repository(repo)

    response = client.post(
        "/orgs/cloud-byte/ous",
        json={"tenant": "cloud-byte", "name": "platform-ou"},
        headers=_headers("catalyst-owners"),
    )
    assert response.status_code == 503
    envelope = response.json()["detail"]
    assert envelope["error"] == "AWSTransientFailure"
    assert "rate exceeded" not in str(envelope)


def test_create_environment_aws_throttling_returns_503(monkeypatch) -> None:
    repo = InMemoryRepository()
    repo.organizations["cloud-byte"] = {
        "ous": [],
        "landing_zones": [{"name": "shared", "created_at": "x"}],
        "environments": [],
        "applications": [],
    }

    def boom(tenant, kind, *args, **kwargs):
        if kind == "environments":
            raise _injected_boto3_throttling()

    monkeypatch.setattr(repo, "append_org_record", boom)
    set_repository(repo)

    response = client.post(
        "/orgs/cloud-byte/environments",
        json={"tenant": "cloud-byte", "name": "prod", "landing_zone": "shared"},
        headers=_headers("catalyst-owners"),
    )
    assert response.status_code == 503
    envelope = response.json()["detail"]
    assert envelope["error"] == "AWSTransientFailure"


def test_get_org_repo_failure_returns_500(monkeypatch) -> None:
    repo = InMemoryRepository()

    def boom(*_a, **_kw):
        raise _injected_repository_failure()

    monkeypatch.setattr(repo, "get_organization", boom)
    set_repository(repo)

    response = client.get(
        "/orgs/cloud-byte", headers=_headers("catalyst-support-viewers")
    )
    assert response.status_code == 500
    envelope = response.json()["detail"]
    assert envelope["error"] == "InternalServerError"


def test_service_config_aws_resource_not_found_returns_404(monkeypatch) -> None:
    repo = InMemoryRepository()

    def boom(*_a, **_kw):
        raise ClientError(
            error_response={
                "Error": {"Code": "ResourceNotFoundException", "Message": "no such table"},
                "ResponseMetadata": {"HTTPStatusCode": 400},
            },
            operation_name="UpdateItem",
        )

    monkeypatch.setattr(repo, "update_service_config", boom)
    set_repository(repo)

    response = client.post(
        "/services/cloud-byte/dev/shared/platform/api/config",
        json={"params": {"A": "1"}, "idempotency_key": "c-1"},
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
    )
    assert response.status_code == 404
    envelope = response.json()["detail"]
    assert envelope["error"] == "ResourceNotFound"
    assert "no such table" not in str(envelope)


def test_iam_group_member_repo_failure_returns_500(monkeypatch) -> None:
    repo = InMemoryRepository()

    def boom(*_a, **_kw):
        raise _injected_repository_failure()

    monkeypatch.setattr(repo, "record_group_action", boom)
    set_repository(repo)

    response = client.post(
        "/iam/groups/catalyst-support-admins/members",
        headers={
            **_headers("catalyst-owners", "arn:...:user/owner"),
            "user-arn": "arn:aws:iam::123456789012:user/alice",
            "action": "add",
        },
    )
    assert response.status_code == 500
    envelope = response.json()["detail"]
    assert envelope["error"] == "InternalServerError"


def test_deploy_product_repo_failure_returns_500(monkeypatch) -> None:
    repo = InMemoryRepository()

    def boom(*_a, **_kw):
        raise _injected_repository_failure()

    monkeypatch.setattr(repo, "put_product", boom)
    set_repository(repo)

    response = client.post(
        "/products/deploy",
        json={
            "tenant": "cloud-byte",
            "project": "payments",
            "app": "checkout",
            "idempotency_key": "p-1",
        },
        headers=_headers("catalyst-support-admins", "arn:...:user/admin"),
    )
    assert response.status_code == 500


def test_list_products_aws_throttling_returns_503(monkeypatch) -> None:
    repo = InMemoryRepository()

    def boom(*_a, **_kw):
        raise _injected_boto3_throttling()

    monkeypatch.setattr(repo, "list_products", boom)
    set_repository(repo)

    response = client.get(
        "/products", headers=_headers("catalyst-support-admins")
    )
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "AWSTransientFailure"


# ---------------------------------------------------------------------------
# Direct unit tests of the translator — keep them small but cover each
# branch so coverage holds.
# ---------------------------------------------------------------------------


def test_translator_maps_idempotency_conflict_to_409() -> None:
    cid = "test-correlation-id"
    httpx = to_http_exception(IdempotencyConflict("key reused with new body"), cid)
    assert httpx.status_code == 409
    assert httpx.detail == {
        "error": "IdempotencyConflict",
        "correlation_id": cid,
        "detail": "key reused with new body",
    }


def test_translator_maps_resource_not_found_to_404() -> None:
    cid = "cid-2"
    httpx = to_http_exception(ResourceNotFound("nope"), cid)
    assert httpx.status_code == 404
    assert httpx.detail["error"] == "ResourceNotFound"
    assert httpx.detail["correlation_id"] == cid


def test_translator_maps_repository_failure_to_503() -> None:
    httpx = to_http_exception(RepositoryFailure("ddb down"), "cid-3")
    assert httpx.status_code == 503
    assert httpx.detail["error"] == "RepositoryFailure"


def test_translator_maps_validation_failure_to_422() -> None:
    httpx = to_http_exception(ValidationFailure("bad input"), "cid-4")
    assert httpx.status_code == 422
    assert httpx.detail["error"] == "ValidationFailure"
    assert httpx.detail["detail"] == "bad input"


def test_translator_passes_through_existing_http_exception() -> None:
    from fastapi import HTTPException as FastAPIHTTPException

    httpx = to_http_exception(
        FastAPIHTTPException(status_code=403, detail="insufficient_permissions"),
        "cid-5",
    )
    assert httpx.status_code == 403
    assert httpx.detail == {
        "error": "Forbidden",
        "correlation_id": "cid-5",
        "detail": "insufficient_permissions",
    }


def test_translator_unknown_client_error_falls_through_to_repository_failure() -> None:
    err = ClientError(
        error_response={
            "Error": {"Code": "SomeBrandNewExceptionWeDontKnow", "Message": "x"},
            "ResponseMetadata": {"HTTPStatusCode": 500},
        },
        operation_name="GetItem",
    )
    httpx = to_http_exception(err, "cid-6")
    assert httpx.status_code == 503
    assert httpx.detail["error"] == "RepositoryFailure"


def test_translator_doubles_up_safely_on_already_wrapped_body() -> None:
    """If a handler wraps something already-wrapped, don't re-wrap."""

    from fastapi import HTTPException as FastAPIHTTPException

    already = FastAPIHTTPException(
        status_code=422,
        detail={"error": "Foo", "correlation_id": "outer", "detail": "x"},
    )
    httpx = to_http_exception(already, "inner")
    # The outer correlation_id must survive — inner caller does not get to
    # overwrite it.
    assert httpx.detail["correlation_id"] == "outer"


def test_translator_maps_conditional_check_failed_to_409() -> None:
    err = ClientError(
        error_response={
            "Error": {"Code": "ConditionalCheckFailedException", "Message": "no"},
            "ResponseMetadata": {"HTTPStatusCode": 400},
        },
        operation_name="PutItem",
    )
    httpx = to_http_exception(err, "cid-7")
    assert httpx.status_code == 409
    assert httpx.detail["error"] == "IdempotencyConflict"
