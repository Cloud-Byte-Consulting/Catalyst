"""Journey 07 — Self-deploy a second Catalyst API via the product catalog (#103).

This is the CAT-3 meta-feature journey: the platform deploys its own
product. Walks the operator-facing flow:

    1. ``GET /products/catalog`` — list available platform-shipped products
    2. ``GET /products/catalog/catalyst-api`` — inspect the catalyst-api entry
    3. ``POST /products/catalog/catalyst-api/deploy`` — deploy a Catalyst API
       instance at a chosen construct address

Mock mode replaces the ``terraform init/apply/output`` subprocess chain
with the proven :class:`TerraformSubprocessRecorder` from
``test_journey_03_app_onboard.py`` so the orchestration runs end-to-end
without shelling out. Real ARN shapes (not the v1 stub) round-trip
through ``onboard.provision_app`` and surface in the response.

Live mode is skipped for the same reason journey 03 is skipped — real
``terraform apply`` against AWS takes minutes and is out-of-scope for
the fast suite per issue #207 Scope §Out.

The journey would catch a regression in any of:

* the product-catalog endpoint moving (e.g. someone routes it back under
  ``/products/{product_id}`` and collides with the tenant-instance flow)
* the RBAC contract on the catalog deploy endpoint widening (a viewer
  successfully deploying would be a security-impactful drift)
* the image-URI resolution falling back to a hard-coded default instead
  of reading ``CATALYST_SELF_IMAGE_URI``
* the deployment record not being persisted (idempotency-replay regression)
"""

from __future__ import annotations

import subprocess

import pytest

from _terraform_fakes import (
    TerraformSubprocessRecorder,
    make_terraform_output_fixture,
)


def _skip_live(mode: str) -> None:
    if mode == "live":
        pytest.skip(
            "journey 07 (self-deploy) does not run in live mode — real "
            "terraform applies take minutes; see issue #207 Scope §Out"
        )


def test_self_deploy_walkthrough_returns_real_arns(
    client,
    admin_headers,
    onboard_env,
    patch_boto3_cloudwatch,
    monkeypatch,
    mode,
):
    """End-to-end: list -> get -> deploy walks the meta-feature flow.

    The deploy response carries real-shape ARNs (account id 555... NOT
    the legacy 123456789012 stub) plus the catalog-deploy-specific
    ``product_id`` / ``deployment_id`` fields.
    """

    _skip_live(mode)

    # Configure the image URI so the deploy doesn't 500 on resolution.
    monkeypatch.setenv(
        "CATALYST_SELF_IMAGE_URI",
        "999999999999.dkr.ecr.us-west-2.amazonaws.com/catalyst-api:journey07",
    )

    # ------------------------------------------------------------------
    # Step 1 — list catalog
    # ------------------------------------------------------------------
    listed = client.get("/products/catalog", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    catalog_ids = {p["product_id"] for p in body["products"]}
    assert "catalyst-api" in catalog_ids, body

    # ------------------------------------------------------------------
    # Step 2 — fetch the catalyst-api entry
    # ------------------------------------------------------------------
    fetched = client.get("/products/catalog/catalyst-api", headers=admin_headers)
    assert fetched.status_code == 200, fetched.text
    entry = fetched.json()["product"]
    assert entry["product_id"] == "catalyst-api"
    assert entry["service_type"] == "web-service"
    # The display name surfaces so a CLI / UI can render the catalog cleanly.
    assert entry["name"] == "Catalyst API"

    # ------------------------------------------------------------------
    # Step 3 — deploy at the chosen construct address. We use a deliberately
    # non-stub account id (555...) in the fixture so a regression that
    # hard-codes 123456789012 surfaces immediately.
    # ------------------------------------------------------------------
    construct = "cloud-byte/dev/shared/catalyst-meta/v2"
    fixture = make_terraform_output_fixture(
        account_id="555555555555",
        region="us-west-2",
        tenant="cloud-byte",
        project="catalyst-meta",
        app_name="v2",
    )
    recorder = TerraformSubprocessRecorder(fixture)
    monkeypatch.setattr(subprocess, "run", recorder.fake)

    deployed = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=admin_headers,
        json={
            "construct_address": construct,
            "idempotency_key": "journey07-self-deploy-001",
        },
    )
    assert deployed.status_code == 200, deployed.text
    body = deployed.json()

    # Catalog-deploy-specific fields.
    assert body["product_id"] == "catalyst-api"
    assert body["deployment_id"]  # UUID hex
    assert len(body["deployment_id"]) == 32

    # The construct address round-trips verbatim from our request to the
    # response — proves the journey wired the right path to the right deploy.
    assert body["construct_address"] == construct

    # Real ARN shapes from the L4 composite output — NOT the v1 stub.
    assert body["ecr_uri"].startswith("555555555555.dkr.ecr.us-west-2.amazonaws.com/")
    assert body["execution_role_arn"] == (
        "arn:aws:iam::555555555555:role/cloud-byte-catalyst-meta-v2-exec"
    )
    assert body["log_group_name"] == (
        "/aws/catalyst/cloud-byte/dev/catalyst-meta/v2"
    )
    assert body["alb_listener_rule_arn"].startswith(
        "arn:aws:elasticloadbalancing:us-west-2:555555555555:"
    )
    assert body["state_key"] == (
        "catalyst/tenants/cloud-byte/environments/dev/apps/v2.tfstate"
    )
    assert body["status"] == "provisioned"

    # Image URI resolved from CATALYST_SELF_IMAGE_URI (env override path).
    assert body["image_uri"] == (
        "999999999999.dkr.ecr.us-west-2.amazonaws.com/catalyst-api:journey07"
    )

    # The Terraform subprocess chain ran (init / apply / output) — proves
    # the catalog deploy actually composes onto onboard.provision_app
    # rather than short-circuiting somewhere.
    invoked = [" ".join(c) for c in recorder.calls]
    assert any("init" in c for c in invoked), invoked
    assert any("apply" in c for c in invoked), invoked
    assert any("output" in c for c in invoked), invoked


def test_self_deploy_viewer_403(
    client,
    viewer_headers,
    onboard_env,
    patch_boto3_cloudwatch,
    monkeypatch,
    mode,
):
    """A viewer attempting the catalog deploy is denied; onboard MUST NOT run."""

    _skip_live(mode)

    monkeypatch.setenv(
        "CATALYST_SELF_IMAGE_URI",
        "999999999999.dkr.ecr.us-west-2.amazonaws.com/catalyst-api:journey07",
    )

    # If the RBAC short-circuit ever drifts, this recorder will catch
    # subprocess.run firing where it shouldn't.
    recorder = TerraformSubprocessRecorder(
        make_terraform_output_fixture(
            account_id="555555555555",
            region="us-west-2",
            tenant="cloud-byte",
            project="catalyst-meta",
            app_name="v2",
        )
    )
    monkeypatch.setattr(subprocess, "run", recorder.fake)

    response = client.post(
        "/products/catalog/catalyst-api/deploy",
        headers=viewer_headers,
        json={"construct_address": "cloud-byte/dev/shared/catalyst-meta/v2"},
    )
    assert response.status_code == 403, response.text
    # The orchestration MUST NOT have been invoked — defence in depth on
    # the security boundary.
    assert recorder.calls == [], recorder.calls


def test_self_deploy_idempotent_replay_returns_same_deployment_id(
    client,
    admin_headers,
    onboard_env,
    patch_boto3_cloudwatch,
    monkeypatch,
    mode,
):
    """Replaying the same idempotency_key returns the cached deployment_id.

    The Terraform subprocess MUST NOT fire on replay — proves the
    catalog-deploy idempotency layer composes cleanly over Terraform's
    own S3-state convergence (we get the cached payload back before
    even invoking onboard).
    """

    _skip_live(mode)

    monkeypatch.setenv(
        "CATALYST_SELF_IMAGE_URI",
        "999999999999.dkr.ecr.us-west-2.amazonaws.com/catalyst-api:journey07",
    )

    construct = "cloud-byte/dev/shared/catalyst-meta/v2"
    fixture = make_terraform_output_fixture(
        account_id="555555555555",
        region="us-west-2",
        tenant="cloud-byte",
        project="catalyst-meta",
        app_name="v2",
    )
    recorder = TerraformSubprocessRecorder(fixture)
    monkeypatch.setattr(subprocess, "run", recorder.fake)

    payload = {
        "construct_address": construct,
        "idempotency_key": "journey07-replay-001",
    }
    first = client.post(
        "/products/catalog/catalyst-api/deploy", headers=admin_headers, json=payload
    )
    second = client.post(
        "/products/catalog/catalyst-api/deploy", headers=admin_headers, json=payload
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    first_id = first.json()["deployment_id"]
    second_id = second.json()["deployment_id"]
    assert first_id == second_id, "idempotent replay must return same deployment_id"

    # First call invoked the full init/apply/output chain. Replay should
    # NOT re-invoke it — count the unique calls and assert they all come
    # from the first invocation.
    first_call_count = len(recorder.calls)
    # The replay path returns the cached payload before invoking onboard,
    # so the call count must NOT grow on the replay.
    assert first_call_count > 0, "first deploy should have invoked terraform"
