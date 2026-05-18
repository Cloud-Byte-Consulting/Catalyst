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
``knack``, ``requests``, or ``boto3``. The test only needs the regex literal
and flags expression, not the runtime behavior.

Issue #172. Surfaced during peer review of PR #165 (peer-review suggestion #2).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from catalyst.constructs import CONSTRUCT_PATTERN

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_SOURCE = REPO_ROOT / "clients" / "catalyst-cli" / "catalyst_cli.py"


def _is_re_compile_call(call_node: ast.AST) -> bool:
    """True iff ``call_node`` is ``re.compile(...)`` specifically.

    Tightened per Copilot review on PR #179: previously this checked only
    that the RHS was *some* call with args, which would false-pass on a
    wrapper like ``CONSTRUCT_RE = wrap(re.compile(r"..."))``. Now we
    require ``re.compile(...)`` exactly.
    """
    if not isinstance(call_node, ast.Call):
        return False
    func = call_node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr != "compile":
        return False
    if not isinstance(func.value, ast.Name) or func.value.id != "re":
        return False
    return True


def _construct_re_value_node(tree: ast.AST) -> ast.Call:
    """Return the ``re.compile(...)`` Call node assigned to ``CONSTRUCT_RE``.

    Handles both ``CONSTRUCT_RE = re.compile(...)`` (Assign) and
    ``CONSTRUCT_RE: re.Pattern[str] = re.compile(...)`` (AnnAssign) shapes.
    Raises with a clear message if the constant has been renamed, moved,
    or wrapped in a non-``re.compile`` callable.
    """
    for node in ast.walk(tree):
        targets: list[ast.expr]
        value: ast.expr | None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "CONSTRUCT_RE" for t in targets):
            continue
        if value is None:
            raise AssertionError(
                "CONSTRUCT_RE has a bare type annotation with no value — "
                "the parity test cannot extract a regex source."
            )
        if not _is_re_compile_call(value):
            raise AssertionError(
                "CONSTRUCT_RE assignment found, but its value is not a direct "
                "`re.compile(...)` call. The parity test relies on a direct call "
                "so the regex source and flags can be extracted via AST. If the "
                "CLI was intentionally restructured, update this parity test in "
                "the same PR."
            )
        return value  # type: ignore[return-value]
    raise AssertionError(
        f"CONSTRUCT_RE assignment not found in {CLI_SOURCE}. If the constant was "
        "renamed or moved, update this parity test in the same PR."
    )


def _extract_cli_construct_re_pattern() -> str:
    """Return the literal string passed as ``re.compile(...)``'s first arg."""
    if not CLI_SOURCE.is_file():
        pytest.skip(f"CLI source not present at {CLI_SOURCE} — running outside repo?")
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    call = _construct_re_value_node(tree)
    if not call.args:
        raise AssertionError("CONSTRUCT_RE = re.compile() called with no arguments")
    try:
        return ast.literal_eval(call.args[0])
    except (ValueError, SyntaxError) as exc:
        raise AssertionError(
            f"CONSTRUCT_RE first arg is not a constant string: {exc}"
        ) from exc


def _extract_cli_construct_re_flags() -> int:
    """Return the resolved flags int passed to ``re.compile(...)``.

    Handles ``re.compile(p, flags=re.IGNORECASE)``, ``re.compile(p,
    re.IGNORECASE | re.MULTILINE)``, and the no-flags case (returns 0).
    The flags expression is extracted as Python source via ``ast.unparse``
    and evaluated in a sandboxed namespace exposing only ``re`` — repo-
    controlled input, no untrusted strings.

    Fixed per Copilot review on PR #179: previously this test re-compiled
    the CLI pattern string with *default* flags, which would never catch
    a CLI-only ``re.IGNORECASE`` divergence.
    """
    if not CLI_SOURCE.is_file():
        pytest.skip(f"CLI source not present at {CLI_SOURCE} — running outside repo?")
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    call = _construct_re_value_node(tree)

    flags_node: ast.expr | None = None
    if len(call.args) >= 2:
        flags_node = call.args[1]
    else:
        for kw in call.keywords:
            if kw.arg == "flags":
                flags_node = kw.value
                break

    if flags_node is None:
        return 0

    flags_src = ast.unparse(flags_node)
    # Sandboxed eval — only ``re`` is in scope, no builtins. The expression
    # comes from a file already version-controlled in this same repository,
    # so the input is trust-equivalent to anything pytest would normally
    # import. The sandbox limits what a hypothetical malicious value could
    # reference at evaluation time.
    return int(eval(flags_src, {"re": re, "__builtins__": {}}))  # noqa: S307


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
    """CLI and server compile their regex with the same flags.

    Flags-only divergence (e.g. CLI adds ``re.IGNORECASE`` while the server
    stays default) would let the server reject inputs the CLI accepts, or
    vice versa, even when the source strings match. This test extracts the
    flags expression directly from the CLI AST so a unilateral flag change
    is detected.

    Both sides are run through ``re.compile`` so Python's implicit defaults
    (e.g. ``re.UNICODE`` for ``str`` patterns) apply identically; only
    *explicit* flag divergence between CLI source and server source surfaces.
    """
    cli_pattern = _extract_cli_construct_re_pattern()
    cli_explicit_flags = _extract_cli_construct_re_flags()
    cli_compiled = re.compile(cli_pattern, cli_explicit_flags)
    assert cli_compiled.flags == CONSTRUCT_PATTERN.flags, (
        f"Regex flags differ — CLI explicit flags={cli_explicit_flags!r} "
        f"(extracted from AST), runtime-resolved CLI flags={cli_compiled.flags!r}, "
        f"server CONSTRUCT_PATTERN.flags={CONSTRUCT_PATTERN.flags!r}. "
        "If one side intentionally uses re.IGNORECASE or similar, the parity "
        "convention is broken — either update both sides or update this test "
        "in the same PR."
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
