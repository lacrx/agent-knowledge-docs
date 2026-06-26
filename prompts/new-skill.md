When I say: New skill: <name>

Create skills/<name>.md using AGENTS.md rules exactly.

I will provide only:
- what it provisions/does
- variables to parameterize
- key constraints

You must produce:
- valid frontmatter (name, topics, summary, references if real, last-updated-today)
- sections in order: Prerequisites, Steps, Constraints, Outputs
- executable steps
- outputs that are verifiable

Always apply standard constraints unless I override:
- pin versions
- no secrets
- least privilege IAM
- tagging standards
- no fake file paths/references

Pipeline (mandatory):
1) python scripts/new_skill.py <name>
2) replace template with full content
3) python scripts/validate_skills.py (fix until pass)
4) python scripts/generate_topic_index.py
5) stop after single skill is valid

Assume I'll make occasional typos. Fix those when you see a mistype.

Return only:
- summary
- validation results
- assumptions