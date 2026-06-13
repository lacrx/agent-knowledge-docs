#!/usr/bin/env python3
"""Scaffold a new skill."""

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def create_skill(name):
    """Create a new skill file with template frontmatter and sections."""
    if not SLUG_PATTERN.match(name):
        raise ValueError(f"Invalid skill name: {name}")

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    path = SKILLS_DIR / f"{name}.md"
    if path.exists():
        raise FileExistsError(f"Skill already exists: {path}")

    title = name.replace("-", " ").title()
    today = date.today().isoformat()

    content = f"""---
name: {name}
topics:
  -
summary: >

references:
  -
last-updated: {today}
---

# {title}

## Prerequisites

## Steps

### Step 1:

## Constraints

| Constraint | Rationale |
|---|---|

## Outputs
"""
    path.write_text(content, encoding="utf-8")
    return path


def main():
    if len(sys.argv) < 2:
        print("Usage: python new_skill.py <slug>")
        sys.exit(1)

    name = sys.argv[1]

    try:
        path = create_skill(name)
        print(f"Created skill: {path}")
    except (ValueError, FileExistsError) as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
