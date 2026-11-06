---
name: consult-knowledge-bases
description: >
  Consult Thomas's knowledge bases (every lacrx/*-knowledge-docs repo on GitHub: lan, agent,
  policy, autocad, ...) before planning, answering or changing things they cover. Use for his
  machines and network (neo, workhorse, thinclient, the VM, SSH, Tailscale, services, Ollama,
  the Neovim + Claude Code setup); engineering, infrastructure, deployment and architecture
  patterns (python, docker, aws, testing, agent SDKs); California housing law, land use,
  transportation safety and other policy work; and AutoCAD LT drawing via the MCP bridge.
  Routes the task with `kb route`, then fetches only the matching pages.
topics:
  - knowledge-base
  - runtime-retrieval
  - agent-workflow
  - gh-cli
summary: >
  Route a task to the right knowledge base(s) and fetch only the matching pages, across every
  lacrx/*-knowledge-docs repo, with the stdlib `kb` script. Replaces fetch-topic-bundle and
  retrieve-from-this-repo.
references:
  - articles/agent-workflow/spec-based-development.md
  - QUICK-REF.md
last-updated: 2026-11-06
---

# Consult Knowledge Bases

One entry point for every knowledge base. Each KB keeps its own rules in its `CLAUDE.md`
(When to Fetch topics, contribution workflow, guardrails); `kb` reads those and the
`QUICK-REF.md` index from GitHub, so this skill never needs a list of KBs or topics.

---

## Prerequisites

- The skill installed at `~/.claude/skills/consult-knowledge-bases/` (`SKILL.md` + `kb`), see Step 6.
- `gh` logged in on this machine, or ssh to `workhorse`, where it is (neo has no `gh`; `kb` uses
  workhorse automatically).
- Python 3.9+ (stdlib only).

---

## Steps

### Step 1: Route the task (always first, costs one or two API calls)

```bash
KB=~/.claude/skills/consult-knowledge-bases/kb
$KB route "harden ssh on neo and check the tailscale setup"
```

- `skip: no knowledge base covers this task` → do not fetch anything; continue without the KB.
- Otherwise each matching KB is listed with its mode and the matching `QUICK-REF` rows and paths.

### Step 2: Fetch only what matched (1 to 3 pages)

```bash
$KB get lan articles/networking/ssh.md
$KB get policy articles/<category>/<page>.md
```

For a problem on the home machines, read `PAINPOINTS.md` in `lan` first; to decide where
something should run, `ROLES.md`.

### Step 3: When routing found the KB but no row

```bash
$KB find tailscale            # search every KB's QUICK-REF rows, no page downloads
$KB toc lan                   # TOPIC-INDEX: one line per page
$KB topic lan vm              # bundle: pages whose row mentions "vm", capped at 5 (--max N)
```

If still nothing: note "not covered in KB" and continue with model knowledge.

### Step 4: Respect each KB's fetch mode

- `planning` (agent, lan, autocad): fetch once while planning; re-fetch only when the task moves
  to a new topic.
- `continuous` (policy): a runtime reference. Fetch during extraction, analysis, drafting and
  evaluation, not just at the start.

### Step 5: Follow the KB's own rules when changing it

Before editing a KB, fetch its `CLAUDE.md` (`$KB get <kb> CLAUDE.md`) and follow its
Contribution and Guardrails sections (validators, generated indexes, `AGENTS.md`). For `lan`,
also confirm current state on the live machine and update the docs in the same task.

### Step 6: Install or update the skill on a machine

```bash
python3 scripts/kb.py install          # from a clone of agent-knowledge-docs
~/.claude/skills/consult-knowledge-bases/kb install   # self-update from GitHub
```

Both write `SKILL.md` and `kb` from GitHub (the KB's default branch) into
`~/.claude/skills/consult-knowledge-bases/`.

### Reference: all commands

```bash
$KB list                       # KBs, default branch, fetch mode, When to Fetch topics
$KB route "<task text>"        # which KBs and rows apply, or skip
$KB find <word>                # rows mentioning <word> in every KB
$KB index <kb>                 # QUICK-REF.md          $KB toc <kb>   TOPIC-INDEX.md
$KB get <kb> <path>...         # raw pages
$KB topic <kb> <word> [--max N]
```

---

## Constraints

- Read-only against the KBs; never clone. GitHub's default branch is the source of truth (not
  always `main`: policy uses `master`), and local clones can be stale or mid-edit.
- Keep context light: route first, fetch at most 1 to 3 pages per question, bundles capped at 5.
- Caches in `~/.cache/kb/`: the KB list and When to Fetch topics for 24 hours, each `QUICK-REF`
  for 10 minutes. Delete the folder to force a refresh.
- No secrets: `gh` uses its stored login.

## Outputs

- `route`: per matching KB its repo, mode, matched topics and up to 5 rows with page paths; or a
  single `skip` line.
- `get` / `topic`: raw markdown on stdout, `=== repo/path ===` before each page when several.
- `find`: one line per matching row, `<kb> [tags] paths`.
- Exit code 0 on success and on "no match"; 1 with a `kb:` message on errors.
