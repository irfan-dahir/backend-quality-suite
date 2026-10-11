---
name: audit-claude-md-drift
description: "Use when asked whether CLAUDE.md is still accurate, or before trusting a rule it states. Checks its prose against what enforces it: stale gate counts, rules whose script left CI, rules with no enforcement. Never edits, but runs the shell commands .backend-suite/claude_md_enforcement.json declares, so review that config like a hook."
invocation: auto
maturity: unverified
---

# /audit-claude-md-drift

You are checking whether this project's `CLAUDE.md` and its actual enforcement have drifted apart. This is the documentation-layer version of the suite's governing principle: an audit that reports nothing must never be indistinguishable from a clean codebase, applied to CLAUDE.md's own claims about itself.

**You report; you never edit CLAUDE.md or any enforcement script without confirmation.**

---

## Step 0 — Preconditions

This audit needs a project-specific mapping from CLAUDE.md's rule statements to
what is supposed to enforce each one:

```
.backend-suite/claude_md_enforcement.json
```

If it does not exist yet, this is a one-time setup: read the project's CLAUDE.md,
find every rule stated as a mechanically-checkable fact (a count, a script that's
claimed to run somewhere, a generated file that's claimed to be gated) versus a
pure process rule (branching discipline, "ask before you push"), and draft the
mapping — see `${CLAUDE_PLUGIN_ROOT}/bin/audit_claude_md_drift.py`'s
`_EXAMPLE_SCHEMA` for the shape of a rule entry. Show the draft before writing it.

**Never invent an "actualCommand" or "claudeMdPattern" that wasn't verified by
actually reading the file.** A guessed regex that happens to match is worse than
an admitted gap — it reports a rule as checked when it never was.

**This config is trusted input, at a hook's level of trust.** The audit itself
edits nothing, but each rule's `actualCommand` is handed to
`subprocess.run(["bash", "-c", cmd], cwd=REPO)` — arbitrary shell, run in the
repository, with whatever side effects that command has. "Read-only" is therefore
a property of this audit's own code, not a guarantee about the config: a
`claude_md_enforcement.json` that someone else wrote, or that arrived in a pull
request, can do anything a shell can. Review it the way you would review a new
entry in `hooks.map.json` before running the audit, and keep every
`actualCommand` a read-only query — a grep, a count, a `git ls-files` — never a
command that writes, installs, or reaches the network.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_claude_md_drift.py"
```

Exit 0 means every mapped, mechanizable rule still matches reality. Exit 1 means
either drift was found, or a mapped check could not be evaluated at all (a
regexp that no longer matches CLAUDE.md's current wording, a command that
errored) — both are failures, because an unresolvable check is not a pass.

## Step 2 — Read the three buckets differently

- **verified, matching** — CLAUDE.md's claim and the mechanism agree. Not a
  finding.
- **unenforceable** — rules the config author already decided have no
  mechanical signal (branch discipline, "ask before every push"). Always
  reported, never a failure by itself. If one of these turns out to be
  checkable after all (a branch-protection API, a commit hook), that's a
  candidate to move into a real check, not to leave as prose forever.
- **DRIFTED / CANNOT VERIFY** — CLAUDE.md states something as true that the
  repo no longer backs up, or the mapping itself has gone stale (the pattern
  used to extract CLAUDE.md's claim no longer matches its current wording).
  Report both as needing a human: either CLAUDE.md is wrong now, or the thing
  it describes stopped doing what it says, or the config needs updating
  because CLAUDE.md was legitimately reworded.

## Step 3 — Report

Summarize each drifted or unresolvable rule with the exact CLAUDE.md wording
it maps to and what the mechanism actually showed. Do not silently narrow the
rule set to make the audit read as passing — an unmapped rule that looks
mechanizable is itself worth flagging as a gap in the config, separate from
the audit's own pass/fail.
