---
title: Build a Copilot SDK Agent
type: skill
summary: >
  Step-by-step skill for building a Python agent with the GitHub Copilot SDK.
  Covers setup, authentication, tool definition, session creation, and streaming.
references:
  - articles/agent-workflow/copilot-sdk-tools.md
last-updated:
---

# Build a Copilot SDK Agent

Executable steps for building a Python agent using the GitHub Copilot SDK. Follow in order.

---

## Phase 1: Project Setup

### Step 1.1: Create project structure

```
project/
├── agent.py          # Main agent entry point
├── tools/            # Tool handler modules
│   └── __init__.py
├── requirements.txt
└── .env              # GITHUB_TOKEN (never commit)
```

### Step 1.2: Install dependencies

```bash
pip install copilot-sdk pydantic
```

### Step 1.3: Verify authentication

```bash
copilot auth login
copilot auth status
```

Export the token:

```bash
export GITHUB_TOKEN="$(copilot auth token)"
```

---

## Phase 2: Define Tools

### Step 2.1: Create a Pydantic model for tool parameters

```python
from pydantic import BaseModel, Field

class SearchParams(BaseModel):
    query: str = Field(..., description="Search query string")
    max_results: int = Field(10, description="Maximum number of results to return")
```

### Step 2.2: Write the tool handler

```python
def handle_search(args: SearchParams, invocation) -> str:
    results = do_search(args.query, args.max_results)
    return json.dumps(results)
```

Rules:
- Handler signature must be `(args, invocation)`
- Must return a **string** — `print()` is not captured
- Use the Pydantic model as `params_type` so the model gets a typed schema

### Step 2.3: Register the tool

```python
from copilot import define_tool

search_tool = define_tool(
    name="search_issues",        # Unique, descriptive name
    description="Search Jira issues by query and return matching results",
    handler=handle_search,
    params_type=SearchParams
)
```

---

## Phase 3: Create Client and Session

### Step 3.1: Initialize the client

```python
from copilot import CopilotClient

client = CopilotClient()
```

### Step 3.2: Verify authentication programmatically

```python
auth = client.get_auth_status()
assert auth.is_authenticated, "Run: copilot auth login"
```

### Step 3.3: Create a session with tools and permissions

```python
from copilot import PermissionHandler

session = client.new_session(
    tools=[search_tool],
    permission_handler=PermissionHandler.approve_all  # Or custom callback
)
```

For custom permission handling:

```python
def check_permission(tool_call_context):
    if tool_call_context.tool_name == "dangerous_tool":
        return PermissionDecision.DENY
    return PermissionDecision.ALLOW

session = client.new_session(
    tools=[search_tool],
    permission_handler=check_permission
)
```

---

## Phase 4: Send Prompts and Handle Responses

### Step 4.1: Blocking mode (simple)

```python
result = await session.send_and_wait("Find all open P0 bugs")
print(result)
```

### Step 4.2: Streaming mode (real-time output)

```python
async for event in session.send("Find all open P0 bugs"):
    if event.type == "text":
        print(event.content, end="", flush=True)
    elif event.type == "tool_call":
        print(f"\n[Calling tool: {event.tool_name}]")
    elif event.type == "tool_result":
        print(f"[Tool result received]")
    elif event.type == "done":
        print("\n[Complete]")
```

---

## Phase 5: Session Resumption (Optional)

### Step 5.1: Save session ID after conversation

```python
saved_session_id = session.session_id
```

### Step 5.2: Resume later

```python
resumed_session = client.resume_session(
    session_id=saved_session_id,
    tools=[search_tool],
    permission_handler=PermissionHandler.approve_all
)

result = await resumed_session.send_and_wait("What were the results from last time?")
```

---

## Minimal Working Example

Complete copy-paste starter:

```python
import asyncio
import json
import os
from pydantic import BaseModel, Field
from copilot import CopilotClient, PermissionHandler, define_tool

class GreetParams(BaseModel):
    name: str = Field(..., description="Name to greet")

def handle_greet(args: GreetParams, invocation) -> str:
    return f"Hello, {args.name}! Welcome aboard."

greet_tool = define_tool(
    name="greet_user",
    description="Greet a user by name",
    handler=handle_greet,
    params_type=GreetParams
)

async def main():
    client = CopilotClient()

    auth = client.get_auth_status()
    assert auth.is_authenticated, "Run: copilot auth login"

    session = client.new_session(
        tools=[greet_tool],
        permission_handler=PermissionHandler.approve_all
    )

    async for event in session.send("Please greet the user named Alice"):
        if event.type == "text":
            print(event.content, end="", flush=True)
    print()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Checklist

- [ ] `copilot auth status` shows authenticated
- [ ] `GITHUB_TOKEN` exported in environment
- [ ] Each tool has a unique, descriptive name
- [ ] Tool handlers return strings, not `None`
- [ ] Pydantic models used for `params_type`
- [ ] Permission handler set (approve_all or custom)
- [ ] Event types checked before accessing content in streaming mode
