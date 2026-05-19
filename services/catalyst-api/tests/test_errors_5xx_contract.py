"""Contract test — alarm enumeration ↔ ``errors.py`` 5xx-class set.

The ``http_5xx_rate`` alarm in
``infrastructure/modules/observability/main.tf`` enumerates the exact set
of error-class dimension values that map to HTTP status ≥ 500.
Enumeration (not a status-bucket filter) is the workaround for
`CloudWatch metric_query` not supporting `IN`-list filtering on
dimensions; the long-term fix tracked in **#226** adds a ``StatusBucket``
dimension to ``ErrorCount`` so this enumeration disappears.

Until #226 lands, this contract test is the load-bearing guard that
catches drift between:

  1. ``catalyst.errors.CatalystAPIError`` subclasses with
     ``status_code >= 500`` (the Python source of truth)
  2. ``ALARM_5XX_ENUMERATION`` (this file — the alarm's hard-coded list)
  3. The literal strings inside the Terraform file (re-asserted via
     regex over ``main.tf``)

If a developer adds a new 5xx error class to ``errors.py`` without
updating the alarm (Terraform) AND this test's constant, the test fails
CI with an actionable message — naming both files that need updating.

Surfaced by §2.5a skeptic on PR #224 during /pr-review-triage. See
issue **#226** for the long-term `StatusBucket` dimension fix that
eliminates the need for this enumeration.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from catalyst import errors


# ---------------------------------------------------------------------------
# The alarm enumeration — keep in lockstep with main.tf's http_5xx_rate.
# ---------------------------------------------------------------------------

#: Exact set of ``ErrorClass`` dimension values the alarm enumerates. Must
#: equal ``{Python 5xx class names} ∪ {middleware fallback strings for
#: status >= 500}``.
#:
#: - ``RepositoryFailure`` — boto3 / DynamoDB non-transient (errors.py)
#: - ``AWSTransientFailure`` — throttling, capacity exhaustion (errors.py)
#: - ``ServerError`` — fallback string emitted by observability middleware's
#:   ``_resolve_error_class`` for bare ``HTTPException`` at status >= 500
#:   that didn't go through the ``to_http_exception`` translator (lands
#:   with #60 / PR #223; on #224's release base the middleware doesn't
#:   exist yet so this dimension value won't appear in CloudWatch until
#:   #60 merges — that's a merge-order coupling, not a contract drift).
ALARM_5XX_ENUMERATION: frozenset[str] = frozenset({
    "RepositoryFailure",
    "AWSTransientFailure",
    "ServerError",
})

#: Middleware fallback strings — strings that appear in
#: ``ALARM_5XX_ENUMERATION`` but are NOT class names introspectable from
#: ``catalyst.errors``. Tracked separately so an introspection failure
#: doesn't mask a real drift.
MIDDLEWARE_FALLBACK_5XX_STRINGS: frozenset[str] = frozenset({"ServerError"})


# ---------------------------------------------------------------------------
# Terraform file location (relative to the repo root).
# ---------------------------------------------------------------------------

# tests/ is services/catalyst-api/tests/, so the repo root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]
TF_ALARM_FILE = REPO_ROOT / "infrastructure" / "modules" / "observability" / "main.tf"


# ---------------------------------------------------------------------------
# Introspection helpers.
# ---------------------------------------------------------------------------


def _introspect_5xx_error_classes_from_errors_module() -> frozenset[str]:
    """Return the set of ``CatalystAPIError`` subclass names with ``status_code >= 500``.

    Used as the Python-side source of truth; if a developer adds a new
    subclass with ``status_code = 503`` (say), it shows up here without
    any manual maintenance.
    """

    classes: set[str] = set()
    for name, obj in inspect.getmembers(errors):
        if not inspect.isclass(obj):
            continue
        if obj is errors.CatalystAPIError:
            continue
        if not issubclass(obj, errors.CatalystAPIError):
            continue
        if getattr(obj, "status_code", 0) >= 500:
            classes.add(name)
    return frozenset(classes)


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


def test_errors_5xx_classes_match_alarm_enumeration() -> None:
    """Catch the case where ``errors.py`` grows a new 5xx class but the alarm doesn't.

    The check: every ``CatalystAPIError`` subclass with ``status_code >= 500``
    must appear in ``ALARM_5XX_ENUMERATION``. The reverse (extra strings in
    the alarm enumeration that aren't classes) is allowed *only* for the
    explicit middleware-fallback strings in
    ``MIDDLEWARE_FALLBACK_5XX_STRINGS``.
    """

    api_5xx_classes = _introspect_5xx_error_classes_from_errors_module()

    missing_from_alarm = api_5xx_classes - ALARM_5XX_ENUMERATION
    assert not missing_from_alarm, (
        "errors.py has 5xx CatalystAPIError subclasses NOT enumerated in the alarm:\n"
        f"  {sorted(missing_from_alarm)}\n"
        "If you added a new 5xx class, update BOTH:\n"
        "  1. infrastructure/modules/observability/main.tf — the http_5xx_rate alarm's metric_query blocks\n"
        "  2. ALARM_5XX_ENUMERATION in this file\n"
        "Long-term fix: kaizen #226 (StatusBucket dimension)."
    )

    extras_in_alarm = ALARM_5XX_ENUMERATION - api_5xx_classes
    unexpected = extras_in_alarm - MIDDLEWARE_FALLBACK_5XX_STRINGS
    assert not unexpected, (
        "The alarm enumerates names that are NOT errors.py classes AND NOT in "
        "MIDDLEWARE_FALLBACK_5XX_STRINGS:\n"
        f"  {sorted(unexpected)}\n"
        "Did a class get renamed or removed? Update both ALARM_5XX_ENUMERATION "
        "and the Terraform file in lockstep."
    )


def test_alarm_terraform_file_enumerates_every_string() -> None:
    """The Terraform alarm file must contain each of the enumerated dimension values.

    Greps for ``ErrorClass = "<value>"`` literal strings inside ``main.tf``.
    Defends against a rename in this Python file that doesn't propagate to
    the Terraform side.
    """

    if not TF_ALARM_FILE.is_file():
        pytest.skip(
            f"Terraform alarm file not present at {TF_ALARM_FILE} — "
            "running outside the worktree?"
        )

    tf_source = TF_ALARM_FILE.read_text(encoding="utf-8")
    for class_name in sorted(ALARM_5XX_ENUMERATION):
        pattern = rf'ErrorClass\s*=\s*"{re.escape(class_name)}"'
        assert re.search(pattern, tf_source), (
            f"Terraform alarm file {TF_ALARM_FILE.name} is missing an "
            f"`ErrorClass = \"{class_name}\"` metric_query block. "
            "Either remove the value from ALARM_5XX_ENUMERATION OR add the "
            "matching metric_query block to the http_5xx_rate alarm."
        )


def test_known_5xx_classes_present_in_errors_module() -> None:
    """Sanity: the canonical 5xx classes haven't been quietly removed from errors.py.

    Defends against the case where someone deletes ``RepositoryFailure``
    or ``AWSTransientFailure`` without realizing the alarm references them.
    """

    api_5xx_classes = _introspect_5xx_error_classes_from_errors_module()
    expected_classes = {"RepositoryFailure", "AWSTransientFailure"}
    missing = expected_classes - api_5xx_classes
    assert not missing, (
        f"Canonical 5xx error classes missing from errors.py: {sorted(missing)}. "
        "These are the boto3/DynamoDB and AWS-transient surfaces; their removal "
        "would silently disable the http_5xx_rate alarm's signal."
    )
