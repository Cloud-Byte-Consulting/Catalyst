from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Tier 1 write models — per-endpoint Pydantic shapes that mirror the CLI
# contract (clients/catalyst-cli/catalyst_cli.py) and ADR-007 §Tier 1.
#
# Every model sets ``extra="forbid"`` so future CLI/API drift surfaces as a
# 422 validation error rather than silently dropping the offending field —
# the exact failure mode that motivated issue #177.
# ---------------------------------------------------------------------------


class LandingZoneCreateRequest(BaseModel):
    """``POST /orgs/{tenant}/landing-zones`` request body.

    Adds ``account_id`` (12-digit AWS account ID) and ``compliance`` to the
    original ``tenant``/``name``/``idempotency_key`` shape that the
    pre-#177 ``OrgWriteRequest`` declared. See ADR-007 §Tier 1 for the
    canonical endpoint contract.
    """

    model_config = ConfigDict(extra="forbid")

    tenant: str
    name: str
    account_id: str = Field(description="12-digit AWS account ID")
    compliance: Literal["standard", "hipaa", "pci-dss"] = "standard"
    idempotency_key: str | None = None

    @field_validator("account_id")
    @classmethod
    def _account_id_is_twelve_digits(cls, value: str) -> str:
        if not (value.isdigit() and len(value) == 12):
            raise ValueError("account_id must be a 12-digit AWS account ID")
        return value


class EnvironmentCreateRequest(BaseModel):
    """``POST /orgs/{tenant}/environments`` request body.

    Carries the parent ``landing_zone`` reference the CLI already sends so
    ``GET /orgs/{tenant}`` can surface the environment under the right LZ
    (per #169 Gherkin AC scenario 2).
    """

    model_config = ConfigDict(extra="forbid")

    tenant: str
    name: str
    landing_zone: str
    idempotency_key: str | None = None


class OuCreateRequest(BaseModel):
    """``POST /orgs/{tenant}/ous`` request body.

    No widening relative to the pre-#177 shape — the CLI already only
    sends ``tenant``/``name``/``idempotency_key`` for OUs. Defined as its
    own model purely so all four Tier 1 endpoints share the same
    ``extra="forbid"`` drift-detection contract.
    """

    model_config = ConfigDict(extra="forbid")

    tenant: str
    name: str
    idempotency_key: str | None = None


class ApplicationCreateRequest(BaseModel):
    """``POST /orgs/{tenant}/applications`` request body.

    Adds ``project`` — applications are catalog entries scoped to a project
    within the tenant, matching the construct address ``tenant/.../project/app``
    from ADR-002.
    """

    model_config = ConfigDict(extra="forbid")

    tenant: str
    project: str
    name: str
    idempotency_key: str | None = None


class ServiceOnboardRequest(BaseModel):
    construct_address: str = Field(description="tenant/env/lz/project/app")
    service_type: Literal["web-service", "worker", "scheduled-job"] = "web-service"
    port: int = 8000
    idempotency_key: str | None = None


class ServiceDeployRequest(BaseModel):
    image_tag: str
    idempotency_key: str


class ServiceConfigRequest(BaseModel):
    params: dict[str, str]
    idempotency_key: str


class ProductDeploymentRequest(BaseModel):
    tenant: str
    project: str
    app: str
    idempotency_key: str


class ProductDeploymentRecord(BaseModel):
    tenant: str
    project: str
    app: str
    lifecycle_state: Literal["planned", "deploying", "active", "failed"]
    resources: list[str]
    updated_at: datetime
