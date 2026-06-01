---
title: Spec-Based Development for AI Agents
topics:
  - agent-workflow
  - specification-driven
  - ai-development
  - developer-experience
summary: >
  Advisory guide for spec-based development with AI agents — write architecture.md,
  implementation.md, and feature specs before coding so agents implement from concrete
  examples rather than vague descriptions.
aliases:
  - spec driven development
  - specification based development
  - ai agent specs
related:
  - copilot-sdk-tools
  - claude-agent-sdk-tools
  - vercel-ai-sdk-tools
  - anthropic-sdk-fastapi-tools
skills:
  - fetch-topic-bundle
last-updated: 2025-06-29
---

# Spec-Based Development for AI Agents

## Overview

Write detailed specifications **before** writing code. AI agents implement **from** specifications.

The core principle is **specification by example** — show behavior through concrete examples, not abstract descriptions. This approach dramatically reduces ambiguity and rework because agents are given precise input/output examples to implement against rather than vague feature descriptions.

---

## When to Initialize vs. When to Implement

On any project, the first question to answer is whether documentation structure already exists.

**Documentation exists** if you see any of:

- `architecture.md`, `design.md`, or `README.md` with architecture sections
- A `/docs` folder
- A `/tasks` or `/specs` folder

**If documentation is missing:** run the initialization checklist ([Step 0](#step-0-initialize-project-first-time-only)) before any coding begins. If unsure, ask the human: *"Should I initialize documentation structure, or does it already exist?"*

---

## Required Document Types

A spec-driven project needs five types of documentation. File names vary by project — what matters is the content.

### 1. High-Level Architecture Document

**Common names:** `architecture.md`, `design.md`, `README.md` (architecture section)

**Contains:**

- System overview and goals
- Major components and their responsibilities
- Technology decisions with rationale
- Non-functional requirements (performance, security)
- Architecture patterns in use

### 2. Implementation Patterns Document

**Common names:** `implementation.md`, `patterns.md`, `developer_guide.md`

**Contains:**

- Detailed code patterns with examples
- Component/class design templates
- Error handling approach
- Testing strategy
- Dependency injection patterns
- Directory structure and file organization

> Agent uses this for: finding **how** to implement (patterns, structure, conventions) — the "look like existing code" rule.

### 3. Architecture Decision Records (ADRs)

Optional but recommended. Numbered files in a dedicated folder (e.g. `docs/adr/001-use-postgres.md`).

**Contains:**

- **Context** — what problem?
- **Decision** — what we chose
- **Rationale** — why?
- **Consequences** — tradeoffs accepted
- **Alternatives** — what we didn't choose and why

> Agent uses this for: understanding **why** decisions were made — avoids re-litigating closed decisions.

### 4. Project Plan / Roadmap

**Common names:** `roadmap.md`, `project_plan.md`, `backlog.md`

**Contains:**

- Project phases or milestones
- Current status (done / in-progress)
- Priorities and next steps
- Overall project goals

> Agent uses this for: knowing **where** the project is — which phase, what's next, what's already complete.

### 5. Feature Specifications

The most important document type.

**Common naming:** date-prefixed or ticket-prefixed (`20230205_feature.md`, `ticket-123_feature.md`)

**Contains:**

- Goal statement
- Concrete examples (Given/When/Then format)
- Implementation phases with tasks and checkboxes
- Acceptance criteria per phase
- File paths where code goes
- Estimated effort

> Agent uses this for: the actual work — **what** to build and exactly **how** to build it.

---

## Feature Specification Structure

Every feature spec must have four sections.

### Header

```markdown
# Feature Name

**Created:** YYYY-MM-DD
**Status:** Draft | In Progress | Complete
**Estimated effort:** X–Y hours
```

### Goal

One clear sentence describing what this achieves.

### Specification by Example

Use Given/When/Then format with concrete values — not abstract descriptions.

#### Example 1: Happy Path

| Field     | Value                                  |
|-----------|----------------------------------------|
| **Given** | User enters valid email `user@example.com` |
| **When**  | Validation runs                        |
| **Then**  | Returns `true`                         |

#### Example 2: Error Case

| Field     | Value                                            |
|-----------|--------------------------------------------------|
| **Given** | User enters invalid email `not-an-email`         |
| **When**  | Validation runs                                  |
| **Then**  | Returns `false` with error `"Invalid email format"` |

### Implementation Phases

Break work into 2–5 hour chunks. Each phase has tasks (checkboxes), a target file, and acceptance criteria:

```markdown
## Phase 1: Models (2 hours)

**Tasks:**
- [ ] Task 1.1: Create EmailValidator class
- [ ] Task 1.2: Add validation method

**File:** `src/services/EmailValidator.cs`

**Acceptance criteria:**
- [ ] Class compiles
- [ ] Handles valid emails correctly
- [ ] Unit tests pass
```

---

## Writing Good Examples

The difference between a spec that works and one that doesn't is **concreteness**.

### Concrete (agent knows exactly what to implement)

```
Given input "abc@test.com"  → valid
Given input "invalid"       → invalid with message "must contain @"
Given input ""              → invalid with message "required"
Given input null            → invalid with message "required"
```

### Vague (too many interpretations)

> "Should be fast"

### Measurable (specific and testable)

```
Given  1000 records
When   processed sequentially
Then   completes in < 5 seconds
```

---

## The Development Process

### Step 0: Initialize Project (first time only)

If documentation structure doesn't exist, create it before any coding.

1. Scan project for existing documentation
2. Create base folders: `docs/`, `docs/adr/`, `tasks/`
3. Generate template files: `architecture.md`, `implementation.md`, `project_plan.md`
4. Analyze existing code to populate templates (language, frameworks, patterns already in use)
5. Mark uncertain sections with `[REVIEW: ...]` for human verification
6. Ask human to review and approve the populated templates

Once structure exists, Step 0 is never repeated.

### Steps 1–5: Normal Development Cycle

| Step | Who                  | What                                                                                                                                          |
|------|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| 1    | Human (or AI-assisted) | Creates feature spec with concrete examples, acceptance criteria, and 2–5 hour phases                                                       |
| 2    | AI Agent             | Reads project roadmap for context, reads assigned feature spec completely, examines referenced architecture/pattern docs                      |
| 3    | AI Agent             | Implements following code examples in spec, applies patterns from architecture docs, writes tests based on acceptance criteria, commits after each phase |
| 4    | AI Agent             | Runs build (must compile), runs tests (must pass), checks all acceptance criteria, updates task checkboxes                                    |
| 5    | AI Agent             | Commits with task reference, notes blockers in spec, identifies next task                                                                    |

Repeat steps 1–5 for each feature. Step 0 only runs once per project.

---

## Daily Workflow Pattern

### Planning

1. Open project roadmap/plan document
2. Find current sprint/milestone section
3. Locate next unchecked task
4. Open that task's feature spec
5. Read the spec completely before writing code

### During Implementation

6. Find current phase in spec
7. Read acceptance criteria for that phase
8. Check if a pattern/architecture doc is referenced — read the relevant section
9. Implement following patterns and examples in spec
10. Run build — fix errors
11. Run tests — fix failures
12. Verify acceptance criteria met
13. Check task checkboxes in spec
14. Commit: `[TaskID] Brief description — Refs: [spec-file] Phase N`

---

## Related Articles

- **[copilot-sdk-tools](copilot-sdk-tools.md)** — Build AI agents that can call Python functions as tools; complements spec-driven workflows.
- **[claude-agent-sdk-tools](claude-agent-sdk-tools.md)** — Build AI agents with Claude Agent SDK; complements spec-driven workflows.
- **[vercel-ai-sdk-tools](vercel-ai-sdk-tools.md)** — Build AI apps with Vercel AI SDK, React hooks, and multi-provider streaming.
- **[anthropic-sdk-fastapi-tools](anthropic-sdk-fastapi-tools.md)** — Build AI-powered APIs with Python FastAPI and the Anthropic SDK.
