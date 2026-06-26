---
name: integrate-bedrock-llm
title: Integrate AWS Bedrock LLM
type: skill
topics:
  - aws
  - python
  - bedrock
  - llm
  - agent-workflow
summary: >
  Integrate AWS Bedrock LLM access into a Python application with a centralized
  client module for text generation and structured JSON extraction, configurable
  model selection, retry logic, and a mock-based testing pattern.
references:
  - skills/setup-python-aws-tests.md
  - articles/ai-ml/bedrock-llm-integration.md
last-updated: 2026-06-25
---

# Integrate AWS Bedrock LLM

Add a centralized Bedrock client module to a Python project for text generation
and structured output extraction. Follow steps in order.

---

## Prerequisites

- Python >= 3.10
- `boto3` installed (`pip install boto3`)
- AWS credentials available via credential chain (env vars, `~/.aws/credentials`, SSO, or instance profile)
- Bedrock model access granted in the target AWS account (request via AWS console under Bedrock > Model access)
- Target model ID known (e.g. `anthropic.claude-sonnet-4-20250514`, `amazon.titan-text-express-v1`)

---

## Steps

### Step 1: Configure environment variables

Create a `.env.example` file documenting every variable. Never commit real
credentials.

```bash
cat > .env.example << 'ENVEOF'
# AWS Bedrock configuration
AWS_REGION=us-east-1
AWS_PROFILE=default
BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-20250514
BEDROCK_MAX_TOKENS=1024
BEDROCK_TEMPERATURE=0.7
BEDROCK_TOP_P=0.9
BEDROCK_STOP_SEQUENCES=[]
BEDROCK_REQUEST_TIMEOUT_SECONDS=60
BEDROCK_RETRIES=3
BEDROCK_STREAMING_ENABLED=false
ENVEOF
```

Export variables for the current session:

```bash
export AWS_REGION="us-east-1"
export AWS_PROFILE="default"
export BEDROCK_MODEL_ID="anthropic.claude-sonnet-4-20250514"
export BEDROCK_MAX_TOKENS="1024"
export BEDROCK_TEMPERATURE="0.7"
export BEDROCK_TOP_P="0.9"
export BEDROCK_STOP_SEQUENCES="[]"
export BEDROCK_REQUEST_TIMEOUT_SECONDS="60"
export BEDROCK_RETRIES="3"
export BEDROCK_STREAMING_ENABLED="false"
```

### Step 2: Authenticate with AWS

Use SSO or static credentials. SSO is preferred for development.

```bash
# Option A: SSO login
aws sso login --profile "${AWS_PROFILE}"

# Option B: Verify existing credentials
aws sts get-caller-identity --profile "${AWS_PROFILE}"

# Verify Bedrock model access
aws bedrock list-foundation-models \
  --region "${AWS_REGION}" \
  --query "modelSummaries[?modelId=='${BEDROCK_MODEL_ID}'].modelId" \
  --output text
```

### Step 3: Create the Bedrock client module

Create `bedrock_client.py` in your project source directory. This is the single
module all application code imports for LLM calls.

```python
"""Centralized AWS Bedrock client for text generation and structured output."""

import json
import logging
import os
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-20250514")
MAX_TOKENS = int(os.environ.get("BEDROCK_MAX_TOKENS", "1024"))
TEMPERATURE = float(os.environ.get("BEDROCK_TEMPERATURE", "0.7"))
TOP_P = float(os.environ.get("BEDROCK_TOP_P", "0.9"))
STOP_SEQUENCES = json.loads(os.environ.get("BEDROCK_STOP_SEQUENCES", "[]"))
REQUEST_TIMEOUT = int(os.environ.get("BEDROCK_REQUEST_TIMEOUT_SECONDS", "60"))
RETRIES = int(os.environ.get("BEDROCK_RETRIES", "3"))
STREAMING_ENABLED = os.environ.get("BEDROCK_STREAMING_ENABLED", "false").lower() == "true"


def _build_client() -> Any:
    """Build a boto3 Bedrock Runtime client with retry and timeout config."""
    boto_config = Config(
        region_name=AWS_REGION,
        retries={"max_attempts": RETRIES, "mode": "adaptive"},
        read_timeout=REQUEST_TIMEOUT,
        connect_timeout=10,
    )
    profile = os.environ.get("AWS_PROFILE")
    session = boto3.Session(profile_name=profile, region_name=AWS_REGION)
    return session.client("bedrock-runtime", config=boto_config)


_client = None


def get_client() -> Any:
    """Return a cached Bedrock Runtime client (singleton)."""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def reset_client() -> None:
    """Reset the cached client. Useful for tests or credential rotation."""
    global _client
    _client = None


# ---------------------------------------------------------------------------
# Text generation
# ---------------------------------------------------------------------------


def generate(
    prompt: str,
    *,
    system: str | None = None,
    model_id: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    stop_sequences: list[str] | None = None,
) -> str:
    """Send a prompt to Bedrock and return the generated text.

    Uses the Converse API which works across model families.
    All parameters fall back to environment-configured defaults.

    Raises:
        ClientError: on throttling, access denied, or model errors.
    """
    client = get_client()

    messages = [{"role": "user", "content": [{"text": prompt}]}]

    inference_config: dict[str, Any] = {
        "maxTokens": max_tokens or MAX_TOKENS,
        "temperature": temperature if temperature is not None else TEMPERATURE,
        "topP": top_p if top_p is not None else TOP_P,
    }
    stops = stop_sequences if stop_sequences is not None else STOP_SEQUENCES
    if stops:
        inference_config["stopSequences"] = stops

    kwargs: dict[str, Any] = {
        "modelId": model_id or MODEL_ID,
        "messages": messages,
        "inferenceConfig": inference_config,
    }
    if system:
        kwargs["system"] = [{"text": system}]

    try:
        response = client.converse(**kwargs)
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "ThrottlingException":
            logger.warning("Bedrock throttled request: %s", exc)
        elif error_code == "AccessDeniedException":
            logger.error("Bedrock access denied. Check model access and IAM: %s", exc)
        elif error_code == "ModelNotReadyException":
            logger.error("Bedrock model not ready: %s", exc)
        raise

    output_message = response["output"]["message"]
    return output_message["content"][0]["text"]


# ---------------------------------------------------------------------------
# Structured JSON extraction
# ---------------------------------------------------------------------------


def generate_json(
    prompt: str,
    *,
    system: str | None = None,
    model_id: str | None = None,
    max_tokens: int | None = None,
) -> Any:
    """Generate a response and parse it as JSON.

    Appends an instruction to return valid JSON. Raises ValueError if the
    response cannot be parsed.
    """
    json_instruction = (
        "Respond with valid JSON only. No markdown fences, no extra text."
    )
    full_system = f"{system}\n\n{json_instruction}" if system else json_instruction

    raw = generate(
        prompt,
        system=full_system,
        model_id=model_id,
        max_tokens=max_tokens,
        temperature=0.0,
    )

    # Strip markdown fences if the model returns them anyway
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Bedrock response as JSON: %s", raw[:200])
        raise ValueError(f"Bedrock response is not valid JSON: {exc}") from exc
```

### Step 4: Create an example invocation script

```python
"""Example: call Bedrock for text generation and structured extraction."""

from bedrock_client import generate, generate_json


def example_text_generation() -> None:
    """Simple text generation."""
    response = generate(
        "Explain the CAP theorem in two sentences.",
        system="You are a concise distributed systems instructor.",
        max_tokens=256,
    )
    print("Text response:", response)


def example_structured_extraction() -> None:
    """Extract structured data as JSON."""
    result = generate_json(
        "List the three pillars of observability with a one-line description each.",
        system="You are a DevOps expert.",
        max_tokens=512,
    )
    print("Structured response:", result)


if __name__ == "__main__":
    example_text_generation()
    example_structured_extraction()
```

### Step 5: Create tests with mocks

Create `test_bedrock_client.py`. All tests use mocks -- no live Bedrock calls.

```python
"""Tests for bedrock_client using mocked boto3 calls."""

import json
from unittest.mock import MagicMock, patch

import pytest

import bedrock_client


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the singleton client before each test."""
    bedrock_client.reset_client()
    yield
    bedrock_client.reset_client()


def _mock_converse_response(text: str) -> dict:
    """Build a mock Converse API response."""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 20},
    }


@patch("bedrock_client._build_client")
def test_generate_returns_text(mock_build):
    """generate() returns the text content from the Converse response."""
    mock_client = MagicMock()
    mock_client.converse.return_value = _mock_converse_response("Hello world")
    mock_build.return_value = mock_client

    result = bedrock_client.generate("Say hello")

    assert result == "Hello world"
    mock_client.converse.assert_called_once()
    call_kwargs = mock_client.converse.call_args[1]
    assert call_kwargs["modelId"] == bedrock_client.MODEL_ID
    assert call_kwargs["messages"][0]["content"][0]["text"] == "Say hello"


@patch("bedrock_client._build_client")
def test_generate_with_system_prompt(mock_build):
    """generate() passes the system prompt when provided."""
    mock_client = MagicMock()
    mock_client.converse.return_value = _mock_converse_response("Ok")
    mock_build.return_value = mock_client

    bedrock_client.generate("Hi", system="Be brief")

    call_kwargs = mock_client.converse.call_args[1]
    assert call_kwargs["system"] == [{"text": "Be brief"}]


@patch("bedrock_client._build_client")
def test_generate_json_parses_response(mock_build):
    """generate_json() parses a valid JSON response."""
    payload = {"pillars": ["metrics", "logs", "traces"]}
    mock_client = MagicMock()
    mock_client.converse.return_value = _mock_converse_response(json.dumps(payload))
    mock_build.return_value = mock_client

    result = bedrock_client.generate_json("List pillars")

    assert result == payload


@patch("bedrock_client._build_client")
def test_generate_json_strips_markdown_fences(mock_build):
    """generate_json() strips markdown code fences from the response."""
    payload = {"key": "value"}
    fenced = f"```json\n{json.dumps(payload)}\n```"
    mock_client = MagicMock()
    mock_client.converse.return_value = _mock_converse_response(fenced)
    mock_build.return_value = mock_client

    result = bedrock_client.generate_json("Extract data")

    assert result == payload


@patch("bedrock_client._build_client")
def test_generate_json_raises_on_invalid_json(mock_build):
    """generate_json() raises ValueError when response is not valid JSON."""
    mock_client = MagicMock()
    mock_client.converse.return_value = _mock_converse_response("not json at all")
    mock_build.return_value = mock_client

    with pytest.raises(ValueError, match="not valid JSON"):
        bedrock_client.generate_json("Extract data")


@patch("bedrock_client._build_client")
def test_generate_overrides_defaults(mock_build):
    """generate() applies per-call overrides for model_id, max_tokens, etc."""
    mock_client = MagicMock()
    mock_client.converse.return_value = _mock_converse_response("Done")
    mock_build.return_value = mock_client

    bedrock_client.generate(
        "Hi",
        model_id="amazon.titan-text-express-v1",
        max_tokens=100,
        temperature=0.0,
        top_p=1.0,
        stop_sequences=["\n"],
    )

    call_kwargs = mock_client.converse.call_args[1]
    assert call_kwargs["modelId"] == "amazon.titan-text-express-v1"
    assert call_kwargs["inferenceConfig"]["maxTokens"] == 100
    assert call_kwargs["inferenceConfig"]["temperature"] == 0.0
    assert call_kwargs["inferenceConfig"]["topP"] == 1.0
    assert call_kwargs["inferenceConfig"]["stopSequences"] == ["\n"]
```

### Step 6: Run the tests

```bash
python -m pytest test_bedrock_client.py -v
```

### Step 7: Add Bedrock client to project dependencies

```bash
# If using requirements.txt
echo "boto3>=1.34.0" >> requirements.txt

# If using pyproject.toml, add to the dependencies list
# "boto3>=1.34.0"
```

### Step 8: Verify credentials and run the example

```bash
# Confirm credentials are valid
aws sts get-caller-identity

# Run the example (requires live Bedrock access)
python example_bedrock.py
```

### Step 9: Commit and PR

```bash
git add bedrock_client.py test_bedrock_client.py .env.example
git commit -m "Add centralized Bedrock LLM client module with tests"
gh pr create --title "Integrate Bedrock LLM client" --body "Adds Bedrock client module with Converse API, structured JSON extraction, retry/timeout config, and mock-based tests"
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use boto3 Bedrock Runtime client only | Bedrock is the AWS-native LLM service; do not mix in Vertex AI or other provider tooling |
| Centralize all Bedrock calls in one module | Single import path makes model swaps, retries, and logging changes atomic |
| Use the Converse API, not `invoke_model` | Converse works across model families without model-specific payload formatting |
| Model ID and generation settings via environment | Allows per-environment tuning without code changes; no redeployment needed |
| No secrets or credentials in committed files | Use AWS credential chain (`AWS_PROFILE`, SSO, instance role); commit only `.env.example` |
| Adaptive retry mode with configurable max attempts | Handles Bedrock throttling (HTTP 429) with exponential backoff automatically |
| Set explicit read timeout | Prevents runaway requests from blocking the application indefinitely |
| Temperature 0.0 for structured extraction | Deterministic output reduces JSON parse failures |
| Test with mocks, never live Bedrock calls | Tests run offline, fast, and free; no AWS account required in CI |
| Strip markdown fences in JSON extraction | Models sometimes wrap JSON in code fences despite instructions |

---

## Outputs

- `bedrock_client.py` -- centralized module with `generate()` and `generate_json()` functions
- `.env.example` -- documents all configurable environment variables
- `example_bedrock.py` -- copy-paste example for text and structured invocation
- `test_bedrock_client.py` -- pytest suite using mocked boto3, no live calls
- Singleton client with adaptive retry and configurable timeout
- Structured JSON extraction with fence-stripping and parse error handling
