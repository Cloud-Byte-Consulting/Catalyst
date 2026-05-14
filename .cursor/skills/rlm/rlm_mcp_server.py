#!/usr/bin/env python3
"""Lightweight MCP (stdio) server that wraps rlm_repl.py for Cursor agents.

Exposes the RLM REPL commands as MCP tools so Cursor agents can interact with
the RLM workflow via tool-native calls instead of Shell round-trips.

Requires Python 3.10+. No external dependencies — uses only stdlib.

Protocol: JSON-RPC 2.0 over stdin/stdout (MCP stdio transport).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
REPL_SCRIPT = REPO_ROOT / ".claude" / "skills" / "rlm" / "scripts" / "rlm_repl.py"
DEFAULT_STATE = str(REPO_ROOT / ".claude" / "rlm_state" / "state.pkl")

sys.path.insert(0, str(REPL_SCRIPT.parent))
import rlm_repl  # noqa: E402

SERVER_INFO = {
    "name": "rlm-repl",
    "version": "1.0.0",
}

TOOLS = [
    {
        "name": "rlm_init",
        "description": (
            "Initialise the RLM REPL state from a context file. "
            "Use when starting an RLM workflow on a large artifact (>50k chars)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "context_path": {
                    "type": "string",
                    "description": "Path to the context file to load.",
                },
                "state_path": {
                    "type": "string",
                    "description": f"Path to state pickle. Default: {DEFAULT_STATE}",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Optional cap on bytes read from context file.",
                },
            },
            "required": ["context_path"],
        },
    },
    {
        "name": "rlm_status",
        "description": "Show current RLM REPL state summary (context size, buffer count, persisted vars).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_path": {
                    "type": "string",
                    "description": f"Path to state pickle. Default: {DEFAULT_STATE}",
                },
                "show_vars": {
                    "type": "boolean",
                    "description": "List persisted variable names. Default: false.",
                },
            },
        },
    },
    {
        "name": "rlm_peek",
        "description": "Preview a character range of the loaded context. Use for scouting artifact structure.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {
                    "type": "integer",
                    "description": "Start character index. Default: 0.",
                },
                "end": {
                    "type": "integer",
                    "description": "End character index. Default: 3000.",
                },
                "state_path": {
                    "type": "string",
                    "description": f"Path to state pickle. Default: {DEFAULT_STATE}",
                },
            },
        },
    },
    {
        "name": "rlm_grep",
        "description": "Search the loaded context for a regex pattern. Returns matches with surrounding snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for.",
                },
                "max_matches": {
                    "type": "integer",
                    "description": "Maximum matches to return. Default: 20.",
                },
                "window": {
                    "type": "integer",
                    "description": "Characters of context around each match. Default: 120.",
                },
                "state_path": {
                    "type": "string",
                    "description": f"Path to state pickle. Default: {DEFAULT_STATE}",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "rlm_chunk",
        "description": (
            "Materialise chunks as files for subagent analysis. "
            "Returns the list of chunk file paths."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "out_dir": {
                    "type": "string",
                    "description": "Output directory for chunk files. Default: .claude/rlm_state/chunks",
                },
                "size": {
                    "type": "integer",
                    "description": "Characters per chunk. Default: 200000.",
                },
                "overlap": {
                    "type": "integer",
                    "description": "Overlap characters between chunks. Default: 0.",
                },
                "state_path": {
                    "type": "string",
                    "description": f"Path to state pickle. Default: {DEFAULT_STATE}",
                },
            },
        },
    },
    {
        "name": "rlm_exec",
        "description": (
            "Execute arbitrary Python code in the RLM REPL environment. "
            "Has access to: content, context, buffers, peek(), grep(), "
            "chunk_indices(), write_chunks(), add_buffer()."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute.",
                },
                "state_path": {
                    "type": "string",
                    "description": f"Path to state pickle. Default: {DEFAULT_STATE}",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "rlm_reset",
        "description": "Delete the RLM REPL state file. Use when done with an RLM session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_path": {
                    "type": "string",
                    "description": f"Path to state pickle. Default: {DEFAULT_STATE}",
                },
            },
        },
    },
    {
        "name": "rlm_export_buffers",
        "description": "Export accumulated buffers to a text file for synthesis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "out_path": {
                    "type": "string",
                    "description": "Output file path for exported buffers.",
                },
                "state_path": {
                    "type": "string",
                    "description": f"Path to state pickle. Default: {DEFAULT_STATE}",
                },
            },
            "required": ["out_path"],
        },
    },
]


def _state(args: dict[str, Any]) -> str:
    return args.get("state_path", DEFAULT_STATE)


def _capture(func, argv: list[str]) -> str:
    """Run an rlm_repl command and capture stdout."""
    import io
    from contextlib import redirect_stdout, redirect_stderr

    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            parser = rlm_repl.build_parser()
            parsed = parser.parse_args(argv)
            parsed.func(parsed)
    except SystemExit:
        pass
    except rlm_repl.RlmReplError as e:
        return f"ERROR: {e}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

    result = out.getvalue()
    errors = err.getvalue()
    if errors:
        result += f"\nSTDERR: {errors}"
    return result


def handle_rlm_init(args: dict[str, Any]) -> str:
    argv = ["--state", _state(args), "init", args["context_path"]]
    if "max_bytes" in args and args["max_bytes"] is not None:
        argv.extend(["--max-bytes", str(args["max_bytes"])])
    return _capture(rlm_repl.cmd_init, argv)


def handle_rlm_status(args: dict[str, Any]) -> str:
    argv = ["--state", _state(args), "status"]
    if args.get("show_vars"):
        argv.append("--show-vars")
    return _capture(rlm_repl.cmd_status, argv)


def handle_rlm_peek(args: dict[str, Any]) -> str:
    start = args.get("start", 0)
    end = args.get("end", 3000)
    code = f"print(peek({start}, {end}))"
    argv = ["--state", _state(args), "exec", "-c", code]
    return _capture(rlm_repl.cmd_exec, argv)


def handle_rlm_grep(args: dict[str, Any]) -> str:
    pattern = args["pattern"].replace("'", "\\'")
    max_matches = args.get("max_matches", 20)
    window = args.get("window", 120)
    code = f"import json; print(json.dumps(grep('{pattern}', max_matches={max_matches}, window={window}), indent=2))"
    argv = ["--state", _state(args), "exec", "-c", code]
    return _capture(rlm_repl.cmd_exec, argv)


def handle_rlm_chunk(args: dict[str, Any]) -> str:
    out_dir = args.get("out_dir", str(REPO_ROOT / ".claude" / "rlm_state" / "chunks"))
    size = args.get("size", 200000)
    overlap = args.get("overlap", 0)
    code = (
        f"import json; paths = write_chunks('{out_dir}', size={size}, overlap={overlap}); "
        f"print(json.dumps({{'chunk_count': len(paths), 'paths': paths}}, indent=2))"
    )
    argv = ["--state", _state(args), "exec", "-c", code]
    return _capture(rlm_repl.cmd_exec, argv)


def handle_rlm_exec(args: dict[str, Any]) -> str:
    argv = ["--state", _state(args), "exec", "-c", args["code"]]
    return _capture(rlm_repl.cmd_exec, argv)


def handle_rlm_reset(args: dict[str, Any]) -> str:
    argv = ["--state", _state(args), "reset"]
    return _capture(rlm_repl.cmd_reset, argv)


def handle_rlm_export_buffers(args: dict[str, Any]) -> str:
    argv = ["--state", _state(args), "export-buffers", args["out_path"]]
    return _capture(rlm_repl.cmd_export_buffers, argv)


TOOL_HANDLERS = {
    "rlm_init": handle_rlm_init,
    "rlm_status": handle_rlm_status,
    "rlm_peek": handle_rlm_peek,
    "rlm_grep": handle_rlm_grep,
    "rlm_chunk": handle_rlm_chunk,
    "rlm_exec": handle_rlm_exec,
    "rlm_reset": handle_rlm_reset,
    "rlm_export_buffers": handle_rlm_export_buffers,
}


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
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return make_error(id_, -32602, f"Unknown tool: {tool_name}")
        try:
            result_text = handler(tool_args)
            return make_response(id_, {
                "content": [{"type": "text", "text": result_text}],
            })
        except Exception as e:
            return make_response(id_, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            })

    if method == "ping":
        return make_response(id_, {})

    if method.startswith("notifications/"):
        return None

    return make_error(id_, -32601, f"Method not found: {method}")


def main() -> None:
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


if __name__ == "__main__":
    os.chdir(str(REPO_ROOT))
    main()
