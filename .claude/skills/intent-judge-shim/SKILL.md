<!-- AUTO-GENERATED from skills/intent-judge-shim/SKILL.md — do not edit here. Run scripts/sync_tool_skills.py to regenerate. -->
<!-- New in Catalyst per decision #3 (intent-judge re-implementation). No upstream SKILL.md source — built from the Delegation map in platform-catalyst/.cursor/agents/intent-judge.md (BittahCriminal/platform-catalyst, BSD-3-Clause). -->
---
name: intent-judge-shim
description: >-
  Thin Cursor MCP server that gates high-risk tool calls with an allow/deny/clarify
  verdict and aggregates output assessments. Implements the three tools called out
  in the upstream intent-judge agent's Delegation map (validate_intent,
  assess_output, score_eval) without vendoring the full plugins/catalyst-judge/
  package. Use when wiring the .cursor/rules/intent-judge.mdc rule, debugging the
  shim, or running smoke tests against it.
---

# intent-judge-shim

## Role

Owns the **thin MCP shim** that backs `.cursor/rules/intent-judge.mdc`. This is
the Catalyst-native answer to decision #3 in
`docs/research/platform-catalyst-agents-evaluation.md`:

> Re-implement as a **lightweight Cursor rule + thin MCP shim (~80 lines)**.
> Do **not** vendor the full `plugins/catalyst-judge/` package.

The shim is `intent_judge_mcp_server.py` in this directory: pure-stdlib
Python, JSON-RPC 2.0 over stdio, hard-capped at ~80 effective lines of code
(excluding module docstring and import header).

## Authoritative references

- `.cursor/rules/intent-judge.mdc` — the rule that selects this server.
- `.cursor/mcp.json` — registers the shim as the `intent-judge` MCP server.
- `docs/research/platform-catalyst-agents-evaluation.md` §5.4 + decision #3 — full rationale.
- Upstream `BittahCriminal/platform-catalyst/.cursor/agents/intent-judge.md` (BSD-3-Clause) — the source agent file whose **Delegation map** the three tools below mirror. We do not import the file itself, only its three-tool surface.

## Binding contract

```jsonc
// .cursor/mcp.json
"intent-judge": {
  "command": "python",
  "args": [".cursor/skills/intent-judge-shim/intent_judge_mcp_server.py"],
  "env": {}
}
```

The server speaks MCP stdio. Reload Cursor after editing `mcp.json`. No
external dependencies — Python 3.10+ stdlib is sufficient.

## Tools

| Tool              | Inputs                                                                                                | Output                                                                                                  |
|-------------------|-------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| `validate_intent` | `tool_name: string`, `arguments: object`, optional `context: string`                                  | `{ verdict: "allow"\|"deny"\|"clarify", reason: string, scanners: { secrets, pii, injection } }`        |
| `assess_output`   | `output: string`, optional `expected: string`, optional `expected_shape: substring\|regex\|json_equal\|llm_judge` | `{ ok: bool, score: 0.0..1.0, reason: string }`                                                         |
| `score_eval`      | `cases: [{ name, output, expected, scorer }]`                                                         | `{ pass: int, fail: int, results: [ { name, ok, score, reason } ] }`                                    |

### Heuristic surface

`validate_intent` runs three deterministic scanners against
`tool_name + json(arguments) + context`:

- **Secrets** — `AKIA`/`ASIA` IDs, `ghp_` tokens, JWT `eyJ…` two-part, `-----BEGIN … PRIVATE KEY-----`.
- **Injection** — `ignore previous`, leading `system:`, `<|im_start|>`, base64 blobs over 120 chars.
- **PII** — email, SSN-shaped digits, credit-card-shaped digits.

A `secrets` or `injection` hit returns `deny`. A `pii`-only hit returns
`clarify`. Otherwise `allow`. There is no LLM fallback — escalation to a
language model is intentionally out of scope (decision #3); use
`@ai-reviewer-architect` + the Bedrock binding MCP if you need a model in
the loop.

### llm_judge is rejected

`assess_output` with `expected_shape: "llm_judge"` deliberately returns
`{ ok: false, score: 0.0, reason: "llm_judge requires upstream LLM call; not implemented in shim" }`.
This is the LOC-cap discipline made visible — adding an LLM client to this
file is a decision-#3 violation and should be raised as a new Kaizen issue
instead.

## How Catalyst invokes this

1. The rule `.cursor/rules/intent-judge.mdc` activates on high-risk tool
   calls (writes, deletes, deploys, secret ops, broad-scope automation).
2. The agent calls `validate_intent` via this MCP server before executing
   the tool call.
3. On `allow`, the agent proceeds and calls `assess_output` against the
   result. On `deny` or `clarify`, the agent halts and transitions an
   Issue to `state/blocked-on-human` per ADR-001.
4. Eval harnesses (`@eval-scoring` style) aggregate per-case results via
   `score_eval`.

## How to invoke from outside Cursor (smoke test)

```powershell
# tools/list — confirms the three tools are advertised
'{"jsonrpc":"2.0","id":1,"method":"tools/list"}' `
  | python .cursor/skills/intent-judge-shim/intent_judge_mcp_server.py
```

```powershell
# validate_intent with a planted secret — expect "deny"
'{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"validate_intent","arguments":{"tool_name":"shell","arguments":{"cmd":"export AWS_SECRET=AKIAIOSFODNN7EXAMPLE"}}}}' `
  | python .cursor/skills/intent-judge-shim/intent_judge_mcp_server.py
```

```powershell
# assess_output with expected_shape=llm_judge — expect ok=false (shim cap)
'{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"assess_output","arguments":{"output":"x","expected":"y","expected_shape":"llm_judge"}}}' `
  | python .cursor/skills/intent-judge-shim/intent_judge_mcp_server.py
```

## Guardrails

- **Do not** vendor `plugins/catalyst-judge/`. Decision #3 is explicit.
- **Do not** add LLM clients, persistent state, or non-stdlib imports.
  If a feature needs more than what fits in ~80 effective LOC, open a
  Kaizen issue and revisit the vendoring decision in the open.
- **Errors do not escape** — JSON-RPC must always return a response. The
  dispatcher wraps tool exceptions and forwards them as `isError: true`
  content.
- **No real secrets in tests** — fixtures must use `AKIAIOSFODNN7EXAMPLE`
  or other documented placeholder values.

## Provenance

This skill is **new in Catalyst** — there is no upstream SKILL.md to vendor.
It encodes the rule-+-shim direction locked in
`docs/research/platform-catalyst-agents-evaluation.md` decision #3 and
mirrors the three-tool Delegation map from
`BittahCriminal/platform-catalyst/.cursor/agents/intent-judge.md`
(BSD-3-Clause). Adapted for Catalyst: pure stdlib, ~80 LOC cap, no LLM
client, no vendored package, ADR-001 escalation path.
