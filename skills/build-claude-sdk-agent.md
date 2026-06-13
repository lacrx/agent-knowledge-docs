---
name: build-claude-sdk-agent
title: Build a Claude Agent SDK Agent
type: skill
topics:
  - claude-agent-sdk
  - python
  - agents
  - ai-development
summary: >
  Step-by-step skill for building a Python agent with the Claude Agent SDK.
  Covers setup, authentication, built-in and custom tools, streaming, multi-agent, and hooks.
references:
  - articles/agent-workflow/claude-sdk-tools.md
last-updated: 2026-06-12
---

# Build a Claude Agent SDK Agent

Executable steps for building a Python agent using the Claude Agent SDK. Follow in order.

---

## Prerequisites

- Python 3.12+
- `ANTHROPIC_API_KEY` set in environment
- `pip install claude-agent-sdk`

## Steps

### Phase 1: Project Setup

### Step 1.1: Create project structure

```
project/
├── agent.py          # Main agent entry point
├── tools/            # Custom MCP tool modules
│   └── __init__.py
├── requirements.txt
└── .env              # ANTHROPIC_API_KEY (never commit)
```

### Step 1.2: Install dependencies

```bash
pip install claude-agent-sdk
```

### Step 1.3: Set authentication

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

No CLI login required. The API key is sufficient.

For alternative providers:

```bash
# AWS Bedrock
export CLAUDE_CODE_USE_BEDROCK=1

# Google Vertex AI
export CLAUDE_CODE_USE_VERTEX=1
```

---

### Phase 2: Basic Agent with Built-in Tools

### Step 2.1: Create options with built-in tools

```python
from claude_agent_sdk import ClaudeAgentOptions, query

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    model="claude-sonnet-4-6",
    permission_mode="acceptEdits"
)
```

Available built-in tools: `Read`, `Write`, `Edit`, `Bash`, `Monitor`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, `AskUserQuestion`.

### Step 2.2: Run a one-shot query

```python
import asyncio

async def main():
    async for message in query(prompt="List all Python files in this project", options=options):
        if message.type == "assistant":
            print(message.content, end="", flush=True)
    print()

asyncio.run(main())
```

---

### Phase 3: Custom Tools via MCP

### Step 3.1: Define a custom tool

```python
from claude_agent_sdk import tool, create_sdk_mcp_server
import json

@tool("search_issues", "Search Jira issues by query", {"query": str, "max_results": int})
async def search_issues(args):
    results = await jira.search(args["query"], limit=args["max_results"])
    return {"content": [{"type": "text", "text": json.dumps(results)}]}
```

Rules:
- Handler must return MCP format: `{"content": [{"type": "text", "text": "..."}]}`
- `print()` is not captured — return the data
- Each tool name must be unique and descriptive

### Step 3.2: Create an MCP server and attach to options

```python
mcp = create_sdk_mcp_server(name="jira", tools=[search_issues])

options = ClaudeAgentOptions(
    mcp_servers={"jira": mcp},
    allowed_tools=["Read", "Bash"],
    model="claude-sonnet-4-6"
)
```

### Step 3.3: Run with custom tools

```python
async def main():
    async for message in query(prompt="Find all open P0 bugs in Jira", options=options):
        if message.type == "assistant":
            print(message.content, end="", flush=True)
    print()

asyncio.run(main())
```

---

### Phase 4: Permission Handling

### Step 4.1: Choose a permission strategy

| Strategy                             | Use When                    |
|--------------------------------------|-----------------------------|
| Interactive (default)                | Development, debugging      |
| `permission_mode="acceptEdits"`      | Trusted automation          |
| `permission_mode="bypassPermissions"` | Fully autonomous pipelines |
| Custom `can_use_tool` callback       | Fine-grained control        |

### Step 4.2: Custom permission callback

```python
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

async def can_use(tool_name, input_data, context):
    blocked_paths = ["/etc/", "/system/", "/root/"]
    file_path = input_data.get("file_path", "")

    if any(file_path.startswith(p) for p in blocked_paths):
        return PermissionResultDeny(message=f"Blocked: {file_path}")

    return PermissionResultAllow(updated_input=input_data)

options = ClaudeAgentOptions(
    can_use_tool=can_use,
    allowed_tools=["Read", "Write", "Edit", "Bash"]
)
```

---

### Phase 5: Persistent Conversations with ClaudeSDKClient

### Step 5.1: Create a long-lived client

```python
from claude_agent_sdk import ClaudeSDKClient

async def main():
    async with ClaudeSDKClient(options=options) as client:
        # First message
        async for message in client.receive_response("Analyze the codebase structure"):
            if message.type == "assistant":
                print(message.content, end="", flush=True)

        # Follow-up — context preserved
        async for message in client.receive_response("Now find any security issues"):
            if message.type == "assistant":
                print(message.content, end="", flush=True)
```

### Step 5.2: Session resumption

```python
# Capture session ID
async for message in query(prompt="Start analysis", options=options):
    if message.subtype == "init":
        session_id = message.data["session_id"]

# Resume later
resume_options = ClaudeAgentOptions(resume=session_id)
async for message in query(prompt="Continue where we left off", options=resume_options):
    if message.type == "assistant":
        print(message.content, end="", flush=True)
```

Session helpers: `list_sessions()`, `get_session_messages()`, `rename_session()`.

---

### Phase 6: Multi-Agent (Optional)

### Step 6.1: Define subagents

```python
from claude_agent_sdk import AgentDefinition

options = ClaudeAgentOptions(
    agents={
        "code-reviewer": AgentDefinition(
            description="Reviews code for bugs, security issues, and style",
            prompt="You are a thorough code reviewer. Flag bugs, security issues, and style violations.",
            tools=["Read", "Grep", "Glob"]
        ),
        "test-writer": AgentDefinition(
            description="Writes unit tests for Python code",
            prompt="You write comprehensive pytest unit tests.",
            tools=["Read", "Write", "Edit", "Bash"]
        )
    },
    allowed_tools=["Agent", "Read", "Edit"]
)
```

The main agent can now delegate to `code-reviewer` or `test-writer` as needed. Subagent messages include `parent_tool_use_id` for tracking.

---

### Phase 7: Hooks (Optional)

### Step 7.1: Add lifecycle hooks

```python
async def log_tool_use(tool_name, input_data):
    print(f"[Hook] About to call: {tool_name}")

async def check_output(tool_name, result):
    if "ERROR" in str(result):
        print(f"[Hook] Tool {tool_name} returned an error")

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": log_tool_use,
        "PostToolUse": check_output
    },
    allowed_tools=["Read", "Bash"]
)
```

Available hooks:

| Hook            | Fires When                  |
|-----------------|-----------------------------|
| `PreToolUse`    | Before a tool call executes |
| `PostToolUse`   | After a tool call completes |
| `Stop`          | Agent is about to stop      |
| `SessionStart`  | New session begins          |
| `SessionEnd`    | Session ends                |

---

### Minimal Working Example

Complete copy-paste starter with a custom tool:

```python
import asyncio
import json
from claude_agent_sdk import (
    ClaudeAgentOptions, query, tool, create_sdk_mcp_server
)

@tool("greet_user", "Greet a user by name", {"name": str})
async def greet_user(args):
    return {
        "content": [
            {"type": "text", "text": f"Hello, {args['name']}! Welcome aboard."}
        ]
    }

mcp = create_sdk_mcp_server(name="greeter", tools=[greet_user])

options = ClaudeAgentOptions(
    mcp_servers={"greeter": mcp},
    model="claude-sonnet-4-6",
    permission_mode="acceptEdits"
)

async def main():
    async for message in query(prompt="Please greet the user named Alice", options=options):
        if message.type == "assistant":
            print(message.content, end="", flush=True)
    print()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Checklist

- [ ] `ANTHROPIC_API_KEY` set in environment
- [ ] `pip install claude-agent-sdk` completed
- [ ] Each custom tool has a unique, descriptive name
- [ ] Custom tool handlers return MCP format, not raw strings
- [ ] Permission strategy chosen (interactive / acceptEdits / custom)
- [ ] Using `async`/`await` throughout — SDK is async-only
- [ ] Built-in tools preferred over custom where possible
- [ ] Event types checked before accessing content in streaming

## Constraints

- No hard-coded secrets — use environment variables
- Custom tool handlers must return MCP format, not raw strings
- SDK is async-only — use `async`/`await` throughout

## Outputs

- Python agent script with Claude Agent SDK integration
- Custom MCP tool server (if tools defined)
- Working streaming output to stdout
