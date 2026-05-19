"""Shared terraform subprocess-fake helpers for the onboard-driven journeys.

Lives outside ``conftest.py`` so journey test files can ``from
tests.e2e._terraform_fakes import ...`` without depending on pytest's
conftest discovery (conftest fixtures are auto-injected via the
function signature; plain helper classes/functions are not).

Mirrors the ``_SubprocessRecorder`` pattern from
``services/catalyst-api/tests/test_onboard.py`` (the #192 / #167 fix).
"""

from __future__ import annotations

import json
import subprocess
from typing import Any


def make_terraform_output_fixture(
    *, account_id: str, region: str, tenant: str, project: str, app_name: str
) -> dict:
    """Build a Terraform-output JSON fixture for a given construct address.

    Mirrors the L4 composite's ``outputs.tf`` contract (per ADR-014/15)
    so the onboard handler converts these into an :class:`OnboardResult`
    that round-trips back through ``POST /services/onboard``.
    """

    return {
        "ecr_uri": {
            "value": f"{account_id}.dkr.ecr.{region}.amazonaws.com/{tenant}-{project}-{app_name}",
            "type": "string",
        },
        "execution_role_arn": {
            "value": f"arn:aws:iam::{account_id}:role/{tenant}-{project}-{app_name}-exec",
            "type": "string",
        },
        "log_group_name": {
            "value": f"/aws/catalyst/{tenant}/dev/{project}/{app_name}",
            "type": "string",
        },
        "alb_listener_rule_arn": {
            "value": (
                f"arn:aws:elasticloadbalancing:{region}:{account_id}:"
                f"listener-rule/app/catalyst-alb/aaaa/bbbb/cccc"
            ),
            "type": "string",
        },
        "catalog_record_key": {
            "value": f"APP#{tenant}/dev/shared/{project}/{app_name}|META",
            "type": "string",
        },
        "construct_address": {
            "value": f"{tenant}/dev/shared/{project}/{app_name}",
            "type": "string",
        },
    }


class TerraformSubprocessRecorder:
    """Captures the full argv of every ``subprocess.run`` invocation.

    Lifted from ``test_onboard.py`` so journey tests don't reimplement
    the pattern. The ``output_fixture`` is JSON-serialised on each
    ``terraform output -json`` call so the onboard handler's parser is
    exercised end-to-end.
    """

    def __init__(self, output_fixture: dict) -> None:
        self.calls: list[list[str]] = []
        self.output_fixture = output_fixture

    def fake(self, cmd: list[str], **_kwargs: Any) -> Any:
        self.calls.append(list(cmd))
        if "output" in cmd:
            stdout = json.dumps(self.output_fixture)
        else:
            stdout = "Terraform has been successfully initialized!\n"
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=stdout, stderr=""
        )
