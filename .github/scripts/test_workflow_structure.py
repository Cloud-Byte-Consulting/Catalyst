"""Local pytest harness for `validate_workflows.py`.

Run with:

    pytest .github/scripts/test_workflow_structure.py -v

It exercises the same structural checks the `ci-smoke` workflow runs, so a
local failure mirrors a CI failure exactly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_workflows import REQUIRED_FILES, validate


@pytest.fixture(scope="module")
def report():
    return validate()


def test_all_required_workflows_present(report) -> None:
    missing = [f for f in report.findings if f.check == "exists" and not f.ok]
    assert not missing, missing


def test_no_failed_checks(report) -> None:
    failed = [f for f in report.findings if not f.ok]
    assert not failed, "\n".join(
        f"{f.workflow} :: {f.check} - {f.detail}" for f in failed
    )


@pytest.mark.parametrize("workflow", REQUIRED_FILES)
def test_workflow_yaml_parses(report, workflow) -> None:
    parses = [
        f for f in report.findings
        if f.workflow == workflow and f.check == "yaml-parses"
    ]
    assert parses, f"no yaml-parses finding for {workflow}"
    assert all(f.ok for f in parses)


def test_service_cd_has_runtime_branches(report) -> None:
    relevant = [
        f for f in report.findings
        if f.workflow == "service-cd.yml" and "deploy branch" in f.check
    ]
    assert relevant, "no runtime branch findings emitted"
    assert all(f.ok for f in relevant), relevant
