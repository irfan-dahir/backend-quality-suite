---
name: audit-unused-tokens
description: "Use when asked which design tokens are unused, or before pruning a palette. Finds tokens the token file declares that no scanned source reads (spacing, radii, durations, curves, sizing, colour); counterpart to /audit-unwired-roles. Read-only: reports findings, never edits."
invocation: auto
maturity: unverified
---

# /audit-unused-tokens

> Documents are referenced by role, e.g. `{{doc:design}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You answer one question: of the tokens this project's token file declares, which
does nothing in the scanned source ever reference?

This is the sibling of `/audit-unwired-roles`, one layer down and across more
categories. An unwired semantic colour role is a **theming** risk — a brand
changes it and nothing moves, so the re-skinning claim is partly false. An
unused raw token is not that; it is pruning work. One `spaceXX` a designer keeps
re-verifying is safe to delete is the whole cost, and it is a real one.

**You report; you do not edit the token file without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_unused_tokens.py` is stdlib-only Python —
nothing to install.

It needs three things, all from config, none hardcoded: the token source and
accessor from `tokens` in the profile, the language adapter from `adapters.lang`
(what counts as "declared" and what counts as "read" are language questions and
live in the adapter), and the `unusedTokens` section of this project's
architecture rules (`audits.archRulesFile`) for scope and for
`requiredTokens` — the subset whose absence is a failure rather than a note.

Exit **2** means it refused: no `unusedTokens` section, no resolvable token
source, or an adapter that cannot enumerate declared names. **An adapter that
cannot tell must report that it cannot tell** — it must never return an empty
set that reads as "there are none".

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_unused_tokens.py"
```

`--out <path>` additionally writes the findings as JSON; the artefact is
regenerable, so always regenerate rather than reading a stale copy.

## Step 2 — Split the result the way the script does

| Tier | Meaning |
|---|---|
| Failing | A token listed in `unusedTokens.requiredTokens` that nothing reads. The project declared this one must be used, so its absence is a regression. |
| Unused | Everything else nothing reads. A pruning candidate, not a failure. |

Before recommending a deletion, check the ways a token can be read that a source
scan cannot see: a name built by string interpolation, a token consumed in
another repository or package, a token referenced only from generated code or
from a platform file the scan's roots exclude. Any of these makes "unused" mean
"not seen here", and the report has to say which it means.

## Step 3 — Report

🔴/🟡/🔵 sections, one token per bullet with the category it belongs to and
where it is declared, plus a summary count and the scanned-roots line, so a
narrow scan cannot read as a whole-project verdict.

- 🔴 Critical: a required token nothing reads.
- 🟡 Should fix: an unused token in a category the project is actively
  migrating — it is about to be re-added by hand by someone who did not find it.
- 🔵 FYI: everything else unused — the pruning list.

---

## What you must never do

- Delete a token from the token file yourself; propose the list and let a human
  decide, since deletion is the one irreversible move here
- Report "unused" without saying what the scan covered — an unused token and a
  token used outside the scanned roots look identical from inside this audit
- Report exit 2 (refused) as a clean run, or an empty declared-token set as "no
  unused tokens"
- Conflate this with `/audit-unwired-roles`: a raw token and a semantic role are
  different claims with different stakes
