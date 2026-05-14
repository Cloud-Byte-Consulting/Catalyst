#!/usr/bin/env python3
"""Lightweight MCP (stdio) server that exposes the AWS Platform Engineering
skill's generators as tool-native MCP calls.

Companion to .cursor/skills/aws-platform-engineering/SKILL.md (per ADR-005).
Mirrors the shape of .cursor/skills/rlm/rlm_mcp_server.py — pure stdlib,
JSON-RPC 2.0 over stdin/stdout (MCP stdio transport), no external deps.

The server's job is template substitution + suggested target-path emission.
The agent does the actual file write using its native Write tool. This keeps
the MCP server side-effect free and trivially testable.

CLI mode (for one-off use outside an agent session):

    python aws_pe_mcp_server.py --cli <capability> --inputs <inputs.json>

Where <capability> is one of:
    landing_zone, terraform_module, oidc_workflow, adr,
    service_skeleton, bedrock_skeleton, static_egress_vpc, golden_path

Requires Python 3.10+. No external dependencies.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = SKILL_ROOT / "templates"

SERVER_INFO = {
    "name": "aws-pe",
    "version": "1.0.0",
}


# ---------------------------------------------------------------------------
# Template loading + substitution
# ---------------------------------------------------------------------------

class TemplateError(Exception):
    """Raised when a template cannot be loaded or rendered."""


def load_template(name: str) -> str:
    path = TEMPLATES_DIR / name
    if not path.is_file():
        raise TemplateError(f"Template not found: {name} (looked in {TEMPLATES_DIR})")
    return path.read_text(encoding="utf-8")


def render(text: str, mapping: dict[str, Any]) -> str:
    """Replace {{key}} occurrences with mapping[key].

    Missing keys are reported by raising TemplateError so the agent can
    surface them rather than silently emitting an unsubstituted token.
    """

    needed = set(re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", text))
    missing = needed - set(mapping.keys())
    if missing:
        raise TemplateError(
            f"Missing template inputs: {sorted(missing)}; got {sorted(mapping.keys())}"
        )

    def _sub(match: "re.Match[str]") -> str:
        key = match.group(1).strip()
        value = mapping[key]
        if value is None:
            return ""
        return str(value)

    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", _sub, text)


def today_iso() -> str:
    return datetime.date.today().isoformat()


def slug(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


# ---------------------------------------------------------------------------
# Capability handlers — each returns dict with `rendered` and `target_path`
# ---------------------------------------------------------------------------

def _required(args: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if args.get(k) in (None, "")]
    if missing:
        raise TemplateError(f"Missing required arguments: {missing}")


def cap_landing_zone(args: dict[str, Any]) -> dict[str, str]:
    _required(args, "landing_zone_name", "tenant", "primary_region")
    name = args["landing_zone_name"]
    tmpl = load_template("landing-zone.md.tmpl")
    rendered = render(tmpl, {
        "landing_zone_name": name,
        "tenant": args["tenant"],
        "primary_region": args["primary_region"],
        "dr_region": args.get("dr_region", "<not-set>"),
        "account_baseline": args.get("account_baseline", "control-tower"),
    })
    target = f"infrastructure/landing-zones/{slug(name)}/README.md"
    return {"rendered": rendered, "target_path": target}


def cap_terraform_module(args: dict[str, Any]) -> dict[str, str]:
    _required(args, "module_name")
    name = args["module_name"]
    module_type = args.get("module_type", "resource")
    tmpl = load_template("terraform-module.tf.tmpl")
    rendered = render(tmpl, {
        "module_name": name,
        "module_type": module_type,
        "aws_provider_version": args.get("aws_provider_version", "~> 5.60"),
    })
    target = f"infrastructure/modules/{module_type}/{slug(name)}/main.tf"
    return {"rendered": rendered, "target_path": target}


def cap_oidc_workflow(args: dict[str, Any]) -> dict[str, str]:
    _required(args, "workflow_name", "aws_role_arn_var_plan", "aws_region")
    workflow_name = args["workflow_name"]
    trigger = args.get("trigger", "pull_request")
    target_branch = args.get("target_branch", "release")
    concurrency = args.get("concurrency_group", f"{slug(workflow_name)}-${{{{ github.ref }}}}")

    if trigger == "pull_request":
        trigger_block = "  pull_request:\n    branches: [release, main]"
    elif trigger == "push":
        trigger_block = f"  push:\n    branches: [{target_branch}]"
    elif trigger == "schedule":
        trigger_block = '  schedule:\n    - cron: "0 9 * * 1-5"'
    elif trigger == "workflow_dispatch":
        trigger_block = "  workflow_dispatch:"
    else:
        trigger_block = f"  {trigger}:"

    tmpl = load_template("github-actions-oidc.yml.tmpl")
    rendered = render(tmpl, {
        "workflow_name": workflow_name,
        "trigger_block": trigger_block,
        "concurrency_group": concurrency,
        "aws_region": args["aws_region"],
        "aws_role_arn_var_plan": args["aws_role_arn_var_plan"],
        "aws_role_arn_var_apply": args.get("aws_role_arn_var_apply", args["aws_role_arn_var_plan"] + "_APPLY"),
        "target_branch": target_branch,
        "environment_name": args.get("environment_name", "production"),
    })
    target = f".github/workflows/{slug(workflow_name)}.yml"
    return {"rendered": rendered, "target_path": target}


def cap_adr(args: dict[str, Any]) -> dict[str, str]:
    _required(args, "adr_number", "adr_title", "context_summary", "decision_summary")
    number = str(args["adr_number"]).zfill(3)
    title = args["adr_title"]

    alts = args.get("alternatives", [])
    if alts:
        rows = "\n".join(
            f"| {a.get('option', '')} | {a.get('why_rejected', '')} |" for a in alts
        )
    else:
        rows = "| <alternative> | <why rejected> |"

    tmpl = load_template("adr.md.tmpl")
    rendered = render(tmpl, {
        "adr_number": number,
        "adr_title": title,
        "date_iso": args.get("date", today_iso()),
        "context_summary": args["context_summary"],
        "decision_summary": args["decision_summary"],
        "alternatives_table": rows,
    })
    target = f"docs/ADR/ADR-{number}-{slug(title)}.md"
    return {"rendered": rendered, "target_path": target}


def cap_service_skeleton(args: dict[str, Any]) -> dict[str, str]:
    _required(args, "service_name")
    name = args["service_name"]
    tmpl = load_template("ecs-fargate-service.tf.tmpl")
    rendered = render(tmpl, {
        "service_name": name,
        "port": args.get("port", 8080),
        "health_check_path": args.get("health_check_path", "/healthz"),
    })
    target = f"infrastructure/services/{slug(name)}/main.tf"
    return {"rendered": rendered, "target_path": target}


def cap_bedrock_skeleton(args: dict[str, Any]) -> dict[str, str]:
    _required(args, "service_name", "bedrock_model_id")
    name = args["service_name"]
    tmpl = load_template("bedrock-service.tf.tmpl")
    rendered = render(tmpl, {
        "service_name": name,
        "bedrock_model_id": args["bedrock_model_id"],
        "multistep": "true" if args.get("multistep") else "false",
    })
    target = f"infrastructure/services/{slug(name)}/main.tf"
    return {"rendered": rendered, "target_path": target}


def cap_static_egress_vpc(args: dict[str, Any]) -> dict[str, str]:
    _required(args, "vpc_name")
    name = args["vpc_name"]
    tmpl = load_template("static-egress-vpc.tf.tmpl")
    rendered = render(tmpl, {
        "vpc_name": name,
        "cidr": args.get("cidr", "10.0.0.0/25"),
    })
    target = f"infrastructure/network/{slug(name)}/main.tf"
    return {"rendered": rendered, "target_path": target}


def cap_golden_path(args: dict[str, Any]) -> dict[str, str]:
    _required(args, "golden_path_name", "linked_module")
    name = args["golden_path_name"]
    tmpl = load_template("golden-path.md.tmpl")
    rendered = render(tmpl, {
        "golden_path_name": name,
        "target_persona": args.get("target_persona", "application-developer"),
        "linked_module": args["linked_module"],
        "date_iso": args.get("date", today_iso()),
    })
    target = f"docs/golden-paths/{slug(name)}.md"
    return {"rendered": rendered, "target_path": target}


CAPABILITIES: dict[str, Callable[[dict[str, Any]], dict[str, str]]] = {
    "landing_zone": cap_landing_zone,
    "terraform_module": cap_terraform_module,
    "oidc_workflow": cap_oidc_workflow,
    "adr": cap_adr,
    "service_skeleton": cap_service_skeleton,
    "bedrock_skeleton": cap_bedrock_skeleton,
    "static_egress_vpc": cap_static_egress_vpc,
    "golden_path": cap_golden_path,
}


# ---------------------------------------------------------------------------
# MCP tool descriptors
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "aws_pe_landing_zone",
        "description": (
            "Render an SRA-aligned AWS landing-zone scaffold doc. "
            "AWS-prescriptive: encodes the SRA OU shape (Security: Tooling+Log Archive; "
            "Infrastructure: Network+Shared Services; Workloads). Returns rendered text + "
            "suggested target path; agent writes the file."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "landing_zone_name": {"type": "string", "description": "Kebab-case identifier (e.g., pharm-prod)."},
                "tenant": {"type": "string", "description": "Catalyst tenant slug."},
                "primary_region": {"type": "string", "description": "Primary AWS region (e.g., us-east-1)."},
                "dr_region": {"type": "string", "description": "DR AWS region (e.g., us-west-2)."},
                "account_baseline": {"type": "string", "enum": ["control-tower", "organizations"], "description": "Default control-tower."},
            },
            "required": ["landing_zone_name", "tenant", "primary_region"],
        },
    },
    {
        "name": "aws_pe_terraform_module",
        "description": "Render a Terraform module skeleton with construct-anchor tagging and policy-as-code hook stubs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_name": {"type": "string"},
                "module_type": {"type": "string", "enum": ["resource", "composite"], "description": "Default resource."},
                "aws_provider_version": {"type": "string", "description": "Default '~> 5.60'."},
            },
            "required": ["module_name"],
        },
    },
    {
        "name": "aws_pe_oidc_workflow",
        "description": (
            "Render a GitHub Actions workflow that auths to AWS via OIDC. "
            "AWS-prescriptive: never long-lived keys; trust policy bound to repo+ref; "
            "separate plan vs apply role ARNs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_name": {"type": "string"},
                "trigger": {"type": "string", "enum": ["pull_request", "push", "schedule", "workflow_dispatch"]},
                "target_branch": {"type": "string", "description": "Branch name for push trigger."},
                "aws_role_arn_var_plan": {"type": "string", "description": "Repo var name for read-only OIDC role."},
                "aws_role_arn_var_apply": {"type": "string", "description": "Repo var name for write-capable OIDC role."},
                "aws_region": {"type": "string"},
                "concurrency_group": {"type": "string"},
                "environment_name": {"type": "string", "description": "GitHub Environment with required reviewers."},
            },
            "required": ["workflow_name", "aws_role_arn_var_plan", "aws_region"],
        },
    },
    {
        "name": "aws_pe_adr",
        "description": (
            "Render an ADR matching both Catalyst's template and the AWS prescriptive ADR shape "
            "(Title/Status/Date/Context/Decision/Consequences/Compliance/Notes). Status starts at Proposed; "
            "encodes the immutability rule. AWS-prescriptive."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "adr_number": {"type": ["integer", "string"], "description": "Next sequential under docs/ADR/."},
                "adr_title": {"type": "string", "description": "Imperative-mood title."},
                "context_summary": {"type": "string"},
                "decision_summary": {"type": "string"},
                "alternatives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "option": {"type": "string"},
                            "why_rejected": {"type": "string"},
                        },
                    },
                },
                "date": {"type": "string", "description": "ISO date. Defaults to today."},
            },
            "required": ["adr_number", "adr_title", "context_summary", "decision_summary"],
        },
    },
    {
        "name": "aws_pe_service_skeleton",
        "description": (
            "Render an ECS Fargate platform-service skeleton with ALB-public/targets-private layout, "
            "least-privilege IAM, X-Ray, structured logging, secrets via SSM/Secrets Manager."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string"},
                "port": {"type": "integer"},
                "health_check_path": {"type": "string"},
            },
            "required": ["service_name"],
        },
    },
    {
        "name": "aws_pe_bedrock_skeleton",
        "description": (
            "Render a Bedrock-backed gen-AI service skeleton matching the GenAI platform-engineering "
            "blueprint (controls layer + prompt-state DDB + Step Functions for multistep + budget throttle)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string"},
                "bedrock_model_id": {"type": "string"},
                "multistep": {"type": "boolean", "description": "True => generate Step Functions state machine."},
            },
            "required": ["service_name", "bedrock_model_id"],
        },
    },
    {
        "name": "aws_pe_static_egress_vpc",
        "description": (
            "Render the static-outbound-IP serverless VPC pattern: 2 public subnets (NAT GW + EIP each) + "
            "2 private subnets (Lambda/ECS lives here). AWS-prescriptive."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vpc_name": {"type": "string"},
                "cidr": {"type": "string", "description": "VPC CIDR. Default 10.0.0.0/25."},
            },
            "required": ["vpc_name"],
        },
    },
    {
        "name": "aws_pe_golden_path",
        "description": (
            "Render an IDP-style golden-path doc with the five non-negotiable sections: "
            "What / Why / Opinion / Paved road / Escape hatch."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "golden_path_name": {"type": "string"},
                "target_persona": {"type": "string"},
                "linked_module": {"type": "string"},
                "date": {"type": "string"},
            },
            "required": ["golden_path_name", "linked_module"],
        },
    },
]


TOOL_TO_CAPABILITY = {
    "aws_pe_landing_zone": "landing_zone",
    "aws_pe_terraform_module": "terraform_module",
    "aws_pe_oidc_workflow": "oidc_workflow",
    "aws_pe_adr": "adr",
    "aws_pe_service_skeleton": "service_skeleton",
    "aws_pe_bedrock_skeleton": "bedrock_skeleton",
    "aws_pe_static_egress_vpc": "static_egress_vpc",
    "aws_pe_golden_path": "golden_path",
}


# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------

def make_response(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def make_error(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle_request(request: dict) -> dict | None:
    method = request.get("method", "")
    id_ = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return make_response(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return make_response(id_, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        capability = TOOL_TO_CAPABILITY.get(tool_name)
        if capability is None:
            return make_error(id_, -32602, f"Unknown tool: {tool_name}")
        handler = CAPABILITIES[capability]
        try:
            result = handler(tool_args)
            text = (
                f"# Suggested target: {result['target_path']}\n"
                f"# Length: {len(result['rendered'])} chars\n"
                f"---\n{result['rendered']}"
            )
            return make_response(id_, {
                "content": [{"type": "text", "text": text}],
            })
        except TemplateError as e:
            return make_response(id_, {
                "content": [{"type": "text", "text": f"TemplateError: {e}"}],
                "isError": True,
            })
        except Exception as e:
            return make_response(id_, {
                "content": [{"type": "text", "text": f"Error: {type(e).__name__}: {e}"}],
                "isError": True,
            })

    if method == "ping":
        return make_response(id_, {})

    if method.startswith("notifications/"):
        return None

    return make_error(id_, -32601, f"Method not found: {method}")


def run_mcp_loop() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = make_error(None, -32700, "Parse error")
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def run_cli() -> int:
    parser = argparse.ArgumentParser(
        prog="aws_pe_mcp_server",
        description="AWS Platform Engineering skill — MCP server + CLI generator",
    )
    parser.add_argument(
        "--cli",
        choices=sorted(CAPABILITIES.keys()),
        help="Run a capability one-shot (CLI mode) instead of the MCP loop.",
    )
    parser.add_argument(
        "--inputs",
        type=str,
        help="Path to JSON file with capability inputs.",
    )
    parser.add_argument(
        "--inputs-json",
        type=str,
        help="Inline JSON for capability inputs.",
    )
    args = parser.parse_args()

    if not args.cli:
        run_mcp_loop()
        return 0

    if args.inputs:
        inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    elif args.inputs_json:
        inputs = json.loads(args.inputs_json)
    else:
        inputs = {}

    handler = CAPABILITIES[args.cli]
    result = handler(inputs)
    sys.stdout.write(f"# Suggested target: {result['target_path']}\n")
    sys.stdout.write(f"# Length: {len(result['rendered'])} chars\n")
    sys.stdout.write("---\n")
    sys.stdout.write(result["rendered"])
    sys.stdout.write("\n")
    return 0


os.chdir(str(REPO_ROOT))


if __name__ == "__main__":
    sys.exit(run_cli())
