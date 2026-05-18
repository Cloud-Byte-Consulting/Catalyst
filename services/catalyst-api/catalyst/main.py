from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from mangum import Mangum
from pydantic import ValidationError

from .catalog import RESOURCE_CATALOG
from .constructs import ConstructAddress
from .models import (
    OrgWriteRequest,
    ProductDeploymentRecord,
    ProductDeploymentRequest,
    ServiceConfigRequest,
    ServiceDeployRequest,
    ServiceOnboardRequest,
)
from .onboard import provision_app
from .rbac import AccessContext, access_dependency, can_read_scope, require_write
from .repository import Repository, get_repository

app = FastAPI(title="Catalyst API")


def repo_dependency() -> Repository:
    return get_repository()


def _correlation_id() -> str:
    return str(uuid.uuid4())


def _idempotent_response(
    repo: Repository, idempotency_key: str | None, payload: dict, response: Response
) -> dict:
    if not idempotency_key:
        return payload
    cached = repo.get_idempotent(idempotency_key)
    if cached is not None:
        response.headers["X-Idempotent-Replay"] = "true"
        return cached
    repo.put_idempotent(idempotency_key, payload)
    return payload


def _parse_construct(value: str) -> ConstructAddress:
    try:
        return ConstructAddress(value=value)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/catalog")
def catalog(access: AccessContext = Depends(access_dependency)) -> dict:
    return {
        "resources": [
            {"key": r.key, "category": r.category, "default_exposure": r.default_exposure}
            for r in RESOURCE_CATALOG
        ],
        "role": access.role,
    }


@app.post("/orgs/{tenant}/ous")
def create_ou(
    tenant: str,
    request: OrgWriteRequest,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier1")
    repo.append_org_record(tenant, "ous", request.name)
    return {"tenant": tenant, "ou_name": request.name, "correlation_id": _correlation_id()}


@app.post("/orgs/{tenant}/landing-zones")
def create_landing_zone(
    tenant: str,
    request: OrgWriteRequest,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier1")
    repo.append_org_record(tenant, "landing_zones", request.name)
    return {"tenant": tenant, "landing_zone": request.name, "correlation_id": _correlation_id()}


@app.post("/orgs/{tenant}/environments")
def create_environment(
    tenant: str,
    request: OrgWriteRequest,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier1")
    repo.append_org_record(tenant, "environments", request.name)
    return {"tenant": tenant, "environment": request.name, "correlation_id": _correlation_id()}


@app.post("/orgs/{tenant}/applications")
def create_application(
    tenant: str,
    request: OrgWriteRequest,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier1")
    repo.append_org_record(tenant, "applications", request.name)
    return {"tenant": tenant, "application": request.name, "correlation_id": _correlation_id()}


@app.get("/orgs/{tenant}")
def get_org(
    tenant: str,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    if not can_read_scope(access, tenant):
        raise HTTPException(status_code=403, detail="insufficient_permissions")
    return {"tenant": tenant, "structure": repo.get_organization(tenant), "correlation_id": _correlation_id()}


@app.post("/services/onboard")
def onboard_service(
    request: ServiceOnboardRequest,
    response: Response,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    """Tier 2 onboard: synchronously provision per-app AWS resources via Terraform.

    Replaces the v1 stubbed-ARN handler with the real ``terraform apply``
    flow committed in ADR-014. The L4 backend key is generated per
    invocation following ADR-015's state-key hierarchy
    (``catalyst/tenants/{tenant}/environments/{env}/apps/{app}.tfstate``)
    inside ``provision_app``.

    Idempotency continues to flow through the existing
    ``_idempotent_response`` wrapper — first call drives the Terraform
    apply, replay returns the cached payload without re-invoking
    ``provision_app`` (so Terraform's own S3-state convergence is only
    exercised on the first call within the 24h idempotency window).
    """

    require_write(access, "tier2")
    construct = _parse_construct(request.construct_address)
    cached = repo.get_idempotent(request.idempotency_key)
    if cached is not None:
        response.headers["X-Idempotent-Replay"] = "true"
        return cached
    repo.init_service(construct.value)
    correlation_id = _correlation_id()
    result = provision_app(
        construct.value,
        idempotency_key=request.idempotency_key,
        correlation_id=correlation_id,
        service_type=request.service_type,
    )
    payload = {
        "construct_address": result.construct_address,
        "ecr_uri": result.ecr_uri,
        "execution_role_arn": result.execution_role_arn,
        "log_group_name": result.log_group_name,
        "alb_listener_rule_arn": result.alb_listener_rule_arn,
        "catalog_record_key": result.catalog_record_key,
        "state_key": result.state_key,
        "status": "provisioned",
        "correlation_id": correlation_id,
    }
    return _idempotent_response(repo, request.idempotency_key, payload, response)


@app.post("/services/{construct_address:path}/deploy")
def deploy_service(
    construct_address: str,
    request: ServiceDeployRequest,
    response: Response,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier2")
    construct = _parse_construct(construct_address)
    if repo.get_service(construct.value) is None:
        raise HTTPException(status_code=404, detail="service_not_found")
    event = {"image_tag": request.image_tag, "at": repo.now().isoformat()}
    repo.append_service_deployment(construct.value, event)
    payload = {
        "construct_address": construct.value,
        "deployed_image_tag": request.image_tag,
        "deployment_status": "stabilizing",
        "correlation_id": _correlation_id(),
    }
    return _idempotent_response(repo, request.idempotency_key, payload, response)


@app.get("/services/{construct_address:path}")
def service_status(
    construct_address: str,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    construct = _parse_construct(construct_address)
    tenant, _, _, project, _ = construct.value.split("/")
    if not can_read_scope(access, tenant, project):
        raise HTTPException(status_code=403, detail="insufficient_permissions")
    service = repo.get_service(construct.value)
    if not service:
        raise HTTPException(status_code=404, detail="service_not_found")
    deployments = service["deployments"]
    latest = deployments[-1] if deployments else None
    return {
        "construct_address": construct.value,
        "current_image_tag": latest["image_tag"] if latest else "none",
        "running_task_count": 1 if latest else 0,
        "last_deploy_at": latest["at"] if latest else None,
        "correlation_id": _correlation_id(),
    }


@app.post("/services/{construct_address:path}/config")
def service_config(
    construct_address: str,
    request: ServiceConfigRequest,
    response: Response,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier2")
    construct = _parse_construct(construct_address)
    repo.update_service_config(construct.value, request.params)
    payload = {
        "construct_address": construct.value,
        "ssm_path_prefix": f"/catalyst/{construct.value}/config/",
        "param_count": len(request.params),
        "correlation_id": _correlation_id(),
    }
    return _idempotent_response(repo, request.idempotency_key, payload, response)


@app.get("/iam/groups")
def list_groups(access: AccessContext = Depends(access_dependency)) -> dict:
    return {
        "groups": [
            "catalyst-owners",
            "catalyst-administrators",
            "catalyst-viewers",
            "catalyst-support-admins",
            "catalyst-support-operators",
            "catalyst-support-viewers",
            "catalyst-breakglass",
        ],
        "correlation_id": _correlation_id(),
    }


@app.post("/iam/groups/{group}/members")
def update_group_membership(
    group: str,
    user_arn: str = Header(...),
    action: str = Header(...),
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    if access.role != "owner":
        raise HTTPException(status_code=403, detail="insufficient_permissions")
    repo.record_group_action(group, action, user_arn)
    return {"group": group, "action": action, "correlation_id": _correlation_id()}


@app.post("/products/deploy")
def deploy_product(
    request: ProductDeploymentRequest,
    response: Response,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    require_write(access, "tier2")
    key = f"{request.tenant}/{request.project}/{request.app}"
    now = datetime.now(timezone.utc)
    record = ProductDeploymentRecord(
        tenant=request.tenant,
        project=request.project,
        app=request.app,
        lifecycle_state="planned",
        resources=[r.key for r in RESOURCE_CATALOG],
        updated_at=now,
    )
    repo.put_product(key, record.model_dump(mode="json"))
    payload = {"product_instance": repo.get_product(key), "correlation_id": _correlation_id()}
    return _idempotent_response(repo, request.idempotency_key, payload, response)


@app.get("/products")
def list_products(
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    visible = []
    for record in repo.list_products():
        if can_read_scope(access, record["tenant"], record["project"]):
            visible.append(record)
    return {"instances": visible, "count": len(visible), "correlation_id": _correlation_id()}


@app.get("/products/{tenant}/{project}/{app_name}")
def get_product(
    tenant: str,
    project: str,
    app_name: str,
    access: AccessContext = Depends(access_dependency),
    repo: Repository = Depends(repo_dependency),
) -> dict:
    if not can_read_scope(access, tenant, project):
        raise HTTPException(status_code=403, detail="insufficient_permissions")
    key = f"{tenant}/{project}/{app_name}"
    record = repo.get_product(key)
    if record is None:
        raise HTTPException(status_code=404, detail="product_not_found")
    return {"product_instance": record, "correlation_id": _correlation_id()}


handler = Mangum(app)
