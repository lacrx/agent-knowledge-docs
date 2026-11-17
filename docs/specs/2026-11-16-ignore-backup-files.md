---
id: 2026-11-16-ignore-backup-files
tier: 2
status: proposed
quiet: yes
paths:
  - .gitignore
---

# Backups are ignored before one is committed, not after

## Problem

- **The `.env` family was already covered; every other backup was not.** Measured against the
  pre-change file rather than assumed: `git check-ignore -v --no-index` reports `.env.bak` and
  `.env.bak-123` both ignored by `.env.*` on line 27, and reports **nothing** for
  `kb.py.bak-123` or `README.md.bak`. So the credential case was safe and the gap is every
  backup of a non-`.env` file.
  - **This is a correction to the first draft of this spec**, which claimed `.env.*` failed to
    match the timestamped form. It does match. The claim was written from the pattern's shape
    instead of from `check-ignore`, which is the habit this spec's own Verification section
    exists to enforce, and it would have made the Problem section argue for a danger that was
    not there.
- **This repository generates exactly the uncovered form.** `kb install` writes
  `scripts/kb.py.bak-<epoch>` on every run, as its own rollback copy. Two were sitting
  untracked in `scripts/` when this was found, from installs on 2026-11-16, and `git add -A`
  would have committed both. That is the live case; the `.env` one is precedent, not exposure.
- **The same shape has already cost this house a permanent blob, in another repository.** In
  `lacrx/assistant` a copy of `.env` made while editing it was swept into a commit by
  `git add -A` on 2026-11-11. That blob is still in that repository's history; the only reason
  the credential is not live is that it was rotated. That repository's rule is `*.bak` **and**
  `*.bak-*`, and both patterns are carried here for the same reason: `*.bak` alone does not
  match `kb.py.bak-1794609784`, verified below.
- **Nothing here would have caught it.** A backup is untracked rather than modified, so it does
  not show in a diff review; it appears in `git status` as one more `??` line beside the files
  somebody meant to add, and `git add -A` does not distinguish them.

## Invariants

- **S1.** A file whose name ends in `.bak`, or in `.bak-<anything>`, SHALL be ignored.
- **S2.** The rule SHALL carry both patterns. `*.bak` alone does not match
  `kb.py.bak-1794609784`, which is the form this repository actually produces.
- **S3.** The ignore rule SHALL NOT be the only defence for a credential. It stops an
  accident, not an intent, and `.env` is separately ignored above it.

## Blast radius

- **One file, nine lines, no code.** Nothing reads `.gitignore` at run time.
- **It can hide a file somebody wanted tracked**, if they deliberately name something
  `*.bak`. Nothing in this repository is named that way today (`git ls-files | grep bak`
  returns nothing), and a deliberate exception is one `!` line.
- **It does not clean up what already exists.** The two untracked backups in `scripts/` stay
  on disk as the rollback copies they are; they are simply no longer offered to `git add`.
  Deleting somebody's recovery material is not this change's business.
- `.gitignore` is in the checker's built-in tier-2 defaults, which is why this change carries a
  spec at all. That classification exists because of the incident above.

## Verification

| Invariant | How |
|---|---|
| S1, S2 | `git check-ignore -v scripts/kb.py.bak-1794609784` reports `.gitignore:50:*.bak-*`, `README.md.bak` reports `.gitignore:49:*.bak`, and `git status --short` goes from two `??` lines to clean with only `.gitignore` modified. Both patterns earn their place: the timestamped stray is matched only by the second. |
| the gap, measured | Against the pre-change file (`git stash`, then `check-ignore --no-index`): `.env.bak` and `.env.bak-123` already ignored by `.env.*`; `kb.py.bak-123` and `README.md.bak` not ignored at all. This is what the change closes, and what it does not. |
| S3 | `.env` and `.env.*` are untouched, above the new block. `grep -n '^\.env' .gitignore` still returns both. |
| blast radius | `git ls-files \| grep -i bak` returns nothing, so no tracked file becomes invisible. |

## Rejected

- **`*.bak` alone.** It does not match `kb.py.bak-1794609784`, which is exactly the form
  generated here — verified with `check-ignore`, not inferred.
- **Ignoring `scripts/*.bak-*` narrowly.** `kb install` is the generator today; the next tool
  that writes a backup beside the file it edits would need another line, and a list of places
  backups may appear is a list somebody has to maintain.
- **Making `kb install` write its backups outside the repository.** A better fix and a larger
  one: it changes a tool's recovery behaviour, and the rollback copy being beside the file is
  arguably why it gets found. Worth doing separately; ignoring them is correct either way,
  because the next generator will not have been fixed.
- **Deleting the two existing backups in this change.** They are recovery copies, untracked,
  and not this change's to remove.
