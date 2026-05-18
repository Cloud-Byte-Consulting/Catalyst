"""Tests for the synchronous Terraform-in-Lambda onboard flow (#167).

The orchestration in :mod:`catalyst.onboard` shells out to a bundled
``terraform`` binary. In tests we monkeypatch :func:`subprocess.run` to
return a fixture representing a successful ``terraform init`` ->
``terraform apply`` -> ``terraform output -json`` chain, then assert
the handler's externally-visible behaviour:

* Real ARNs (the L4 composite's output shape) flow back to the caller.
* ``PutMetricData`` is emitted with the right namespace + dimensions on
  both the success and failure branches.
* The ``-backend-config="key=..."`` arg the handler emits matches the
  ADR-015 L4 convention exactly.
* The structured log line carries the three compliance-required keys
  (``endpoint=services_onboard``, ``correlation_id``, ``state_key``).
* The idempotency-replay path returns the cached payload without
  reinvoking the subprocess.

These tests are marked ``real_provision_app`` so the conftest-level fake
in ``conftest.py`` does NOT replace :func:`catalyst.onboard.provision_app`
— they exercise the real function with subprocess + boto3 stubbed.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid

import pytest
from fastapi.testclient import TestClient

from catalyst.main import app
from catalyst.repository import InMemoryRepository, set_repository

pytestmark = pytest.mark.real_provision_app


client = TestClient(app)


def _headers(group: str = "catalyst-support-admins") -> dict:
    return {
        "x-caller-arn": "arn:aws:iam::123456789012:user/admin",
        "x-iam-groups": group,
    }


# ---------------------------------------------------------------------------
# Subprocess fake — represents a successful terraform init/apply/output chain.
#
# The fake captures every invocation in `_calls` so individual tests can
# assert on the argv shape (e.g. the backend-config "key=…" flag matches
# ADR-015's L4 convention).
# ---------------------------------------------------------------------------


TERRAFORM_OUTPUT_FIXTURE = {
    "ecr_uri": {
        "value": "123456789012.dkr.ecr.us-west-2.amazonaws.com/acme-payments-checkout",
        "type": "string",
    },
    "execution_role_arn": {
        "value": "arn:aws:iam::123456789012:role/acme-payments-checkout-exec",
        "type": "string",
    },
    "log_group_name": {
        "value": "/aws/catalyst/acme/dev/payments/checkout",
        "type": "string",
    },
    "alb_listener_rule_arn": {
        "value": (
            "arn:aws:elasticloadbalancing:us-west-2:123456789012:"
            "listener-rule/app/catalyst-alb/aaaa/bbbb/cccc"
        ),
        "type": "string",
    },
    "catalog_record_key": {
        "value": "APP#acme/dev/shared/payments/checkout|META",
        "type": "string",
    },
    "construct_address": {
        "value": "acme/dev/shared/payments/checkout",
        "type": "string",
    },
}


class _SubprocessRecorder:
    """Captures the full argv of every subprocess.run invocation."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def make_success(self):
        def fake(cmd, **kwargs):
            self.calls.append(list(cmd))
            # The orchestration only consumes stdout from `terraform output -json`;
            # init/apply stdout is just streamed to logs. We return the JSON
            # fixture on `output` and empty stdout otherwise so the JSON
            # parser doesn't choke on stray bytes.
            if "output" in cmd:
                stdout = json.dumps(TERRAFORM_OUTPUT_FIXTURE)
            else:
                stdout = "Terraform has been successfully initialized!\n"
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=stdout, stderr=""
            )

        return fake

    def make_apply_failure(self):
        def fake(cmd, **kwargs):
            self.calls.append(list(cmd))
            if "apply" in cmd:
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=cmd,
                    output="",
                    stderr="Error: AccessDenied invoking IAM CreateRole",
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="ok\n", stderr=""
            )

        return fake


class _MetricRecorder:
    """Records every PutMetricData call so tests can assert on the metric shape."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_metric_data(self, **kwargs):
        self.calls.append(kwargs)


@pytest.fixture
def env_setup(monkeypatch):
    """Ensure CATALYST_STATE_BUCKET / CATALYST_LOCK_TABLE are populated."""

    monkeypatch.setenv("CATALYST_STATE_BUCKET", "catalyst-tf-state-123456789012-us-west-2")
    monkeypatch.setenv("CATALYST_LOCK_TABLE", "catalyst-tf-lock-123456789012-us-west-2")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("CATALYST_ALB_LISTENER_ARN", "")
    monkeypatch.setenv("CATALYST_ALB_TARGET_GROUP_ARN", "")
    set_repository(InMemoryRepository())


def _patch_metric(monkeypatch):
    """Hand the onboard module a stubbed CloudWatch client and return it."""

    recorder = _MetricRecorder()

    def cw_factory(client_name, region_name=None):  # noqa: ARG001
        return recorder

    # Patch boto3.client at the import site so the lazy ``import boto3`` in
    # ``catalyst.onboard._emit_metric`` returns our stub.
    import boto3

    monkeypatch.setattr(boto3, "client", cw_factory)
    return recorder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_onboard_returns_real_arns_on_success(env_setup, monkeypatch):
    recorder = _SubprocessRecorder()
    monkeypatch.setattr(subprocess, "run", recorder.make_success())
    _patch_metric(monkeypatch)

    response = client.post(
        "/services/onboard",
        json={
            "construct_address": "acme/dev/shared/payments/checkout",
            "service_type": "web-service",
            "port": 8000,
            "idempotency_key": "onboard-real-arns",
        },
        headers=_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()

    # Real ARNs from the L4 composite outputs.tf contract — not the v1 stub shape.
    assert body["construct_address"] == "acme/dev/shared/payments/checkout"
    assert (
        body["ecr_uri"]
        == "123456789012.dkr.ecr.us-west-2.amazonaws.com/acme-payments-checkout"
    )
    assert (
        body["execution_role_arn"]
        == "arn:aws:iam::123456789012:role/acme-payments-checkout-exec"
    )
    assert body["log_group_name"] == "/aws/catalyst/acme/dev/payments/checkout"
    assert body["alb_listener_rule_arn"].startswith(
        "arn:aws:elasticloadbalancing:us-west-2:"
    )
    assert body["catalog_record_key"] == "APP#acme/dev/shared/payments/checkout|META"
    assert body["status"] == "provisioned"
    assert "correlation_id" in body
    # The v1 stub returned a `task_role_arn` field — the new contract uses
    # `execution_role_arn` to match the L4 composite output naming.
    assert "task_role_arn" not in body

    # subprocess.run was called at least three times: init, apply, output.
    invoked = [" ".join(c) for c in recorder.calls]
    assert any("init" in c for c in invoked)
    assert any("apply" in c for c in invoked)
    assert any("output" in c for c in invoked)


def test_onboard_emits_putmetricdata_on_success(env_setup, monkeypatch):
    recorder = _SubprocessRecorder()
    monkeypatch.setattr(subprocess, "run", recorder.make_success())
    metric_recorder = _patch_metric(monkeypatch)

    response = client.post(
        "/services/onboard",
        json={
            "construct_address": "acme/dev/shared/payments/checkout",
            "service_type": "web-service",
            "port": 8000,
            "idempotency_key": "onboard-metric-success",
        },
        headers=_headers(),
    )

    assert response.status_code == 200
    assert len(metric_recorder.calls) == 1
    metric = metric_recorder.calls[0]
    assert metric["Namespace"] == "Catalyst/Onboard"
    data = metric["MetricData"][0]
    assert data["MetricName"] == "OnboardDuration"
    assert data["Unit"] == "Milliseconds"
    dims = {d["Name"]: d["Value"] for d in data["Dimensions"]}
    assert dims["Endpoint"] == "services_onboard"
    assert dims["Result"] == "success"


def test_onboard_emits_putmetricdata_on_failure(env_setup, monkeypatch):
    recorder = _SubprocessRecorder()
    monkeypatch.setattr(subprocess, "run", recorder.make_apply_failure())
    metric_recorder = _patch_metric(monkeypatch)

    response = client.post(
        "/services/onboard",
        json={
            "construct_address": "acme/dev/shared/payments/checkout",
            "service_type": "web-service",
            "port": 8000,
            "idempotency_key": "onboard-metric-failure",
        },
        headers=_headers(),
    )

    assert response.status_code == 500
    assert "correlation_id=" in response.json()["detail"]

    assert len(metric_recorder.calls) == 1
    metric = metric_recorder.calls[0]
    dims = {d["Name"]: d["Value"] for d in metric["MetricData"][0]["Dimensions"]}
    assert dims["Endpoint"] == "services_onboard"
    assert dims["Result"] == "failure"


def test_onboard_idempotent_replay_returns_cached_arns(env_setup, monkeypatch):
    recorder = _SubprocessRecorder()
    monkeypatch.setattr(subprocess, "run", recorder.make_success())
    _patch_metric(monkeypatch)

    payload = {
        "construct_address": "acme/dev/shared/payments/checkout",
        "service_type": "web-service",
        "port": 8000,
        "idempotency_key": "onboard-replay-001",
    }
    first = client.post("/services/onboard", json=payload, headers=_headers())
    calls_after_first = len(recorder.calls)

    second = client.post("/services/onboard", json=payload, headers=_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers.get("X-Idempotent-Replay") == "true"
    # Replay MUST NOT re-invoke the terraform subprocess chain.
    assert len(recorder.calls) == calls_after_first
    # And the cached payload is byte-equal to the first response.
    assert second.json() == first.json()


def test_onboard_state_key_matches_adr_015(env_setup, monkeypatch):
    recorder = _SubprocessRecorder()
    monkeypatch.setattr(subprocess, "run", recorder.make_success())
    _patch_metric(monkeypatch)

    response = client.post(
        "/services/onboard",
        json={
            "construct_address": "acme/dev/shared/payments/checkout",
            "service_type": "web-service",
            "port": 8000,
            "idempotency_key": "onboard-statekey",
        },
        headers=_headers(),
    )
    assert response.status_code == 200

    # Find the terraform init invocation and pull out the key=… backend-config.
    init_call = next(c for c in recorder.calls if "init" in c)
    backend_key_arg = next(
        arg
        for arg in init_call
        if arg.startswith("-backend-config=key=")
    )
    expected_key = "catalyst/tenants/acme/environments/dev/apps/checkout.tfstate"
    assert backend_key_arg == f"-backend-config=key={expected_key}"

    # The state key is also surfaced in the response payload so the caller can
    # correlate ops back to the L4 state file.
    assert response.json()["state_key"] == expected_key


def test_onboard_structured_log_includes_required_fields(env_setup, monkeypatch, caplog):
    """ADR-014 + ADR-015 §Compliance — the onboard log line MUST carry
    endpoint=services_onboard, correlation_id, and state_key."""

    recorder = _SubprocessRecorder()
    monkeypatch.setattr(subprocess, "run", recorder.make_success())
    _patch_metric(monkeypatch)

    import logging

    with caplog.at_level(logging.INFO, logger="catalyst.onboard"):
        response = client.post(
            "/services/onboard",
            json={
                "construct_address": "acme/dev/shared/payments/checkout",
                "service_type": "web-service",
                "port": 8000,
                "idempotency_key": "onboard-structured-log",
            },
            headers=_headers(),
        )
    assert response.status_code == 200

    # caplog captures every log record; find the onboard_complete record and
    # assert the three compliance-required keys are present.
    complete_records = [r for r in caplog.records if r.message == "onboard_complete"]
    assert complete_records, "expected an onboard_complete log line on success"
    record = complete_records[-1]
    record_dict = record.__dict__
    assert record_dict.get("endpoint") == "services_onboard"
    assert record_dict.get("correlation_id")  # present and non-empty
    assert (
        record_dict.get("state_key")
        == "catalyst/tenants/acme/environments/dev/apps/checkout.tfstate"
    )


def test_onboard_missing_state_bucket_fails_500(monkeypatch):
    """Misconfiguration (no CATALYST_STATE_BUCKET) surfaces as 500, not 200.

    The handler short-circuits before subprocess invocation so this also
    documents that the env-resolution path runs before the terraform
    binary is touched.
    """

    monkeypatch.delenv("CATALYST_STATE_BUCKET", raising=False)
    monkeypatch.delenv("CATALYST_LOCK_TABLE", raising=False)
    set_repository(InMemoryRepository())

    recorder = _SubprocessRecorder()
    monkeypatch.setattr(subprocess, "run", recorder.make_success())
    _patch_metric(monkeypatch)

    response = client.post(
        "/services/onboard",
        json={
            "construct_address": "acme/dev/shared/payments/checkout",
            "service_type": "web-service",
            "port": 8000,
            "idempotency_key": "onboard-misconfig",
        },
        headers=_headers(),
    )
    assert response.status_code == 500
    assert "CATALYST_STATE_BUCKET" in response.json()["detail"]
    # The subprocess MUST NOT have been invoked when the env is unset.
    assert recorder.calls == []


def test_onboard_worker_omits_alb_rule(env_setup, monkeypatch):
    """service_type=worker -> the terraform_output_fixture has no ALB rule
    in real life, so the response carries `alb_listener_rule_arn=None`."""

    recorder = _SubprocessRecorder()

    # Same fixture but with the ALB rule cleared, to mirror what the worker
    # path would actually emit from the L4 composite.
    worker_fixture = dict(TERRAFORM_OUTPUT_FIXTURE)
    worker_fixture["alb_listener_rule_arn"] = {"value": None, "type": "string"}

    def fake(cmd, **kwargs):
        recorder.calls.append(list(cmd))
        if "output" in cmd:
            stdout = json.dumps(worker_fixture)
        else:
            stdout = "ok\n"
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=stdout, stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake)
    _patch_metric(monkeypatch)

    response = client.post(
        "/services/onboard",
        json={
            "construct_address": "acme/dev/shared/payments/checkout",
            "service_type": "worker",
            "port": 8000,
            "idempotency_key": "onboard-worker-001",
        },
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["alb_listener_rule_arn"] is None


def test_onboard_subprocess_timeout_returns_500(env_setup, monkeypatch):
    """A subprocess.TimeoutExpired during apply maps to a 500 with correlation id."""

    def fake(cmd, **kwargs):
        if "apply" in cmd:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake)
    _patch_metric(monkeypatch)

    response = client.post(
        "/services/onboard",
        json={
            "construct_address": "acme/dev/shared/payments/checkout",
            "service_type": "web-service",
            "port": 8000,
            "idempotency_key": "onboard-timeout-001",
        },
        headers=_headers(),
    )
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "terraform_apply_timeout" in detail
    assert "correlation_id=" in detail
