When I say: New article: <slug> in <category>

Create one article file only:
articles/<category>/<slug>.md

I will provide only:
- topics
- companion skill(s)
- focus

You must produce:
- valid frontmatter (title, topics, skills if real, summary, aliases if useful, related only if real, last-updated-today)
- advisory article content, not step-by-step instructions
- clear rationale, tradeoffs, patterns, and common mistakes
- no fake links, no fake companion skills, no secrets

Constraints:
- follow AGENTS.md article rules exactly
- lowercase hyphenated topics tags
- keep under 500 lines
- article explains why/how to think, skill explains exact steps

Pipeline:
1) python scripts/new_article.py <slug> --category <category>
2) write full article content
3) python scripts/validate_articles.py and fix until pass
4) python scripts/generate_topic_index.py
5) stop after this single article is valid

Before finishing, self-check:
- filename matches slug
- related links and companion skills are real
- topics are valid
- validator passes

Return only:
- summary
- validation result
- assumptions