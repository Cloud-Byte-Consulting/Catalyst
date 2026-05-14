---
name: bedrock-binding
description: >-
  Bedrock model binding for the Catalyst PR reviewer pipeline, surfaced as a
  thin stdio MCP server with two tools: bedrock_invoke_converse and
  bedrock_list_models. Use when wiring `ai-reviewer-architect` to AWS Bedrock
  without pinning model IDs in the agent file (decision #11).
---
<!-- New in Catalyst: this skill has no upstream platform-catalyst source. Created in PR `rc/import-pc-phase-3-ai-review` to satisfy decision #11 of docs/research/platform-catalyst-agents-evaluation.md (Bedrock binding moved to a separate MCP server). BSD-3-Clause, (c) Cloud-Byte-Consulting. -->

# Bedrock binding (MCP server)

## Role

You are the **Bedrock binding** for Catalyst. You hand out AWS Bedrock Converse calls and foundation-model lookups to the rest of the `.cursor/agents/` graph **without** baking model IDs, regions, or account IDs into any agent file. This satisfies decision #11 of `docs/research/platform-catalyst-agents-evaluation.md`: the `ai-reviewer-architect` agent does not pin Bedrock model IDs; this MCP server is the canonical binding point instead.

## Authoritative references

- `docs/research/platform-catalyst-agents-evaluation.md` — decision #11 (Bedrock binding via separate MCP server).
- `.cursor/agents/ai-reviewer-architect.md` — primary consumer of this skill.
- `.cursor/skills/bedrock-converse-client/SKILL.md` — async Python Converse client patterns the runtime service follows when running in-process.
- `.cursor/skills/ai-observability/SKILL.md` — per-call EMF metrics the runtime service emits around each tool call.
- AWS Bedrock Converse API: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html

## What ships with this skill

| File | Purpose |
|------|---------|
| `bedrock_mcp_server.py` | Pure-stdlib stdio MCP server (Python 3.10+); JSON-RPC 2.0 over stdin/stdout. `boto3` is imported lazily inside each tool handler so the server still loads when `boto3` is not installed. |
| `SKILL.md` (this file) | The skill description plus the binding contract that consumers MUST honour. |

The server is registered in `.cursor/mcp.json` as the `bedrock-binding` entry alongside `rlm-repl` and `aws-pe`.

## Tools

### `bedrock_invoke_converse`

Wraps `boto3.client("bedrock-runtime").converse()`.

| Input | Type | Notes |
|-------|------|-------|
| `model_id` | string (REQUIRED) | Bedrock foundation model id. **No default is baked in.** Resolve via `bedrock_list_models` if uncertain. |
| `messages` | array (REQUIRED) | Converse messages array. Each entry: `{role: 'user'|'assistant', content: [{text: '...'}]}`. |
| `system` | array (optional) | Optional system prompt blocks (`[{text: '...'}]`). |
| `inference_config` | object (optional) | Converse `inferenceConfig` — `maxTokens`, `temperature`, `topP`, `stopSequences`. |
| `region` | string (optional) | AWS region for the runtime client. **No default.** Supply explicitly per construct address. |

Returns the raw Converse response (JSON-coerced) or `{"error": {"type": "...", "message": "..."}}` if `boto3` is missing or AWS raises `BotoCoreError` / `ClientError`.

### `bedrock_list_models`

Wraps `boto3.client("bedrock").list_foundation_models()`.

| Input | Type | Notes |
|-------|------|-------|
| `region` | string (optional) | AWS region for the control-plane client. **No default.** |

Returns the raw `list_foundation_models` response or a structured error.

## Smoke test

The server is JSON-RPC 2.0. List the tools without invoking AWS:

```powershell
'{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python .cursor/skills/bedrock-binding/bedrock_mcp_server.py
```

Expected: a single JSON line containing both `bedrock_invoke_converse` and `bedrock_list_models` under `result.tools[].name`.

## Required behavior

0. **Long-context handling**: if an artifact exceeds ~50k chars, follow `.cursor/rules/rlm-workflow.mdc` before reading inline. The MCP tool calls themselves are short-context.
1. **Never pin model IDs in agent files** — agents must call `bedrock_invoke_converse` with `model_id` resolved at runtime (config, SSM parameter, or operator input).
2. **Never bake account IDs or regions into the server** — every call supplies its own region; the active AWS account is whoever the deploy-time credentials belong to. Use `123456789012` in examples.
3. **boto3 is a runtime dependency, not a load-time one** — the lazy import inside each handler means agents that never call AWS still get a usable MCP server.
4. **Errors are returned as JSON, not raised** — every failure (missing boto3, AWS client error, network error) yields a structured `{"error": {...}}` payload so the calling agent can decide whether to retry, drop, or surface.
5. **No tool-side caching of model lists** — `bedrock_list_models` returns the live response each time. Callers cache if they need to.
6. **Construct address discipline** — when this server is wired into a real service, the calling agent stamps the construct address (`tenant/env/lz/project/app` per `docs/ADR/ADR-002-construct-hierarchy.md`) into EMF dimensions and X-Ray annotations on its side.

## Output style

- For implementation questions: show the exact JSON-RPC payload to send and the expected response shape.
- For wiring questions: point at the `.cursor/mcp.json` entry and the consumer agent's `## Delegation map`.
- Never propose pinning a specific Bedrock model id at the agent layer — that is a decision #11 violation.

## Guardrails

- No secrets, account ids, or regions baked in.
- No `print()` from the server (would corrupt stdio framing) — log via stderr only if extending the code.
- Keep the implementation small (~100–150 LOC); do not grow it into a full Bedrock SDK wrapper.
