---
title: Instruction File Design
topics:
  - agent-workflow
  - claude-md
  - instruction-files
  - context-management
  - agent-skills
  - path-scoped-rules
  - ai-development
  - developer-experience
summary: >
  Advisory guide for CLAUDE.md and other agent instruction files — route a fact by what it is
  about rather than by who found it, move subsystem detail into skills that load on match and
  file-scoped boundaries into rules that fire on a path (per repo, or per user for what every
  repo shares), and gate the size mechanically so the file cannot grow back.
aliases:
  - claude md design
  - claude.md
  - agents.md
  - agent instruction files
  - agents md structure
  - instruction file size
  - context window cost
  - project skills
  - skills vs claude md
  - painpoints file
  - path scoped rules
  - claude rules directory
  - rules vs skills
  - paths frontmatter
  - machine wide rule
  - user level rules
  - every repository
  - where a fact goes
  - instruction file is too big
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
| A rule that only matters while one particular file is open | a path-scoped rule (`.claude/rules/<name>.md` with a `paths:` list) | the harness injects it when a read or write touches a matching path, so no model has to judge it relevant |
| The same, but true of **every** repository on the machine | a user-level path-scoped rule (`~/.claude/rules/<name>.md`) | it fires the same way in any project, so a cross-repo rule needs no copy per repo |
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

### A security invariant needs a mechanism that fires, not one that is offered

Whoever edits a file must meet its boundary rule **without having invoked anything**. That
requirement is the right one and it is what rules out a skill: a skill is *offered* to the
model as a description, and the model decides. For a boundary whose violation is silent,
"probably loads" is not a mechanism.

**A path-scoped rule satisfies the requirement, so the invariant can move after all.** The
earlier version of this article concluded that such an invariant "does not move", and that
conclusion was correct given only the two destinations it knew about. It was a claim about the
mechanisms the author had found, written in the confident present tense as a claim about the
problem. Worth stating plainly, because the same shape is the most common defect this whole
article is about.

The split that still applies is by **mechanism**, not by sensitivity:

| What it is | Where | Why |
|---|---|---|
| A boundary that only matters while a particular file is open | a path-scoped rule | it fires on the path; nothing judges it relevant |
| A boundary of that kind that holds in every repository | a **user-level** path-scoped rule | one copy, every project; see the section below |
| A subsystem narrative somebody reads while working on it | a skill | a missed load costs context, not a guarantee |
| A boundary somebody must know **before** they open anything | the instruction file, in one sentence | nothing can inject it, because there is no path yet |

That last row is what keeps the instruction file from emptying out entirely. "Is this service
reachable from the internet?" is a question asked before any file is opened, so the one-line
answer belongs where it is always present; the reasoning behind it belongs in the rule. In the
measured case six such sentences stayed: the authentication boundary, the page's XSS
invariant, scope isolation, the unconditional restricted flag, the guard stopping a pull
request from merging itself past the reviewer, and the single sanctioned writer of the
credential file.

Getting this wrong in the other direction is easy and worth watching for: a verbatim move
leaves the invariant in *both* places, which is the duplication the whole exercise exists to
remove. Grep the destination for what the instruction file claims to own.

### Path-scoped rules come in two scopes, and the machine-wide one is easy to miss

A `paths:` rule can live in the repository (`.claude/rules/`) or in the user's own config
(`~/.claude/rules/`). **Both fire the same way; the user-level one fires in every project.**
That is the right home for a rule about the toolchain rather than the code: how the agent's own
settings are rendered, where a fact goes when you are editing an instruction file, how a
repository's review-and-spec configuration is assembled. Those are true of twenty repositories,
and a per-repo rule would be twenty copies of one fact — the defect this whole article is about.

Three things worth knowing before relying on it:

- **It is per-user, so it does not travel with the code.** A teammate cloning the repository
  gets the repo rules and none of the user-level ones. Use it for rules about *your* machines
  and toolchain, not for anything a contributor needs.
- **On more than one machine, put the files in whatever already syncs and symlink to them.**
  In the measured case `~/.claude/rules` is a symlink into the synced vault directory, beside
  the shared memories and agent definitions, which was already the pattern for those.
  **Verified that rules load through the symlink** before anything was moved into one — that
  was the risk worth retiring first, and the second machine needed the symlink created by hand.
- **A machine-wide rule and a repo rule can both fire on one read.** Keep their contents
  disjoint, or you have reintroduced the duplication one layer up. In the measured case the
  cross-repo layer holds how a tier is assembled and the repo layer holds that repository's own
  tier-2 list, with the generated table staying in the always-loaded file because it is needed
  when writing any commit message and that touches no file at all.

### Prove the mechanism before you trust it, with a negative control

A loading mechanism is a claim about the harness, and the only honest way to hold it is to
test it. Before moving a thousand lines into path-scoped rules, the measured case wrote four
throwaway rule files carrying sentinel strings and ran each in a fresh one-shot session:

| Probe | What it establishes |
|---|---|
| a rule naming one exact file, then read that file | the mechanism injects at all |
| a rule naming `dir/prefix*.ext`, then read a match | `*` globs are honoured |
| a rule naming `dir/**`, then read something under it | `**` is honoured |
| **all of the above present, read nothing** | **it does not inject unconditionally** |

The fourth is the one that matters and the one most likely to be skipped. A mechanism that
always injects is the instruction file with extra steps, and every positive probe passes
identically either way. The same reasoning applies to a skill, where the check is that it
appears in a fresh session's skill list — and in the measured case one skill had sat
unloadable for two weeks because its file was named `skill.md` rather than `SKILL.md`, with
its directory, frontmatter and contents all correct.

Two further checks, both cheap and both caught something real:

- **Every path in a `paths:` list must resolve to something that exists.** An entry matching
  nothing is a rule that never fires, which is indistinguishable from a rule that does not
  exist. This caught an instruction file that referred to `ask.py` throughout while the file
  was two directories down at `app/agents/ask.py`.
- **Check whether version control is even looking at the directory.** Where the harness reads
  rules from a dotted directory, a `.gitignore` line excluding that directory means the move
  is invisible to `git status` and absent from the commit. Git does not descend into an
  excluded directory, so an un-ignore for something inside it is never consulted: the
  exclusion has to be written against the directory's *contents* with an exception per shipped
  subdirectory. In the measured case the first attempt committed an instruction file with 329
  lines deleted and the destination absent from the diff, with every check passing because
  every check read the working tree.

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
  measurement that made a rule something other than arbitrary. The measured case ended at
  **24 KB from 211 KB, 89% gone, entirely by moving** — but it passed through two stages whose
  figures were each written down as the end of the road. The gate's comment recorded a 40 KB
  target as "not reachable by this route" with 108 KB left, which was true of the route it
  named and false as the sentence it reads as; the remaining material was the file-scoped
  boundaries and the mechanism for those had not been found yet. Then at 33.8 KB the remainder
  was called "genuinely cross-cutting", which was wrong about four sections because they were
  judged by their titles rather than by which files they are about — the only question a
  `paths:` list can act on. Record *which* route you measured, and expect the number to move
  again when you find a mechanism you did not know.
- **A dozen destinations is a different cognitive load from one file.** It is better than
  2,700 lines, but a reader now has to know the map. A routing table at the top of the
  instruction file ("where a new fact goes", "what to read when") is the cheapest fix and
  should be written at the same time as the first skill — **and it is itself a fact in two
  places.** In the measured case the table listed six rules within minutes of the seventh
  existing. Update it in the commit that adds the destination, not afterwards.
- **A path-scoped rule is silent about itself.** Nobody reading the instruction file learns
  that a boundary exists for a file they are not opening, which is why the one-sentence form
  stays behind. The honest statement of the cost: a session asking a question without opening
  the relevant file gets the answer and not the reasoning.
- **This is advisory, not a framework.** No tooling is required beyond a shell line in the
  pre-merge script and a directory of markdown.

## Related Articles

- **[spec-based-development](spec-based-development.md)** — the spec file this article routes
  investigations into, and the document types a project needs alongside its instruction file.
