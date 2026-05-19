"""Journey 02 — Owner registers tenant → landing-zone → environment (Track B).

Walks the Tier 1 write surface end-to-end:

* ``POST /orgs/{tenant}/landing-zones`` with the widened #199 body
  (``account_id`` + ``compliance``) and asserts the new fields round-trip
  back through ``GET /orgs/{tenant}``.
* ``POST /orgs/{tenant}/environments`` linking the LZ created above.
* ``POST /orgs/{tenant}/applications`` with the ``project`` field added
  in #177/#199.
* ``GET /orgs/{tenant}`` returns the full hierarchy with all new fields
  intact.

This journey would catch a regression in any of:

* the #177 ``extra="forbid"`` discipline silently dropping a field
* the #199 widened CLI contract drifting from the API model
* the #61 correlation-id middleware not threading through writes
* the repository persistence shape (the #199 ``attributes={…}`` plumbing
  on ``InMemoryRepository.append_org_record``)
"""

from __future__ import annotations


def test_owner_walks_tier1_hierarchy_end_to_end(
    client, owner_headers, viewer_headers, tenant_slug
):
    """Single test asserts the full round-trip: write → write → write → read."""

    # ----- Landing zone -------------------------------------------------
    lz_payload = {
        "tenant": tenant_slug,
        "name": "shared",
        "account_id": "061051223073",
        "compliance": "standard",
        "idempotency_key": f"lz-{tenant_slug}",
    }
    lz_response = client.post(
        f"/orgs/{tenant_slug}/landing-zones",
        headers=owner_headers,
        json=lz_payload,
    )
    assert lz_response.status_code == 200, lz_response.text
    lz_body = lz_response.json()
    # #169 Gherkin AC scenario 1 — the response surfaces these fields verbatim.
    assert lz_body["landing_zone_id"] == f"{tenant_slug}/shared"
    assert lz_body["construct_address"] == f"{tenant_slug}/shared"
    assert lz_body["status"] == "provisioned"
    assert lz_body["account_id"] == "061051223073"
    assert lz_body["compliance"] == "standard"

    # ----- Environment --------------------------------------------------
    env_payload = {
        "tenant": tenant_slug,
        "name": "prod",
        "landing_zone": "shared",
        "idempotency_key": f"env-{tenant_slug}",
    }
    env_response = client.post(
        f"/orgs/{tenant_slug}/environments",
        headers=owner_headers,
        json=env_payload,
    )
    assert env_response.status_code == 200, env_response.text
    env_body = env_response.json()
    assert env_body["environment_id"] == f"{tenant_slug}/shared/prod"
    assert env_body["landing_zone"] == "shared"
    assert env_body["status"] == "provisioned"

    # ----- Application --------------------------------------------------
    app_payload = {
        "tenant": tenant_slug,
        "project": "payments",
        "name": "checkout",
        "idempotency_key": f"app-{tenant_slug}",
    }
    app_response = client.post(
        f"/orgs/{tenant_slug}/applications",
        headers=owner_headers,
        json=app_payload,
    )
    assert app_response.status_code == 200, app_response.text
    app_body = app_response.json()
    assert app_body["application"] == "checkout"
    assert app_body["project"] == "payments"

    # ----- GET /orgs/{tenant} — full hierarchy --------------------------
    read = client.get(f"/orgs/{tenant_slug}", headers=viewer_headers)
    assert read.status_code == 200, read.text
    structure = read.json()["structure"]
    # The #199 widened fields must survive the round-trip.
    persisted_lz = next(l for l in structure["landing_zones"] if l["name"] == "shared")
    assert persisted_lz["account_id"] == "061051223073"
    assert persisted_lz["compliance"] == "standard"
    persisted_env = next(e for e in structure["environments"] if e["name"] == "prod")
    assert persisted_env["landing_zone"] == "shared"
    persisted_app = next(a for a in structure["applications"] if a["name"] == "checkout")
    assert persisted_app["project"] == "payments"


def test_environment_referencing_unknown_landing_zone_is_a_clear_422(
    client, owner_headers, tenant_slug
):
    """Regression-locks the #169 AC scenario 3 boundary message.

    A handler that swallowed the unknown-LZ check would land the env
    silently and only blow up at deploy-time — this assertion forces a
    422 with a human-readable message at the boundary.
    """

    response = client.post(
        f"/orgs/{tenant_slug}/environments",
        headers=owner_headers,
        json={
            "tenant": tenant_slug,
            "name": "prod",
            "landing_zone": "never-registered",
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    # #61 harmonised error body → {error, correlation_id, detail} under "detail".
    envelope = body.get("detail", body)
    assert envelope["error"] == "ValidationFailure"
    assert "unknown landing zone" in envelope["detail"]
    assert "correlation_id" in envelope
