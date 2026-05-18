import os
import sys

import pytest

SERVICE_ROOT = os.path.dirname(os.path.abspath(__file__))
if SERVICE_ROOT not in sys.path:
    sys.path.insert(0, SERVICE_ROOT)


def pytest_configure(config):
    """Register custom markers used in this suite."""

    config.addinivalue_line(
        "markers",
        (
            "real_provision_app: opt out of the conftest fake for "
            "catalyst.onboard.provision_app so the test can drive the "
            "real subprocess-stubbed flow (see tests/test_onboard.py)."
        ),
    )


@pytest.fixture(autouse=True)
def _fake_provision_app(monkeypatch, request):
    """Replace :func:`catalyst.onboard.provision_app` with a deterministic fake.

    The synchronous Terraform-in-Lambda onboard flow (#167 / ADR-014)
    invokes a real ``terraform`` subprocess. Most tests in this suite do
    not exercise the orchestration itself — they only need ``POST
    /services/onboard`` to return *a* successful payload so they can move
    on to deploy/config/status assertions. The fake here keeps the
    handler honest (it still passes through ``_idempotent_response`` and
    the correlation-id minting) without shelling out.

    Tests that DO want to drive the real orchestration (i.e.
    ``tests/test_onboard.py``) opt out of this fixture with the
    ``real_provision_app`` marker.
    """

    if "real_provision_app" in request.keywords:
        return

    from catalyst import main as main_module
    from catalyst.onboard import OnboardResult

    def fake(
        construct_address,
        idempotency_key,
        correlation_id,
        *,
        service_type="web-service",
        **_kwargs,
    ):
        tenant, environment, _lz, project, app_name = construct_address.split("/")
        return OnboardResult(
            construct_address=construct_address,
            ecr_uri=f"123456789012.dkr.ecr.us-west-2.amazonaws.com/{tenant}-{project}-{app_name}",
            execution_role_arn=f"arn:aws:iam::123456789012:role/{tenant}-{project}-{app_name}-exec",
            log_group_name=f"/aws/catalyst/{tenant}/{environment}/{project}/{app_name}",
            alb_listener_rule_arn=(
                f"arn:aws:elasticloadbalancing:us-west-2:123456789012:"
                f"listener-rule/app/catalyst-alb/aaaa/bbbb/{correlation_id[:8]}"
                if service_type == "web-service"
                else None
            ),
            catalog_record_key=f"APP#{construct_address}|META",
            correlation_id=correlation_id,
            state_key=(
                f"catalyst/tenants/{tenant}/environments/{environment}/apps/"
                f"{app_name}.tfstate"
            ),
        )

    monkeypatch.setattr(main_module, "provision_app", fake)
