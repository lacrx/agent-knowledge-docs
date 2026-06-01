---
title: Claude Agent SDK — Building Agents with Tools
topics:
  - claude-agent-sdk
  - python
  - agents
  - ai-development
  - tools
skills:
  - build-claude-agent
summary: >
  Advisory guide for the Claude Agent SDK — query(), ClaudeSDKClient, and custom tools
  via MCP servers, permission handling, streaming, and session resumption.
aliases:
  - claude agent sdk python
  - claude agent sdk
  - claude agent tools
related:
  - spec-based-development
  - anthropic-sdk-fastapi-tools
last-updated:
---

# Claude Agent SDK — Building Agents with Tools

## Overview

The Claude Agent SDK (`pip install claude-agent-sdk`) lets you build agents that can use built-in tools or call your own Python functions as custom tools. The SDK handles the tool loop automatically — your job is to define tools, configure options, and process the response stream.

> **Skill:** For step-by-step implementation including the minimal working example, use the `build-claude-agent` skill.

---

## The Three Things You Need

Every Claude Agent SDK project needs exactly three objects:

| Object               | Lifecycle              | Description                                                          |
|----------------------|------------------------|----------------------------------------------------------------------|
| `query()`            | One-shot, per task     | Async generator for single agent tasks; returns an iterator of messages |
| `ClaudeSDKClient`    | Long-lived, per app    | Context manager for bidirectional conversation with persistent context |
| `ClaudeAgentOptions`  | One per configuration  | Config object: `allowed_tools`, `model`, `mcp_servers`, `permission_mode`, `system_prompt` |

The SDK does the tool loop for you — when the model decides to call a tool, the SDK invokes your handler and feeds the result back automatically.

---

## Authentication

1. **`ANTHROPIC_API_KEY` exported in the environment** — the SDK reads it from `os.environ`; never hard-code it
2. **Alternative providers supported** — Bedrock, Vertex AI, and Azure via `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, etc.

No CLI login step required. The API key is sufficient.

---

## Tools: Built-in vs. Custom

### Built-in Tools

The SDK ships with pre-implemented tools that require no code — just allow them in options:

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]
)
```

### Custom Tools via MCP

Define custom tools with the `@tool` decorator and serve them through an in-process MCP server:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("search_issues", "Search Jira issues by query", {"query": str, "max_results": int})
async def search_issues(args):
    results = await jira.search(args["query"], limit=args["max_results"])
    return {"content": [{"type": "text", "text": json.dumps(results)}]}

mcp = create_sdk_mcp_server(name="jira", tools=[search_issues])
options = ClaudeAgentOptions(mcp_servers={"jira": mcp})
```

---

## Permission Handling

Every tool call triggers a permission check. Three strategies:

- **Interactive (default)** — Prompts for approval on each tool call. Best for development.
- **`permission_mode="acceptEdits"`** — Auto-approves read/write operations. Good for trusted automation.
- **Custom callback** — Write a `can_use_tool` function for fine-grained control:

```python
async def can_use(tool_name, input_data, context):
    if tool_name == "Write" and "/system/" in input_data.get("file_path", ""):
        return PermissionResultDeny(message="Blocked: system files")
    return PermissionResultAllow(updated_input=input_data)

options = ClaudeAgentOptions(can_use_tool=can_use)
```

---

## Streaming

Both `query()` and `ClaudeSDKClient` stream via async iterators. No separate streaming API needed:

```python
async for message in query(prompt="Analyze this codebase", options=options):
    if message.type == "assistant":
        print(message.content, end="", flush=True)
```

Enable partial message delivery with `include_partial_messages=True` in options for real-time token display.

Message types in the stream: `UserMessage`, `AssistantMessage`, `SystemMessage`, `ResultMessage`, `StreamEvent`, `RateLimitEvent`.

---

## Tool Design Decisions

### Custom tool handlers must return the MCP format

The return value must be `{"content": [{"type": "text", "text": "..."}]}` — not a raw string. If your handler produces structured data, `json.dumps()` it into the text field.

### Each tool needs a unique name

Duplicate tool names cause the model to call the wrong tool silently. Use descriptive, unambiguous names (e.g. `search_jira_issues`, not `search`).

### Prefer built-in tools when possible

Built-in tools (`Read`, `Edit`, `Bash`, etc.) are battle-tested and require no handler code. Only create custom MCP tools for domain-specific capabilities.

---

## Session Resumption

Capture `session_id` from the init message, then pass it to resume:

```python
# First conversation
async for message in query(prompt="Start analysis", options=options):
    if message.subtype == "init":
        session_id = message.data["session_id"]

# Resume later
async for message in query(prompt="Continue", options=ClaudeAgentOptions(resume=session_id)):
    ...
```

Sessions are stored on disk in `.claude/sessions/` by default. Helper functions available: `list_sessions()`, `get_session_messages()`, `rename_session()`.

---

## Multi-Agent Support

Define subagents that the main agent can delegate to:

```python
options = ClaudeAgentOptions(
    agents={
        "code-reviewer": AgentDefinition(
            description="Reviews code for bugs and style",
            prompt="You are a code reviewer...",
            tools=["Read", "Grep", "Glob"]
        )
    },
    allowed_tools=["Agent"]
)
```

Subagent messages include `parent_tool_use_id` for tracking which agent spawned which.

---

## Hooks

Python functions that fire at lifecycle events:

| Hook            | Fires When                        |
|-----------------|-----------------------------------|
| `PreToolUse`    | Before a tool call executes       |
| `PostToolUse`   | After a tool call completes       |
| `Stop`          | Agent is about to stop            |
| `SessionStart`  | New session begins                |
| `SessionEnd`    | Session ends                      |

Configure via `hooks` dict in `ClaudeAgentOptions`.

---

## Common Pitfalls

| Symptom                                    | Fix                                                                                                   |
|--------------------------------------------|-------------------------------------------------------------------------------------------------------|
| `RuntimeError` on startup                  | Ensure `ANTHROPIC_API_KEY` is set in environment                                                      |
| Custom tool runs but model ignores result  | Handler must return `{"content": [{"type": "text", "text": "..."}]}`, not a raw string               |
| `async` errors everywhere                  | Both `query()` and `ClaudeSDKClient` are async-only — use `asyncio.run()` or `await`                  |
| Session not resuming                       | Check `.claude/sessions/` exists and `session_id` matches; sessions are stored on disk                |
| Permission prompts on every call           | Set `permission_mode="acceptEdits"` or `"bypassPermissions"` for automation                           |

---

## Related Articles

- **[spec-based-development](spec-based-development.md)** — Write architecture and feature specs before coding; complements SDK-based agent workflows.
- **[copilot-sdk-tools](copilot-sdk-tools.md)** — Equivalent guide for GitHub Copilot Python SDK.
- **[anthropic-sdk-fastapi-tools](anthropic-sdk-fastapi-tools.md)** — Build AI-powered APIs with Python FastAPI and the Anthropic SDK.
