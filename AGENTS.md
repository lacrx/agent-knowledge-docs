---
description: Onboarding guide for AI agents and human contributors to the knowledge base repo.
alwaysApply: false
---
# Agent Knowledge Base — Onboarding

## Purpose
- **AI agents**: Retrieve articles and skills at runtime to inform planning and implementation.
- **Developers**: Look up rationale, trade-offs, and step-by-step procedures for supported topics.
- **Contributors**: Add or update articles and skills following the formats and validation rules below.

---
## Repository Structure
```
├── articles/                  # Advisory reference docs (rationale, trade-offs)
│   ├── agent-workflow/        #   AI SDK integration patterns
│   ├── monitoring/            #   Observability and logging
│   └── testing/               #   Testing strategies and patterns
├── skills/                    # Executable step-by-step procedures (flat)
├── scripts/                   # Generators and validators (stdlib-only Python)
├── tests/                     # Pytest suite for all scripts
├── QUICK-REF.md               # Auto-generated lookup table (do not edit)
├── TOPIC-INDEX.md             # Auto-generated topic index (do not edit)
├── CLAUDE.md                  # Claude Code agent instructions
└── AGENTS.md                  # This file
```

---
## How Agents Retrieve Content
Fetch files directly via the GitHub API. Never clone the repo.
```bash
# Quick-reference index
gh api repos/lacrx/agent-knowledge-docs/contents/QUICK-REF.md?ref=main -H "Accept: application/vnd.github.raw+json"
# An article
gh api repos/lacrx/agent-knowledge-docs/contents/articles/agent-workflow/claude-sdk-tools.md?ref=main -H "Accept: application/vnd.github.raw+json"
# A skill
gh api repos/lacrx/agent-knowledge-docs/contents/skills/build-claude-sdk-agent.md?ref=main -H "Accept: application/vnd.github.raw+json"
```
**Discovery flow**: Fetch `QUICK-REF.md` → find matching row → fetch linked article or skill. If no match, try `TOPIC-INDEX.md`. If still no match, note "not covered" and continue.

---
## Article Format
```yaml
---
title: Human-Readable Title
topics: [lowercase-hyphen-tag]
skills: [companion-skill-slug]
summary: >
  One-line summary.
aliases: [alternate-name]
last-updated: YYYY-MM-DD
---
```
- Maximum 500 lines. Topic tags: `^[a-z0-9]+(-[a-z0-9]+)*$`.
- Focus on rationale and trade-offs, not step-by-step instructions.
- Reference companion skills for executable procedures.

---
## Skill Format
```yaml
---
name: skill-slug-matching-filename
topics: [lowercase-hyphen-tag]
summary: >
  One-line summary.
references: [articles/category/related-article.md]
last-updated: YYYY-MM-DD
---
```
- Must contain `## Prerequisites`, `## Steps`, `## Constraints`, `## Outputs` sections.
- Steps: numbered, with full copy-paste-ready code blocks. No hard-coded secrets.
- One task per skill. `name` must match filename stem.

---
## How to Contribute
### Adding an Article
1. Pick or create a category under `articles/` (lowercase-hyphen name).
2. Run `python scripts/new_article.py <slug> --category <category>`.
3. Fill in body sections and frontmatter.
4. Run validation and regenerate indexes, then commit together.

### Adding a Skill
1. Run `python scripts/new_skill.py <slug>`.
2. Fill in Steps with numbered, executable instructions.
3. Run validation and regenerate indexes, then commit together.

---
## Validation
Run before every commit:
```bash
python scripts/validate_articles.py
python scripts/validate_skills.py
python scripts/generate_topic_index.py
python -m pytest tests/
```

---
## Guardrails
- Never hard-code secrets — use env vars or secret managers.
- Never edit `TOPIC-INDEX.md` or `QUICK-REF.md` manually — auto-generated.
- All content must pass validation before merging.
- Update `last-updated` in frontmatter on every change.
- Articles = advisory (rationale, trade-offs). Skills = executable (steps).
- Regenerate indexes whenever articles or skills change.

---
Last updated: 2026-06-12
