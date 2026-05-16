from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OrgWriteRequest(BaseModel):
    tenant: str
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
