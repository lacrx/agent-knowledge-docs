#!/usr/bin/env python3
"""Validate article frontmatter and structure."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "articles"

REQUIRED_FIELDS = ("title", "topics", "summary", "last-updated")
MAX_LINES = 500
TOPIC_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

FRONTMATTER_DELIM = re.compile(r"^---\s*$")
KV_PATTERN = re.compile(r"^(\w[\w-]*):\s*(.*)$")
LIST_ITEM = re.compile(r"^\s+-\s+(.+)$")


def parse_frontmatter(text):
    """Parse YAML frontmatter from text."""
    lines = text.splitlines()
    if not lines or not FRONTMATTER_DELIM.match(lines[0]):
        return None

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
                result[key] = _strip_quotes(value)
            else:
                result[key] = []
            continue

    return result


def _strip_quotes(s):
    """Strip surrounding single or double quotes."""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s.strip()


def find_articles():
    """Find all markdown files under articles/."""
    if not ARTICLES_DIR.exists():
        return []
    return sorted(ARTICLES_DIR.rglob("*.md"))


def validate_article(path):
    """Validate a single article file. Returns list of error strings."""
    errors = []
    text = path.read_text(encoding="utf-8")

    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        errors.append(f"exceeds {MAX_LINES} line limit ({len(lines)} lines)")

    fm = parse_frontmatter(text)
    if fm is None:
        errors.append("no valid frontmatter block found (must start and end with ---)")
        return errors

    for field in REQUIRED_FIELDS:
        if field not in fm:
            errors.append(f"missing required field: {field}")

    topics = fm.get("topics")
    if topics is not None:
        if isinstance(topics, str):
            errors.append("topics must be a list, not a string")
        elif isinstance(topics, list):
            if not topics:
                errors.append("topics list is empty")
            else:
                for tag in topics:
                    if not TOPIC_PATTERN.match(tag):
                        errors.append(f"invalid topic tag: {tag}")

    summary = fm.get("summary")
    if summary is not None:
        if isinstance(summary, str) and not summary.strip():
            errors.append("summary is empty")

    skills = fm.get("skills")
    if skills is not None:
        if isinstance(skills, str):
            errors.append("skills must be a list, not a string")
        elif isinstance(skills, list):
            for slug in skills:
                if not SLUG_PATTERN.match(slug):
                    errors.append(f"invalid skill slug: {slug}")

    return errors


def main():
    articles = find_articles()
    if not articles:
        print("No articles found.")
        return

    failed = False
    for path in articles:
        rel = path.relative_to(ROOT)
        errors = validate_article(path)
        if errors:
            for error in errors:
                print(f"FAIL: {rel} - {error}")
            failed = True
        else:
            print(f"PASS: {rel}")

    if failed:
        print("\nValidation failed. Fix the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
