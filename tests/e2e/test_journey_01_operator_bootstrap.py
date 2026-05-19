"""Journey 01 — Operator bootstrap (Track A).

The operator-side bootstrap (Terraform apply, OIDC role wiring, ALB
plumbing) is exercised by ``ci-smoke.yml`` + ``docs/smoke-tests.md`` Tier
1. What this journey locks down is the *contract the API exposes once
bootstrap is complete*:

* ``GET /health`` returns ``{"status": "ok"}`` with a correlation id
  threaded into both the body and the ``X-Correlation-ID`` response
  header (#61 middleware).
* ``GET /iam/groups`` lists the canonical Catalyst group vocabulary
  (ADR-008) — so a regression that drops one of the three core groups
  surfaces here before it breaks an RBAC journey downstream.

Both endpoints are read-only and safe to run against a live stack.

Gherkin AC §1: "all six journey tests pass against moto-mocked AWS …
finishes in under 60 seconds".
"""

from __future__ import annotations

import uuid


def test_health_returns_ok_with_correlation_id(client, correlation_id_header):
    """Liveness probe round-trips the correlation id in body + header."""

    response = client.get("/health", headers=correlation_id_header)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["correlation_id"] == correlation_id_header["X-Correlation-ID"]
    assert response.headers["X-Correlation-ID"] == correlation_id_header["X-Correlation-ID"]


def test_health_generates_correlation_id_when_absent(client):
    """Caller may omit X-Correlation-ID; the middleware mints a UUIDv4."""

    response = client.get("/health")
    assert response.status_code == 200, response.text
    body = response.json()
    minted = body["correlation_id"]
    # Must be a parseable UUID — proves the middleware is wired, not just
    # echoing an empty string.
    uuid.UUID(minted)
    assert response.headers["X-Correlation-ID"] == minted


def test_iam_groups_lists_canonical_catalyst_groups(client, viewer_headers):
    """``GET /iam/groups`` surfaces the canonical Catalyst group vocabulary.

    The list must include the three core groups (owners, administrators,
    viewers) plus the support-tier and breakglass groups. Asserts on the
    *core three* rather than the full set so an intentional extension
    (e.g. a new tenant-scoped flavour) doesn't break this contract test.
    """

    response = client.get("/iam/groups", headers=viewer_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    groups = set(body["groups"])
    # Three canonical groups every Catalyst stack must expose.
    assert {
        "catalyst-owners",
        "catalyst-administrators",
        "catalyst-viewers",
    } <= groups, f"missing canonical core groups; got {sorted(groups)}"
    # Correlation-id round-trip on a non-trivial endpoint.
    assert "correlation_id" in body
