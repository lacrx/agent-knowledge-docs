---
title: Bedrock LLM Integration
topics:
  - bedrock
  - llm
  - aws
  - python
  - ai-integration
summary: Design patterns and trade-offs for integrating AWS Bedrock LLMs into Python applications, covering client design, prompt handling, retries, structured output, and testing strategies.
skills:
  - integrate-bedrock-llm
aliases:
  - bedrock-ai-integration
  - aws-bedrock-llm
  - bedrock-model-invocation
related:
  - bedrock-knowledge-bases
last-updated: 2026-06-25
---

# Bedrock LLM Integration

## Overview

AWS Bedrock provides managed access to foundation models from Anthropic, Meta, Mistral, Amazon, and others through a unified API. Instead of managing API keys and direct connections to each model provider, Bedrock routes all inference through your AWS account using standard IAM authentication. This simplifies credential management, centralizes billing, and keeps traffic within your AWS network boundary.

Integrating Bedrock into a production application requires more than just calling `invoke_model`. You need a centralized client module, sensible retry and timeout configuration, structured output extraction, and a testing strategy that avoids live model calls. This article covers the design patterns and trade-offs that matter when building Bedrock-backed features in Python applications.

> **Skill:** For step-by-step implementation, use the `integrate-bedrock-llm` skill.

## Centralized Client Design

Wrap all Bedrock interactions behind a single module or class rather than scattering `boto3.client("bedrock-runtime")` calls throughout the codebase. A centralized client provides:

- **One place to configure** model ID, region, retries, and timeouts
- **A seam for testing** -- swap the real client for a stub in tests
- **Consistent error handling** -- catch and translate Bedrock exceptions once

A minimal pattern:

```python
import boto3
from botocore.config import Config

class BedrockLLM:
    def __init__(self, model_id: str, region: str = "us-east-1"):
        self.model_id = model_id
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(
                retries={"max_attempts": 3, "mode": "adaptive"},
                read_timeout=30,
                connect_timeout=5,
            ),
        )

    def invoke(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
        # Model-specific payload construction here
        ...
```

Keep model-specific payload formatting (Anthropic Messages API vs. Meta Llama format vs. Amazon Titan format) inside this module. Callers should pass plain strings or structured messages and get plain strings or parsed objects back.

## Model Selection

Bedrock exposes multiple model families. The choice affects cost, latency, capability, and payload format.

| Model Family | Strengths | Payload Format | Considerations |
|---|---|---|---|
| Anthropic Claude | Reasoning, instruction following, long context | Messages API (JSON) | Highest quality for complex tasks; higher cost per token |
| Meta Llama | Open-weight, good general performance | Llama-specific JSON | Good cost/quality ratio; shorter context windows |
| Amazon Titan | AWS-native, embeddings support | Titan JSON format | Useful for embeddings; text generation quality varies |
| Mistral | Fast inference, code tasks | Mistral JSON format | Good latency; smaller model options available |

Select the model based on the task. Use higher-capability models (Claude) for complex reasoning, extraction, or safety-critical outputs. Use smaller/cheaper models for classification, simple extraction, or high-volume low-stakes tasks. You can use different models for different features within the same application.

Store the model ID in configuration, not in code:

```python
# config.py or environment variable
BEDROCK_MODEL_ID = "anthropic.claude-sonnet-4-20250514"
```

This makes it easy to swap models without code changes when newer versions release or pricing shifts.

## Request Configuration

### Retries

Bedrock can return throttling errors (`ThrottlingException`) or transient failures. Configure retries at the boto3 level:

```python
Config(retries={"max_attempts": 3, "mode": "adaptive"})
```

The `adaptive` retry mode uses exponential backoff with jitter and respects `Retry-After` headers. This is preferred over `standard` mode for LLM workloads where throttling is common under load.

For application-level retries (e.g., retrying on malformed model output), implement your own retry loop with a capped attempt count. Do not retry indefinitely -- LLM failures are often deterministic for a given prompt.

### Timeouts

LLM inference is slow compared to typical API calls. Set timeouts that account for the model and prompt size:

- **`connect_timeout`**: 5-10 seconds (network-level)
- **`read_timeout`**: 30-120 seconds depending on expected output length and model

For streaming responses (`invoke_model_with_response_stream`), the read timeout applies to each chunk, not the full response. Streaming is preferred for user-facing applications to reduce time-to-first-token.

### Token Limits

Always set `max_tokens` explicitly. If omitted, some models default to very short outputs. Setting it too high wastes money on padding. Estimate the expected output length and add a margin:

```python
# Structured extraction: expect ~200 tokens, set 512 for safety
response = llm.invoke(prompt, max_tokens=512, temperature=0.0)

# Free-form generation: expect ~1000 tokens, set 2048
response = llm.invoke(prompt, max_tokens=2048, temperature=0.7)
```

Use `temperature=0.0` for deterministic tasks (extraction, classification). Use higher temperatures only when variation is desired.

## Prompt and Response Handling

### Prompt Construction

Keep prompts as templates with clear structure. Separate the system instruction from the user content:

```python
SYSTEM_PROMPT = """You are a data extraction assistant. Extract the requested
fields from the provided text. Return valid JSON only."""

def build_messages(document: str, fields: list[str]) -> list[dict]:
    return [
        {"role": "user", "content": f"Extract these fields: {fields}\n\nDocument:\n{document}"}
    ]
```

For the Anthropic Messages API on Bedrock, the payload structure mirrors the direct API:

```python
import json

payload = {
    "anthropic_version": "bedrock-2023-05-31",
    "system": SYSTEM_PROMPT,
    "messages": messages,
    "max_tokens": 1024,
    "temperature": 0.0,
}

response = client.invoke_model(
    modelId=model_id,
    contentType="application/json",
    body=json.dumps(payload),
)
```

### JSON Extraction from Responses

LLM responses are strings. When you need structured data, parse the response defensively:

```python
import json
import re

def extract_json(response_text: str) -> dict | None:
    """Extract JSON from an LLM response, handling markdown fences."""
    # Try direct parse first
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None
```

Do not assume the model will always return valid JSON. Even with explicit instructions, models occasionally prepend explanatory text or produce malformed output. Always validate the parsed result against your expected schema before using it.

### Fallback and Error Strategies

Design for failure at multiple levels:

1. **Parse failure**: If JSON extraction fails, retry once with a more explicit prompt ("Return ONLY valid JSON, no other text").
2. **Model error**: If Bedrock returns a service error, the boto3 retry config handles transient issues. For persistent errors, fall back to a secondary model or return a graceful error.
3. **Validation failure**: If the parsed output is missing required fields, retry with the validation error included in the prompt as feedback.
4. **Timeout**: If the model is too slow, consider a smaller model or shorter prompt. Do not simply increase timeouts indefinitely.

```python
def invoke_with_fallback(self, prompt: str, max_retries: int = 2) -> dict | None:
    for attempt in range(max_retries):
        try:
            raw = self.invoke(prompt)
            result = extract_json(raw)
            if result is not None:
                return result
            # Retry with stricter instruction
            prompt = f"{prompt}\n\nIMPORTANT: Return ONLY valid JSON."
        except self.client.exceptions.ThrottlingException:
            if attempt == max_retries - 1:
                raise
    return None
```

## Authentication

Bedrock uses standard AWS credential resolution. The boto3 client automatically checks, in order:

1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`)
2. Shared credential file (`~/.aws/credentials`)
3. AWS config file (`~/.aws/config`)
4. Container credential provider (ECS task role)
5. Instance metadata (EC2 instance profile)

### Local Development

Use `aws sso login` to authenticate during development:

```bash
aws sso login --profile your-profile
export AWS_PROFILE=your-profile
```

This avoids storing long-lived credentials locally. Configure your SSO profile in `~/.aws/config` with the appropriate Bedrock permissions.

### Production

In production (ECS/Fargate, Lambda, EC2), rely on IAM roles attached to the compute resource. The application code does not need to handle credentials explicitly -- boto3 resolves them automatically from the instance/task metadata.

Required IAM permissions for Bedrock inference:

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream"
  ],
  "Resource": "arn:aws:bedrock:*::foundation-model/*"
}
```

Scope the resource ARN to specific models in production to follow least-privilege principles.

## Testing Strategy

Never call live Bedrock endpoints in unit or integration tests. LLM calls are slow, expensive, non-deterministic, and create flaky tests.

### Stubbing the Client

Use the centralized client design to inject stubs:

```python
from unittest.mock import MagicMock

def make_stub_llm(response_text: str) -> BedrockLLM:
    """Create a BedrockLLM with a stubbed boto3 client."""
    llm = BedrockLLM.__new__(BedrockLLM)
    llm.model_id = "test-model"
    llm.client = MagicMock()
    llm.client.invoke_model.return_value = {
        "body": io.BytesIO(json.dumps({
            "content": [{"type": "text", "text": response_text}]
        }).encode())
    }
    return llm
```

### What to Test

- **Prompt construction**: Verify that templates produce the expected messages structure for given inputs.
- **Response parsing**: Test `extract_json` and validation logic against known good and bad response strings.
- **Error handling**: Verify that throttling, timeouts, and malformed responses trigger the expected fallback behavior.
- **Integration boundaries**: Use `botocore.stub.Stubber` for tests that need to verify the exact AWS API call shape without hitting the network.

```python
from botocore.stub import Stubber

def test_invoke_model_call_shape():
    llm = BedrockLLM(model_id="anthropic.claude-sonnet-4-20250514")
    with Stubber(llm.client) as stubber:
        stubber.add_response("invoke_model", expected_response, expected_params)
        result = llm.invoke("test prompt")
        stubber.assert_no_pending_responses()
```

### End-to-End Validation

For periodic confidence that prompts work with real models, maintain a small suite of smoke tests that run against live Bedrock (gated behind an environment flag). These should not run in CI -- run them manually or on a schedule.

> **Skill:** For setting up AWS test infrastructure with mocking, use the `setup-python-aws-tests` skill.

## Bedrock vs. Direct Model-Provider APIs

A key architectural decision is whether to use Bedrock or call model providers directly (e.g., the Anthropic API directly).

| Factor | Bedrock | Direct Provider API |
|---|---|---|
| **Authentication** | IAM roles, no API keys to manage | API keys per provider, must be stored/rotated |
| **Network path** | Stays within AWS (VPC endpoints available) | Traffic leaves your AWS network |
| **Billing** | Consolidated AWS bill | Separate bill per provider |
| **Model availability** | Subset of each provider's models; new models delayed | Full model catalog, day-one access |
| **API compatibility** | AWS-wrapped payload format, slight differences | Native API, full feature set |
| **Rate limits** | AWS account-level quotas, adjustable via support | Provider-level quotas |
| **Streaming** | Supported via `invoke_model_with_response_stream` | Natively supported (SSE) |
| **Features** | May lag on latest features (e.g., tool use, caching) | Latest features immediately |
| **Pricing** | Generally similar; on-demand or provisioned throughput | Pay-per-token, volume discounts vary |

**Use Bedrock when**: your infrastructure is AWS-native, you want unified IAM auth, you need VPC-contained traffic, or you want one billing surface for multiple model providers.

**Use direct APIs when**: you need day-one access to new models/features, your workload is not AWS-hosted, or you need provider-specific features not yet available in Bedrock.

In many cases, a hybrid approach works: use Bedrock for production workloads (benefiting from IAM and network controls) and direct APIs for development/experimentation (benefiting from faster feature availability).

## Common Mistakes

- **Hardcoding model IDs** throughout the codebase instead of centralizing in configuration. Model versions change; update one config value, not twenty files.
- **No timeout configuration**. The default boto3 read timeout (60s) may be too short for long-context prompts or too generous for latency-sensitive paths.
- **Testing with live models in CI**. This creates slow, expensive, flaky pipelines. Stub the client and test prompt construction and response parsing separately.
- **Ignoring response parsing failures**. Models do not always return valid JSON even when instructed. Always handle the parse-failure path.
- **Using the same model for all tasks**. A classification task does not need the same model as a multi-step reasoning task. Match model capability (and cost) to the task.
- **Not setting `temperature=0.0` for deterministic tasks**. Non-zero temperature adds randomness that makes extraction and classification outputs inconsistent and harder to test.
- **Overly broad IAM permissions**. Granting `bedrock:*` when only `InvokeModel` on specific models is needed violates least privilege.
- **Retrying on deterministic failures**. If the model consistently returns bad output for a prompt, retrying the same prompt wastes money. Modify the prompt or fall back.

## References

- [AWS Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/)
- [Boto3 Bedrock Runtime API Reference](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-runtime.html)
- [Botocore Retry Configuration](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/retries.html)
