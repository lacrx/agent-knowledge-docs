---
name: integrate-bedrock-knowledge-bases
topics:
  - bedrock
  - knowledge-bases
  - aws
  - python
  - rag
summary: >
  Integrate AWS Bedrock Knowledge Bases retrieval into a Python application with
  a centralized module for retrieve-and-generate and retrieve-only flows,
  configurable query settings, and mock-based testing.
references:
  - articles/ai-ml/bedrock-knowledge-bases.md
last-updated: 2026-06-25
---

# Integrate Bedrock Knowledge Bases

Add a centralized retrieval module to a Python project for querying AWS Bedrock
Knowledge Bases. Supports both retrieve-and-generate (RAG) and retrieve-only
flows with configurable search type, ranking, and score thresholds. Follow steps
in order.

---

## Prerequisites

- Python >= 3.10
- `boto3` installed (`pip install boto3`)
- AWS credentials available via credential chain (env vars, `~/.aws/credentials`, SSO, or instance profile)
- Bedrock model access granted in the target AWS account (Bedrock > Model access in the AWS console)
- A Bedrock Knowledge Base provisioned with at least one synced data source
- Knowledge Base ID known (visible in the Bedrock console under Knowledge Bases)
- Target model ID known for generation (e.g. `anthropic.claude-sonnet-4-20250514`)

---

## Steps

### Step 1: Install dependencies

```bash
pip install boto3
echo "boto3>=1.34.0" >> requirements.txt
```

### Step 2: Create environment configuration

Create a `.env.example`. Never commit real credentials or knowledge base IDs.

```bash
cat > .env.example << 'ENVEOF'
AWS_REGION=us-east-1
AWS_PROFILE=default
BEDROCK_KB_ID=YOUR_KNOWLEDGE_BASE_ID
BEDROCK_KB_MODEL_ID=anthropic.claude-sonnet-4-20250514
BEDROCK_KB_RETRIEVAL_LIMIT=5
BEDROCK_KB_SEARCH_TYPE=HYBRID
BEDROCK_KB_SCORE_THRESHOLD=0.0
BEDROCK_KB_REQUEST_TIMEOUT_SECONDS=30
BEDROCK_KB_RETRIES=3
BEDROCK_KB_OUTPUT_MODE=rag
ENVIRONMENT=development
ENVEOF
```

### Step 3: Create the retrieval module

Create `kb_retriever.py`. This is the single module all application code imports
for Knowledge Base queries.

```python
"""Centralized AWS Bedrock Knowledge Bases retrieval module."""

import logging
import os
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
KB_ID = os.environ.get("BEDROCK_KB_ID", "")
MODEL_ID = os.environ.get("BEDROCK_KB_MODEL_ID", "anthropic.claude-sonnet-4-20250514")
RETRIEVAL_LIMIT = int(os.environ.get("BEDROCK_KB_RETRIEVAL_LIMIT", "5"))
SEARCH_TYPE = os.environ.get("BEDROCK_KB_SEARCH_TYPE", "HYBRID")
SCORE_THRESHOLD = float(os.environ.get("BEDROCK_KB_SCORE_THRESHOLD", "0.0"))
REQUEST_TIMEOUT = int(os.environ.get("BEDROCK_KB_REQUEST_TIMEOUT_SECONDS", "30"))
RETRIES = int(os.environ.get("BEDROCK_KB_RETRIES", "3"))
OUTPUT_MODE = os.environ.get("BEDROCK_KB_OUTPUT_MODE", "rag")

_client = None

def _build_client() -> Any:
    boto_config = Config(
        region_name=AWS_REGION,
        retries={"max_attempts": RETRIES, "mode": "adaptive"},
        read_timeout=REQUEST_TIMEOUT,
        connect_timeout=10,
    )
    profile = os.environ.get("AWS_PROFILE")
    session = boto3.Session(profile_name=profile, region_name=AWS_REGION)
    return session.client("bedrock-agent-runtime", config=boto_config)

def get_client() -> Any:
    global _client
    if _client is None:
        _client = _build_client()
    return _client

def reset_client() -> None:
    global _client
    _client = None

def _handle_client_error(exc: ClientError) -> None:
    error_code = exc.response["Error"]["Code"]
    error_map = {
        "ThrottlingException": (logging.WARNING, "Bedrock throttled request."),
        "AccessDeniedException": (logging.ERROR, "Access denied. Check IAM and model access."),
        "ResourceNotFoundException": (logging.ERROR, "Knowledge Base not found. Verify BEDROCK_KB_ID."),
        "ValidationException": (logging.ERROR, "Invalid parameters. Check search type and model ID."),
        "ServiceQuotaExceededException": (logging.ERROR, "Service quota exceeded."),
    }
    level, msg = error_map.get(error_code, (logging.ERROR, f"Unexpected error: {error_code}"))
    logger.log(level, "%s: %s", msg, exc)

def retrieve_and_generate(
    query: str,
    *,
    knowledge_base_id: str | None = None,
    model_id: str | None = None,
    retrieval_limit: int | None = None,
    search_type: str | None = None,
    metadata_filter: dict | None = None,
) -> dict[str, Any]:
    """Query a Knowledge Base and return an LLM-generated response.
    Returns dict with keys: text, citations, source_chunks.
    """
    client = get_client()
    kb_id = knowledge_base_id or KB_ID
    if not kb_id:
        raise ValueError("Knowledge Base ID is required. Set BEDROCK_KB_ID.")

    vec_cfg: dict[str, Any] = {"numberOfResults": retrieval_limit or RETRIEVAL_LIMIT}
    st = search_type or SEARCH_TYPE
    if st != "SEMANTIC":
        vec_cfg["overrideSearchType"] = st
    if metadata_filter:
        vec_cfg["filter"] = metadata_filter

    try:
        response = client.retrieve_and_generate(
            input={"text": query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": kb_id,
                    "modelArn": model_id or MODEL_ID,
                    "retrievalConfiguration": {"vectorSearchConfiguration": vec_cfg},
                },
            },
        )
    except ClientError as exc:
        _handle_client_error(exc)
        raise

    return _parse_rag_response(response)

def retrieve(
    query: str,
    *,
    knowledge_base_id: str | None = None,
    retrieval_limit: int | None = None,
    search_type: str | None = None,
    metadata_filter: dict | None = None,
) -> list[dict[str, Any]]:
    """Retrieve raw chunks without LLM generation.
    Returns list of dicts with keys: text, score, location, metadata.
    """
    client = get_client()
    kb_id = knowledge_base_id or KB_ID
    if not kb_id:
        raise ValueError("Knowledge Base ID is required. Set BEDROCK_KB_ID.")

    vec_cfg: dict[str, Any] = {"numberOfResults": retrieval_limit or RETRIEVAL_LIMIT}
    st = search_type or SEARCH_TYPE
    if st != "SEMANTIC":
        vec_cfg["overrideSearchType"] = st
    if metadata_filter:
        vec_cfg["filter"] = metadata_filter

    try:
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": vec_cfg},
        )
    except ClientError as exc:
        _handle_client_error(exc)
        raise

    return _parse_retrieve_response(response)
```

### Step 4: Add response parsing utilities

Add these functions to the bottom of `kb_retriever.py`.

```python
def _parse_rag_response(response: dict) -> dict[str, Any]:
    output_text = response.get("output", {}).get("text", "")
    citations = []
    for citation in response.get("citations", []):
        for ref in citation.get("retrievedReferences", []):
            citations.append({
                "text": ref.get("content", {}).get("text", ""),
                "location": ref.get("location", {}),
                "score": ref.get("score"),
            })
    return {"text": output_text, "citations": citations, "source_chunks": [c["text"] for c in citations]}

def _parse_retrieve_response(response: dict) -> list[dict[str, Any]]:
    return [
        {
            "text": r.get("content", {}).get("text", ""),
            "score": r.get("score"),
            "location": r.get("location", {}),
            "metadata": r.get("metadata", {}),
        }
        for r in response.get("retrievalResults", [])
    ]
```

### Step 5: Add retry and error handling

Retry is handled by the adaptive retry mode in the boto3 `Config` (set in
Step 3). The `_handle_client_error` function (also in Step 3) logs structured
details for throttling, access denied, missing KB, validation errors, and quota
limits. No additional code is needed -- both are already wired into
`retrieve_and_generate()` and `retrieve()`.

### Step 6: Add test fixtures and mock patterns

Create `test_kb_retriever.py`. All tests use mocks -- no live Bedrock calls.

```python
"""Tests for kb_retriever using mocked boto3 calls."""

from unittest.mock import MagicMock, patch
import pytest
import kb_retriever

@pytest.fixture(autouse=True)
def _reset():
    kb_retriever.reset_client()
    yield
    kb_retriever.reset_client()

@pytest.fixture()
def mock_client():
    with patch("kb_retriever._build_client") as mock_build:
        client = MagicMock()
        mock_build.return_value = client
        yield client

def _rag_response(text, chunks=None):
    refs = [{"content": {"text": c}, "location": {"type": "S3"}, "score": 0.95} for c in (chunks or [])]
    return {
        "output": {"text": text},
        "citations": [{"retrievedReferences": refs}] if refs else [],
    }

def _retrieve_response(chunks):
    return {"retrievalResults": [
        {"content": {"text": t}, "score": s, "location": {"type": "S3"}, "metadata": {}}
        for t, s in chunks
    ]}

def test_rag_returns_parsed(mock_client):
    mock_client.retrieve_and_generate.return_value = _rag_response("Answer.", ["Chunk A", "Chunk B"])
    result = kb_retriever.retrieve_and_generate("question?", knowledge_base_id="kb-123")
    assert result["text"] == "Answer."
    assert result["source_chunks"] == ["Chunk A", "Chunk B"]

def test_retrieve_returns_chunks(mock_client):
    mock_client.retrieve.return_value = _retrieve_response([("First", 0.95), ("Second", 0.80)])
    result = kb_retriever.retrieve("query", knowledge_base_id="kb-123")
    assert len(result) == 2
    assert result[0]["text"] == "First"
    assert result[0]["score"] == 0.95

def test_rag_raises_without_kb_id(mock_client):
    original = kb_retriever.KB_ID
    kb_retriever.KB_ID = ""
    try:
        with pytest.raises(ValueError, match="Knowledge Base ID is required"):
            kb_retriever.retrieve_and_generate("query")
    finally:
        kb_retriever.KB_ID = original

def test_retrieve_raises_without_kb_id(mock_client):
    original = kb_retriever.KB_ID
    kb_retriever.KB_ID = ""
    try:
        with pytest.raises(ValueError, match="Knowledge Base ID is required"):
            kb_retriever.retrieve("query")
    finally:
        kb_retriever.KB_ID = original

def test_rag_passes_search_type(mock_client):
    mock_client.retrieve_and_generate.return_value = _rag_response("Ok")
    kb_retriever.retrieve_and_generate("q", knowledge_base_id="kb-123", search_type="HYBRID")
    call = mock_client.retrieve_and_generate.call_args[1]
    vec = call["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]
    assert vec["retrievalConfiguration"]["vectorSearchConfiguration"]["overrideSearchType"] == "HYBRID"
```

Run tests:

```bash
python -m pytest test_kb_retriever.py -v
```

### Step 7: Create example query script

Create `example_kb_query.py`:

```python
"""Example: query a Bedrock Knowledge Base."""

from kb_retriever import retrieve, retrieve_and_generate

def example_rag() -> None:
    result = retrieve_and_generate("What is our deployment policy?")
    print("Response:", result["text"])
    for i, c in enumerate(result["citations"], 1):
        print(f"  [{i}] {c['text'][:100]}...")

def example_retrieve_only() -> None:
    chunks = retrieve("deployment rollback procedure", retrieval_limit=3)
    for chunk in chunks:
        print(f"  Score: {chunk['score']:.2f} - {chunk['text'][:100]}...")

if __name__ == "__main__":
    example_rag()
    example_retrieve_only()
```

### Step 8: Verify locally

```bash
aws sts get-caller-identity
python -m pytest test_kb_retriever.py -v
python example_kb_query.py  # requires live Bedrock access
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use Bedrock Knowledge Bases APIs (`bedrock-agent-runtime`), not Kendra or Vertex AI | Bedrock KB is the AWS-native managed RAG service; mixing providers adds complexity |
| Knowledge Base ID and model ID via environment variables | Per-environment configuration without code changes or redeployment |
| Centralize all retrieval logic in `kb_retriever.py` | Single import path makes search-type changes, retries, and logging atomic |
| No secrets or credentials in committed files | Use AWS credential chain; commit only `.env.example` |
| Adaptive retry with configurable max attempts | Handles Bedrock throttling (HTTP 429) with exponential backoff automatically |
| Explicit read timeout | Prevents runaway retrieval requests from blocking the application |
| Support both retrieve-and-generate and retrieve-only flows | Retrieve-only lets callers control the prompt or use a different generation model |
| Test with mocks, never live Bedrock calls | Tests run offline, fast, and free; no AWS account or KB needed in CI |
| Log structured error details per error category | Throttling, access denied, and missing KB require different operational responses |

---

## Outputs

- `kb_retriever.py` -- centralized module with `retrieve_and_generate()` and `retrieve()` functions, response parsing, and error handling
- `.env.example` -- documents all configurable environment variables
- `example_kb_query.py` -- example for RAG and retrieve-only query modes
- `test_kb_retriever.py` -- pytest suite using mocked boto3, no live Bedrock access needed
- Singleton client with adaptive retry and configurable timeout
- Parsed response dicts with text, citations, source chunks, scores, and metadata
