---
name: fetch-topic-bundle
title: Fetch Topic Bundle
type: skill
topics:
  - agent-workflow
  - specification-driven
  - ai-development
  - developer-experience
summary: >
  Fetch all skills matching a given topic tag from the knowledge base in one pass.
  Used at session start to bulk-load every relevant skill into context via the GitHub API.
references:
  - articles/agent-workflow/spec-based-development.md
  - QUICK-REF.md
last-updated: 2026-06-12
---

# Fetch Topic Bundle

Bulk-fetch every skill matching a topic tag from the knowledge base repo. Designed for
session-start bootstrapping: one script, one topic, all matching skills loaded into context.

---

## Prerequisites

- `gh` CLI installed and authenticated (`gh auth status`)
- `bash` with `base64`, `grep`, `sed`, `sort` available
- Network access to GitHub API

---

## Steps

### Step 1: Set parameters

```bash
# ── Configuration ──────────────────────────────────────────────
TOPIC="ai-development"           # Target topic tag to match
OWNER="lacrx"                    # Repository owner
REPO="agent-knowledge-docs"      # Repository name
BRANCH="main"                    # Branch to fetch from
QUICK_REF_PATH="QUICK-REF.md"   # Path to the quick-reference index
```

### Step 2: Fetch QUICK-REF.md from the repo

Two approaches — pick one.

**Approach A: Accept raw header (simpler, plain text)**

```bash
QUICK_REF=$(gh api \
  -H "Accept: application/vnd.github.raw+json" \
  "repos/${OWNER}/${REPO}/contents/${QUICK_REF_PATH}?ref=${BRANCH}")
```

**Approach B: Base64 decode (default JSON response)**

```bash
QUICK_REF=$(gh api \
  "repos/${OWNER}/${REPO}/contents/${QUICK_REF_PATH}?ref=${BRANCH}" \
  --jq '.content' | base64 --decode)
```

Both return identical content. Approach A is one fewer pipe. Approach B works if you
need other metadata from the same response (sha, size, etc.).

### Step 3: Filter rows containing the target topic

```bash
MATCHED_ROWS=$(echo "$QUICK_REF" | grep -i "$TOPIC")
```

Each row in QUICK-REF.md is a pipe-delimited table row. The first column contains
comma-separated topic tags. Grep matches any row where the topic appears anywhere,
including the skills column — which is fine because skill paths don't collide with
topic tag names.

### Step 4: Extract and deduplicate skill paths

```bash
SKILL_PATHS=$(echo "$MATCHED_ROWS" \
  | grep -oE 'skills/[A-Za-z0-9_.+/-]+\.md' \
  | sort -u)
```

This regex captures paths like `skills/build-claude-agent.md` or
`skills/sub-dir/my-skill.md`. `sort -u` deduplicates in case multiple
articles reference the same skill.

### Step 5: Fetch and print each skill

**Using Accept raw header:**

```bash
for SKILL_PATH in $SKILL_PATHS; do
  echo "=== ${SKILL_PATH} ==="
  gh api \
    -H "Accept: application/vnd.github.raw+json" \
    "repos/${OWNER}/${REPO}/contents/${SKILL_PATH}?ref=${BRANCH}"
  echo ""
done
```

**Using base64 decode:**

```bash
for SKILL_PATH in $SKILL_PATHS; do
  echo "=== ${SKILL_PATH} ==="
  gh api \
    "repos/${OWNER}/${REPO}/contents/${SKILL_PATH}?ref=${BRANCH}" \
    --jq '.content' | base64 --decode
  echo ""
done
```

---

## Complete Script

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
TOPIC="${1:?Usage: fetch-topic-bundle.sh <topic>}"
OWNER="lacrx"
REPO="agent-knowledge-docs"
BRANCH="main"
QUICK_REF_PATH="QUICK-REF.md"

# ── Fetch the quick-reference index ────────────────────────────
QUICK_REF=$(gh api \
  -H "Accept: application/vnd.github.raw+json" \
  "repos/${OWNER}/${REPO}/contents/${QUICK_REF_PATH}?ref=${BRANCH}")

# ── Filter rows matching the topic ─────────────────────────────
MATCHED_ROWS=$(echo "$QUICK_REF" | grep -i "$TOPIC" || true)

if [ -z "$MATCHED_ROWS" ]; then
  echo "No skills found for topic: ${TOPIC}" >&2
  exit 0
fi

# ── Extract and deduplicate skill paths ─────────────────────────
SKILL_PATHS=$(echo "$MATCHED_ROWS" \
  | grep -oE 'skills/[A-Za-z0-9_.+/-]+\.md' \
  | sort -u)

if [ -z "$SKILL_PATHS" ]; then
  echo "Matched rows found but no skill paths extracted for topic: ${TOPIC}" >&2
  exit 0
fi

SKILL_COUNT=$(echo "$SKILL_PATHS" | wc -l)
echo "Fetching ${SKILL_COUNT} skill(s) for topic: ${TOPIC}" >&2

# ── Fetch and print each skill ──────────────────────────────────
for SKILL_PATH in $SKILL_PATHS; do
  echo "=== ${SKILL_PATH} ==="
  gh api \
    -H "Accept: application/vnd.github.raw+json" \
    "repos/${OWNER}/${REPO}/contents/${SKILL_PATH}?ref=${BRANCH}"
  echo ""
done
```

---

## Constraints

- No hard-coded secrets — `gh` uses existing auth token
- Read-only — never modify repository content
- Output to stdout only — no disk writes
- Empty topic match exits cleanly, not with error

## Outputs

- Raw markdown content of all matching skills, printed to stdout
- Each skill separated by `=== path ===` header
- Count of fetched skills on stderr

## Checklist

- [ ] `gh auth status` shows authenticated
- [ ] Target topic exists in QUICK-REF.md topic column
- [ ] Script outputs `=== path ===` header before each skill
- [ ] No duplicate skills in output
- [ ] Empty topic match exits cleanly with message, not error
