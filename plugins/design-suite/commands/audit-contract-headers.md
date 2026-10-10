---
name: audit-contract-headers
description: "Use when asked whether screen contracts or adapter interfaces are still accurate, or after adding or removing an adapter field. Checks each screen's contract header against its adapter: omitted fields, dangling entries, unread fields. Read-only: reports findings, never edits."
invocation: auto
maturity: proven
---

# /audit-contract-headers

> Documents are referenced by role, e.g. `{{doc:instructions}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" instructions`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are auditing the agreement between a screen's declared contract and its real
one. Where a project's screens carry a header naming the inputs they may read and
the outputs they may call, that header is an interface — and unlike the code, it
has no compiler.

**You report; you do not edit without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_contract_headers.py` is stdlib-only Python.

It needs a `contractHeaders` section in the project's architecture-rules file
(the profile's `audits.archRulesFile`). Without one it exits 2 and says so —
that is a refusal, not a pass. If the project has no header convention, this
skill does not apply; say so rather than inventing a config.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_contract_headers.py"
```

**Read the exit code before the output.**

| Exit | Means |
|---|---|
| 0 | every header matches its adapter |
| 1 | findings — real drift, listed |
| 2 | **could not look** — unresolvable config, a glob matching nothing, or a language whose adapter cannot read class structure |

A `2` must never be reported as clean. It is the INERT case in
[CONCEPTS.md](${CLAUDE_PLUGIN_ROOT}/../../docs/CONCEPTS.md): an audit that
reports nothing must not be indistinguishable from a healthy codebase.

## Step 2 — Read the four kinds differently, because the fix differs

| Kind | Means | Usual fix |
|---|---|---|
| `undocumented_field` | the screen reads it; the header omits it | add the line |
| `stale_header_entry` | the header names it; the class does not declare it | delete the line |
| `dead_adapter_field` | declared, and read nowhere in the project | **usually delete the field** |
| `missing_contract_header` | no header at all | write one, or say why the file is out of scope |

`dead_adapter_field` is the one that needs judgement, and the one where the
obvious fix is wrong. Documenting a field nothing reads makes it permanent and
makes the header longer while telling a reader less. Deleting it is normally the
honest answer — but check first whether it is:

- **about to be wired** in the same effort, in which case say so and leave it;
- **plumbed through composition** to a sibling screen. The audit already accounts
  for this and will not flag it, so a flagged field genuinely has no reader.

When a project's field appears dead but its name suggests infrastructure someone
intends to use (loading and error state are the recurring case), check whether an
upstream repo owns that vocabulary before deleting or renaming — adopting the
owner's names later beats coining local ones now.

## Step 3 — Report

Same format as the other audit skills: 🔴/🟡/🔵 sections, one finding per bullet
with `file:line`, and a count. Suggested severity:

- 🔴 `stale_header_entry` and `missing_contract_header` — the header is actively
  misleading, or absent where the convention requires one.
- 🟡 `undocumented_field` — a real omission, and the most likely to hide a screen
  reaching past its contract.
- 🔵 `dead_adapter_field` — not a defect in behaviour, but each one is a
  maintenance cost and a future wrong header. Group them; do not list fifteen
  bullets where one line and a table will do.

If the run was clean, say what was checked — how many screens, against how many
adapters. "No findings" without a corpus size is the sentence this suite exists
to distrust.

---

## What you must never do

- Report exit 2 as a pass, or a refusal as "no findings".
- Delete an adapter field without confirmation, however dead it looks.
- Add a `dead_adapter_field` to the header to make the audit go quiet. That trades
  a reported problem for a permanent one.
- Baseline a finding without a reason. An entry left `UNJUSTIFIED` is reported on
  every run precisely so that "we decided" and "nobody got round to it" stay
  distinguishable.
