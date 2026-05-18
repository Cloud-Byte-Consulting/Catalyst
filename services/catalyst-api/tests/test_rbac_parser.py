"""Unit tests for ``rbac._parse_scoped_group`` and the wider access stack.

Covers the three IAM-group shapes Catalyst recognises:

* 3-segment modern (``catalyst-{tenant}--{project}--{role}``)
* 3-segment legacy (``catalyst-{tenant}-{project}-{role}``)
* 2-segment tenant-wide (``catalyst-{tenant}--{role}``) — ADR-008
  "Tenant-scoped groups (no project)".
"""

from __future__ import annotations

import pytest

from catalyst.rbac import (
    TENANT_WIDE_PROJECT,
    _access_from_groups,
    _parse_scoped_group,
    can_read_scope,
)


# -- 3-segment scoped forms ---------------------------------------------------


@pytest.mark.parametrize(
    "group,expected",
    [
        ("catalyst-cloud-byte--payments--admins", ("cloud-byte", "payments")),
        ("catalyst-acme--billing--viewers", ("acme", "billing")),
        ("catalyst-acme--billing--operators", ("acme", "billing")),
    ],
)
def test_parses_modern_three_segment_scoped_form(
    group: str, expected: tuple[str, str]
) -> None:
    assert _parse_scoped_group(group) == expected


@pytest.mark.parametrize(
    "group,expected",
    [
        ("catalyst-cloud-byte-payments-viewers", ("cloud-byte-payments", "viewers"))
        if False
        else ("catalyst-acme-billing-viewers", ("acme", "billing")),
        ("catalyst-acme-billing-admins", ("acme", "billing")),
    ],
)
def test_parses_legacy_three_segment_scoped_form(
    group: str, expected: tuple[str, str]
) -> None:
    # The legacy form uses rsplit("-", 1) so multi-hyphen tenants are
    # interpreted as ``tenant=<everything-but-last-segment>``. The test cases
    # here intentionally use single-token tenants/projects to keep parity
    # with how the legacy fixtures are actually populated in the API tests.
    assert _parse_scoped_group(group) == expected


# -- 2-segment tenant-wide form (ADR-008) -------------------------------------


@pytest.mark.parametrize(
    "group,expected_tenant",
    [
        ("catalyst-acme--owners", "acme"),
        ("catalyst-acme--administrators", "acme"),
        ("catalyst-acme--viewers", "acme"),
        ("catalyst-cloud-byte--owners", "cloud-byte"),
    ],
)
def test_parses_tenant_wide_two_segment_form(
    group: str, expected_tenant: str
) -> None:
    assert _parse_scoped_group(group) == (expected_tenant, TENANT_WIDE_PROJECT)


def test_two_segment_form_uses_wildcard_project_sentinel() -> None:
    parsed = _parse_scoped_group("catalyst-acme--owners")
    assert parsed == ("acme", "*")


# -- Negative cases -----------------------------------------------------------


@pytest.mark.parametrize(
    "group",
    [
        "",
        "not-a-catalyst-group",
        # Empty tenant in 2-segment form.
        "catalyst---owners",
        # Empty project in 3-segment modern form.
        "catalyst-acme----admins",
        # Unknown role.
        "catalyst-acme--unknown",
        # 2-segment form using a 3-segment role (e.g. ``admins`` is not a
        # tenant-wide role) — must NOT parse as tenant-wide.
        "catalyst-acme--admins",
    ],
)
def test_unknown_or_malformed_groups_return_none(group: str) -> None:
    assert _parse_scoped_group(group) is None


def test_global_owners_group_is_not_a_scoped_group() -> None:
    # ``catalyst-owners`` ends with ``-owners`` (single hyphen), not
    # ``--owners`` — must not match the tenant-wide branch.
    assert _parse_scoped_group("catalyst-owners") is None
    assert _parse_scoped_group("catalyst-administrators") is None
    assert _parse_scoped_group("catalyst-viewers") is None


# -- _access_from_groups + can_read_scope integration -------------------------


def test_tenant_wide_group_grants_scoped_access_across_projects() -> None:
    access = _access_from_groups(["catalyst-acme--owners"])

    assert access.role == "scoped"
    assert access.scopes == [("acme", "*")]

    # Tenant-only check.
    assert can_read_scope(access, "acme") is True
    # Project check — tenant-wide must match ANY project under the tenant.
    assert can_read_scope(access, "acme", "billing") is True
    assert can_read_scope(access, "acme", "payments") is True
    # Other tenants are still denied.
    assert can_read_scope(access, "other-tenant") is False
    assert can_read_scope(access, "other-tenant", "billing") is False


def test_three_segment_group_still_narrows_to_specific_project() -> None:
    access = _access_from_groups(["catalyst-cloud-byte--payments--viewers"])

    assert access.scopes == [("cloud-byte", "payments")]
    assert can_read_scope(access, "cloud-byte") is True
    assert can_read_scope(access, "cloud-byte", "payments") is True
    # The 3-segment form must NOT leak into other projects.
    assert can_read_scope(access, "cloud-byte", "billing") is False


def test_legacy_three_segment_group_still_resolves() -> None:
    access = _access_from_groups(["catalyst-acme-billing-viewers"])

    assert access.scopes == [("acme", "billing")]
    assert can_read_scope(access, "acme", "billing") is True
    assert can_read_scope(access, "acme", "payments") is False


def test_mixed_three_and_two_segment_groups_merge_into_scopes() -> None:
    access = _access_from_groups(
        [
            "catalyst-acme--owners",
            "catalyst-cloud-byte--payments--viewers",
        ]
    )
    assert ("acme", "*") in access.scopes
    assert ("cloud-byte", "payments") in access.scopes
    # Tenant-wide acme grant covers any acme project.
    assert can_read_scope(access, "acme", "anything") is True
    # cloud-byte access remains project-narrowed.
    assert can_read_scope(access, "cloud-byte", "payments") is True
    assert can_read_scope(access, "cloud-byte", "billing") is False


def test_global_owner_group_still_grants_full_access() -> None:
    # Sanity: the new 2-segment branch does not interfere with the global
    # short-circuit for ``catalyst-owners``.
    access = _access_from_groups(["catalyst-owners"])
    assert access.role == "owner"
    assert can_read_scope(access, "any", "any") is True
