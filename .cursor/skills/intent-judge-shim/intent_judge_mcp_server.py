#!/usr/bin/env python3
"""intent-judge MCP shim — BSD-3-Clause, decision #3.

This file is NEW in Catalyst — there is no upstream source file to import.
Per decision #3 in docs/research/platform-catalyst-agents-evaluation.md
("re-implement as a lightweight Cursor rule + thin MCP shim ~80 LOC, do NOT
vendor the full plugins/catalyst-judge/ package"), this server is hard-capped
at ~80 lines of effective code (excluding this docstring and the import
block). It deliberately does not embed the upstream Python package, the
Relay Go port, any LLM client, or persistent state; llm_judge requests are
explicitly rejected with ok=false.

The three tools below match the Delegation map in the upstream
`.cursor/agents/intent-judge.md` (`@intent-validation`, `@output-assessment`,
`@eval-scoring`).

Transport: JSON-RPC 2.0 over stdin/stdout (MCP stdio). Pure stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

SERVER = {"name": "intent-judge", "version": "0.1.0"}
SECRET_RE = re.compile(r"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
INJECT_RE = re.compile(r"ignore (?:all )?previous|^\s*system:|<\|im_start\|>|disregard above", re.I | re.M)
PII_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|\b\d{3}-\d{2}-\d{4}\b|\b(?:\d[ -]?){13,19}\b")
LONG_B64 = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")

def _schema(req: list, **props) -> dict: return {"type": "object", "required": req, "properties": props}

TOOLS = [
    {"name": "validate_intent", "description": "Heuristic allow/deny/clarify verdict for a pending tool call. Scans args for secrets/PII/injection. No LLM (decision #3 LOC cap).", "inputSchema": _schema(["tool_name", "arguments"], tool_name={"type": "string"}, arguments={"type": "object"}, context={"type": "string"})},
    {"name": "assess_output", "description": "Compare output against expected_shape: substring|regex|json_equal. llm_judge is rejected (shim cap).", "inputSchema": _schema(["output"], output={"type": "string"}, expected={"type": "string"}, expected_shape={"type": "string", "enum": ["substring", "regex", "json_equal", "llm_judge"]})},
    {"name": "score_eval", "description": "Aggregate per-case assess_output calls into pass/fail counts and per-case results.", "inputSchema": _schema(["cases"], cases={"type": "array", "items": {"type": "object"}})},
]

def _scan(text: str) -> dict:
    return {"secrets": bool(SECRET_RE.search(text)), "pii": bool(PII_RE.search(text)),
            "injection": bool(INJECT_RE.search(text) or LONG_B64.search(text))}

def validate_intent(p: dict) -> dict:
    blob = p.get("tool_name", "") + "\n" + json.dumps(p.get("arguments", {}), default=str) + "\n" + p.get("context", "")
    s = _scan(blob)
    if s["secrets"] or s["injection"]:
        return {"verdict": "deny", "reason": f"scanner-triggered: {[k for k, v in s.items() if v]}", "scanners": s}
    if s["pii"]:
        return {"verdict": "clarify", "reason": "PII pattern detected; confirm intent before proceeding", "scanners": s}
    return {"verdict": "allow", "reason": "no scanner fired (heuristic-only shim)", "scanners": s}

def assess_output(p: dict) -> dict:
    out, exp, shape = p.get("output", ""), p.get("expected", ""), p.get("expected_shape", "substring")
    if shape == "llm_judge":
        return {"ok": False, "score": 0.0, "reason": "llm_judge requires upstream LLM call; not implemented in shim"}
    if shape == "json_equal":
        try:
            ok = json.loads(out) == json.loads(exp)
        except (json.JSONDecodeError, ValueError) as e:
            return {"ok": False, "score": 0.0, "reason": f"json parse error: {e}"}
    elif shape == "regex":
        ok = bool(exp) and bool(re.search(exp, out))
    else:
        ok = bool(exp) and exp.lower() in out.lower()
    return {"ok": ok, "score": 1.0 if ok else 0.0, "reason": f"{shape} {'matched' if ok else 'did not match'}"}

def score_eval(p: dict) -> dict:
    results, npass, nfail = [], 0, 0
    for c in p.get("cases", []) or []:
        r = assess_output({"output": c.get("output", ""), "expected": c.get("expected", ""), "expected_shape": c.get("scorer", "substring")})
        r["name"] = c.get("name", "")
        results.append(r)
        npass, nfail = (npass + 1, nfail) if r["ok"] else (npass, nfail + 1)
    return {"pass": npass, "fail": nfail, "results": results}

HANDLERS = {"validate_intent": validate_intent, "assess_output": assess_output, "score_eval": score_eval}

def _resp(i: Any, r: Any) -> dict: return {"jsonrpc": "2.0", "id": i, "result": r}
def _err(i: Any, c: int, m: str) -> dict: return {"jsonrpc": "2.0", "id": i, "error": {"code": c, "message": m}}

def dispatch(req: dict):
    m, i, p = req.get("method", ""), req.get("id"), req.get("params") or {}
    if m == "initialize":
        return _resp(i, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": SERVER})
    if m == "tools/list":
        return _resp(i, {"tools": TOOLS})
    if m == "tools/call":
        h = HANDLERS.get(p.get("name", ""))
        if not h:
            return _err(i, -32602, f"unknown tool: {p.get('name')}")
        try:
            out = h(p.get("arguments", {}) or {})
        except Exception as e:  # noqa: BLE001 — JSON-RPC must never raise
            return _resp(i, {"content": [{"type": "text", "text": json.dumps({"error": f"{type(e).__name__}: {e}"})}], "isError": True})
        return _resp(i, {"content": [{"type": "text", "text": json.dumps(out)}]})
    if m == "ping":
        return _resp(i, {})
    if m.startswith("notifications/"):
        return None
    return _err(i, -32601, f"method not found: {m}")

def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            r: Any = _err(None, -32700, "parse error")
        else:
            r = dispatch(req)
        if r is not None:
            sys.stdout.write(json.dumps(r) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
