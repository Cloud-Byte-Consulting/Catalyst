from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request


@dataclass
class AccessContext:
    role: str
    scopes: list[tuple[str, str]]


_GROUP_CACHE: dict[tuple[str, tuple[str, ...]], tuple[datetime, AccessContext]] = {}
_CACHE_TTL = timedelta(minutes=5)


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

        # Backward-compatibility for pre-delimiter naming:
        # catalyst-{tenant}-{project}-{role}
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


def _access_from_groups(groups: list[str]) -> AccessContext:
    if "catalyst-breakglass" in groups or "catalyst-owners" in groups:
        return AccessContext("owner", [("*", "*")])
    if "catalyst-support-admins" in groups or "catalyst-administrators" in groups:
        return AccessContext("administrator", [("*", "*")])
    if "catalyst-support-viewers" in groups or "catalyst-viewers" in groups:
        return AccessContext("viewer", [("*", "*")])

    scopes: list[tuple[str, str]] = []
    for group in groups:
        parsed = _parse_scoped_group(group)
        if parsed:
            scopes.append(parsed)

    if scopes:
        return AccessContext("scoped", scopes)
    return AccessContext("none", [])


def resolve_access(caller: str, groups: list[str]) -> AccessContext:
    cache_key = (caller, tuple(sorted(groups)))
    now = datetime.now(timezone.utc)
    if cache_key in _GROUP_CACHE:
        cached_at, cached = _GROUP_CACHE[cache_key]
        if now - cached_at <= _CACHE_TTL:
            return cached

    resolved = _access_from_groups(groups)
    _GROUP_CACHE[cache_key] = (now, resolved)
    return resolved


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
    caller = request.headers.get("x-caller-arn", "anonymous")
    groups = [g.strip() for g in request.headers.get("x-iam-groups", "").split(",") if g.strip()]
    return resolve_access(caller, groups)
