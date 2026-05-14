---
name: python-cli-and-testing
description: "Scaffolds Catalyst's Python CLI (using Microsoft's `knack`) and Python test suites (using `pytest` with strict markers/config, coverage gate via `pytest-cov`, and AWS service mocking via `moto`). Companion to the `aws-platform-engineering` skill — owns the Python tooling guarantees the AWS Platform Engineer persona enforces. Encoded as scaffolds rather than libraries: Catalyst keeps its dependency surface narrow."
---

# Python CLI + Testing — Cursor skill

Two bound capability families:

1. **CLI scaffolds** — Catalyst's client CLI (and any similar tool) uses
   Microsoft's [`knack`](https://github.com/microsoft/knack) framework. The
   skill's `scaffold-knack-cli` capability emits a working multi-command
   skeleton with `--help` per subcommand, table / JSON / TSV output, a
   custom YAML formatter, validators, and a custom exception class. Pytest
   tests for command parsing and output formatting come pre-wired.
2. **Test scaffolds** — `pytest` with strict markers + strict config, the
   `tests/{unit,integration,e2e}` layout, fixtures (`tmp_path`,
   `monkeypatch`, `capsys`, factory, AWS-stub via `moto`), `parametrize`
   coverage of happy + error paths, markers (`slow`, `integration`, `e2e`),
   coverage via `pytest-cov` with `--cov-fail-under=85`, and an example for
   testing an automation-service API handler.

Sources (cited in
[`docs/research/aws-agentic-platform-engineering.md`](../../../docs/research/aws-agentic-platform-engineering.md)
§Python tooling):

- pytest — [docs.pytest.org / stable](https://docs.pytest.org/en/stable/),
  [Fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html),
  [Parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html),
  [Configuration](https://docs.pytest.org/en/stable/reference/customize.html),
  [Monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html),
  [tmp_path](https://docs.pytest.org/en/stable/how-to/tmp_path.html),
  [capsys / capture](https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html),
  [Markers](https://docs.pytest.org/en/stable/how-to/mark.html).
- pytest-cov — [pypi.org/project/pytest-cov/](https://pypi.org/project/pytest-cov/).
- pytest-xdist — [pypi.org/project/pytest-xdist/](https://pypi.org/project/pytest-xdist/).
- moto — [docs.getmoto.org](https://docs.getmoto.org/).
- knack — [github.com/microsoft/knack](https://github.com/microsoft/knack);
  [docs/commands.md](https://github.com/microsoft/knack/blob/dev/docs/commands.md),
  [docs/arguments.md](https://github.com/microsoft/knack/blob/dev/docs/arguments.md),
  [docs/help.md](https://github.com/microsoft/knack/blob/dev/docs/help.md),
  [docs/output.md](https://github.com/microsoft/knack/blob/dev/docs/output.md),
  [docs/validators.md](https://github.com/microsoft/knack/blob/dev/docs/validators.md),
  [docs/events.md](https://github.com/microsoft/knack/blob/dev/docs/events.md).

> **Decision boundary** (per ADR-005 §Python tooling): `knack` for CLI;
> `pytest` for tests; `moto` for AWS mocking. No `Click` / `Typer` /
> `argparse` for new CLIs in Catalyst; no `unittest` / `nose2` for new test
> suites; no `placebo` / `vcrpy` as the default AWS-mock layer.

---

## Capability 1 — `scaffold-knack-cli`

**When to use.** Any new Python CLI inside Catalyst — the platform CLI, the
client CLI, ad-hoc operator tools that need consistent help / output /
validators. Mirrors Azure CLI's structure (knack is the framework Azure CLI
is built on per [microsoft/knack repo](https://github.com/microsoft/knack)).

**Inputs.**

- `cli_name` — short executable name (e.g., `catalyst`).
- `package_name` — Python package (e.g., `catalyst_cli`).
- `subcommand_groups` — list of top-level groups (default
  `["env", "issue", "deploy"]`).

**Output shape.**

```
<package_name>/
├── __init__.py
├── __main__.py            # python -m <package_name>
├── cli.py                 # CLI() instantiation; entry point function
├── commands.py            # CLICommandsLoader subclass + load_command_table
├── handlers.py            # the actual command-handler functions
├── arguments.py           # ArgumentsContext customisations + validators
├── help.py                # YAML help authoring per knack docs
├── validators.py          # named callables for ArgumentsContext.validator
├── formatters.py          # custom YAML output formatter (knack ships
│                          # JSON/JSON-colored/Table/TSV out of the box —
│                          # YAML is added here)
├── exceptions.py          # CatalystCliError + structured exit codes
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_handlers.py
    │   ├── test_validators.py
    │   └── test_formatters.py
    └── integration/
        └── test_cli_invocation.py
```

### Reference: `cli.py`

```python
"""Catalyst CLI entry point. Built on Microsoft's `knack` framework.

knack repo: https://github.com/microsoft/knack
knack docs (commands/arguments/help/output) cited in
docs/research/aws-agentic-platform-engineering.md §Python tooling.
"""
from __future__ import annotations

import sys
from collections import OrderedDict

from knack import CLI
from knack.commands import CLICommandsLoader, CommandGroup
from knack.arguments import ArgumentsContext
from knack.help_files import helps   # YAML help authoring per knack docs/help.md

from .exceptions import CatalystCliError, EXIT_CODES
from .formatters import register_yaml_formatter

CLI_NAME = "catalyst"


class CatalystCommandsLoader(CLICommandsLoader):
    def load_command_table(self, args):   # noqa: ARG002
        # `__name__#{}` resolves handler dotted paths into this package.
        with CommandGroup(self, "env", f"{__package__}.handlers#{{}}") as g:
            g.command("list", "env_list")
            g.command("show", "env_show")
        with CommandGroup(self, "issue", f"{__package__}.handlers#{{}}") as g:
            g.command("create", "issue_create")
            g.command("transition", "issue_transition")
        with CommandGroup(self, "deploy", f"{__package__}.handlers#{{}}") as g:
            g.command("plan", "deploy_plan")
            g.command("apply", "deploy_apply")
        return OrderedDict(self.command_table)

    def load_arguments(self, command):
        from .validators import validate_env_slug

        with ArgumentsContext(self, "") as ac:
            ac.argument(
                "output",
                options_list=("--output", "-o"),
                choices=["table", "json", "tsv", "yaml"],
                default="table",
                help="Output format. Default: table.",
            )
        with ArgumentsContext(self, "env") as ac:
            ac.argument(
                "env",
                options_list=("--env", "-e"),
                validator=validate_env_slug,
                help="Static env slug: dev | stage | prod | preview-<suffix>.",
            )
        super().load_arguments(command)


def main(argv: list[str] | None = None) -> int:
    register_yaml_formatter()    # adds 'yaml' alongside knack's built-ins
    cli = CLI(
        cli_name=CLI_NAME,
        config_dir=None,
        commands_loader_cls=CatalystCommandsLoader,
    )
    try:
        return cli.invoke(sys.argv[1:] if argv is None else argv)
    except CatalystCliError as e:
        # Structured exit per the exceptions module — never bare-traceback.
        cli.out_file.write(f"error: {e}\n")
        return EXIT_CODES[type(e).__name__]
```

### Reference: `__main__.py`

```python
"""`python -m catalyst_cli` entry point."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
```

### Reference: `handlers.py` (sketch)

```python
"""Command handlers. Pure functions — no IO at module load. The CLI
framework wires these into the command table via dotted-path strings, so the
handler signature MUST match the `--option-name` -> `option_name` mapping
that knack derives from the function parameters (see knack/docs/arguments.md).
"""
from __future__ import annotations

from typing import Any


def env_list(output: str = "table") -> list[dict[str, Any]]:   # noqa: ARG001
    # output is consumed by the CLI core's formatter selection.
    return [
        {"name": "dev", "tenant": "catalyst", "region": "us-east-1"},
        {"name": "stage", "tenant": "catalyst", "region": "us-east-1"},
        {"name": "prod", "tenant": "catalyst", "region": "us-east-1"},
    ]


def env_show(env: str, output: str = "table") -> dict[str, Any]:   # noqa: ARG001
    return {"name": env, "tenant": "catalyst", "region": "us-east-1"}


def issue_create(title: str, body: str, label: list[str] | None = None) -> dict[str, Any]:
    return {"created": True, "title": title, "body_chars": len(body), "labels": label or []}


def issue_transition(issue: int, to_state: str) -> dict[str, str]:
    return {"issue": str(issue), "to_state": to_state, "ok": "true"}


def deploy_plan(env: str, app: str) -> dict[str, Any]:
    return {"env": env, "app": app, "diff_summary": "no changes"}


def deploy_apply(env: str, app: str) -> dict[str, Any]:
    return {"env": env, "app": app, "applied": True}
```

### Reference: `validators.py`

```python
"""Custom validators per knack/docs/arguments.md. Validators receive the
parsed namespace and may mutate it OR raise to abort the command before the
handler runs.
"""
from __future__ import annotations

import re

from .exceptions import ValidationError

_ENV_RE = re.compile(r"^(dev|stage|prod|preview-[a-z0-9-]{1,40})$")


def validate_env_slug(namespace) -> None:
    value = getattr(namespace, "env", None)
    if value is None:
        return
    if not _ENV_RE.match(value):
        raise ValidationError(
            f"--env value {value!r} is invalid; "
            "must be one of: dev, stage, prod, or preview-<suffix>."
        )
```

### Reference: `formatters.py` (custom YAML output)

```python
"""knack ships JSON / JSON-colored / Table / TSV out of the box (per
knack/docs/output.md). Catalyst CLIs additionally support YAML output via
this hook. The registration lives in cli.py to keep the entry point pure.
"""
from __future__ import annotations

from typing import Any

# Stdlib `json` + a tiny YAML emitter keeps the dep surface narrow. If
# pyyaml is already a project dep, swap to `yaml.safe_dump` and delete the
# fallback below.
try:
    import yaml as _yaml   # type: ignore[import-not-found]
except ImportError:   # pragma: no cover — fallback path
    _yaml = None


def _to_yaml(obj: Any) -> str:
    if _yaml is not None:
        return _yaml.safe_dump(obj, sort_keys=False, default_flow_style=False)

    # Minimal stdlib fallback — handles dict/list/scalar/None.
    def _emit(o: Any, indent: int = 0) -> str:
        pad = "  " * indent
        if isinstance(o, dict):
            return "".join(f"{pad}{k}: {_emit(v, indent + 1).lstrip()}" if not isinstance(v, (dict, list)) else f"{pad}{k}:\n{_emit(v, indent + 1)}" for k, v in o.items())
        if isinstance(o, list):
            return "".join(f"{pad}- {_emit(item, indent + 1).lstrip()}" for item in o)
        return f"{pad}{o!r}\n" if isinstance(o, str) else f"{pad}{o}\n"

    return _emit(obj)


def register_yaml_formatter() -> None:
    """Register 'yaml' with the knack output system.

    knack's CLI core uses `output.OutputProducer` and a registry of
    formatters keyed by output-format name (per knack/docs/output.md). The
    safest portable hook is to register on the OutputProducer class.
    """
    from knack.output import OutputProducer

    def _yaml_formatter(_, result):
        return _to_yaml(result)

    OutputProducer.format_dict["yaml"] = _yaml_formatter   # type: ignore[attr-defined]
```

### Reference: `exceptions.py`

```python
"""Structured CLI exceptions + exit codes."""


class CatalystCliError(Exception):
    """Base for all CLI errors that should produce a clean (non-traceback)
    exit. Subclasses are mapped to an integer exit code via EXIT_CODES.
    """


class ValidationError(CatalystCliError):
    """Raised by validators in arguments.py."""


class RemoteError(CatalystCliError):
    """Raised when a remote (GitHub / AWS) call fails non-recoverably."""


EXIT_CODES = {
    "ValidationError": 2,   # mirrors argparse semantics
    "RemoteError": 3,
    "CatalystCliError": 1,
}
```

### Reference: `help.py` (YAML help authoring)

```python
"""knack help authoring is YAML-based per knack/docs/help.md. Importing
this module registers help against the global `helps` dict; the CLI loader
imports this module at startup.
"""
from knack.help_files import helps

helps["env"] = """
type: group
short-summary: Commands to inspect Catalyst environments.
"""

helps["env list"] = """
type: command
short-summary: List static envs the caller has access to.
examples:
  - name: List envs as JSON
    text: catalyst env list --output json
"""

helps["env show"] = """
type: command
short-summary: Show details for a specific env.
parameters:
  - name: --env -e
    type: string
    short-summary: 'Static env slug: dev | stage | prod | preview-<suffix>.'
examples:
  - name: Inspect prod
    text: catalyst env show --env prod --output yaml
"""

helps["issue create"] = """
type: command
short-summary: Create a Catalyst tracking issue with the standard label set.
"""

helps["deploy plan"] = """
type: command
short-summary: Run terraform plan for an app in an env (read-only OIDC role).
"""
```

### Pytest tests for the CLI (sketch)

```python
# tests/unit/test_validators.py
import pytest

from catalyst_cli.exceptions import ValidationError
from catalyst_cli.validators import validate_env_slug


class _NS:
    def __init__(self, env=None):
        self.env = env


@pytest.mark.parametrize("good", ["dev", "stage", "prod", "preview-abc", "preview-2026-q2-feature"])
def test_env_slug_accepts_valid(good):
    validate_env_slug(_NS(env=good))   # does not raise


@pytest.mark.parametrize("bad", ["", "DEV", "production", "preview-", "preview-bad!", "feature/x"])
def test_env_slug_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        validate_env_slug(_NS(env=bad))


def test_env_slug_skips_when_unset():
    validate_env_slug(_NS(env=None))   # no-op
```

```python
# tests/integration/test_cli_invocation.py
"""End-to-end-ish: drive the CLI via main(argv=...) and capture output."""
import json

import pytest

from catalyst_cli.cli import main


def test_env_list_table_default(capsys):
    rc = main(["env", "list"])
    captured = capsys.readouterr()
    assert rc == 0
    # Table header per knack's table output.
    assert "Name" in captured.out or "name" in captured.out


def test_env_list_json(capsys):
    rc = main(["env", "list", "--output", "json"])
    captured = capsys.readouterr()
    assert rc == 0
    parsed = json.loads(captured.out)
    assert isinstance(parsed, list)
    assert all("name" in item for item in parsed)


def test_env_show_validation_failure(capsys):
    rc = main(["env", "show", "--env", "production"])
    captured = capsys.readouterr()
    assert rc == 2   # ValidationError -> exit 2
    assert "invalid" in captured.out.lower() or "invalid" in captured.err.lower()
```

---

## Capability 2 — `scaffold-pytest-config`

**When to use.** Any Python project (CLI, automation service, helper
library) inside Catalyst. Emits a `pyproject.toml` `[tool.pytest.ini_options]`
block, `tests/` layout, a `conftest.py` with the standard fixtures, and a
test example covering happy + error paths.

### Reference: `pyproject.toml` `[tool.pytest.ini_options]` block

```toml
# pyproject.toml — pytest config (per docs.pytest.org/.../reference/customize.html)
#
# Strict markers + strict config catch typos and unregistered markers at
# collection time. addopts -ra surfaces all non-pass results in the summary.

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "--showlocals",
    "--tb=short",
    "--import-mode=importlib",
]
markers = [
    "slow: marks tests that take >5s to run (deselect with '-m \"not slow\"')",
    "integration: cross-module integration tests (deselect with '-m \"not integration\"')",
    "e2e: end-to-end tests against a real or local-emulated AWS env (default skip)",
    "moto: tests that use the moto AWS mock library",
]
log_cli = false
log_cli_level = "INFO"
log_cli_format = "%(asctime)s %(levelname)s %(name)s %(message)s"
filterwarnings = [
    "error",                       # fail on warnings by default
    "ignore::DeprecationWarning:botocore.*",
]
# doctest opt-in — enable per-module by adding `pytest.collect_doctests = True`
# in the relevant conftest.py rather than turning on globally (loud).
# doctest_optionflags = ["NORMALIZE_WHITESPACE", "ELLIPSIS"]

[tool.coverage.run]
branch = true
source = ["src", "catalyst_cli"]
omit = ["*/tests/*", "*/__main__.py"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "@overload",
]
fail_under = 85
show_missing = true
skip_covered = false
```

### Reference: `tests/conftest.py`

```python
"""Top-level conftest — shared fixtures for every Catalyst Python project.

Fixtures intentionally lean on pytest's built-ins (tmp_path, monkeypatch,
capsys) per docs.pytest.org/.../how-to/fixtures.html. AWS mocking goes
through moto (per ADR-005 §Python tooling).
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Construct-anchor fixtures — per ADR-002, every Catalyst test should know
# what tenant / env / lz / project / app it represents.
# ---------------------------------------------------------------------------
@pytest.fixture
def construct_anchors() -> dict[str, str]:
    return {
        "tenant": "catalyst",
        "environment": "dev",
        "landing_zone": "test-lz",
        "project": "platform",
        "application": "catalyst-api",
    }


# ---------------------------------------------------------------------------
# AWS mocking — moto is the standard. The fixture sets fake credentials
# (boto3 will refuse to talk to real AWS without them) and a default region.
# ---------------------------------------------------------------------------
@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def s3_client(aws_credentials):   # noqa: ARG001
    """Return a moto-mocked S3 client. Requires `moto[s3]>=5.0`."""
    from moto import mock_aws   # local import keeps moto optional at collect time

    import boto3

    with mock_aws():
        yield boto3.client("s3", region_name="us-east-1")


@pytest.fixture
def ddb_client(aws_credentials):   # noqa: ARG001
    from moto import mock_aws
    import boto3

    with mock_aws():
        yield boto3.client("dynamodb", region_name="us-east-1")


# ---------------------------------------------------------------------------
# Factory fixture — produces stub records for tests that need many.
# ---------------------------------------------------------------------------
@pytest.fixture
def make_issue_payload() -> Any:
    counter = {"n": 0}

    def _make(**overrides: Any) -> dict[str, Any]:
        counter["n"] += 1
        base = {
            "number": counter["n"],
            "title": f"Test issue {counter['n']}",
            "labels": ["type/kaizen", "tenant/catalyst", "env/dev"],
            "state": "open",
        }
        base.update(overrides)
        return base

    return _make


# ---------------------------------------------------------------------------
# Filesystem fixture — pytest's tmp_path is fine; this just shows the
# convention for tests that need a "repo-like" tree.
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_repo(tmp_path) -> Iterator[Any]:
    (tmp_path / ".github").mkdir()
    (tmp_path / "docs" / "ADR").mkdir(parents=True)
    (tmp_path / "infrastructure").mkdir()
    yield tmp_path


# ---------------------------------------------------------------------------
# Auto-skip for env-gated tests.
# ---------------------------------------------------------------------------
def pytest_collection_modifyitems(config, items):   # noqa: ARG001
    skip_e2e = pytest.mark.skip(reason="e2e tests require RUN_E2E=1")
    if os.environ.get("RUN_E2E") != "1":
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)
```

### Reference: parametrize covering happy + error paths

```python
# tests/unit/test_label_parser.py
import pytest


@pytest.mark.parametrize(
    "labels,expected_tenant,expected_env",
    [
        (["tenant/catalyst", "env/dev"], "catalyst", "dev"),
        (["env/prod", "tenant/catalyst"], "catalyst", "prod"),
        (["tenant/customer-a", "env/preview-pr-42"], "customer-a", "preview-pr-42"),
    ],
    ids=["dev-anchored", "prod-reversed-order", "preview-customer-a"],
)
def test_extracts_construct_anchors(labels, expected_tenant, expected_env):
    from catalyst_api.labels import extract_construct_anchors

    result = extract_construct_anchors(labels)
    assert result["tenant"] == expected_tenant
    assert result["environment"] == expected_env


@pytest.mark.parametrize(
    "labels,expected_error",
    [
        ([], "missing tenant"),
        (["env/dev"], "missing tenant"),
        (["tenant/catalyst"], "missing environment"),
        (["tenant/", "env/dev"], "empty tenant"),
        (["tenant/catalyst", "env/PROD"], "invalid env slug"),
    ],
    ids=["empty", "no-tenant", "no-env", "empty-tenant", "uppercase-env"],
)
def test_rejects_malformed_labels(labels, expected_error):
    from catalyst_api.labels import extract_construct_anchors, LabelError

    with pytest.raises(LabelError, match=expected_error):
        extract_construct_anchors(labels)
```

### Reference: testing the automation service API

The service handler MUST be factored so business logic is unit-testable
*without* the HTTP / Lambda envelope. The skill emits this shape:

```python
# src/catalyst_api/handler.py
"""Lambda + FastAPI both call into pure-Python business logic. Tests run
against the business logic directly; an integration test exercises the
HTTP-shape via httpx.AsyncClient OR the Lambda-shape via direct invoke."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IssueCreated:
    number: int
    url: str


def create_kaizen_issue(
    *,
    title: str,
    body: str,
    construct_anchors: dict[str, str],
    gh_client: Any,   # injected — tests pass a fake; runtime passes a real client
) -> IssueCreated:
    """Pure business logic. No HTTP, no boto3, no Lambda context."""
    if not title.strip():
        raise ValueError("title must be non-empty")

    labels = [
        "type/kaizen",
        f"tenant/{construct_anchors['tenant']}",
        f"env/{construct_anchors['environment']}",
        f"project/{construct_anchors['project']}",
        f"app/{construct_anchors['application']}",
    ]
    resp = gh_client.create_issue(title=title, body=body, labels=labels)
    return IssueCreated(number=resp["number"], url=resp["html_url"])
```

```python
# tests/unit/test_handler_business_logic.py
from catalyst_api.handler import IssueCreated, create_kaizen_issue


class _FakeGhClient:
    def __init__(self):
        self.calls = []

    def create_issue(self, *, title, body, labels):
        self.calls.append({"title": title, "body": body, "labels": labels})
        return {"number": 42, "html_url": f"https://example/issues/42"}


def test_create_kaizen_issue_happy(construct_anchors):
    gh = _FakeGhClient()
    result = create_kaizen_issue(
        title="add static-egress VPC for partner-x",
        body="...",
        construct_anchors=construct_anchors,
        gh_client=gh,
    )
    assert isinstance(result, IssueCreated)
    assert result.number == 42
    call = gh.calls[0]
    assert "type/kaizen" in call["labels"]
    assert f"tenant/{construct_anchors['tenant']}" in call["labels"]


def test_create_kaizen_issue_rejects_blank_title(construct_anchors):
    import pytest

    gh = _FakeGhClient()
    with pytest.raises(ValueError, match="title must be non-empty"):
        create_kaizen_issue(title="   ", body="x", construct_anchors=construct_anchors, gh_client=gh)
    assert gh.calls == []   # no remote call attempted
```

```python
# tests/integration/test_handler_http.py
"""HTTP-shape integration test. Sync TestClient is acceptable; the async
variant uses httpx.AsyncClient with @pytest.mark.asyncio — only needed if
the handler is itself async."""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_post_kaizen_via_http(monkeypatch):
    # Patch the GH client factory at the point of consumption so the HTTP
    # layer never reaches the network.
    from catalyst_api import app, deps
    from tests.unit.test_handler_business_logic import _FakeGhClient   # reuse

    monkeypatch.setattr(deps, "build_gh_client", lambda: _FakeGhClient())

    client = TestClient(app)
    resp = client.post(
        "/kaizens",
        json={
            "title": "rotate KMS key",
            "body": "...",
            "construct_anchors": {
                "tenant": "catalyst",
                "environment": "dev",
                "landing_zone": "test-lz",
                "project": "platform",
                "application": "catalyst-api",
            },
        },
    )
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["number"] == 42
    assert payload["url"].endswith("/issues/42")
```

### Reference: moto-backed test for AWS-touching code

```python
# tests/integration/test_s3_helpers.py
import pytest


@pytest.mark.moto
def test_uploads_sbom_to_s3(s3_client, tmp_path):
    """Demonstrates moto + tmp_path + capsys composition."""
    bucket = "catalyst-sboms"
    s3_client.create_bucket(Bucket=bucket)

    sbom = tmp_path / "sbom.spdx.json"
    sbom.write_text('{"spdxVersion": "SPDX-2.3"}')

    from catalyst_api.s3_helpers import upload_sbom

    key = upload_sbom(s3_client=s3_client, bucket=bucket, path=sbom, sha="abc123")
    assert key == "sboms/abc123/sbom.spdx.json"

    head = s3_client.head_object(Bucket=bucket, Key=key)
    assert head["ContentLength"] == sbom.stat().st_size
```

### Marker selection

```bash
# Default: skip e2e (auto-skipped by conftest unless RUN_E2E=1).
pytest

# Fast loop: unit only.
pytest -m "not integration and not e2e and not slow"

# Everything except slow.
pytest -m "not slow"

# Just moto-backed AWS tests.
pytest -m moto

# CI matrix: unit + integration with coverage gate.
pytest -m "not e2e and not slow" --cov --cov-report=xml --cov-fail-under=85

# Parallel (pytest-xdist).
pytest -n auto -m "not e2e"
```

---

## Capability 3 — `scaffold-pytest-ci-workflow`

**When to use.** Any GitHub Actions workflow that runs Python tests for
Catalyst. Pairs with `aws-platform-engineering` capability #3 (OIDC) — this
workflow does NOT touch AWS by default; if it does, it MUST adopt the OIDC
pattern from that template.

```yaml
# .github/workflows/python-tests.yml
# Generated by .cursor/skills/python-cli-and-testing capability
# `scaffold-pytest-ci-workflow` per ADR-005 §Python tooling.

name: Python — pytest

on:
  pull_request:
    paths:
      - "**/*.py"
      - "pyproject.toml"
      - "requirements*.txt"
      - ".github/workflows/python-tests.yml"
  push:
    branches: [release]
  workflow_dispatch:

permissions:
  contents: read
  pull-requests: write
  checks: write

concurrency:
  group: python-tests-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  pytest:
    name: pytest (${{ matrix.python }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python: ["3.11", "3.12"]
    steps:
      - name: Checkout
        uses: actions/checkout@v4   # pin to a verified SHA before merge

      - name: Setup Python
        uses: actions/setup-python@v5   # pin to a verified SHA before merge
        with:
          python-version: ${{ matrix.python }}
          cache: "pip"

      - name: Install
        run: |
          python -m pip install --upgrade pip
          # Pin runtime + dev deps in pyproject.toml [project.optional-dependencies].dev
          pip install -e ".[dev]"

      - name: Run pytest with coverage gate
        run: |
          pytest -q -ra --strict-markers --strict-config \
            --junitxml=junit.xml \
            --cov --cov-report=xml --cov-report=term \
            --cov-fail-under=85 \
            -m "not e2e and not slow"

      - name: Upload JUnit XML
        if: always()
        uses: actions/upload-artifact@v4   # pin to a verified SHA before merge
        with:
          name: junit-${{ matrix.python }}
          path: junit.xml
          retention-days: 30

      - name: Upload coverage XML
        if: always()
        uses: actions/upload-artifact@v4   # pin to a verified SHA before merge
        with:
          name: coverage-${{ matrix.python }}
          path: coverage.xml
          retention-days: 30
```

---

## Composition with the AWS Platform Engineering skill

- The `aws-platform-engineering` skill capability #3
  (`generate-actions-oidc-workflow`) handles workflows that touch AWS.
- This skill's capability 3 (`scaffold-pytest-ci-workflow`) is for Python
  test runs that do NOT need AWS write access. If a test workflow needs
  AWS read (e.g., to pull an Inspector finding), the workflow MUST adopt
  the OIDC pattern (read-only role) per G-1.
- AWS service mocks default to **`moto`**. `placebo` and `vcrpy` are
  available but their use must be justified in the test module's
  docstring (see ADR-005 §Python tooling).

## References

- ADR: [`docs/ADR/ADR-005-aws-agentic-platform-engineering.md`](../../../docs/ADR/ADR-005-aws-agentic-platform-engineering.md) §Python tooling
- Research: [`docs/research/aws-agentic-platform-engineering.md`](../../../docs/research/aws-agentic-platform-engineering.md) §Python tooling
- Persona: [`.cursor/agents/aws-platform-engineer.md`](../../agents/aws-platform-engineer.md) §G-14
- Workspace rule: [`.cursor/rules/aws-platform-engineering.mdc`](../../rules/aws-platform-engineering.mdc) §Python tooling
