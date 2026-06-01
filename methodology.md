---
title: Agent Workflow Methodology
topics:
  - agent-workflow
  - methodology
  - knowledge-management
summary: >
  Core methodology for working with AI agents — decompose complex work into small,
  reusable knowledge units (skills and articles) that agents fetch at runtime.
aliases:
  - agent methodology
  - agent workflow methodology
  - knowledge base methodology
related:
  - spec-based-development
  - copilot-sdk-tools
  - claude-agent-sdk-tools
last-updated:
---

# Agent Workflow Methodology

## Core Principle

Break complex work into small, self-contained knowledge units stored in a layered knowledge base that agents fetch at runtime. Knowledge compounds — every completed project feeds back a refined skill or article, making the next invocation faster and more reliable.

---

## Knowledge Unit Types

| Type        | Purpose                                              | Example                          |
|-------------|------------------------------------------------------|----------------------------------|
| **Skill**   | Executable steps an agent follows mechanically       | Build a Copilot SDK agent        |
| **Article** | Rationale an agent reads when planning               | Spec-based development guide     |

---

## The Process

### 1. Plan Before Building

Write a plan document that decomposes the problem into phased chunks. Each chunk maps to a skill the agent can execute independently.

### 2. Copy-Adapt-Extend

Each new project inherits ~60% from prior work. Find the closest existing skill or article, copy it, adapt to the new context, extend where needed.

### 3. Fetch, Don't Hold

The agent doesn't hold everything in context at once. It consults a routing table, pulls only the relevant skill, executes it, then moves to the next chunk.

### 4. Feed Back

Every completed project feeds back a refined skill or article. The knowledge base grows with each project.

---

## The Result

Massively complex problems are never solved monolithically. They're decomposed into agent-sized pieces that can be:

- **Reordered** — phases can shift based on priority
- **Reused** — skills work across projects
- **Improved independently** — fix one skill without touching others

---

## Related Articles

- **[spec-based-development](spec-based-development.md)** — Write specs before code; agents implement from concrete examples.
- **[copilot-sdk-tools](copilot-sdk-tools.md)** — Build AI agents with GitHub Copilot Python SDK.
- **[claude-agent-sdk-tools](claude-agent-sdk-tools.md)** — Build AI agents with Claude Agent SDK.
