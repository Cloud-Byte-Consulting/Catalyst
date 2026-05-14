#!/usr/bin/env python3
"""Thin stdio MCP server that wraps AWS Bedrock for Catalyst agents.

This server satisfies decision #11 of
`docs/research/platform-catalyst-agents-evaluation.md`: the
`ai-reviewer-architect` agent file does **not** pin Bedrock model IDs — every
binding (model id, region, account) is supplied at call time through this MCP
server. Two tools are exposed:

- ``bedrock_invoke_converse`` — wraps ``bedrock-runtime.Converse``.
- ``bedrock_list_models`` — wraps ``bedrock.list_foundation_models``.

Protocol: JSON-RPC 2.0 over stdin/stdout (MCP stdio transport). Requires
Python 3.10+. ``boto3`` is **lazily imported inside each tool handler** so the
server still loads cleanly when boto3 is not installed (the tool call simply
returns a structured error instead of crashing the process).

License: BSD-3-Clause, (c) Cloud-Byte-Consulting. New in Catalyst; no upstream
source — this file is Catalyst-specific glue for the platform-catalyst import.
"""

from __future__ import annotations

import json
import sys
from typing import Any

SERVER_INFO = {"name": "bedrock-binding", "version": "1.0.0"}

TOOLS = [
    {
        "name": "bedrock_invoke_converse",
        "description": (
            "Invoke the AWS Bedrock Converse API for a given model. Model id, "
            "messages, optional system prompt, optional inferenceConfig and "
            "region are all caller-supplied — this server does not bake in any "
            "defaults (decision #11). Returns the raw Converse response shape "
            "or a structured error."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {
                    "type": "string",
                    "description": (
                        "Bedrock foundation model id (e.g. an Anthropic Claude "
                        "Converse-supported id). REQUIRED. No default."
                    ),
                },
                "messages": {
                    "type": "array",
                    "description": (
                        "Converse messages array. Each item: "
                        "{role: 'user'|'assistant', content: [{text: '...'}]}"
                    ),
                    "items": {"type": "object"},
                },
                "system": {
                    "type": "array",
                    "description": "Optional system prompt blocks ([{text: '...'}]).",
                    "items": {"type": "object"},
                },
                "inference_config": {
                    "type": "object",
                    "description": (
                        "Optional Converse inferenceConfig (maxTokens, "
                        "temperature, topP, stopSequences)."
                    ),
                },
                "region": {
                    "type": "string",
                    "description": (
                        "Optional AWS region for the bedrock-runtime client. "
                        "No default — supply explicitly."
                    ),
                },
            },
            "required": ["model_id", "messages"],
        },
    },
    {
        "name": "bedrock_list_models",
        "description": (
            "List Bedrock foundation models available to the caller via "
            "bedrock.list_foundation_models. Returns the raw response shape or "
            "a structured error. Region is caller-supplied with no default."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": (
                        "Optional AWS region for the bedrock control-plane "
                        "client. No default — supply explicitly."
                    ),
                },
            },
        },
    },
]


def _structured_error(error_type: str, message: str) -> dict[str, Any]:
    return {"error": {"type": error_type, "message": message}}


def _invoke_converse(args: dict[str, Any]) -> dict[str, Any]:
    """Invoke Bedrock Converse with lazy boto3 import and structured errors."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as e:
        return _structured_error(
            "DependencyMissing",
            f"boto3 is not installed in this Python environment: {e}",
        )

    model_id = args.get("model_id")
    messages = args.get("messages")
    if not isinstance(model_id, str) or not model_id:
        return _structured_error("InvalidArguments", "'model_id' must be a non-empty string")
    if not isinstance(messages, list):
        return _structured_error("InvalidArguments", "'messages' must be an array")

    client_kwargs: dict[str, Any] = {}
    region = args.get("region")
    if isinstance(region, str) and region:
        client_kwargs["region_name"] = region

    converse_kwargs: dict[str, Any] = {"modelId": model_id, "messages": messages}
    system = args.get("system")
    if isinstance(system, list) and system:
        converse_kwargs["system"] = system
    inference_config = args.get("inference_config")
    if isinstance(inference_config, dict) and inference_config:
        converse_kwargs["inferenceConfig"] = inference_config

    try:
        client = boto3.client("bedrock-runtime", **client_kwargs)
        response = client.converse(**converse_kwargs)
    except ClientError as e:
        return _structured_error("ClientError", str(e))
    except BotoCoreError as e:
        return _structured_error("BotoCoreError", str(e))
    except Exception as e:  # noqa: BLE001 - convert any boto/runtime failure into a structured tool result
        return _structured_error(type(e).__name__, str(e))

    return _strip_non_json(response)


def _list_models(args: dict[str, Any]) -> dict[str, Any]:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as e:
        return _structured_error(
            "DependencyMissing",
            f"boto3 is not installed in this Python environment: {e}",
        )

    client_kwargs: dict[str, Any] = {}
    region = args.get("region")
    if isinstance(region, str) and region:
        client_kwargs["region_name"] = region

    try:
        client = boto3.client("bedrock", **client_kwargs)
        response = client.list_foundation_models()
    except ClientError as e:
        return _structured_error("ClientError", str(e))
    except BotoCoreError as e:
        return _structured_error("BotoCoreError", str(e))
    except Exception as e:  # noqa: BLE001
        return _structured_error(type(e).__name__, str(e))

    return _strip_non_json(response)


def _strip_non_json(obj: Any) -> Any:
    """Best-effort coerce a boto3 response into JSON-serialisable shapes."""
    try:
        return json.loads(json.dumps(obj, default=str))
    except (TypeError, ValueError):
        return {"repr": repr(obj)}


TOOL_HANDLERS = {
    "bedrock_invoke_converse": _invoke_converse,
    "bedrock_list_models": _list_models,
}


def _response(id_: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method", "")
    id_ = request.get("id")
    params = request.get("params", {}) or {}

    if method == "initialize":
        return _response(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _response(id_, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {}) or {}
        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return _error(id_, -32602, f"Unknown tool: {tool_name}")
        try:
            payload = handler(tool_args)
            return _response(id_, {
                "content": [{"type": "text", "text": json.dumps(payload, indent=2, default=str)}],
                "isError": "error" in payload,
            })
        except Exception as e:  # noqa: BLE001 - last-resort guard so the JSON-RPC loop never dies
            return _response(id_, {
                "content": [{"type": "text", "text": json.dumps(_structured_error(type(e).__name__, str(e)))}],
                "isError": True,
            })

    if method == "ping":
        return _response(id_, {})

    if method.startswith("notifications/"):
        return None

    return _error(id_, -32601, f"Method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_error(None, -32700, "Parse error")) + "\n")
            sys.stdout.flush()
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
