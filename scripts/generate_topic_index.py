#!/usr/bin/env python3
"""Generate topic-index.md and quick-ref.md from article/skill frontmatter.

Uses only the Python 3.13 standard library. No PyYAML dependency.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "articles"
SKILLS_DIR = ROOT / "skills"

FRONTMATTER_DELIM = re.compile(r"^---\s*$")
KV_PATTERN = re.compile(r"^(\w[\w-]*):\s*(.*)$")
LIST_ITEM = re.compile(r"^\s+-\s+(.+)$")


def parse_frontmatter(text: str) -> dict | None:
    """Regex-based YAML frontmatter parser.

    Detects --- delimiters, parses key: value pairs and - list items.
    Strips surrounding quotes from values. Returns None if no valid block found.
    """
    lines = text.splitlines()

    # Find opening delimiter
    if not lines or not FRONTMATTER_DELIM.match(lines[0]):
        return None

    # Find closing delimiter
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if FRONTMATTER_DELIM.match(line):
            end = i
            break

    if end is None:
        return None

    result = {}
    current_key = None

    for line in lines[1:end]:
        list_match = LIST_ITEM.match(line)
        if list_match:
            if current_key is not None:
                if not isinstance(result.get(current_key), list):
                    result[current_key] = []
                result[current_key].append(_strip_quotes(list_match.group(1)))
            continue

        kv_match = KV_PATTERN.match(line)
        if kv_match:
            key = kv_match.group(1)
            value = kv_match.group(2).strip()
            current_key = key
            if value:
                # Inline value (not a list)
                result[key] = _strip_quotes(value)
            else:
                # Expect list items to follow
                result[key] = []
            continue

    return result


def _strip_quotes(s: str) -> str:
    """Strip surrounding single or double quotes."""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s.strip()


def _truncate_summary(summary: str, max_len: int = 120) -> str:
    """Truncate summary to max_len characters with ellipsis."""
    summary = summary.strip()
    # Handle multi-line YAML scalars (>)
    summary = re.sub(r"\s+", " ", summary)
    if len(summary) <= max_len:
        return summary
    return summary[: max_len - 3].rstrip() + "..."


def find_articles() -> list[Path]:
    """Find all markdown files under articles/."""
    if not ARTICLES_DIR.exists():
        return []
    return sorted(ARTICLES_DIR.rglob("*.md"))


def find_skills() -> list[Path]:
    """Find all markdown files under skills/."""
    if not SKILLS_DIR.exists():
        return []
    return sorted(SKILLS_DIR.rglob("*.md"))



def build_topic_index(article_entries: list[dict]) -> dict[str, list[dict]]:
    """Build topic-keyed map for legacy format."""
    index = {}
    for entry in article_entries:
        for topic in entry["topics"]:
            if topic not in index:
                index[topic] = []
            index[topic].append(entry)
    return index


def build_article_index() -> list[dict]:
    """Build list of entry dicts from articles."""
    articles = find_articles()
    entries = []

    for path in articles:
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm is None:
            continue

        title = fm.get("title", path.stem)
        rel_path = str(path.relative_to(ROOT))
        summary = fm.get("summary", "")
        if isinstance(summary, list):
            summary = " ".join(summary)
        topics = fm.get("topics", [])
        if isinstance(topics, str):
            topics = [topics]
        skills = fm.get("skills", [])
        if isinstance(skills, str):
            skills = [skills]
        aliases = fm.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]

        entries.append({
            "title": title,
            "stem": path.stem,
            "path": rel_path,
            "summary": summary,
            "topics": topics,
            "skills": skills,
            "aliases": aliases,
        })

    return sorted(entries, key=lambda e: e["path"])


def generate_topic_index(entries: list[dict]) -> str:
    """Generate topic-index.md content."""
    lines = [
        "<!-- auto-generated, do not edit manually. See also quick-ref.md -->",
        "",
        "# Topic Index",
        "",
    ]

    for entry in entries:
        heading = " / ".join(entry["topics"]) if entry["topics"] else entry["stem"]
        stem = entry["stem"]
        path = entry["path"]
        skills_str = ", ".join(entry["skills"]) if entry["skills"] else "_(none)_"

        lines.append(f"## {heading}")
        lines.append("")
        lines.append(f"**{stem}** → [{stem}]({path})")
        lines.append(f"Skills: {skills_str}")

        if entry["aliases"]:
            aliases_str = ", ".join(entry["aliases"])
            lines.append(f"Aliases: {aliases_str}")

        lines.append("")

    return "\n".join(lines)


def generate_quick_ref(entries: list[dict]) -> str:
    """Generate quick-ref.md content."""
    lines = [
        "<!-- auto-generated, do not edit manually -->",
        "",
        "# Quick Reference",
        "",
        "| Topics | Article | Skills |",
        "|--------|---------|--------|",
    ]

    for entry in entries:
        topics_cell = ", ".join(entry["topics"])
        stem = entry["stem"]
        path = entry["path"]
        article_cell = f"[{stem}]({path})"

        if entry["skills"]:
            skills_cell = ", ".join(
                f"[{name}](skills/{name}.md)" for name in entry["skills"]
            )
        else:
            skills_cell = "_(none)_"

        lines.append(f"| {topics_cell} | {article_cell} | {skills_cell} |")

    lines.append("")
    return "\n".join(lines)


def main():
    entries = build_article_index()

    if not entries:
        print("No articles found. Exiting.")
        sys.exit(0)

    topic_index_content = generate_topic_index(entries)
    quick_ref_content = generate_quick_ref(entries)

    topic_index_path = ROOT / "TOPIC-INDEX.md"
    quick_ref_path = ROOT / "QUICK-REF.md"

    topic_index_path.write_text(topic_index_content, encoding="utf-8")
    quick_ref_path.write_text(quick_ref_content, encoding="utf-8")

    print(f"Generated TOPIC-INDEX.md and QUICK-REF.md from {len(entries)} articles.")


if __name__ == "__main__":
    main()
