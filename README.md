# Agent Knowledge Base

Shared reference docs and executable skills for AI agents and developers working with our stack.

## What's in here

| Path | What it is |
|---|---|
| `articles/` | Advisory context — how things work, why decisions were made |
| `skills/` | Executable step-by-step instructions agents can follow |
| `scripts/` | Validation and index generation (stdlib Python) |
| `tests/` | pytest suite for scripts |
| `TOPIC-INDEX.md` | Auto-generated index of all articles and skills by topic |
| `QUICK-REF.md` | Auto-generated lookup table — start here to find things |

## How to use (agents)

See [retrieve-from-this-repo.md](skills/retrieve-from-this-repo.md) for the full guide.

Quick version — fetch files with the GitHub API:

```bash
# Find what you need
gh api repos/lacrx/agent-knowledge-docs/contents/QUICK-REF.md?ref=main \
  -H "Accept: application/vnd.github.raw+json"

# Fetch a skill
gh api repos/lacrx/agent-knowledge-docs/contents/skills/provision-athena-database.md?ref=main \
  -H "Accept: application/vnd.github.raw+json"

# Fetch an article
gh api repos/lacrx/agent-knowledge-docs/contents/articles/aws/fargate/deploying-python-web-apps-to-fargate.md?ref=main \
  -H "Accept: application/vnd.github.raw+json"
```

Never clone the repo. One file at a time.

## How to contribute

See [AGENTS.md](AGENTS.md) for format rules and the full contribution workflow.

Quick version:

1. Add or edit content in `articles/` or `skills/`
2. Validate:
   ```bash
   python scripts/validate_articles.py
   python scripts/validate_skills.py
   ```
3. Regenerate the index:
   ```bash
   python scripts/generate_topic_index.py
   ```
4. Open a PR — CI runs validation and checks for index drift
