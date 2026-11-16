---
title: Instruction File Design
topics:
  - agent-workflow
  - ai-development
  - developer-experience
summary: >
  Advisory guide for CLAUDE.md and other agent instruction files — route a fact by what it is
  about rather than by who found it, move subsystem detail into skills that load on match,
  and gate the size mechanically so the file cannot grow back.
aliases:
  - claude md design
  - agent instruction files
  - agents md structure
skills:
  - consult-knowledge-bases
last-updated: 2026-11-16
---

# Instruction File Design

## Overview

An instruction file (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`) is read **in full at the start
of every session**, whatever the task is. Its cost is unconditional. Its value is not.

That asymmetry is the whole design problem, and it does not announce itself. The file grows
one honest paragraph at a time, each one worth writing, and no single commit looks wrong.
Then a session about billing loads four hundred lines about a television.

This article is written from a measured case: a project file that went from **18 KB to 211 KB
in eight days** — about 27 KB a day — and crossed the host's 150,000-character ceiling for
instruction files. Roughly half of it was subsystem narrative. A sibling repository by the
same author was already doing it right at 8.9 KB plus two skills, which is how we know the
shape works rather than merely sounds good.

## Details

### Route a fact by what it is about, not by who found it

The instinct when a file gets long is to split it by project, or by date, or to compress the
prose. All three keep the same material in the same position. Route it instead:

| The fact is about | It belongs in | Why |
|---|---|---|
| Something outside the repository — a vendor API, hardware, a protocol, a container runtime | a knowledge base, referenced and **never restated** | it is true for anyone, outlives this codebase, and is reusable by every other project |
| One subsystem of this code | a skill in the repo (`.claude/skills/<name>/SKILL.md`) | it versions with the code, and loads only when its description matches |
| The change being made now — what was observed, the invariants, the blast radius | a spec file next to the code | it is the record of a decision, not a standing rule |
| A symptom somebody will hit and misdiagnose | a `PAINPOINTS.md` indexed by the symptom | you arrive with a symptom, not a subsystem name |
| A rule that holds across subsystems, or a boundary | the instruction file | this is what it is for |

**The failure the first four rows prevent is one fact in two places.** In the measured case
the knowledge base article said of itself that it was "the shared source of truth for both"
consumers of a device, while the project file restated its contents in a second repository
with nothing comparing them. The article separately held two contradictory paragraphs about
the same API call, the newer correct and the older left standing.

### A knowledge base is for knowledge whose subject has no repository

Resist "a knowledge-docs repo per project". It sounds like the same idea and is not.

A KB repository is the right home for machines, policy, vendor behaviour, patterns that span
codebases — things with no repo of their own. Most of a project's instruction file is about
*that project's code*, and moving it out breaks two things worth keeping: the atomic coupling
between a change and its record in one commit, and whatever path-based grading a reviewer or
CI applies. Keep code-facts with the code.

Measured split in the case above: about **40 KB outside-world** (two KB articles) against
about **97 KB code-facts** (four in-repo skills). Routing by project would have moved all 137
KB to the wrong side of that line.

### Skills are the lazy-load mechanism

A skill is offered to the model as its **name and one-line description**; the body loads only
when that description matches. So a 25 KB subsystem narrative costs a sentence until it is
needed.

Two rules make that safe:

- **Name the files in the description, not only the subject.** A description that says "use
  when working on the television" misses a session that is editing `catalog_builder.py` and
  does not use the word. Listing the files it covers is what makes the match reliable.
- **Verify the skill is actually discoverable**, in a fresh session, rather than inferring it
  from file placement. A one-shot prompt is enough:
  ```bash
  claude -p "List the names of every skill available to you. Output only names." --max-turns 1
  ```
  A skill whose description never matches is **worse** than inline text: the session proceeds
  not knowing the subsystem has rules at all.

### A security invariant does not move

This is the exception that makes the rest safe. If a file sits behind a reviewer's path
filter, whoever edits it must meet its boundary rule **without having invoked anything**.

So split the entry rather than the subject: the *rule* stays in the instruction file, the
*narrative* goes to the skill, and the skill carries a named pointer saying where the rule
lives. In the measured case this applied to a page's escape-then-whitelist XSS invariant, a
purchase guard, and a credential-storage decision — each one left behind deliberately while
its investigation moved.

Getting this wrong in the other direction is easy and worth watching for: a verbatim move
leaves the invariant in *both* places, which is the duplication the whole exercise exists to
remove. Grep the skill for what the instruction file claims to own.

### Gate the size mechanically, and ratchet it down

Add a size ceiling to whatever runs before merge, and **lower it in the same commit that
creates the headroom, never raise it**. One constant, with its history in comments:

```bash
CLAUDE_MD_MAX=109000   # 211000 -> 200000 -> 175000 -> 151000 -> 124000 -> 115000 -> 109000

check_instruction_size() {
    local size; size=$(wc -c < CLAUDE.md)
    if [ "$size" -gt "$CLAUDE_MD_MAX" ]; then
        printf 'CLAUDE.md is %s bytes, over the %s limit.\n' "$size" "$CLAUDE_MD_MAX" >&2
        printf '  outside-world fact -> the knowledge base\n' >&2
        printf '  one-subsystem fact -> .claude/skills/<name>/SKILL.md\n' >&2
        printf '  cross-cutting rule -> stays here\n' >&2
        return 1
    fi
}
```

**Make the refusal name the destinations.** A gate that only says no gets edited; one that
says where to put the thing instead gets used.

### Prove a move against the commit, never the working tree

The single most important mechanical lesson, and it cost a near-miss to learn.

A move was verified by reading the moved file, counting its lines and diffing it against what
had been deleted. Every check passed. The file was ignored by `.gitignore`, so it was **not in
the commit**: 329 lines deleted from the instruction file, nothing added to hold them,
`git status` clean, the pull request's gate green.

```bash
git show HEAD:path/to/moved.md | wc -l    # reads the commit
wc -l path/to/moved.md                    # reads the disk, and will lie to you
```

The gitignore form matters too, and fails silently in the wrong direction:

```gitignore
.claude/*           # NOT `.claude/` — git does not descend into an excluded
!.claude/skills/    # directory, so a `!` rule beneath one is never consulted
```

A good verification for a move is three parts, all read from the commit: how many removed
lines appear verbatim at the destination, a keyed-phrase check that anything *rephrased*
survived somewhere, and a check that the destination does not restate what the source kept.
Run each one deliberately wrong once, to confirm it can fail.

### What a gate cannot do

It measures size, never whether a deleted rule landed anywhere, and never whether a sentence
is still true. Three habits cover the rest:

- **The machine is the truth; the file records how it was set up.** A sentence stating what
  something does, with no command and no output beside it, is a belief. In the measured case
  one such sentence about hardware survived six days and a feature was designed on top of it
  before anybody measured; the measurement said the opposite.
- **Retire on write.** Adding a rule means deleting the one it replaces, or marking it
  retired in a form a checker enforces. Without this nothing ever shrinks, and superseded
  sentences keep a confident present tense.
- **Date the file.** `Last reviewed: YYYY-MM-DD` at the top, as a reference page would have.
  A file nobody has reviewed in two months should say so.

## Trade-offs

- **Every move costs a lookup.** A question about a subsystem now needs a skill invoked or a
  KB page fetched, where the text used to be in context already. That is the trade, and it is
  only worth it because the text was in context on every session including the ones that
  never read it.
- **Condensing is not moving, and should be decided separately.** Moves are mechanically
  verifiable; rewriting prose shorter is judgment, and what gets lost is usually the
  measurement that made a rule something other than arbitrary. In the measured case the
  original 40 KB target turned out to be unreachable by moving alone, and the remainder was
  left at 108 KB with the gate's own comment recording *why* — rather than ratcheting toward
  a number chosen before anybody had read what was left.
- **Four or five skills is a different cognitive load from one file.** It is better than
  2,700 lines, but a reader now has to know the map. A routing table at the top of the
  instruction file ("where a new fact goes", "what to read when") is the cheapest fix and
  should be written at the same time as the first skill.
- **This is advisory, not a framework.** No tooling is required beyond a shell line in the
  pre-merge script and a directory of markdown.

## Related Articles

- **[spec-based-development](spec-based-development.md)** — the spec file this article routes
  investigations into, and the document types a project needs alongside its instruction file.
