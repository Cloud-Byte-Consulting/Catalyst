"""Journey 05 — RBAC paths.

Five sub-cases assert the role-resolution contract laid out in ADR-008.
The vocabulary lives in :mod:`catalyst.rbac`; this journey is the
boundary-level regression lock that catches a role-table or scope-check
drift before it ships:

1. ``catalyst-support-viewers`` can ``GET /orgs/{tenant}`` → 200
2. ``catalyst-support-viewers`` cannot ``POST /orgs/{tenant}/landing-zones`` → 403
3. Tenant-scoped (``catalyst-{tenant}--owners``) caller can ``POST
   /services/onboard`` on a construct in **their** tenant → 200
4. Tenant-scoped caller cannot read products in a **different** tenant
   via ``GET /products/{tenant}/{project}/{app}`` → 403
5. ``headers``-mode caller with no ``x-iam-groups`` header is denied on
   writes (current behaviour: 403 from ``require_write``; the missing-
   credential 401 path lives in ``sigv4`` mode against
   ``x-catalyst-identity-url`` and is covered by journey 06).
"""

from __future__ import annotations

import subprocess

import pytest

from _terraform_fakes import (
    TerraformSubprocessRecorder,
    make_terraform_output_fixture,
)


def test_viewer_can_get_org(client, viewer_headers, owner_headers, tenant_slug):
    """Sub-case 1: viewer reads ``GET /orgs/{tenant}``."""

    # Seed the org so the read has something to return.
    client.post(
        f"/orgs/{tenant_slug}/landing-zones",
        headers=owner_headers,
        json={
            "tenant": tenant_slug,
            "name": "shared",
            "account_id": "061051223073",
            "compliance": "standard",
        },
    )
    response = client.get(f"/orgs/{tenant_slug}", headers=viewer_headers)
    assert response.status_code == 200, response.text
    assert response.json()["tenant"] == tenant_slug


def test_viewer_cannot_post_landing_zone(client, viewer_headers, tenant_slug):
    """Sub-case 2: viewer is denied on a Tier 1 write."""

    response = client.post(
        f"/orgs/{tenant_slug}/landing-zones",
        headers=viewer_headers,
        json={
            "tenant": tenant_slug,
            "name": "shared",
            "account_id": "061051223073",
            "compliance": "standard",
        },
    )
    assert response.status_code == 403, response.text


def test_tenant_scoped_caller_can_write_tier2_within_their_tenant(
    client, onboard_env, patch_boto3_cloudwatch, monkeypatch, mode, correlation_id_header
):
    """Sub-case 3: ``catalyst-{tenant}--owners`` resolves to ``scoped`` role
    which is allowed on tier 2 writes (ADR-008 §"Tenant-scoped groups").

    Live mode skips because this drives the onboard flow.
    """

    if mode == "live":
        pytest.skip(
            "tenant-scoped tier-2 write asserts via onboard; real terraform "
            "applies are out of scope (#207 Scope §Out)"
        )

    construct = "acme/dev/shared/payments/checkout"
    fixture = make_terraform_output_fixture(
        account_id="555555555555",
        region="us-west-2",
        tenant="acme",
        project="payments",
        app_name="checkout",
    )
    recorder = TerraformSubprocessRecorder(fixture)
    monkeypatch.setattr(subprocess, "run", recorder.fake)

    headers = {
        "x-caller-arn": "arn:aws:iam::555555555555:user/tenant-scoped",
        "x-iam-groups": "catalyst-acme--owners",
        **correlation_id_header,
    }
    response = client.post(
        "/services/onboard",
        headers=headers,
        json={
            "construct_address": construct,
            "service_type": "web-service",
            "port": 8000,
            "idempotency_key": "journey05-scoped-onboard",
        },
    )
    assert response.status_code == 200, response.text


def test_tenant_scoped_caller_cannot_read_other_tenants_product(
    client, owner_headers, correlation_id_header
):
    """Sub-case 4: ``GET /products/{tenant}/{project}/{app}`` filters on scope.

    Seed a product in tenant ``acme`` from an owner. Then attempt to
    read it as a caller scoped to tenant ``other-tenant`` — must 403.
    """

    # Seed a product under acme/payments/checkout via the global owner.
    seed = client.post(
        "/products/deploy",
        headers={
            "x-caller-arn": "arn:aws:iam::555555555555:user/seed",
            "x-iam-groups": "catalyst-owners",
            **correlation_id_header,
        },
        json={
            "tenant": "acme",
            "project": "payments",
            "app": "checkout",
            "idempotency_key": "journey05-seed-prod",
        },
    )
    assert seed.status_code == 200, seed.text

    # Now read it as a tenant-scoped admin in a DIFFERENT tenant.
    other_headers = {
        "x-caller-arn": "arn:aws:iam::555555555555:user/other-scoped",
        "x-iam-groups": "catalyst-other-tenant--billing--admins",
        **correlation_id_header,
    }
    response = client.get(
        "/products/acme/payments/checkout", headers=other_headers
    )
    assert response.status_code == 403, response.text


def test_missing_iam_groups_header_denies_writes_in_headers_mode(
    client, correlation_id_header, tenant_slug
):
    """Sub-case 5: no ``x-iam-groups`` in headers mode → 403 on writes.

    The brief's original target was 401, but per :mod:`catalyst.rbac`
    the ``headers`` auth mode resolves to the ``none`` role on a missing
    group list and ``require_write`` raises ``HTTPException(403)``. The
    401 path lives in ``sigv4`` mode (no ``x-catalyst-identity-url``)
    and is asserted in journey 06.
    """

    headers = {
        # x-caller-arn present, x-iam-groups deliberately omitted.
        "x-caller-arn": "arn:aws:iam::555555555555:user/no-groups",
        **correlation_id_header,
    }
    response = client.post(
        f"/orgs/{tenant_slug}/landing-zones",
        headers=headers,
        json={
            "tenant": tenant_slug,
            "name": "shared",
            "account_id": "061051223073",
            "compliance": "standard",
        },
    )
    assert response.status_code == 403, response.text
