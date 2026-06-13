#!/usr/bin/env python3
"""Scaffold a new article."""

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "articles"

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def list_categories():
    """List existing category directories under articles/."""
    if not ARTICLES_DIR.exists():
        return []
    return sorted([d.name for d in ARTICLES_DIR.iterdir() if d.is_dir()])


def create_article(name, category):
    """Create a new article file with template frontmatter and sections."""
    if not SLUG_PATTERN.match(name):
        raise ValueError(f"Invalid article name: {name}")
    if not SLUG_PATTERN.match(category):
        raise ValueError(f"Invalid category name: {category}")

    category_dir = ARTICLES_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)

    path = category_dir / f"{name}.md"
    if path.exists():
        raise FileExistsError(f"Article already exists: {path}")

    title = name.replace("-", " ").title()
    today = date.today().isoformat()

    content = f"""---
title: {title}
topics:
  -
summary: >

skills:
  -
aliases:
  -
last-updated: {today}
---

# {title}

## Overview

## Details

## Trade-offs

## References
"""
    path.write_text(content, encoding="utf-8")
    return path


def main():
    if len(sys.argv) < 3:
        print("Usage: python new_article.py <slug> --category <category>")
        categories = list_categories()
        if categories:
            print(f"Available categories: {', '.join(categories)}")
        sys.exit(1)

    name = sys.argv[1]
    category = None
    for i, arg in enumerate(sys.argv):
        if arg == "--category" and i + 1 < len(sys.argv):
            category = sys.argv[i + 1]

    if category is None:
        print("Error: --category required")
        sys.exit(1)

    try:
        path = create_article(name, category)
        print(f"Created article: {path}")
    except (ValueError, FileExistsError) as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
