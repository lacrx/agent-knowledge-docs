---
name: build-anthropic-sdk-fastapi-agent
title: Build an Anthropic SDK + FastAPI Server
type: skill
topics:
  - anthropic-sdk
  - fastapi
  - python
  - ai-development
summary: >
  Step-by-step skill for building an AI-powered API with the Anthropic Python SDK
  and FastAPI. Covers setup, routes, tool loop, streaming SSE, OpenAPI generation, and CORS.
references:
  - articles/agent-workflow/anthropic-sdk-fastapi-tools.md
last-updated: 2026-06-12
---

# Build an Anthropic SDK + FastAPI Server

Executable steps for building an AI-powered API server using the Anthropic Python SDK and FastAPI. Follow in order.

---

## Prerequisites

- Python 3.12+
- `ANTHROPIC_API_KEY` set in environment
- `pip install fastapi uvicorn anthropic pydantic`

## Steps

### Phase 1: Project Setup

### Step 1.1: Create project structure

```
project/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, routes, lifespan
│   ├── models.py         # Pydantic request/response models
│   ├── tools.py          # Tool definitions and handlers
│   └── agent.py          # Tool loop logic
├── requirements.txt
└── .env                  # ANTHROPIC_API_KEY (never commit)
```

### Step 1.2: Install dependencies

```bash
pip install fastapi uvicorn anthropic pydantic python-dotenv
```

### Step 1.3: Set authentication

```bash
# .env
ANTHROPIC_API_KEY="sk-ant-..."
```

```python
# app/main.py
from dotenv import load_dotenv
load_dotenv()
```

No CLI login. The API key is sufficient.

---

### Phase 2: Define Models

### Step 2.1: Request and response models

```python
# app/models.py
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message to send to Claude")
    model: str = Field("claude-sonnet-4-6", description="Model to use")
    max_tokens: int = Field(1024, description="Max tokens in response")
    system: str | None = Field(None, description="Optional system prompt")

class ChatResponse(BaseModel):
    content: str
    model: str
    usage: dict

class AgentRequest(BaseModel):
    message: str = Field(..., description="User message for the agent")
    model: str = Field("claude-sonnet-4-6", description="Model to use")
    max_tokens: int = Field(4096, description="Max tokens per turn")
    max_turns: int = Field(10, description="Max tool loop iterations")
```

Rules:
- Use `Field(..., description='...')` on every field — drives OpenAPI docs
- Response models enforce output shape; clients get typed contracts
- FastAPI returns 422 automatically on invalid input

---

### Phase 3: Create FastAPI App with Client

### Step 3.1: App with lifespan (client initialization)

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from anthropic import Anthropic

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = Anthropic()
    yield

app = FastAPI(title="AI Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Step 3.2: Basic chat endpoint (no tools)

```python
from fastapi import Request
from app.models import ChatRequest, ChatResponse

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    client = req.app.state.client

    response = client.messages.create(
        model=request.model,
        max_tokens=request.max_tokens,
        system=request.system or "You are a helpful assistant.",
        messages=[{"role": "user", "content": request.message}]
    )

    return ChatResponse(
        content=response.content[0].text,
        model=response.model,
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens
        }
    )
```

---

### Phase 4: Define Tools

### Step 4.1: Tool schemas (Anthropic format)

```python
# app/tools.py
import json

TOOLS = [
    {
        "name": "search_issues",
        "description": "Search Jira issues by query and return matching results",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "max_results": {"type": "integer", "description": "Max results", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_ticket",
        "description": "Create a new Jira ticket",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Ticket title"},
                "description": {"type": "string", "description": "Ticket body"},
                "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]}
            },
            "required": ["title", "description"]
        }
    }
]
```

### Step 4.2: Tool handler dispatch

```python
# app/tools.py
async def handle_tool(name: str, input: dict) -> str:
    if name == "search_issues":
        results = await jira.search(input["query"], input.get("max_results", 10))
        return json.dumps(results)

    if name == "create_ticket":
        ticket = await jira.create(input["title"], input["description"], input.get("priority", "P2"))
        return json.dumps({"id": ticket.id, "url": ticket.url})

    raise ValueError(f"Unknown tool: {name}")
```

Rules:
- Handler must return a **string** (JSON-serialized for structured data)
- Each tool `name` must be unique
- `input_schema` follows JSON Schema spec

---

### Phase 5: Implement the Tool Loop

### Step 5.1: Agent loop logic

```python
# app/agent.py
from anthropic import Anthropic
from anthropic.types import ToolUseBlock, TextBlock
from app.tools import TOOLS, handle_tool

async def run_agent(client: Anthropic, message: str, model: str, max_tokens: int, max_turns: int) -> str:
    messages = [{"role": "user", "content": message}]

    for _ in range(max_turns):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            tools=TOOLS
        )

        # Check if done
        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if isinstance(b, TextBlock)]
            return "\n".join(text_blocks)

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

        # Feed results back
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return "Max turns reached without completion."
```

### Step 5.2: Wire agent to route

```python
# app/main.py
from app.models import AgentRequest
from app.agent import run_agent

@app.post("/agent")
async def agent_endpoint(request: AgentRequest, req: Request):
    client = req.app.state.client

    result = await run_agent(
        client=client,
        message=request.message,
        model=request.model,
        max_tokens=request.max_tokens,
        max_turns=request.max_turns
    )

    return {"content": result}
```

---

### Phase 6: Streaming (Server-Sent Events)

### Step 6.1: SSE streaming endpoint

```python
from fastapi.responses import StreamingResponse

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, req: Request):
    client = req.app.state.client

    async def generate():
        with client.messages.stream(
            model=request.model,
            max_tokens=request.max_tokens,
            messages=[{"role": "user", "content": request.message}]
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Step 6.2: Streaming agent with tool calls

```python
@app.post("/agent/stream")
async def agent_stream(request: AgentRequest, req: Request):
    client = req.app.state.client

    async def generate():
        messages = [{"role": "user", "content": request.message}]

        for turn in range(request.max_turns):
            with client.messages.stream(
                model=request.model,
                max_tokens=request.max_tokens,
                messages=messages,
                tools=TOOLS
            ) as stream:
                for event in stream:
                    if hasattr(event, 'text'):
                        yield f"data: {json.dumps({'type': 'text', 'text': event.text})}\n\n"

                response = stream.get_final_message()

            if response.stop_reason == "end_turn":
                yield "data: [DONE]\n\n"
                return

            # Process tool calls
            tool_results = []
            for block in response.content:
                if isinstance(block, ToolUseBlock):
                    yield f"data: {json.dumps({'type': 'tool_call', 'name': block.name})}\n\n"
                    result = await handle_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
                    yield f"data: {json.dumps({'type': 'tool_result', 'name': block.name})}\n\n"

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

### Phase 7: OpenAPI Spec for Frontend Clients

### Step 7.1: Export and generate TypeScript types

FastAPI generates OpenAPI automatically. Use it to generate typed frontend clients:

```bash
# Start the server
uvicorn app.main:app --reload

# Export spec
curl http://localhost:8000/openapi.json > openapi.json

# Generate TypeScript types
npx openapi-typescript openapi.json -o src/api/types.ts

# Or full client with orval
npx orval --input http://localhost:8000/openapi.json
```

No manual type sync needed between Python backend and TypeScript frontend.

---

### Phase 8: Run the Server

### Step 8.1: Development

```bash
uvicorn app.main:app --reload --port 8000
```

### Step 8.2: Production

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Step 8.3: Verify

```bash
# Health check
curl http://localhost:8000/docs    # Swagger UI

# Test chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, Claude!"}'

# Test agent
curl -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "Find all open P0 bugs"}'
```

### Minimal Working Example

```python
# main.py
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from anthropic import Anthropic
from anthropic.types import ToolUseBlock, TextBlock
from pydantic import BaseModel, Field

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = Anthropic()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    model: str = Field("claude-sonnet-4-6")
    max_tokens: int = Field(1024)

TOOLS = [{
    "name": "greet_user",
    "description": "Greet a user by name",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Name to greet"}},
        "required": ["name"]
    }
}]

def handle_tool(name: str, input: dict) -> str:
    if name == "greet_user":
        return f"Hello, {input['name']}! Welcome aboard."
    raise ValueError(f"Unknown tool: {name}")

@app.post("/chat")
async def chat(request: ChatRequest, req: Request):
    client = req.app.state.client
    messages = [{"role": "user", "content": request.message}]

    for _ in range(5):
        response = client.messages.create(
            model=request.model, max_tokens=request.max_tokens,
            messages=messages, tools=TOOLS
        )

        if response.stop_reason == "end_turn":
            text = "\n".join(b.text for b in response.content if isinstance(b, TextBlock))
            return {"content": text}

        tool_results = []
        for block in response.content:
            if isinstance(block, ToolUseBlock):
                result = handle_tool(block.name, block.input)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return {"content": "Max turns reached."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Constraints

- No hard-coded secrets — use environment variables and `.env` files
- Tool handlers must return strings, not raw objects
- Tool loop must have a `max_turns` guard against infinite loops

## Outputs

- FastAPI application with `/chat` and `/agent` endpoints
- Tool definitions and handler module
- OpenAPI spec auto-generated by FastAPI
