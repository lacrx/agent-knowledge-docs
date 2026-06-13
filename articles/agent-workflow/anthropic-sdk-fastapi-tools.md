---
title: Anthropic SDK + FastAPI — Building AI-Powered APIs
topics:
  - anthropic-sdk
  - fastapi
  - python
  - api-development
  - ai-development
  - tools
skills:
  - build-fastapi-ai-server
summary: >
  Advisory guide for building AI-powered APIs with the Anthropic Python SDK and FastAPI —
  Pydantic models, streaming responses, tool use, OpenAPI generation, and background tasks.
aliases:
  - anthropic sdk fastapi
  - fastapi ai
  - python fastapi api
  - fastapi claude
related:
  - spec-based-development
  - claude-agent-sdk-tools
  - vercel-ai-sdk-tools
  - copilot-sdk-tools
last-updated: 2026-06-12
---

# Python FastAPI — Building AI-Powered APIs

## Overview

FastAPI (`pip install fastapi`) lets you build high-performance APIs with automatic OpenAPI spec generation, Pydantic validation, and async support. For AI apps, it pairs with the Anthropic SDK to serve Claude-powered endpoints with streaming, tool use, and structured output — your job is to define routes, models, and wire up the AI client.

> **Skill:** For step-by-step implementation including the minimal working example, use the `build-fastapi-ai-server` skill.

---

## The Three Things You Need

Every FastAPI AI project needs exactly three pieces:

| Object              | Lifecycle             | Description                                                          |
|---------------------|-----------------------|----------------------------------------------------------------------|
| `FastAPI()`         | Long-lived, one per app | Application instance; holds routes, middleware, lifespan events     |
| `Anthropic()`       | Long-lived, one per app | Claude API client; handles authentication and requests              |
| Pydantic `BaseModel` | One per request/response | Defines typed schemas for validation, serialization, and OpenAPI  |

FastAPI handles request validation, serialization, and OpenAPI generation automatically. The Anthropic SDK handles the tool loop. Your job is to connect them.

---

## Authentication

Two keys to manage — never hard-code either:

```bash
# Claude API access
ANTHROPIC_API_KEY="sk-ant-..."

# Optional: your own API auth for clients
API_SECRET_KEY="your-app-secret"
```

The Anthropic client reads `ANTHROPIC_API_KEY` from environment automatically.

---

## Core Dependencies

```bash
pip install fastapi uvicorn anthropic pydantic
```

| Package      | Purpose                                    |
|--------------|--------------------------------------------|
| `fastapi`    | Web framework, routing, OpenAPI generation |
| `uvicorn`    | ASGI server to run the app                 |
| `anthropic`  | Claude API client                          |
| `pydantic`   | Request/response models, validation        |

---

## Route & Model Definition

Define request/response models with Pydantic, then wire to routes:

```python
from pydantic import BaseModel, Field
from fastapi import FastAPI

app = FastAPI()

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message to send to Claude")
    model: str = Field("claude-sonnet-4-6", description="Model to use")
    max_tokens: int = Field(1024, description="Max tokens in response")

class ChatResponse(BaseModel):
    content: str
    model: str
    usage: dict

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    ...
```

Rules:
- Use `Field(..., description='...')` on every field — drives OpenAPI docs
- Response models enforce output shape; clients get typed contracts
- FastAPI validates input automatically — invalid requests return 422

---

## Anthropic SDK Integration

### Blocking (simple)

```python
from anthropic import Anthropic

client = Anthropic()

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    response = client.messages.create(
        model=request.model,
        max_tokens=request.max_tokens,
        messages=[{"role": "user", "content": request.message}]
    )
    return ChatResponse(
        content=response.content[0].text,
        model=response.model,
        usage={"input": response.usage.input_tokens, "output": response.usage.output_tokens}
    )
```

### Streaming (Server-Sent Events)

```python
from fastapi.responses import StreamingResponse

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def generate():
        with client.messages.stream(
            model=request.model,
            max_tokens=request.max_tokens,
            messages=[{"role": "user", "content": request.message}]
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {text}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## Tool Use

### Define tools as Pydantic models + handlers

```python
from anthropic.types import ToolUseBlock
import json

tools = [
    {
        "name": "search_issues",
        "description": "Search Jira issues by query",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 10}
            },
            "required": ["query"]
        }
    }
]

async def handle_tool(name: str, input: dict) -> str:
    if name == "search_issues":
        results = await jira.search(input["query"], input.get("max_results", 10))
        return json.dumps(results)
    raise ValueError(f"Unknown tool: {name}")
```

### Run the tool loop

```python
@app.post("/agent")
async def agent(request: ChatRequest):
    messages = [{"role": "user", "content": request.message}]

    while True:
        response = client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            messages=messages,
            tools=tools
        )

        if response.stop_reason == "end_turn":
            return {"content": response.content[0].text}

        # Process tool calls
        tool_results = []
        for block in response.content:
            if isinstance(block, ToolUseBlock):
                result = await handle_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
```

---

## OpenAPI Spec Generation

FastAPI generates OpenAPI specs automatically from your Pydantic models. This is the bridge to TypeScript frontends:

```bash
# Export the spec
curl http://localhost:8000/openapi.json > openapi.json

# Generate TypeScript client (frontend)
npx openapi-typescript openapi.json -o src/api/types.ts
# Or with orval for full client generation
npx orval --input http://localhost:8000/openapi.json
```

No manual type sync needed between Python backend and TypeScript frontend.

---

## Lifespan Events

Initialize and clean up resources (DB connections, AI client) at app start/stop:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.client = Anthropic()
    app.state.db = await connect_db()
    yield
    # Shutdown
    await app.state.db.close()

app = FastAPI(lifespan=lifespan)
```

---

## Middleware & Dependencies

### CORS (required for React frontends)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Auth dependency

```python
from fastapi import Depends, HTTPException, Header

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != os.environ["API_SECRET_KEY"]:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.post("/chat", dependencies=[Depends(verify_api_key)])
async def chat(request: ChatRequest):
    ...
```

---

## Background Tasks

For long-running AI operations (batch processing, document analysis):

```python
from fastapi import BackgroundTasks

@app.post("/analyze")
async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid4())
    background_tasks.add_task(run_analysis, task_id, request)
    return {"task_id": task_id, "status": "processing"}

@app.get("/analyze/{task_id}")
async def get_result(task_id: str):
    result = await get_stored_result(task_id)
    return result
```

---

## Common Pitfalls

| Symptom                                      | Fix                                                                                     |
|----------------------------------------------|-----------------------------------------------------------------------------------------|
| CORS errors from React frontend              | Add `CORSMiddleware` with your frontend origin                                          |
| `422 Unprocessable Entity`                   | Request body doesn't match Pydantic model — check field names and types                |
| Streaming response cuts off                  | Use `StreamingResponse` with `text/event-stream`; don't return early                   |
| Tool loop runs forever                       | Check for `stop_reason == "end_turn"` not just `stop_reason != "tool_use"`             |
| Sync Anthropic client blocks event loop      | Use `anthropic.AsyncAnthropic()` or run sync calls in thread pool                      |
| OpenAPI spec missing fields                  | Add `Field(description=...)` to all Pydantic model fields                              |

---

## Related Articles

- **[spec-based-development](spec-based-development.md)** — Write architecture and feature specs before coding; complements API development workflows.
- **[claude-agent-sdk-tools](claude-sdk-tools.md)** — Claude Agent SDK for autonomous agent workflows (Python).
- **[vercel-ai-sdk-tools](vercel-ai-sdk-tools.md)** — Vercel AI SDK for full-stack TypeScript AI apps.
- **[copilot-sdk-tools](copilot-sdk-tools.md)** — GitHub Copilot Python SDK for tool-based agents.
