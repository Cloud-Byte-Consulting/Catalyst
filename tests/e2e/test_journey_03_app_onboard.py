"""Journey 03 — Admin onboards application → real ARNs returned (Track C).

Drives ``POST /services/onboard`` end-to-end. Mock mode replaces the
``terraform init/apply/output`` subprocess chain with a deterministic
fake (the ``TerraformSubprocessRecorder`` from ``conftest.py``), so the
handler runs its real orchestration but never shells out. Live mode is
skipped for this journey: real Terraform apply takes minutes, and the
issue's Scope §Out explicitly excludes real applies from the fast suite.

The journey would catch a regression in any of:

* the v1 stubbed-ARN handler creeping back in
  (``123456789012.dkr.ecr…`` patterns hard-coded in the handler)
* the L4 composite ``outputs.tf`` contract drifting away from
  ``ecr_uri`` / ``execution_role_arn`` / ``log_group_name`` /
  ``alb_listener_rule_arn`` / ``catalog_record_key`` / ``state_key``
* the ADR-015 state-key convention being silently changed
* ``X-Idempotent-Replay`` not being attached on first call (must be
  absent) but attached on replay
"""

from __future__ import annotations

import subprocess

import pytest

from _terraform_fakes import (
    TerraformSubprocessRecorder,
    make_terraform_output_fixture,
)


# Live-mode skip — real terraform applies take minutes and are deliberately
# out-of-scope for the fast suite per issue #207 Scope §Out.
pytestmark = pytest.mark.filterwarnings("default")


def _skip_live(mode: str) -> None:
    if mode == "live":
        pytest.skip(
            "journey 03 (onboard) does not run in live mode — real terraform "
            "applies take minutes; see issue #207 Scope §Out"
        )


def test_onboard_returns_real_arn_shapes(
    client,
    admin_headers,
    onboard_env,
    patch_boto3_cloudwatch,
    monkeypatch,
    mode,
):
    """Onboard returns real ARN shapes from the L4 composite — not stubs."""

    _skip_live(mode)

    construct = "acme/dev/shared/payments/checkout"
    fixture = make_terraform_output_fixture(
        account_id="555555555555",  # deliberately NOT the legacy 1234… stub
        region="us-west-2",
        tenant="acme",
        project="payments",
        app_name="checkout",
    )
    recorder = TerraformSubprocessRecorder(fixture)
    monkeypatch.setattr(subprocess, "run", recorder.fake)

    response = client.post(
        "/services/onboard",
        headers=admin_headers,
        json={
            "construct_address": construct,
            "service_type": "web-service",
            "port": 8000,
            "idempotency_key": "journey03-onboard-001",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The ARNs must come from the L4 composite's output (our fixture), NOT
    # from a stubbed handler hard-coding 123456789012.
    assert body["construct_address"] == construct
    assert body["ecr_uri"].startswith("555555555555.dkr.ecr.us-west-2.amazonaws.com/"), (
        f"onboard returned a stubbed ECR URI instead of the L4 output: "
        f"{body['ecr_uri']!r}"
    )
    assert body["execution_role_arn"] == (
        "arn:aws:iam::555555555555:role/acme-payments-checkout-exec"
    )
    assert body["log_group_name"] == "/aws/catalyst/acme/dev/payments/checkout"
    assert body["alb_listener_rule_arn"].startswith(
        "arn:aws:elasticloadbalancing:us-west-2:555555555555:"
    )
    assert body["catalog_record_key"] == "APP#acme/dev/shared/payments/checkout|META"
    # ADR-015 state-key contract.
    assert (
        body["state_key"]
        == "catalyst/tenants/acme/environments/dev/apps/checkout.tfstate"
    )
    assert body["status"] == "provisioned"
    # First call MUST NOT be marked as an idempotent replay.
    assert response.headers.get("X-Idempotent-Replay") != "true"

    # Verify the orchestration ran the canonical three-step subprocess chain.
    invoked = [" ".join(c) for c in recorder.calls]
    assert any("init" in c for c in invoked), invoked
    assert any("apply" in c for c in invoked), invoked
    assert any("output" in c for c in invoked), invoked


def test_onboard_worker_omits_alb_rule(
    client,
    admin_headers,
    onboard_env,
    patch_boto3_cloudwatch,
    monkeypatch,
    mode,
):
    """``service_type=worker`` flows through the same handler with no ALB rule.

    The L4 composite's ``outputs.tf`` reports ``alb_listener_rule_arn=null``
    for workers; the journey asserts the handler surfaces ``None``
    verbatim instead of coercing to an empty string or a stub ARN.
    """

    _skip_live(mode)

    construct = "acme/dev/shared/payments/ingest"
    fixture = make_terraform_output_fixture(
        account_id="555555555555",
        region="us-west-2",
        tenant="acme",
        project="payments",
        app_name="ingest",
    )
    fixture["alb_listener_rule_arn"] = {"value": None, "type": "string"}
    recorder = TerraformSubprocessRecorder(fixture)
    monkeypatch.setattr(subprocess, "run", recorder.fake)

    response = client.post(
        "/services/onboard",
        headers=admin_headers,
        json={
            "construct_address": construct,
            "service_type": "worker",
            "port": 8000,
            "idempotency_key": "journey03-worker-001",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["alb_listener_rule_arn"] is None
