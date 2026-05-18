"""Synchronous Terraform-in-Lambda orchestration for ``POST /services/onboard``.

This module implements the v2 onboard flow chosen in
:doc:`/docs/ADR/ADR-014-services-onboard-provisioning-mode` (Option A —
synchronous ``terraform apply`` inside the Lambda). The container image
bundles the ``terraform`` binary at ``/opt/terraform/terraform`` and the
``catalyst-app`` L4 composite source at ``/opt/catalyst-app/`` (see
``Dockerfile``), so the runtime working dir is just a tiny
``main.tf`` + ``versions.tf`` that calls the bundled module.

State-key contract (ADR-015 §State-key convention):

    catalyst/tenants/{tenant}/environments/{env}/apps/{app}.tfstate

The committed Terraform declares ``backend "s3" {}`` with no inline
key — every onboard invocation supplies the per-app key dynamically via
``-backend-config="key=…"`` (ADR-015 §Backend-config generation
strategy).

The flow:

    1. Parse the construct address into its five segments.
    2. Build a working directory under ``/tmp/onboard-{correlation_id}/``
       with a small caller ``main.tf`` invoking the bundled composite.
    3. Run ``terraform init`` with backend-config flags (state bucket,
       L4 state key, region, lock table) as a subprocess.
    4. Run ``terraform apply -auto-approve`` as a subprocess.
    5. Run ``terraform output -json`` to harvest the real ARNs.
    6. Emit ``PutMetricData`` (namespace ``Catalyst/Onboard``, dimensions
       ``Endpoint=services_onboard`` + ``Result=success|failure``) plus a
       structured log line including ``endpoint``, ``correlation_id``,
       and ``state_key`` (ADR-014 §Compliance + ADR-015 §Compliance).

Failures from any subprocess raise ``HTTPException(500)`` with the
correlation id surfaced in the response so callers can correlate the
failure with the CloudWatch logs of the same invocation.

Idempotency continues to flow through the existing ``_idempotent_response``
machinery in :mod:`catalyst.main`; S3-state convergence handles AWS-side
replay automatically (ADR-014 §Rationale).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .constructs import ConstructAddress

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level configuration knobs.
#
# These are overridable via env vars for two reasons:
#
# 1. Tests need to point at a non-existent terraform binary path so the
#    subprocess fake gets a chance to run before subprocess.run goes
#    looking for the real binary. The default points at the Lambda
#    image's bundled binary path.
# 2. The composite source path is bundled at /opt/catalyst-app/ by the
#    Dockerfile but a future deploy might mount it elsewhere; this is
#    not user-tuneable in normal operation.
# ---------------------------------------------------------------------------

TERRAFORM_BIN = os.environ.get("TERRAFORM_BIN", "/opt/terraform/terraform")
CATALYST_APP_MODULE_SOURCE = os.environ.get(
    "CATALYST_APP_MODULE_SOURCE", "/opt/catalyst-app/"
)

#: CloudWatch metric namespace from ADR-014 §Compliance bullet 5.
METRIC_NAMESPACE = "Catalyst/Onboard"

#: Subprocess wall-clock timeout per invocation (init, apply, output).
#: Set conservatively under the Lambda 15-min cap so we surface our own
#: timeout (with a correlation id) before Lambda's runtime hard-kill.
_INIT_TIMEOUT_SECONDS = 5 * 60
_APPLY_TIMEOUT_SECONDS = 13 * 60
_OUTPUT_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class OnboardResult:
    """Return shape for :func:`provision_app`.

    Fields mirror the L4 composite's outputs.tf contract plus the
    correlation id the caller threads back into the API response.
    """

    construct_address: str
    ecr_uri: str
    execution_role_arn: str
    log_group_name: str
    alb_listener_rule_arn: str | None
    catalog_record_key: str
    correlation_id: str
    state_key: str


# ---------------------------------------------------------------------------
# Subprocess + Terraform helpers.
#
# Each helper takes the working dir as an argument (not a module-level
# global) so concurrent invocations in the same Lambda container — if
# they ever happen, e.g. provisioned concurrency — don't collide on /tmp.
# ---------------------------------------------------------------------------


def _build_state_key(tenant: str, environment: str, app: str) -> str:
    """Return the ADR-015 L4 backend key for ``tenant/env/app``."""

    return (
        f"catalyst/tenants/{tenant}/environments/{environment}/apps/{app}.tfstate"
    )


def _build_working_dir(working_dir: Path, region: str) -> None:
    """Write the per-invocation Terraform root into ``working_dir``.

    The root is intentionally minimal: a versions.tf, a backend "s3" {}
    declaration with no inline config (the caller supplies it via
    -backend-config), and a single module block invoking the bundled
    catalyst-app composite. Outputs re-expose the composite's outputs so
    ``terraform output -json`` returns the JSON we parse below.
    """

    working_dir.mkdir(parents=True, exist_ok=True)

    (working_dir / "versions.tf").write_text(
        "terraform {\n"
        '  required_version = ">= 1.7.0"\n'
        "  required_providers {\n"
        "    aws = {\n"
        '      source  = "hashicorp/aws"\n'
        '      version = ">= 5.0"\n'
        "    }\n"
        "  }\n"
        '  backend "s3" {}\n'
        "}\n"
    )

    (working_dir / "main.tf").write_text(
        f'provider "aws" {{\n'
        f'  region = "{region}"\n'
        f"}}\n"
        f"\n"
        f'variable "tenant"               {{ type = string }}\n'
        f'variable "environment"          {{ type = string }}\n'
        f'variable "project"              {{ type = string }}\n'
        f'variable "app"                  {{ type = string }}\n'
        f'variable "state_bucket"         {{ type = string }}\n'
        f'variable "aws_region"           {{ type = string }}\n'
        f'variable "service_type"         {{ type = string }}\n'
        f'variable "catalog_table_name"   {{ type = string }}\n'
        f'variable "alb_listener_arn"     {{ type = string }}\n'
        f'variable "alb_target_group_arn" {{ type = string }}\n'
        f"\n"
        f'module "app" {{\n'
        f'  source = "{CATALYST_APP_MODULE_SOURCE}"\n'
        f"\n"
        f"  tenant       = var.tenant\n"
        f"  environment  = var.environment\n"
        f"  project      = var.project\n"
        f"  app          = var.app\n"
        f"  state_bucket = var.state_bucket\n"
        f"  aws_region   = var.aws_region\n"
        f"  service_type = var.service_type\n"
        f"\n"
        f"  catalog_table_name   = var.catalog_table_name\n"
        f"  alb_listener_arn     = var.alb_listener_arn\n"
        f"  alb_target_group_arn = var.alb_target_group_arn\n"
        f"}}\n"
        f"\n"
        f'output "ecr_uri"               {{ value = module.app.ecr_uri }}\n'
        f'output "execution_role_arn"    {{ value = module.app.execution_role_arn }}\n'
        f'output "log_group_name"        {{ value = module.app.log_group_name }}\n'
        f'output "alb_listener_rule_arn" {{ value = module.app.alb_listener_rule_arn }}\n'
        f'output "catalog_record_key"    {{ value = module.app.catalog_record_key }}\n'
        f'output "construct_address"     {{ value = module.app.construct_address }}\n'
    )


def _run_terraform(
    args: list[str], *, working_dir: Path, timeout: int
) -> subprocess.CompletedProcess:
    """Invoke the bundled Terraform binary, streaming stdout to logs.

    Wraps :func:`subprocess.run` with a fixed env + timeout. Tests
    monkeypatch ``subprocess.run`` (not this helper) so the seam is at
    the standard-library boundary, which keeps the test fake honest
    about argv shape.
    """

    cmd = [TERRAFORM_BIN, *args]
    logger.info(
        "terraform_subprocess_start",
        extra={"cmd": " ".join(cmd), "cwd": str(working_dir)},
    )
    result = subprocess.run(  # noqa: S603 - cmd is fully constructed from constants + validated input
        cmd,
        cwd=str(working_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    if result.stdout:
        # Stream the apply log so an operator paging the CloudWatch group
        # can follow the terraform plan/apply progress lines without
        # re-running locally.
        for line in result.stdout.splitlines():
            logger.info("terraform_stdout", extra={"line": line})
    return result


def _terraform_init(
    working_dir: Path,
    *,
    state_bucket: str,
    state_key: str,
    region: str,
    lock_table: str,
) -> None:
    """Run ``terraform init`` with backend-config flags per ADR-015."""

    _run_terraform(
        [
            "init",
            "-input=false",
            "-no-color",
            f'-backend-config=bucket={state_bucket}',
            f'-backend-config=key={state_key}',
            f'-backend-config=region={region}',
            f'-backend-config=dynamodb_table={lock_table}',
        ],
        working_dir=working_dir,
        timeout=_INIT_TIMEOUT_SECONDS,
    )


def _terraform_apply(
    working_dir: Path,
    *,
    variables: dict[str, str],
) -> None:
    """Run ``terraform apply -auto-approve`` with per-call variables."""

    args = ["apply", "-auto-approve", "-input=false", "-no-color"]
    for name, value in variables.items():
        args.append(f"-var={name}={value}")
    _run_terraform(args, working_dir=working_dir, timeout=_APPLY_TIMEOUT_SECONDS)


def _terraform_output(working_dir: Path) -> dict[str, Any]:
    """Parse ``terraform output -json`` into a dict of ``name -> value``."""

    result = _run_terraform(
        ["output", "-json", "-no-color"],
        working_dir=working_dir,
        timeout=_OUTPUT_TIMEOUT_SECONDS,
    )
    raw = json.loads(result.stdout or "{}")
    # ``terraform output -json`` returns ``{ "name": { "value": ..., "type": ... } }``.
    # Flatten to ``{ "name": <value> }`` for ergonomics.
    return {name: meta.get("value") for name, meta in raw.items()}


# ---------------------------------------------------------------------------
# CloudWatch + structured log helpers.
#
# Both are import-lazy because the runtime cold-start path does not need
# them until the first onboard invocation, and unit tests don't always
# want to stub PutMetricData out of moto's surface.
# ---------------------------------------------------------------------------


def _emit_metric(
    duration_ms: float,
    *,
    result: str,
    region: str,
    cw_client: Any | None = None,
) -> None:
    """Emit the ADR-014 §Compliance OnboardDuration metric.

    Failures here are swallowed — the metric is observability, not
    correctness; a failed PutMetricData call MUST NOT mask a successful
    apply.
    """

    try:
        if cw_client is None:
            import boto3

            cw_client = boto3.client("cloudwatch", region_name=region)
        cw_client.put_metric_data(
            Namespace=METRIC_NAMESPACE,
            MetricData=[
                {
                    "MetricName": "OnboardDuration",
                    "Unit": "Milliseconds",
                    "Value": float(duration_ms),
                    "Dimensions": [
                        {"Name": "Endpoint", "Value": "services_onboard"},
                        {"Name": "Result", "Value": result},
                    ],
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001 - observability MUST NOT mask the result
        logger.warning(
            "onboard_putmetric_failed",
            extra={"error": str(exc), "result": result},
        )


def _emit_structured_log(
    *,
    correlation_id: str,
    state_key: str,
    result: str,
    duration_ms: float,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit the ADR-014 + ADR-015 §Compliance structured onboard log line.

    Required fields (compliance contract):

        * ``endpoint=services_onboard``
        * ``correlation_id=<uuid>``
        * ``state_key=<L4 backend key>``

    The line is emitted at INFO on success and ERROR on failure so the
    CloudWatch metric-filter path (the secondary verification path in
    ADR-014 §Deferred) can distinguish.
    """

    payload = {
        "endpoint": "services_onboard",
        "correlation_id": correlation_id,
        "state_key": state_key,
        "result": result,
        "duration_ms": duration_ms,
    }
    if extra:
        payload.update(extra)
    if result == "success":
        logger.info("onboard_complete", extra=payload)
    else:
        logger.error("onboard_failed", extra=payload)


# ---------------------------------------------------------------------------
# Public entrypoint.
# ---------------------------------------------------------------------------


def provision_app(
    construct_address: str,
    idempotency_key: str | None,
    correlation_id: str,
    *,
    state_bucket: str | None = None,
    lock_table: str | None = None,
    region: str | None = None,
    service_type: str = "web-service",
    alb_listener_arn: str | None = None,
    alb_target_group_arn: str | None = None,
    catalog_table_name: str | None = None,
    cw_client: Any | None = None,
) -> OnboardResult:
    """Provision the L4 resources for ``construct_address`` and return ARNs.

    Parameters
    ----------
    construct_address:
        ``tenant/env/lz/project/app`` (already-validated against
        :class:`ConstructAddress`).
    idempotency_key:
        Caller-supplied idempotency key. Carried through for log
        threading only — the actual idempotency replay is handled by the
        upstream ``_idempotent_response`` wrapper in
        :mod:`catalyst.main`.
    correlation_id:
        Correlation id minted by the handler; surfaced in structured
        logs and in the response on failure.

    Raises
    ------
    HTTPException
        500 on any subprocess failure (init/apply/output) or JSON parse
        error. The correlation id is included in the detail so the
        caller can grep the logs for the same request.
    """

    address = ConstructAddress(value=construct_address)
    tenant, environment, _lz, project, app = address.value.split("/")

    state_bucket = state_bucket or os.environ.get("CATALYST_STATE_BUCKET", "")
    lock_table = lock_table or os.environ.get("CATALYST_LOCK_TABLE", "")
    region = region or os.environ.get("AWS_REGION") or os.environ.get(
        "AWS_DEFAULT_REGION", "us-west-2"
    )

    if not state_bucket or not lock_table:
        raise HTTPException(
            status_code=500,
            detail=(
                "onboard misconfigured: CATALYST_STATE_BUCKET and "
                "CATALYST_LOCK_TABLE must be set"
            ),
        )

    state_key = _build_state_key(tenant=tenant, environment=environment, app=app)
    working_dir = Path(tempfile.gettempdir()) / f"onboard-{correlation_id}"

    started_at = time.monotonic()
    log_extras = {
        "tenant": tenant,
        "environment": environment,
        "project": project,
        "app": app,
        "service_type": service_type,
        "idempotency_key": idempotency_key or "",
    }

    try:
        _build_working_dir(working_dir, region=region)

        _terraform_init(
            working_dir,
            state_bucket=state_bucket,
            state_key=state_key,
            region=region,
            lock_table=lock_table,
        )

        variables: dict[str, str] = {
            "tenant": tenant,
            "environment": environment,
            "project": project,
            "app": app,
            "state_bucket": state_bucket,
            "aws_region": region,
            "service_type": service_type,
            "catalog_table_name": catalog_table_name
            or os.environ.get("CATALYST_CATALOG_TABLE", "catalyst-platform-state"),
            "alb_listener_arn": alb_listener_arn
            or os.environ.get("CATALYST_ALB_LISTENER_ARN", ""),
            "alb_target_group_arn": alb_target_group_arn
            or os.environ.get("CATALYST_ALB_TARGET_GROUP_ARN", ""),
        }
        _terraform_apply(working_dir, variables=variables)

        outputs = _terraform_output(working_dir)
        duration_ms = (time.monotonic() - started_at) * 1000.0

        result = OnboardResult(
            construct_address=outputs.get("construct_address") or address.value,
            ecr_uri=outputs.get("ecr_uri", ""),
            execution_role_arn=outputs.get("execution_role_arn", ""),
            log_group_name=outputs.get("log_group_name", ""),
            alb_listener_rule_arn=outputs.get("alb_listener_rule_arn"),
            catalog_record_key=outputs.get("catalog_record_key", ""),
            correlation_id=correlation_id,
            state_key=state_key,
        )
        _emit_metric(duration_ms, result="success", region=region, cw_client=cw_client)
        _emit_structured_log(
            correlation_id=correlation_id,
            state_key=state_key,
            result="success",
            duration_ms=duration_ms,
            extra=log_extras,
        )
        return result
    except HTTPException:
        # Re-raise misconfiguration errors without remapping to 500-via-Exception
        # so the operator-facing message stays specific.
        duration_ms = (time.monotonic() - started_at) * 1000.0
        _emit_metric(duration_ms, result="failure", region=region, cw_client=cw_client)
        _emit_structured_log(
            correlation_id=correlation_id,
            state_key=state_key,
            result="failure",
            duration_ms=duration_ms,
            extra=log_extras,
        )
        raise
    except subprocess.CalledProcessError as exc:
        duration_ms = (time.monotonic() - started_at) * 1000.0
        _emit_metric(duration_ms, result="failure", region=region, cw_client=cw_client)
        _emit_structured_log(
            correlation_id=correlation_id,
            state_key=state_key,
            result="failure",
            duration_ms=duration_ms,
            extra={
                **log_extras,
                "returncode": exc.returncode,
                # Truncate stderr to keep the structured-log line bounded.
                "stderr": (exc.stderr or "")[:2000],
            },
        )
        raise HTTPException(
            status_code=500,
            detail=(
                f"terraform_apply_failed correlation_id={correlation_id} "
                f"returncode={exc.returncode}"
            ),
        ) from exc
    except subprocess.TimeoutExpired as exc:
        duration_ms = (time.monotonic() - started_at) * 1000.0
        _emit_metric(duration_ms, result="failure", region=region, cw_client=cw_client)
        _emit_structured_log(
            correlation_id=correlation_id,
            state_key=state_key,
            result="failure",
            duration_ms=duration_ms,
            extra={**log_extras, "timeout_seconds": exc.timeout},
        )
        raise HTTPException(
            status_code=500,
            detail=(
                f"terraform_apply_timeout correlation_id={correlation_id} "
                f"timeout={exc.timeout}"
            ),
        ) from exc
    except Exception as exc:  # noqa: BLE001 - last-resort rewrap so caller always sees 500
        duration_ms = (time.monotonic() - started_at) * 1000.0
        _emit_metric(duration_ms, result="failure", region=region, cw_client=cw_client)
        _emit_structured_log(
            correlation_id=correlation_id,
            state_key=state_key,
            result="failure",
            duration_ms=duration_ms,
            extra={**log_extras, "error": str(exc)},
        )
        raise HTTPException(
            status_code=500,
            detail=f"onboard_failed correlation_id={correlation_id}: {exc}",
        ) from exc
    finally:
        # Lambda's /tmp is bounded (512 MB default); reclaim the working
        # dir on every invocation so successive onboards don't accrue.
        try:
            shutil.rmtree(working_dir, ignore_errors=True)
        except Exception:  # noqa: BLE001 - cleanup MUST NOT raise
            pass
