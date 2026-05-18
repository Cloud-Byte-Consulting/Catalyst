"""Parity test: CLI ``CONSTRUCT_RE`` must equal server ``CONSTRUCT_PATTERN``.

The Catalyst construct-address pattern (``tenant/env/lz/project/app``) is
enforced **twice** — once client-side in ``clients/catalyst-cli/catalyst_cli.py``
(``CONSTRUCT_RE``) and once server-side in
``services/catalyst-api/catalyst/constructs.py`` (``CONSTRUCT_PATTERN``). If a
contributor updates one without the other, the CLI and API will disagree about
what counts as a valid construct address — and the divergence will be invisible
until somebody reports a confusing 422.

This test fails loudly on drift. It deliberately AST-parses the CLI source
(rather than importing the module) so that running the test does not pull in
``knack``, ``requests``, or ``boto3``. The test only needs the regex literal,
not the runtime behavior.

Issue #172. Surfaced during peer review of PR #169.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from catalyst.constructs import CONSTRUCT_PATTERN

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_SOURCE = REPO_ROOT / "clients" / "catalyst-cli" / "catalyst_cli.py"


def _extract_cli_construct_re_pattern() -> str:
    """Read the CLI source via AST and return the literal string passed to
    ``re.compile`` for ``CONSTRUCT_RE``.

    No CLI imports happen — we walk the AST and pull the first argument out
    of the ``re.compile(...)`` call assigned to ``CONSTRUCT_RE``.
    """
    if not CLI_SOURCE.is_file():
        pytest.skip(f"CLI source not present at {CLI_SOURCE} — running outside repo?")
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "CONSTRUCT_RE"
            for target in node.targets
        ):
            continue
        # Expect the value to be `re.compile("...")` — pull the first arg literal.
        if not (isinstance(node.value, ast.Call) and node.value.args):
            raise AssertionError(
                "CONSTRUCT_RE assignment found but its value is not re.compile(...) — "
                "either the CLI changed shape or the parity test needs an update."
            )
        try:
            return ast.literal_eval(node.value.args[0])
        except (ValueError, SyntaxError) as exc:
            raise AssertionError(
                f"CONSTRUCT_RE first arg is not a constant string: {exc}"
            ) from exc
    raise AssertionError(
        f"CONSTRUCT_RE assignment not found in {CLI_SOURCE}. If the constant was "
        "renamed or moved, update this parity test in the same PR."
    )


def test_construct_regex_pattern_parity() -> None:
    """CLI and server share the same construct-address regex source string."""
    cli_pattern = _extract_cli_construct_re_pattern()
    server_pattern = CONSTRUCT_PATTERN.pattern
    assert cli_pattern == server_pattern, (
        "Construct-address regex drift between CLI and server!\n"
        f"  CLI    (clients/catalyst-cli/catalyst_cli.py): {cli_pattern!r}\n"
        f"  Server (services/catalyst-api/catalyst/constructs.py): {server_pattern!r}\n"
        "Updating one side requires updating the other. Both files should reference\n"
        "this test in their module docstring."
    )


def test_construct_regex_flags_parity() -> None:
    """Both regexes compile with the same flags (default — no IGNORECASE etc.).

    A flag-only divergence would let the server accept inputs the CLI rejects
    or vice versa, even when the source strings match. Defensive guard.
    """
    cli_pattern_str = _extract_cli_construct_re_pattern()
    cli_compiled = re.compile(cli_pattern_str)
    assert cli_compiled.flags == CONSTRUCT_PATTERN.flags, (
        f"Regex flags differ — CLI re-compile flags={cli_compiled.flags!r}, "
        f"server CONSTRUCT_PATTERN.flags={CONSTRUCT_PATTERN.flags!r}. "
        "If one side intentionally uses re.IGNORECASE or similar, the parity "
        "convention is broken."
    )


def test_construct_regex_canonical_examples() -> None:
    """The shared regex accepts the canonical 5-segment form and rejects others.

    Locks the behavior down so a future widening (e.g. underscores) is visible
    in both this test and in the parity check above. Examples mirror the ones
    documented in ADR-002 §Construct hierarchy.
    """
    accepts = [
        "cloud-byte/dev/shared/platform/app1",
        "tenant/env/lz/project/app",
        "a/b/c/d/e",
    ]
    rejects = [
        "tenant/env/lz/project",          # 4 segments, not 5
        "tenant/env/lz/project/app/extra",  # 6 segments
        "TENANT/env/lz/project/app",       # uppercase forbidden
        "tenant/env/lz/project/app_1",      # underscore forbidden
        "tenant//lz/project/app",          # empty segment
        "",
    ]
    for value in accepts:
        assert CONSTRUCT_PATTERN.match(value), f"server regex should accept {value!r}"
    for value in rejects:
        assert not CONSTRUCT_PATTERN.match(value), f"server regex should reject {value!r}"
