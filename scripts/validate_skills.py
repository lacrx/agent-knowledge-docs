#!/usr/bin/env python3
"""Validate skill frontmatter and structure."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

REQUIRED_FIELDS = ("name", "topics", "summary", "references", "last-updated")
REQUIRED_SECTIONS = ("Prerequisites", "Steps", "Constraints", "Outputs")
MAX_LINES = 500
TOPIC_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

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


def find_skills():
    """Find all markdown files under skills/."""
    if not SKILLS_DIR.exists():
        return []
    return sorted(SKILLS_DIR.rglob("*.md"))


def _strip_fenced_code_blocks(text):
    """Remove fenced code block content so section headings inside aren't counted."""
    lines = text.splitlines()
    result = []
    in_block = False
    for line in lines:
        if line.strip().startswith("```"):
            in_block = not in_block
            continue
        if not in_block:
            result.append(line)
    return "\n".join(result)


def validate_skill(path, root=None):
    """Validate a single skill file. Returns list of error strings."""
    if root is None:
        root = ROOT

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

    name = fm.get("name")
    if name is not None and name != path.stem:
        errors.append(f"name '{name}' does not match filename '{path.stem}'")

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

    references = fm.get("references")
    if references is not None:
        if isinstance(references, str):
            errors.append("references must be a list, not a string")
        elif isinstance(references, list):
            for ref in references:
                ref_path = root / ref
                if not ref_path.exists():
                    errors.append(f"reference file not found: {ref}")

    stripped = _strip_fenced_code_blocks(text)
    for section in REQUIRED_SECTIONS:
        pattern = re.compile(rf"^##\s+{re.escape(section)}\b", re.MULTILINE)
        if not pattern.search(stripped):
            errors.append(f"missing required section: ## {section}")

    return errors


def main():
    skills = find_skills()
    if not skills:
        print("No skills found.")
        return

    failed = False
    for path in skills:
        rel = path.relative_to(ROOT)
        errors = validate_skill(path)
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
