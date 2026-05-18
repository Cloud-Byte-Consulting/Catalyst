from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SHELL_SCRIPT = REPO_ROOT / "scripts" / "bootstrap-aws-account.sh"
POWERSHELL_SCRIPT = REPO_ROOT / "scripts" / "bootstrap-aws-account.ps1"


def _write_fake_aws(tmp_path: Path) -> Path:
    aws_path = tmp_path / "aws"
    aws_path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import os
            import sys

            log_file = os.environ.get("FAKE_AWS_LOG")
            if log_file:
                with open(log_file, "a", encoding="utf-8") as handle:
                    handle.write(" ".join(sys.argv[1:]) + "\\n")

            args = sys.argv[1:]
            cmd = " ".join(args)

            if cmd.startswith("iam get-role"):
                sys.exit(255)
            if cmd.startswith("iam get-group"):
                sys.exit(255)
            if cmd.startswith("dynamodb describe-table"):
                sys.exit(255)
            if cmd.startswith("s3api head-bucket"):
                sys.exit(255)
            if cmd.startswith("iam list-attached-role-policies"):
                print("0")
                sys.exit(0)
            if cmd.startswith("iam list-open-id-connect-providers"):
                print("")
                sys.exit(0)
            if cmd.startswith("iam get-open-id-connect-provider"):
                sys.exit(255)

            print("{}")
            sys.exit(0)
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    aws_path.chmod(aws_path.stat().st_mode | stat.S_IEXEC)

    cmd_wrapper = tmp_path / "aws.cmd"
    cmd_wrapper.write_text(
        "@echo off\r\n"
        "python \"%~dp0aws\" %*\r\n",
        encoding="utf-8",
    )
    return aws_path


def _base_env(tmp_path: Path) -> dict[str, str]:
    log_file = tmp_path / "aws.log"
    fake_aws = _write_fake_aws(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{fake_aws.parent}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_AWS_LOG"] = str(log_file)
    env["AWS_REGION"] = "us-west-2"
    env["AWS_ACCOUNT_ID"] = "123456789012"
    env["GITHUB_REPOSITORY"] = "Cloud-Byte-Consulting/Catalyst"
    env["BOOTSTRAP_ADMIN_PRINCIPAL_ARN"] = "arn:aws:iam::123456789012:role/BootstrapOperator"
    return env


def _read_log(tmp_path: Path) -> str:
    log_path = tmp_path / "aws.log"
    if not log_path.exists():
        return ""
    return log_path.read_text(encoding="utf-8")


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_bash_dry_run_does_not_call_aws(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [
            "bash",
            "scripts/bootstrap-aws-account.sh",
            "--dry-run",
            "--region",
            "us-west-2",
            "--account-id",
            "123456789012",
            "--github-repository",
            "Cloud-Byte-Consulting/Catalyst",
            "--bootstrap-admin-principal-arn",
            "arn:aws:iam::123456789012:role/BootstrapOperator",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "[DRY-RUN]" in proc.stdout
    assert _read_log(tmp_path) == ""


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_bash_requires_env_values(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["AWS_REGION"] = ""
    proc = subprocess.run(
        ["bash", "scripts/bootstrap-aws-account.sh", "--dry-run"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "Missing AWS region" in proc.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_bash_rejects_example_bootstrap_principal_for_wrong_account(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [
            "bash",
            "scripts/bootstrap-aws-account.sh",
            "--dry-run",
            "--region",
            "us-east-1",
            "--account-id",
            "061051223073",
            "--github-repository",
            "Cloud-Byte-Consulting/Catalyst",
            "--bootstrap-admin-principal-arn",
            "arn:aws:iam::123456789012:role/BootstrapOperator",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    combined = proc.stderr + proc.stdout
    assert "example account 123456789012" in combined


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_bash_warns_when_bootstrap_principal_is_account_root(tmp_path: Path) -> None:
    """ADR-012 / issue #166: account:root MUST emit a [WARN] but MUST NOT block."""
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [
            "bash",
            "scripts/bootstrap-aws-account.sh",
            "--dry-run",
            "--region",
            "us-west-2",
            "--account-id",
            "123456789012",
            "--github-repository",
            "Cloud-Byte-Consulting/Catalyst",
            "--bootstrap-admin-principal-arn",
            "arn:aws:iam::123456789012:root",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    combined = _strip_ansi(proc.stderr + proc.stdout)
    assert "BOOTSTRAP_ADMIN_PRINCIPAL_ARN is account:root" in combined
    assert "ADR-012" in combined
    assert "ADR-008" in combined


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_bash_does_not_warn_when_bootstrap_principal_is_role(tmp_path: Path) -> None:
    """A scoped role principal MUST NOT trigger the account:root warning."""
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [
            "bash",
            "scripts/bootstrap-aws-account.sh",
            "--dry-run",
            "--region",
            "us-west-2",
            "--account-id",
            "123456789012",
            "--github-repository",
            "Cloud-Byte-Consulting/Catalyst",
            "--bootstrap-admin-principal-arn",
            "arn:aws:iam::123456789012:role/BootstrapOperator",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    combined = _strip_ansi(proc.stderr + proc.stdout)
    assert "BOOTSTRAP_ADMIN_PRINCIPAL_ARN is account:root" not in combined


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_bash_print_github_actions_runner_policy_is_valid_json(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env.get('PATH', '')}"
    proc = subprocess.run(
        [
            "bash",
            "scripts/bootstrap-aws-account.sh",
            "--print-github-actions-runner-policy",
            "--region",
            "us-west-2",
            "--account-id",
            "111111111111",
            "--prefix",
            "catalyst",
            "--bootstrap-role-path",
            "/catalyst/bootstrap/",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    policy = json.loads(proc.stdout.strip())
    assert policy["Version"] == "2012-10-17"
    actions = json.dumps(policy["Statement"])
    assert "PutBucketPublicAccessBlock" in actions
    assert "catalyst-tf-state-111111111111-us-west-2" in actions
    assert "catalyst-api-data-111111111111-us-west-2" in actions
    assert "S3CatalystApiDataBucket" in actions


@pytest.mark.skipif(
    shutil.which("bash") is None or os.name == "nt",
    reason="bash command-construction test requires POSIX path semantics",
)
def test_bash_constructs_expected_commands(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [
            "bash",
            "scripts/bootstrap-aws-account.sh",
            "--region",
            "us-west-2",
            "--account-id",
            "123456789012",
            "--github-repository",
            "Cloud-Byte-Consulting/Catalyst",
            "--bootstrap-admin-principal-arn",
            "arn:aws:iam::123456789012:role/BootstrapOperator",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    log = _read_log(tmp_path)
    assert "iam create-role --role-name catalyst-bootstrap-admin" in log
    assert "--path /catalyst/bootstrap/" in log
    assert "s3api create-bucket --bucket catalyst-tf-state-123456789012-us-west-2" in log
    assert "s3api create-bucket --bucket catalyst-api-data-123456789012-us-west-2" in log
    assert "dynamodb create-table --table-name catalyst-terraform-locks" in log
    assert "iam create-open-id-connect-provider" in log
    assert "iam create-role --role-name catalyst-github-plan" in log
    assert "iam create-role --role-name catalyst-github-apply" in log
    assert "iam create-role --role-name catalyst-github-deploy" in log


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not available")
def test_powershell_dry_run_does_not_call_aws(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    proc = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(POWERSHELL_SCRIPT), "-DryRun"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "[DRY-RUN]" in proc.stdout
    assert _read_log(tmp_path) == ""


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not available")
def test_powershell_requires_env_values(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["AWS_ACCOUNT_ID"] = ""
    proc = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(POWERSHELL_SCRIPT), "-DryRun"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "Missing AWS account id" in proc.stderr


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not available")
def test_powershell_rejects_example_bootstrap_principal_for_wrong_account(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(POWERSHELL_SCRIPT),
            "-DryRun",
            "-Region",
            "us-east-1",
            "-AccountId",
            "061051223073",
            "-GitHubRepository",
            "Cloud-Byte-Consulting/Catalyst",
            "-BootstrapAdminPrincipalArn",
            "arn:aws:iam::123456789012:role/BootstrapOperator",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    combined = _strip_ansi(proc.stderr + proc.stdout)
    normalized = " ".join(combined.replace("|", " ").split())
    assert "example account 123456789012" in normalized


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not available")
def test_powershell_print_github_actions_runner_policy_is_valid_json(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env.get('PATH', '')}"
    proc = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(POWERSHELL_SCRIPT),
            "-PrintGitHubActionsRunnerPolicy",
            "-Region",
            "us-west-2",
            "-AccountId",
            "111111111111",
            "-Prefix",
            "catalyst",
            "-BootstrapRolePath",
            "/catalyst/bootstrap/",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    policy = json.loads(proc.stdout.strip())
    assert policy["Version"] == "2012-10-17"
    dumped = json.dumps(policy["Statement"])
    assert "PutBucketPublicAccessBlock" in dumped
    assert "catalyst-api-data-111111111111-us-west-2" in dumped
    assert "S3CatalystApiDataBucket" in dumped


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not available")
def test_powershell_constructs_expected_commands(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    proc = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(POWERSHELL_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    log = _read_log(tmp_path)
    assert "iam create-role --role-name catalyst-bootstrap-admin" in log
    assert "--path /catalyst/bootstrap/" in log
    assert "s3api create-bucket --bucket catalyst-tf-state-123456789012-us-west-2" in log
    assert "s3api create-bucket --bucket catalyst-api-data-123456789012-us-west-2" in log
    assert "dynamodb create-table --table-name catalyst-terraform-locks" in log
    assert "iam create-open-id-connect-provider" in log
    assert "iam create-role --role-name catalyst-github-plan" in log
    assert "iam create-role --role-name catalyst-github-apply" in log
    assert "iam create-role --role-name catalyst-github-deploy" in log
