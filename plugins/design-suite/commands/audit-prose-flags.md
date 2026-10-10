---
name: audit-prose-flags
description: "Use when maintaining this plugin's own skills, or after renaming or removing a script flag. Checks every flag a skill's markdown names beside a bin/*.py script exists in that script. Suite-maintenance, not consumer-project. Read-only: reports findings, never edits."
invocation: auto
maturity: unverified
---

# /audit-prose-flags

You check one narrow thing: when a skill's markdown tells Claude to run a script
in this plugin's `bin/` and names a command-line flag beside it, does that flag
actually exist in that script?

(No example invocation is written out here on purpose. This audit harvests every
script-and-flag pair it finds in this plugin's markdown, so an illustrative
example naming a script that does not exist would be harvested as a real claim
and reported as a finding by the very audit this file documents.)

`audit_skill_paths.py` already proves the *script* exists. It passes cleanly on
a line naming a real script and a flag nobody ever implemented — Claude runs it,
argparse exits 2, and the skill's recipe dies at step three. The path gate cannot
see it, because the path is fine.

This is the same class of bug as a hand-written catalogue: prose asserting a fact
about code, with nothing comparing the two.

**Scope note:** this audits *this plugin's own* markdown against *this plugin's
own* scripts. It is maintenance tooling for the suite, not a check a consuming
project runs against its application code.

**You report; you do not edit skills without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_prose_flags.py` is stdlib-only Python — nothing
to install. It needs no profile section: it reads markdown and argparse, both of
which are in the tree.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_prose_flags.py"
```

| Flag | Effect |
|---|---|
| `--root <path>` | Scan a different directory of plugins |
| `--list` | Print what the scan harvested — every flag/script pair it attributed, before judging any of them |

Reach for `--list` whenever a finding looks wrong: attribution is per line, so a
flag named far from its script's name can be attributed to the wrong script, and
the harvest is where you see that rather than guessing at it.

## Step 2 — Read the exit codes exactly

| Exit | Meaning |
|---|---|
| 0 | Every documented flag is real |
| 1 | At least one documented flag does not exist |
| 2 | The scan found nothing to check |

**Exit 2 is not a pass.** An empty scan means no markdown/script pairs were
harvested at all — a moved directory, a wrong `--root`, a changed file layout —
and reporting it as "all flags valid" is precisely the silence this suite exists
to forbid.

## Step 3 — Know what it cannot catch, and say so

A **negated** claim. A skill saying "`--from-survey` does *not* exist" would be
wrong in the opposite direction and nothing here would notice: the flag is
named, the flag is real, the sentence is still false. Catching that means
reading the sentence rather than the token, which is a judgement call and
belongs in a review, not a gate.

Say which half is covered rather than letting a green run imply both.

## Step 4 — Report

🔴/🟡/🔵 sections, one finding per bullet naming the markdown `file:line`, the
flag, and the script it was attributed to.

- 🔴 Critical: a flag that does not exist — the documented invocation is broken
  today, for anyone who follows it.
- 🔵 FYI: an attribution that looks wrong on inspection; propose rewording the
  line so the flag sits beside its own script.

---

## What you must never do

- Report exit 2 (nothing scanned) as a clean run
- "Fix" a finding by deleting the flag from the prose without checking whether
  the *script* is what regressed — a removed flag and a mistyped one need
  opposite repairs
- Add a flag to a script just to make the documentation true, without
  confirming that flag is wanted
