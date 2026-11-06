#!/usr/bin/env python3
"""kb: consult every lacrx/*-knowledge-docs repo from GitHub.

Discovers the knowledge bases, routes a task to the ones whose CLAUDE.md
"When to Fetch" topics or QUICK-REF rows it touches, and fetches pages with the
GitHub API (never a clone). Stdlib only; runs on Python 3.9+.

  kb list                      knowledge bases, branch, fetch mode, topics
  kb route "<task text>"       which KBs and QUICK-REF rows apply, or "skip"
  kb find <word>               search every KB's QUICK-REF rows (no page downloads)
  kb index <kb>                QUICK-REF.md            kb toc <kb>   TOPIC-INDEX.md
  kb get <kb> <path>...        raw pages
  kb topic <kb> <word> [--max N]  pages whose QUICK-REF row mentions <word> (default 5)
  kb install [--dest DIR]      install/update the Claude Code skill from GitHub

<kb> is the short name: lan, agent, policy, autocad, ... (repo name minus
"-knowledge-docs"). Uses `gh` when it is installed and logged in, otherwise runs
`gh` on workhorse over ssh.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

OWNER = "lacrx"
SUFFIX = "-knowledge-docs"
SKILL_REPO = "agent-knowledge-docs"
SKILL_NAME = "consult-knowledge-bases"
CACHE_DIR = Path(os.environ.get("KB_CACHE_DIR", Path.home() / ".cache" / "kb"))
REPOS_TTL = 24 * 3600
INDEX_TTL = 10 * 60
DEFAULT_MAX_PAGES = 5
MAX_ROUTE_ROWS = 5

LINK = re.compile(r"\]\(([^)\s]+\.md)\)")
WHEN_HEADING = re.compile(r"^##\s+When to Fetch\b(.*)$", re.IGNORECASE)
TOPICS_AFTER = re.compile(r"(?:touches|involves)\s*:\s*(.+?)(?:\.\s|\.$|$)", re.IGNORECASE | re.DOTALL)


class KbError(Exception):
    pass


# ---------------------------------------------------------------- gh access

_GH_LOCAL = None


def _gh_local() -> bool:
    global _GH_LOCAL
    if _GH_LOCAL is None:
        _GH_LOCAL = bool(shutil.which("gh")) and subprocess.run(
            ["gh", "auth", "status"], capture_output=True
        ).returncode == 0
    return _GH_LOCAL


def gh(args: list) -> str:
    """Run gh locally, or on workhorse over ssh when gh isn't available here."""
    if _gh_local():
        cmd = ["gh"] + args
    else:
        quoted = " ".join("'" + a.replace("'", "'\\''") + "'" for a in args)
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "workhorse", "gh " + quoted]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise KbError(res.stderr.strip() or "gh failed: " + " ".join(args))
    return res.stdout


def raw(repo: str, path: str, branch: str) -> str:
    return gh(["api", "-H", "Accept: application/vnd.github.raw+json",
               "repos/%s/%s/contents/%s?ref=%s" % (OWNER, repo, path, branch)])


# ---------------------------------------------------------------- cache

def _cached(name: str, ttl: int, produce):
    path = CACHE_DIR / name
    try:
        if time.time() - path.stat().st_mtime < ttl:
            return path.read_text()
    except OSError:
        pass
    text = produce()
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    except OSError:
        pass
    return text


# ---------------------------------------------------------------- parsing

def parse_when_to_fetch(claude_md: str) -> tuple:
    """Return (topics, mode) from a CLAUDE.md "## When to Fetch" section.

    mode is "continuous" when the heading says so (runtime reference, e.g. the
    policy KB), "planning" otherwise, or "always" when no section exists.
    """
    lines = claude_md.splitlines()
    for i, line in enumerate(lines):
        m = WHEN_HEADING.match(line.strip())
        if not m:
            continue
        mode = "continuous" if "continuous" in m.group(1).lower() else "planning"
        body = []
        for nxt in lines[i + 1:]:
            if nxt.startswith("## "):
                break
            body.append(nxt)
        text = " ".join(body)
        tm = TOPICS_AFTER.search(text)
        if not tm:
            return [], mode
        topics = [t.strip().strip("`").lower() for t in tm.group(1).split(",")]
        return [t for t in topics if t], mode
    return [], "always"


def parse_rows(quick_ref: str) -> list:
    """QUICK-REF table rows as dicts: tags (first column), paths, text."""
    rows = []
    for line in quick_ref.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= set("-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or cells[0].lower() == "topics":
            continue
        tags = [t.strip().lower() for t in cells[0].split(",") if t.strip()]
        paths = []
        for p in LINK.findall(line):
            if p not in paths:
                paths.append(p)
        rows.append({"tags": tags, "paths": paths, "text": line})
    return rows


def _stem(word: str) -> str:
    """Crude stem so "doors"/"door" and "drawing"/"draw" meet; applied to both sides."""
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _norm(text: str) -> str:
    return " " + " ".join(_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())) + " "


def term_in(term: str, task_norm: str) -> bool:
    """Whole-word match on stemmed words; hyphenated terms also match with spaces."""
    t = _norm(term).strip()
    return bool(t) and (" " + t + " ") in task_norm


# ---------------------------------------------------------------- knowledge bases

def discover() -> list:
    def produce():
        out = gh(["repo", "list", OWNER, "--limit", "200", "--json", "name,defaultBranchRef,description"])
        kbs = []
        for r in json.loads(out):
            if not r["name"].endswith(SUFFIX):
                continue
            branch = (r.get("defaultBranchRef") or {}).get("name") or "main"
            try:
                topics, mode = parse_when_to_fetch(raw(r["name"], "CLAUDE.md", branch))
            except KbError:
                topics, mode = [], "always"
            kbs.append({"kb": r["name"][: -len(SUFFIX)], "repo": r["name"], "branch": branch,
                        "description": r.get("description") or "", "topics": topics, "mode": mode})
        return json.dumps(sorted(kbs, key=lambda k: k["kb"]))
    return json.loads(_cached("repos.json", REPOS_TTL, produce))


def kb_by_name(name: str, kbs: list) -> dict:
    for k in kbs:
        if k["kb"] == name or k["repo"] == name:
            return k
    raise KbError("unknown knowledge base '%s'; have: %s" % (name, ", ".join(k["kb"] for k in kbs)))


def quick_ref(kb: dict) -> str:
    return _cached(kb["kb"] + "-QUICK-REF.md", INDEX_TTL, lambda: raw(kb["repo"], "QUICK-REF.md", kb["branch"]))


def route(task: str, kbs: list, fetch_index=quick_ref) -> list:
    """For each KB: matched When-to-Fetch topics and the QUICK-REF rows the task touches."""
    task_norm = _norm(task)
    results = []
    for kb in kbs:
        gate = [t for t in kb["topics"] if term_in(t, task_norm)]
        rows = []
        for row in parse_rows(fetch_index(kb)):
            hits = [t for t in row["tags"] if term_in(t, task_norm)]
            if hits:
                rows.append((len(hits), hits, row))
        rows.sort(key=lambda r: -r[0])
        if gate or rows:
            results.append({"kb": kb, "gate": gate, "rows": rows[:MAX_ROUTE_ROWS]})
    return results


# ---------------------------------------------------------------- commands

def cmd_list(kbs, _args):
    for k in kbs:
        topics = ", ".join(k["topics"]) if k["topics"] else "(no When to Fetch list: consult when in scope)"
        print("%-9s %-24s %-7s %-10s %s" % (k["kb"], k["repo"], k["branch"], k["mode"], k["description"]))
        print("          topics: %s" % (topics[:300] + ("..." if len(topics) > 300 else "")))


def cmd_route(kbs, args):
    if not args:
        raise KbError("usage: kb route \"<task text>\"")
    results = route(" ".join(args), kbs)
    if not results:
        print("skip: no knowledge base covers this task (no When to Fetch topic or QUICK-REF tag matched)")
        return
    for r in results:
        k = r["kb"]
        why = ("topics: " + ", ".join(r["gate"])) if r["gate"] else "QUICK-REF tags only"
        print("%s (%s, %s; %s)" % (k["kb"], k["repo"], k["mode"], why))
        if not r["rows"]:
            print("  no QUICK-REF row matched; try: kb toc %s" % k["kb"])
        for _n, hits, row in r["rows"]:
            print("  [%s] %s" % (", ".join(hits), "  ".join(row["paths"]) or "(no links)"))


def cmd_find(kbs, args):
    if len(args) != 1:
        raise KbError("usage: kb find <word>")
    word = args[0].lower()
    found = 0
    for k in kbs:
        for row in parse_rows(quick_ref(k)):
            if word in row["text"].lower():
                found += 1
                print("%-8s [%s] %s" % (k["kb"], ", ".join(row["tags"][:6]), "  ".join(row["paths"])))
    if not found:
        print("kb: '%s' is in no QUICK-REF; try: kb toc <kb>" % word, file=sys.stderr)


def cmd_index(kbs, args, path="QUICK-REF.md"):
    if len(args) != 1:
        raise KbError("usage: kb index|toc <kb>")
    k = kb_by_name(args[0], kbs)
    print(quick_ref(k) if path == "QUICK-REF.md" else raw(k["repo"], path, k["branch"]))


def cmd_get(kbs, args):
    if len(args) < 2:
        raise KbError("usage: kb get <kb> <path>...")
    k = kb_by_name(args[0], kbs)
    for p in args[1:]:
        if len(args) > 2:
            print("=== %s/%s ===" % (k["repo"], p))
        print(raw(k["repo"], p, k["branch"]))


def cmd_topic(kbs, args):
    max_pages = DEFAULT_MAX_PAGES
    if "--max" in args:
        i = args.index("--max")
        max_pages = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    if len(args) != 2:
        raise KbError("usage: kb topic <kb> <word> [--max N]")
    k = kb_by_name(args[0], kbs)
    word = args[1].lower()
    paths = []
    for row in parse_rows(quick_ref(k)):
        if word in row["text"].lower():
            paths += [p for p in row["paths"] if p not in paths]
    if not paths:
        print("kb: no QUICK-REF row in %s mentions '%s'; try: kb toc %s" % (k["repo"], word, k["kb"]), file=sys.stderr)
        return
    print("kb: %d page(s) for '%s' in %s%s" % (len(paths), word, k["repo"],
          "; fetching the first %d" % max_pages if len(paths) > max_pages else ""), file=sys.stderr)
    for p in paths[:max_pages]:
        print("=== %s/%s ===" % (k["repo"], p))
        print(raw(k["repo"], p, k["branch"]))
    if len(paths) > max_pages:
        print("=== not fetched (use kb get %s <path>): %s" % (k["kb"], "  ".join(paths[max_pages:])))


def cmd_install(kbs, args):
    dest = Path(args[args.index("--dest") + 1]).expanduser() if "--dest" in args \
        else Path.home() / ".claude" / "skills" / SKILL_NAME
    k = kb_by_name(SKILL_REPO, kbs)
    skill = raw(k["repo"], "skills/%s.md" % SKILL_NAME, k["branch"])
    script = raw(k["repo"], "scripts/kb.py", k["branch"])
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(skill)
    (dest / "kb").write_text(script)
    (dest / "kb").chmod(0o755)
    print("installed %s from %s@%s into %s" % (SKILL_NAME, k["repo"], k["branch"], dest))


COMMANDS = {
    "list": cmd_list, "route": cmd_route, "find": cmd_find, "get": cmd_get, "topic": cmd_topic,
    "install": cmd_install, "index": cmd_index,
    "toc": lambda kbs, a: cmd_index(kbs, a, "TOPIC-INDEX.md"),
}


def main(argv: list) -> int:
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in COMMANDS:
        print(__doc__.strip())
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    try:
        COMMANDS[argv[0]](discover(), argv[1:])
    except KbError as e:
        print("kb: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
