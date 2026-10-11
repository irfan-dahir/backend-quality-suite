---
name: ratify
description: "Use when asked to ratify, approve, or sign off a profile field, or when doctor reports fields as UNTRUSTED. Records one field as 'declared' or 'approved', signed, dated and commit-stamped. Writes to .backend-suite/profile.json, so never invoked without an explicit instruction."
invocation: explicit
maturity: unverified
---

# /ratify

> Documents are referenced by role — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" <role>`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.

You help a human ratify a profile field. `doctor.py` refuses to trust a field
whose provenance is `inferred` or unrecorded, and prints the ratified-of-total
count on every run — but until `bin/ratify.py` existed there was no way to
approve anything except hand-editing `.backend-suite/profile.json`.

That matters more than convenience. The mitigation for "a skill argued well for
a wrong mapping" is *inferred provenance plus ratification*. Half a mitigation is
worse than none: it produces a profile everyone believes was reviewed, because
the mechanism for reviewing it exists on paper.

**This command WRITES to the profile.** That is why it is `explicit`, and why
nothing here may be run on your own initiative — a ratification is a person's
signature, and a signature an agent applied on their behalf is not one.

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/ratify.py` is stdlib-only Python — nothing to
install. It needs a git repository, because staleness is measured in commits,
not in days: without a readable HEAD it exits 2 rather than writing a stamp it
cannot later check.

## Step 1 — See what is outstanding

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/ratify.py" --list
```

Three results print differently on purpose, and you must relay which one you
got: no provenance block at all (nothing has ever been reviewed), a block with
nothing outstanding, and a list. A tool whose listing looks the same on an
unreviewed profile and a fully-reviewed one is this suite's governing failure in
miniature.

## Step 2 — Get the human's decision, per field

Ratifying is per field, and the two states are not interchangeable:

| State | Flag | Means |
|---|---|---|
| `approved` | *(default)* | A human read a machine's proposal and agrees with it. Requires that something was actually proposed. |
| `declared` | `--declare` | A human wrote this value themselves. There was no proposal to review. |

Before proposing either, show the human the value, where it came from, and what
you checked against the tree. Then let them answer. Do not pick the state for
them and do not sign for them: `--by` is required precisely because an approval
nobody signed cannot be re-examined, and reads downstream exactly like one that
was.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/ratify.py" source.root --by NAME \
        --evidence "what was actually checked"
python3 "${CLAUDE_PLUGIN_ROOT}/bin/ratify.py" project.framework --declare --by NAME
```

Other flags: `--on YYYY-MM-DD` for the decision's date, `--profile` and `--dir`
for a non-default location, and `--force` to re-stamp a field that is already
trusted. Treat `--force` as a separate confirmation, not a retry — it exists for
a deliberate re-examination, not for making a refusal go away.

## Step 3 — Read the refusals as designed behaviour

It refuses in every case where the record would be less true than it looks: a
field the profile does not have, an approval with nothing proposed, re-approving
an already-trusted field, an identical re-run (the silent no-op), a path that is
not on disk (which writes a CONTRADICTED on sight), and no readable HEAD. Exit
**1** is refused-but-fixable-by-you; exit **2** is refused-and-cannot-be-answered-here.

Relay the refusal verbatim. None of them is a failure to work around.

## Step 4 — Report

Say what was ratified, who signed it, against which commit, and what is still
outstanding — the script prints all of that. If it reports the working tree was
dirty, repeat that: a confirmation against uncommitted files is not reproducible
by anyone else at that commit, and the entry says so.

Then point at `doctor.py`, which is where the new state shows up in context.

---

## What you must never do

- Ratify anything without an explicit, per-field instruction from a human — an
  agent-applied signature defeats the entire mechanism
- Put your own name, or the model's, in `--by`
- Use `--declare` to get past a refusal an approval gave you; the two record
  different facts
- Reach for `--force` to silence a refusal
- Summarise `--list`'s "no provenance block" case as "nothing outstanding"
