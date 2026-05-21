---
name: ai-output-validation
description: >-
  Pydantic v2 schemas for AI model responses: FindingsReport, StyleReport,
  SynthesisReport, the parse-retry-drop pattern, confidence scoring, and
  structured review finding models. Use when defining or validating output
  from Bedrock Converse API calls.
---
<!-- Vendored from: platform-catalyst/skills/ai-output-validation/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->

# AI output validation

## Role

You guide the design of pydantic v2 schemas that validate Bedrock model output, implementing the parse-retry-drop pattern from `AGENTS.md`.

## Instructions

### 1. The parse-retry-drop pattern

From `AGENTS.md` (AI-native rules):
> Always validate model output against a pydantic schema. Parse failure → retry once → drop the call's contribution if still invalid.

```python
from pydantic import BaseModel, ValidationError
import structlog

logger = structlog.get_logger()

async def validated_converse(
    client: BedrockClient,
    model: BedrockModel,
    system_prompt: str,
    user_message: str,
    schema: type[BaseModel],
    agent_name: str,
) -> BaseModel | None:
    """Converse with validation: parse → retry → drop."""
    for attempt in range(2):  # max 2 attempts
        response = await client.converse(model, system_prompt, user_message)
        text = extract_text(response)

        try:
            # Extract JSON from response (model may wrap in markdown)
            json_str = extract_json_block(text)
            result = schema.model_validate_json(json_str)
            logger.info("ai_output_validated",
                agent=agent_name, attempt=attempt + 1, schema=schema.__name__)
            return result
        except (ValidationError, ValueError) as e:
            logger.warning("ai_output_validation_failed",
                agent=agent_name, attempt=attempt + 1, error=str(e))
            if attempt == 0:
                # Retry with a clarification appended
                user_message += (
                    "\n\nYour previous response did not match the required JSON schema. "
                    f"Validation error: {e}. Please respond with valid JSON only."
                )

    logger.error("ai_output_dropped", agent=agent_name, schema=schema.__name__)
    return None  # Drop this agent's contribution
```

### 2. Finding schemas

```python
from pydantic import BaseModel, Field
from enum import StrEnum
from datetime import datetime

class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class FindingCategory(StrEnum):
    SQL_INJECTION = "sql_injection"
    WILDCARD_IAM = "wildcard_iam"
    SHELL_INJECTION = "shell_injection"
    SECRETS_EXPOSURE = "secrets_exposure"
    MISSING_VALIDATION = "missing_validation"
    PROMPT_INJECTION_ATTEMPT = "prompt_injection_attempt"
    XSS = "xss"
    INSECURE_DESERIALIZATION = "insecure_deserialization"
    OTHER = "other"

class Verdict(StrEnum):
    APPROVE = "approve"
    COMMENT = "comment"
    REQUEST_CHANGES = "request_changes"

class Finding(BaseModel):
    file: str = Field(..., description="File path relative to repo root")
    line: int = Field(..., ge=1, description="Line number")
    severity: Severity
    category: FindingCategory
    description: str = Field(..., min_length=10, max_length=500)
    suggestion: str = Field(..., min_length=10, max_length=500)

class FindingsReport(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    summary: str = Field(..., min_length=10, max_length=1000)
    verdict: Verdict

class StyleSuggestion(BaseModel):
    file: str
    line: int = Field(..., ge=1)
    rule: str = Field(..., description="Convention violated")
    current: str = Field(..., description="What the code currently does")
    suggested: str = Field(..., description="What it should do")

class StyleReport(BaseModel):
    suggestions: list[StyleSuggestion] = Field(default_factory=list)
    summary: str
    verdict: Verdict

class SynthesisReport(BaseModel):
    security_findings: list[Finding] = Field(default_factory=list)
    style_suggestions: list[StyleSuggestion] = Field(default_factory=list)
    combined_summary: str
    final_verdict: Verdict
    review_comment_markdown: str = Field(..., description="GitHub PR review comment body")
```

### 3. JSON extraction helper

Models sometimes wrap JSON in markdown code fences:

```python
import re
import json

def extract_json_block(text: str) -> str:
    """Extract JSON from model output, handling markdown fences."""
    # Try markdown code fence first
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try raw JSON (starts with { or [)
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return text

    raise ValueError(f"No JSON found in model output (length={len(text)})")
```

### 4. Handling dropped contributions

When a model's output fails validation twice, drop it gracefully:

```python
async def run_review_pipeline(diff: str, context: PRContext) -> SynthesisReport:
    security = await validated_converse(client, BedrockModel.SONNET,
        SECURITY_SYSTEM_PROMPT, format_user_message(diff, context),
        FindingsReport, "security-reviewer")

    style = await validated_converse(client, BedrockModel.HAIKU,
        STYLE_SYSTEM_PROMPT, format_user_message(diff, context),
        StyleReport, "style-reviewer")

    # Build synthesis input — handle None (dropped) gracefully
    synthesis_input = build_synthesis_input(
        security_findings=security,
        style_findings=style,
    )

    synthesis = await validated_converse(client, BedrockModel.HAIKU,
        SYNTHESIS_SYSTEM_PROMPT, synthesis_input,
        SynthesisReport, "synthesizer")

    if synthesis is None:
        # Even the synthesizer failed — return a minimal safe report
        return SynthesisReport(
            combined_summary="Review pipeline failed to produce valid output.",
            final_verdict=Verdict.COMMENT,
            review_comment_markdown="Automated review encountered validation errors. Manual review recommended.",
        )

    return synthesis
```

## Output

- **Schema definition**: pydantic v2 model with field constraints + enum types
- **Validation wrapper**: `validated_converse` function with parse-retry-drop
- **JSON extractor**: handles markdown fences and raw JSON

## Guardrails

- Every model output MUST be validated against a pydantic schema — no raw string usage.
- Parse-retry-drop is the pattern — never retry more than once, never force invalid output.
- Field constraints (min_length, max_length, ge) catch malformed model output early.
- Dropped contributions log at `error` level with agent name and schema.
- Never trust model output for security decisions without human review of the schema.
