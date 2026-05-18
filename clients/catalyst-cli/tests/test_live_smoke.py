"""Opt-in live-stack smoke tests for the Catalyst CLI (#157).

These tests hit a real Catalyst ALB. They auto-skip when
``CATALYST_API_ENDPOINT`` is not set, so the default ``pytest`` invocation
remains hermetic. Run them explicitly with ``pytest -m live`` after a
deploy to catch integration regressions (header casing, content-type,
allowlist behavior, cold-start timeout) that the mock-based tests can't
see.

The default CI invocation is ``pytest -m 'not live' ...`` — see
``.github/workflows/pr-checks.yml`` cli-tests job.

Manual invocation (post-deploy or pre-demo):

    export CATALYST_API_ENDPOINT="http://catalyst-alb-XXXX.us-east-1.elb.amazonaws.com"
    pytest -m live clients/catalyst-cli/tests -v

The endpoint must be reachable from the test machine (the ALB ingress
allowlist must include the test machine's egress IP). See
``docs/smoke-tests.md`` Tier 2 for the canonical curl equivalents.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

CLI_DIR = Path(__file__).resolve().parent.parent
if str(CLI_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_DIR))

import catalyst_cli  # noqa: E402

# Auto-skip the whole module when no endpoint is configured. This is
# cleaner than per-test skipif because the module-level marker also
# applies to test-collection in `pytest -m live --collect-only`.
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("CATALYST_API_ENDPOINT"),
        reason="live smoke requires CATALYST_API_ENDPOINT pointing at a reachable ALB",
    ),
]


@pytest.fixture(autouse=True)
def _live_env(monkeypatch):
    """Default to unauthenticated mode unless the operator has set
    CATALYST_AUTH explicitly. The live tests use endpoints that work
    without SigV4 (in CATALYST_AUTH_MODE=headers, the API server's
    default per ADR-008).
    """
    if not os.environ.get("CATALYST_AUTH"):
        monkeypatch.setenv("CATALYST_AUTH", "none")


def test_live_health_returns_status_ok():
    """GET /health returns {"status":"ok"} from the live ALB within 5s."""
    payload = catalyst_cli.health_command()
    assert isinstance(payload, dict), payload
    assert payload.get("status") == "ok", payload


def test_live_catalog_returns_canonical_resources():
    """GET /catalog returns the canonical RESOURCE_CATALOG.

    The count must match the source-of-truth in
    ``services/catalyst-api/catalyst/catalog.py``. We import the catalog
    module to read the expected count rather than hardcoding it — that
    way the test stays correct if the catalog is intentionally extended.
    """
    payload = catalyst_cli.catalog_list_command()
    assert isinstance(payload, dict), payload
    resources = payload.get("resources")
    assert isinstance(resources, list), payload
    assert len(resources) >= 1, f"resources should be non-empty: {payload}"
    # Best-effort upstream-count comparison. If services/catalyst-api is
    # not importable from this test (e.g. running CLI tests in isolation),
    # skip the comparison rather than fail.
    api_catalog = Path(__file__).resolve().parents[2] / "services" / "catalyst-api"
    try:
        sys.path.insert(0, str(api_catalog))
        from catalyst.catalog import RESOURCE_CATALOG  # type: ignore  # noqa
        assert len(resources) == len(RESOURCE_CATALOG), (
            f"live catalog count ({len(resources)}) != canonical count "
            f"({len(RESOURCE_CATALOG)}) — service redeployed?"
        )
    except ImportError:
        pass
    finally:
        if str(api_catalog) in sys.path:
            sys.path.remove(str(api_catalog))


def test_live_services_status_invalid_address_rejected():
    """GET /services/<bad-address> errors out before sending the request.

    The CLI validates the construct address pattern locally. This protects
    against accidentally hitting the API with malformed input.
    """
    with pytest.raises(SystemExit) as exc:
        catalyst_cli.services_status_command("not-a-valid-address")
    assert "invalid construct address" in str(exc.value)


def test_live_render_round_trips_health():
    """The render() helper produces stable JSON for the live response."""
    payload = catalyst_cli.health_command()
    rendered = catalyst_cli.render(payload)
    assert isinstance(rendered, str)
    assert json.loads(rendered) == payload
