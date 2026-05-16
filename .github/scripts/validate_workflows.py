"""Static structural validator for Catalyst GitHub Actions workflows.

Runs both in CI (via `.github/workflows/ci-smoke.yml`) and locally (via
`pytest .github/scripts/test_workflow_structure.py`).

The goal is to verify the OIDC role-assume pattern and runtime branching
without applying anything to AWS:

* every AWS-touching workflow has `permissions.id-token: write` and uses
  `aws-actions/configure-aws-credentials@v4` with a `role-to-assume` secret
* the OIDC role secrets line up with the IAM module's role outputs
  (`plan` / `apply` / `deploy`)
* `service-cd.yml` has both lambda and ecs deploy paths gated on `RUNTIME`

The validator returns a non-zero exit code when any check fails and prints a
human-readable summary of every check.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

OIDC_ROLE_SECRETS = {
    "terraform.yml": "AWS_ROLE_PLAN_ARN",
    "tf-drift.yml": "AWS_ROLE_PLAN_ARN",
    "service-cd.yml": "AWS_ROLE_DEPLOY_ARN",
}

# The consolidated terraform.yml must also reference the apply-role secret
# (used on push -> release). The OIDC validator checks role-to-assume against
# the matching plan/apply secrets via this extra rule below.
TERRAFORM_APPLY_SECRET = "AWS_ROLE_APPLY_ARN"

REQUIRED_FILES = [
    "pr-checks.yml",
    "terraform.yml",
    "tf-drift.yml",
    "service-cd.yml",
    "validate-policies.yml",
]


@dataclass
class Finding:
    workflow: str
    check: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, workflow: str, check: str, ok: bool, detail: str = "") -> None:
        self.findings.append(Finding(workflow, check, ok, detail))

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings)

    def render(self) -> str:
        lines = []
        for f in self.findings:
            mark = "PASS" if f.ok else "FAIL"
            extra = f" - {f.detail}" if f.detail else ""
            lines.append(f"[{mark}] {f.workflow} :: {f.check}{extra}")
        return "\n".join(lines)


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _all_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for job in (workflow.get("jobs") or {}).values():
        steps.extend(job.get("steps") or [])
    return steps


def _has_oidc_permissions(workflow: dict[str, Any]) -> bool:
    perms = workflow.get("permissions")
    if isinstance(perms, dict):
        return perms.get("id-token") == "write"
    return False


def _uses_configure_aws_credentials(workflow: dict[str, Any]) -> tuple[bool, str | None]:
    for step in _all_steps(workflow):
        uses = step.get("uses", "")
        if uses.startswith("aws-actions/configure-aws-credentials@"):
            with_block = step.get("with") or {}
            return True, with_block.get("role-to-assume")
    return False, None


def _service_cd_runtime_branches(workflow: dict[str, Any]) -> tuple[bool, bool, bool]:
    """Return (has_runtime_env, has_lambda_branch, has_ecs_branch)."""
    env_block = workflow.get("env") or {}
    has_runtime_env = "RUNTIME" in env_block
    lambda_branch = False
    ecs_branch = False
    for step in _all_steps(workflow):
        cond = str(step.get("if") or "")
        if "RUNTIME" in cond and "lambda" in cond:
            lambda_branch = True
        if "RUNTIME" in cond and "ecs" in cond:
            ecs_branch = True
    return has_runtime_env, lambda_branch, ecs_branch


def validate(workflows_dir: Path = WORKFLOWS) -> Report:
    report = Report()

    for required in REQUIRED_FILES:
        path = workflows_dir / required
        report.add(required, "exists", path.exists(),
                   "" if path.exists() else f"missing {path.relative_to(REPO_ROOT)}")
        if not path.exists():
            continue
        wf = _load(path)
        report.add(required, "yaml-parses", isinstance(wf, dict))
        if not isinstance(wf, dict):
            continue

        if required in OIDC_ROLE_SECRETS:
            expected_secret = OIDC_ROLE_SECRETS[required]
            report.add(required, "permissions.id-token=write",
                       _has_oidc_permissions(wf))
            uses_creds, role_expr = _uses_configure_aws_credentials(wf)
            report.add(required, "uses configure-aws-credentials", uses_creds)
            if uses_creds:
                detail = role_expr or ""
                ok = bool(role_expr) and expected_secret in (role_expr or "")
                report.add(
                    required,
                    f"role-to-assume references secrets.{expected_secret}",
                    ok,
                    detail,
                )

        if required == "terraform.yml":
            uses_creds, role_expr = _uses_configure_aws_credentials(wf)
            if uses_creds:
                ok_apply = bool(role_expr) and TERRAFORM_APPLY_SECRET in (role_expr or "")
                report.add(
                    required,
                    f"role-to-assume also references secrets.{TERRAFORM_APPLY_SECRET}",
                    ok_apply,
                    role_expr or "",
                )

        if required == "service-cd.yml":
            has_env, lam, ecs = _service_cd_runtime_branches(wf)
            report.add(required, "env.RUNTIME defined", has_env)
            report.add(required, "lambda deploy branch present", lam)
            report.add(required, "ecs deploy branch present", ecs)

        if required == "pr-checks.yml":
            steps = _all_steps(wf)
            has_fmt = any("fmt" in str(s.get("run", "")) for s in steps)
            has_validate = any("validate" in str(s.get("run", "")) for s in steps)
            has_pytest = any("pytest" in str(s.get("run", "")) for s in steps)
            report.add(required, "terraform fmt step", has_fmt)
            report.add(required, "terraform validate step", has_validate)
            report.add(required, "pytest step", has_pytest)

        if required == "validate-policies.yml":
            steps = _all_steps(wf)
            has_conftest = any("conftest" in str(s.get("run", "")) for s in steps)
            report.add(required, "conftest verify step", has_conftest)

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit findings as JSON instead of text",
    )
    parser.add_argument(
        "--workflows-dir",
        default=str(WORKFLOWS),
        help="path to .github/workflows (default: repo workflows)",
    )
    args = parser.parse_args(argv)

    report = validate(Path(args.workflows_dir))
    if args.json:
        print(json.dumps(
            {
                "ok": report.ok,
                "findings": [f.__dict__ for f in report.findings],
            },
            indent=2,
        ))
    else:
        print(report.render())
        if report.ok:
            print(f"\nAll {len(report.findings)} checks passed.")
        else:
            failed = [f for f in report.findings if not f.ok]
            print(f"\n{len(failed)} of {len(report.findings)} checks failed.")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
