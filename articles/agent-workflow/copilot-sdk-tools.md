---
title: GitHub Copilot Python SDK — Building Agents with Tools
topics:
  - copilot-sdk
  - python
  - agents
  - ai-development
  - tools
skills:
  - build-copilot-sdk-agent
summary: >
  Advisory guide for the GitHub Copilot Python SDK — CopilotClient, Session, and Tool
  objects, permission handling, streaming, and session resumption.
aliases:
  - copilot sdk python
  - github copilot sdk
  - copilot agent tools
related:
  - spec-based-development
  - claude-agent-sdk-tools
  - anthropic-sdk-fastapi-tools
last-updated: 2026-06-29
---

# GitHub Copilot Python SDK — Building Agents with Tools

## Overview

The GitHub Copilot Python SDK lets you build agents that can call your own Python functions as tools. The SDK spawns the Copilot CLI as a subprocess, handles authentication and token refresh, and runs the tool loop natively — your job is to define tools and handle the response stream.

> **Skill:** For step-by-step implementation including the minimal working example, use the `build-copilot-sdk-agent` skill.

---

## The Three Things You Need

Every Copilot SDK agent needs exactly three objects:

| Object           | Lifecycle            | Description                                                    |
|------------------|----------------------|----------------------------------------------------------------|
| `CopilotClient`  | Long-lived, one per app | Wraps the CLI subprocess                                     |
| `Session`        | One per conversation | Holds history and registered tools                             |
| `Tool`           | One per capability   | Built with `define_tool(name, description, handler, param_type)` |

That's it. The SDK does the tool loop for you — when the model decides to call a tool, the SDK invokes your handler and feeds the result back automatically.

---

## Authentication

1. **Copilot CLI installed and authenticated** — run `copilot auth login`, then verify with `copilot auth status`
2. **`GITHUB_TOKEN` exported in the environment** — the SDK reads it from `os.environ`; never hard-code it

The SDK exposes `client.get_auth_status()` so you can assert authentication before proceeding.

---

## Permission Handling

Every tool call triggers a permission check. Two strategies:

- **`PermissionHandler.approve_all`** — Auto-approves every tool call. Safe for local/trusted tools.
- **Custom callback** — Write a function that receives the tool call context and returns `PermissionDecision.ALLOW` or `PermissionDecision.DENY`. Use this for production UIs that need user confirmation.

---

## Streaming vs. Blocking

| Method                        | Returns                    | Use When                            |
|-------------------------------|----------------------------|-------------------------------------|
| `session.send(prompt)`        | Async iterator of events   | You want to display tokens as they arrive |
| `session.send_and_wait(prompt)` | Final result (awaited)   | You only need the complete answer   |

Event types in the stream: `text`, `tool_call`, `tool_result`, `done`, and others. Check `event.type` before accessing content.

---

## Tool Design Decisions

### Prefer Pydantic for `param_type`

Defining a `BaseModel` subclass gives the model a typed schema for the tool's arguments. Without it, the model receives less guidance and may pass malformed args. Use `Field(..., description='...')` on each field — the description is sent to the model as documentation.

### Each tool needs a unique name

Duplicate tool names cause the model to call the wrong tool silently. Use descriptive, unambiguous names (e.g. `search_jira_issues`, not `search`).

### Handler must return a string

The handler's return value is what the model sees as the tool result. `print()` output is not captured. If your handler produces structured data, serialize it to a string before returning.

---

## Session Resumption

Access `session.session_id` after a conversation. Pass it to `client.resume_session(session_id, ...)` to continue — history is preserved by the CLI subprocess. Useful for multi-turn workflows that are interrupted and resumed later.

---

## Common Pitfalls

| Symptom                                    | Fix                                                                                                          |
|--------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| `RuntimeError: not authenticated`          | Run `copilot auth login`, then restart your script                                                           |
| Tool args arrive as `{}`                   | Ensure handler signature is `(args, invocation)` and `params_type` matches what the model sends              |
| Tool runs but model never sees the result  | Handler must return a string — `print()` is not enough                                                       |
| `ImportError: PermissionHandler`           | SDK 0.2.0 exports from `copilot`; 0.2.1+ from `copilot.session` — use a `try/except` import                 |

---

## Related Articles

- **[spec-based-development](spec-based-development.md)** — Write architecture and feature specs before coding; complements SDK-based agent workflows.
- **[claude-agent-sdk-tools](claude-agent-sdk-tools.md)** — Equivalent guide for Claude Agent SDK.
- **[anthropic-sdk-fastapi-tools](anthropic-sdk-fastapi-tools.md)** — Build AI-powered APIs with Python FastAPI.
