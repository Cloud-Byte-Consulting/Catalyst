"""Role resolution for the Catalyst API.

The API supports two resolution modes, selected by ``CATALYST_AUTH_MODE``:

* ``headers`` (default; used by tests and local dev) — read the caller ARN
  and IAM group list directly from the ``x-caller-arn`` /
  ``x-iam-groups`` request headers. This is how the in-cluster CLI and the
  pytest suite drive the API without standing up STS or IAM.

* ``sigv4`` (production) — read ``x-catalyst-identity-url``, replay it
  against STS to verify the caller's IAM identity (see
  :mod:`catalyst.identity`), then call ``iam:ListGroupsForUser`` to
  resolve their groups. The result is cached per-process for the configured
  TTL so steady-state traffic does not hit STS/IAM on every request.

Group naming follows ADR-008 and the migration note at
``docs/migrations/2026-05-15-rbac-scoped-group-delimiter.md`` —
``catalyst-{tenant}--{project}--{role}``, with backward compatibility for
the legacy single-hyphen form.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request


@dataclass
class AccessContext:
    role: str
    scopes: list[tuple[str, str]]
    caller_arn: str = ""


_GROUP_CACHE: dict[tuple[str, tuple[str, ...]], tuple[datetime, AccessContext]] = {}
_DEFAULT_CACHE_TTL = timedelta(minutes=5)


def _cache_ttl() -> timedelta:
    try:
        from .settings import get_settings

        return timedelta(seconds=get_settings().iam_group_cache_ttl_seconds)
    except Exception:  # noqa: BLE001 - settings should never block the request path
        return _DEFAULT_CACHE_TTL


def _parse_scoped_group(group: str) -> tuple[str, str] | None:
    if not group.startswith("catalyst-"):
        return None

    for role in ("admins", "operators", "viewers"):
        modern_suffix = f"--{role}"
        if group.endswith(modern_suffix):
            body = group[len("catalyst-") : -len(modern_suffix)]
            if "--" not in body:
                return None
            tenant, project = body.split("--", 1)
            if tenant and project:
                return (tenant, project)
            return None

        legacy_suffix = f"-{role}"
        if group.endswith(legacy_suffix):
            body = group[len("catalyst-") : -len(legacy_suffix)]
            if "-" not in body:
                return None
            tenant, project = body.rsplit("-", 1)
            if tenant and project:
                return (tenant, project)
            return None
    return None


def _access_from_groups(groups: list[str], *, caller_arn: str = "") -> AccessContext:
    if "catalyst-breakglass" in groups or "catalyst-owners" in groups:
        return AccessContext("owner", [("*", "*")], caller_arn=caller_arn)
    if "catalyst-support-admins" in groups or "catalyst-administrators" in groups:
        return AccessContext("administrator", [("*", "*")], caller_arn=caller_arn)
    if "catalyst-support-viewers" in groups or "catalyst-viewers" in groups:
        return AccessContext("viewer", [("*", "*")], caller_arn=caller_arn)

    scopes: list[tuple[str, str]] = []
    for group in groups:
        parsed = _parse_scoped_group(group)
        if parsed:
            scopes.append(parsed)

    if scopes:
        return AccessContext("scoped", scopes, caller_arn=caller_arn)
    return AccessContext("none", [], caller_arn=caller_arn)


def resolve_access(caller: str, groups: list[str]) -> AccessContext:
    cache_key = (caller, tuple(sorted(groups)))
    now = datetime.now(timezone.utc)
    if cache_key in _GROUP_CACHE:
        cached_at, cached = _GROUP_CACHE[cache_key]
        if now - cached_at <= _cache_ttl():
            return cached

    resolved = _access_from_groups(groups, caller_arn=caller)
    _GROUP_CACHE[cache_key] = (now, resolved)
    return resolved


def _clear_cache() -> None:
    """Test seam — drop the per-process IAM group cache."""

    _GROUP_CACHE.clear()


def require_write(access: AccessContext, tier: str) -> None:
    if access.role == "owner":
        return
    if tier == "tier2" and access.role in {"administrator", "scoped"}:
        return
    raise HTTPException(status_code=403, detail="insufficient_permissions")


def can_read_scope(access: AccessContext, tenant: str, project: str | None = None) -> bool:
    if access.role in {"owner", "administrator", "viewer"}:
        return True
    return any(t == tenant and (project is None or p == project) for t, p in access.scopes)


async def access_dependency(request: Request) -> AccessContext:
    """FastAPI dependency that turns a request into an :class:`AccessContext`.

    Selects between ``headers`` (test/local) and ``sigv4`` (production) based
    on ``CATALYST_AUTH_MODE``. Production failures result in HTTP 401 so the
    error is distinguishable from authorisation failures (HTTP 403).
    """

    try:
        from .settings import get_settings

        auth_mode = get_settings().auth_mode
    except Exception:  # noqa: BLE001 - settings problems are non-fatal here
        auth_mode = "headers"

    if auth_mode == "sigv4":
        return await _resolve_sigv4(request)

    caller = request.headers.get("x-caller-arn", "anonymous")
    groups = [g.strip() for g in request.headers.get("x-iam-groups", "").split(",") if g.strip()]
    return resolve_access(caller, groups)


async def _resolve_sigv4(request: Request) -> AccessContext:
    presigned_url = request.headers.get("x-catalyst-identity-url")
    if not presigned_url:
        raise HTTPException(
            status_code=401,
            detail="missing x-catalyst-identity-url; sign sts:GetCallerIdentity and forward the URL",
        )
    state = getattr(request.app, "state", None)
    verifier = getattr(state, "identity_verifier", None) if state else None
    group_lookup = getattr(state, "group_lookup", None) if state else None

    if verifier is None:
        from .identity import verify_presigned_identity as verifier  # type: ignore[assignment]
    if group_lookup is None:
        from .identity import fetch_iam_groups as group_lookup  # type: ignore[assignment]

    try:
        identity = verifier(presigned_url)  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001 - rewrap to consistent 401
        raise HTTPException(status_code=401, detail=f"identity_verification_failed: {exc}") from exc

    cache_key = (identity.arn, ())
    now = datetime.now(timezone.utc)
    cached = _GROUP_CACHE.get(cache_key)
    if cached and now - cached[0] <= _cache_ttl():
        return cached[1]

    try:
        groups = list(group_lookup(identity.arn))  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"group_lookup_failed: {exc}"
        ) from exc

    resolved = _access_from_groups(groups, caller_arn=identity.arn)
    _GROUP_CACHE[cache_key] = (now, resolved)
    return resolved
