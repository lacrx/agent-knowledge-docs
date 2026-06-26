---
name: retrieve-from-this-repo
topics:
  - knowledge-base
  - runtime-retrieval
  - agent-workflow
  - gh-cli
summary: >
  Fetch articles and skills from the knowledge base repo at runtime using gh CLI.
  Covers auth check, discovery workflow, and content retrieval via GitHub API.
references:
  - articles/agent-workflow/spec-based-development.md
  - QUICK-REF.md
last-updated: 2026-06-12
---

# Retrieve from Knowledge Base Repo

Fetch articles and skills from the shared knowledge base at runtime using only `gh` CLI. No cloning required.

---

## Prerequisites

- `gh` CLI installed and authenticated (`gh auth status` passes)
- Network access to GitHub API
- No local clone required

## Steps

### Repository Coordinates

| Field    | Value                        |
|----------|------------------------------|
| Owner    | `lacrx`                      |
| Repo     | `agent-knowledge-docs`       |
| Branch   | `main`                       |
| API base | `repos/lacrx/agent-knowledge-docs` |

---

### Common Paths

| Content Type   | Pattern                                |
|----------------|----------------------------------------|
| Quick reference | `quick-ref.md`                        |
| Topic index    | `topic-index.md`                       |
| Article        | `articles/<category>/<name>.md`        |
| Skill          | `skills/<name>.md`                     |

---

### Step 1: Auth Check

Run `gh auth status`. Confirm logged in. Do NOT proceed without it.

```bash
gh auth status
```

If this fails, stop immediately. Tell the user: "gh CLI is not authenticated. Run `gh auth login` first."

---

### Step 2: Define Fetch Helper

Define a shell function for retrieving raw content:

```bash
kb_fetch() {
  local path="$1"
  gh api "repos/lacrx/agent-knowledge-docs/contents/${path}" \
    -H "Accept: application/vnd.github.raw+json"
}
```

This returns raw markdown directly — no base64 decoding needed.

---

### Step 3: Discovery Workflow

Follow these steps in order to locate the right content.

### 3.1: Fetch quick-ref.md first

```bash
kb_fetch "quick-ref.md"
```

This is a compact routing table (~3KB) that maps topics to article paths and skill names. Search it for your topic.

### 3.2: If no match, fall back to topic-index.md

```bash
kb_fetch "topic-index.md"
```

Full tag-to-article map. More comprehensive, larger file.

### 3.3: If still no match

Note "not covered" and continue without reference content. Do NOT block on missing KB entries.

### 3.4: Fetch a specific article

```bash
kb_fetch "articles/<category>/<name>.md"
```

Example: `kb_fetch "articles/agent-workflow/spec-based-development.md"`

### 3.5: Fetch a specific skill

```bash
kb_fetch "skills/<name>.md"
```

Example: `kb_fetch "skills/build-claude-sdk-agent.md"`

### 3.6: Optional — full tree discovery

If you need to browse all available content:

```bash
gh api "repos/lacrx/agent-knowledge-docs/git/trees/main?recursive=1" --jq '.tree[].path'
```

---

### Role Rules

| Agent Role                   | Reads              | Purpose                                          | Does NOT                          |
|------------------------------|--------------------|--------------------------------------------------|-----------------------------------|
| Research / Planning agent    | Articles           | Advisory context: rationale, trade-offs, decisions | Follow skill steps                |
| Coding / Implementation agent | Skills           | Step-by-step execution instructions              | Read articles (context was already handed off) |
| Any agent (discovery only)   | quick-ref.md, topic-index.md | Routing — find the right file path    | Use index content as implementation guidance |

Role separation is strict. Research agents gather context from articles and hand it off. Implementation agents receive that context and follow skills mechanically.

---

### Troubleshooting

| Symptom                                  | Cause                                    | Fix                                                              |
|------------------------------------------|------------------------------------------|------------------------------------------------------------------|
| `gh: command not found`                  | gh CLI not installed                     | Install: `brew install gh` or `apt install gh`                   |
| `gh auth status` fails                   | Not logged in                            | Run `gh auth login` — do NOT proceed without auth               |
| Variable not expanding in path           | Single quotes around `${path}`           | Use double quotes: `"repos/.../contents/${path}"`               |
| 404 response                             | Path is case-sensitive or doesn't exist  | Use discovery (Step 3.6) to find correct path                   |
| Topic not in quick-ref or topic-index    | Content not yet written                  | Note "not covered", continue without reference                   |
| `gh api` returns permission error        | Repo not accessible with current token   | Stop and tell user: "Cannot access repo. Check gh auth scopes." |

---

## Constraints

- **Retrieval only** — never push, commit, or modify content in the repo
- **No disk writes** — output to stdout; do not save files locally
- **No cloning** — API calls only; the repo is never checked out
- **Role separation** — research reads articles, implementation follows skills; never cross

## Outputs

- Raw markdown content printed to stdout
- Agent proceeds with retrieved context or notes "not covered"
