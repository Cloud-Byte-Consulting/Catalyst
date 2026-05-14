---
name: bedrock-converse-client
description: >-
  Bedrock runtime Converse/ConverseStream API patterns: message structure,
  model ID selection, token limits, system prompts, retry with tenacity,
  error handling, and async client management. Use when making Bedrock
  API calls from pr-reviewer-consumer or ops-intel-reporter.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/bedrock-converse-client/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# Bedrock Converse client

## Role

You guide implementation of Bedrock Converse API calls in Catalyst services, ensuring correct message structure, model selection, and error handling per `AGENTS.md` Bedrock-specific guidance.

## Instructions

### 1. Async client setup

```python
import aioboto3
from types import TracebackType

class BedrockClient:
    """Async Bedrock runtime client with connection reuse."""

    def __init__(self, region: str = "us-east-1"):
        self._session = aioboto3.Session()
        self._region = region
        self._client = None

    async def __aenter__(self):
        self._client = await self._session.client(
            "bedrock-runtime", region_name=self._region
        ).__aenter__()
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.__aexit__(*exc)
```

### 2. Model IDs (pinned from AGENTS.md)

```python
from enum import StrEnum

class BedrockModel(StrEnum):
    SONNET = "anthropic.claude-sonnet-4-5-20250929-v1:0"  # correctness + security
    HAIKU = "anthropic.claude-3-5-haiku-20241022-v1:0"    # style + synthesis + ops-intel
```

### 3. Converse API call

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from botocore.exceptions import ClientError

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(ClientError),
)
async def converse(
    self,
    model: BedrockModel,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> dict:
    """Call Bedrock Converse API with retry on transient errors."""
    response = await self._client.converse(
        modelId=model,
        messages=[
            {
                "role": "user",
                "content": [{"text": user_message}],
            }
        ],
        system=[{"text": system_prompt}],
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
    )
    return response
```

### 4. Response extraction

```python
def extract_text(response: dict) -> str:
    """Extract text content from Converse API response."""
    output = response.get("output", {})
    message = output.get("message", {})
    content = message.get("content", [])
    return "".join(block.get("text", "") for block in content)

def extract_usage(response: dict) -> dict:
    """Extract token usage from Converse API response."""
    usage = response.get("usage", {})
    return {
        "input_tokens": usage.get("inputTokens", 0),
        "output_tokens": usage.get("outputTokens", 0),
        "total_tokens": usage.get("inputTokens", 0) + usage.get("outputTokens", 0),
    }
```

### 5. Streaming (ConverseStream)

```python
async def converse_stream(
    self,
    model: BedrockModel,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 4096,
) -> AsyncIterator[str]:
    """Stream responses from Bedrock ConverseStream API."""
    response = await self._client.converse_stream(
        modelId=model,
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        system=[{"text": system_prompt}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0},
    )
    stream = response.get("stream")
    async for event in stream:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            text = delta.get("text", "")
            if text:
                yield text
```

### 6. Error handling

- **ThrottlingException**: retry with exponential backoff (tenacity handles this)
- **ModelTimeoutException**: retry once, then log and skip
- **ValidationException**: do NOT retry — malformed request, fix the code
- **AccessDeniedException**: do NOT retry — IAM misconfiguration

### 7. Cross-region failover

Per `AGENTS.md` and the Bedrock binding MCP (`.cursor/skills/bedrock-binding/`): use inference profiles for us-east-1 ↔ us-west-2 failover without code changes. The model ID in the profile handles routing. Model IDs are never pinned in agent files (decision #11) — supply them via the MCP server inputs.

## Output

- **Client class**: async context manager with Converse/ConverseStream methods
- **Call pattern**: system prompt + user message + config + response extraction
- **Error handling**: retry decorator + error classification

## Guardrails

- Always Converse API, never InvokeModel.
- Model IDs are string constants, never user input.
- Temperature 0.0 for deterministic review output.
- Max 2 retries on transient errors, 0 on permanent.
- Never log the full diff content — it may contain secrets. Log metadata only (file count, line count).
