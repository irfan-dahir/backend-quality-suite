---
name: audit-adapter-pattern
description: "Mechanically check that screens never import the layers they are supposed to reach only through an adapter — state-management, repositories, data sources, HTTP clients. Rule and directory layout both come from this project's arch-rules.json, never from a hardcoded convention. Never changes your code; saves its report to .design-suite/adapter-pattern-findings.json on every run. Use when asked whether the adapter/presentation boundary still holds, or after adding a screen."
invocation: auto
maturity: unverified
---

# /audit-adapter-pattern

> **What it writes.** This audit never edits source, but every plain run
> (no flag needed) saves its raw report to `.design-suite/adapter-pattern-findings.json` (override with `--out`),
> and `--findings` additionally writes the envelope under `.design-suite/findings/`.
> Those files are what `/design-debt` and the MCP server read, so they are
> written deliberately. Keep them out of git — they quote your source.

> Documents are referenced by role, e.g. `{{doc:architecture}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" architecture`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are the adapter-boundary auditor. A screen is meant to receive everything it
needs through an adapter; the moment it imports a BLoC, a repository, a data
source or an HTTP client directly, the contract header stops describing what the
screen actually depends on and the screen stops being portable.

This is a deterministic check — an import is either present or it is not — so
there is no heuristic tier here and a finding is not a judgement call.

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_adapter_pattern.py` is stdlib-only Python —
nothing to install.

It reads **both** halves of its rule from this project's architecture rules
(`audits.archRulesFile` in the profile, conventionally
`.design-suite/arch-rules.json`), section `adapterPattern`. Nothing about a
directory layout is hardcoded in the script.

| Key | Meaning |
|---|---|
| `screensDir` | Directory holding screens (the scan root) |
| `screensGlob` | Which files under `screensDir` count as screens. The Dart adapter supplies a feature-first default; **no other stack has one**, so on any other stack this key is required |
| `bannedImports` | Import roots a screen may not reach directly |
| `exemptSuffixes` | File-name suffixes skipped by rule (Dart default: route-entry `_page_wrapper.dart`) |

Which files are source and how an import is spelled come from the language
adapter, not from this file.

**Known limit:** TypeScript path aliases such as `@/x` are not resolved. An
aliased import is compared as written, so a banned root reached through an alias
is not caught — spell `bannedImports` the way imports are actually written, and
do not read a clean run on an aliased codebase as proof.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_adapter_pattern.py"
```

Useful flags:

| Flag | Effect |
|---|---|
| `--dir <path>` | Audit one directory instead of `adapterPattern.screensDir` |
| `--out <path>` | Where the findings JSON is written (defaults to this project's findings artefact) |
| `--findings [<path>]` | Also write the shared findings envelope `/design-debt` reads |

## Step 2 — Read the refusals as refusals

Exit **2** means the audit did **not** run. It refuses when:

- there is no `adapterPattern` section in the architecture rules;
- the section still holds `init.py`'s `TODO` placeholders (`bannedImports` or
  `screensGlob`), or `bannedImports` is empty;
- no language adapter matches this project, or the adapter cannot read imports;
- there is no screens scope for this stack (no `screensGlob`, no adapter default);
- the scoped directory does not exist, or **zero files** matched the scope.

Exit 0 is only ever returned when at least one in-scope file was scanned and
none violates. Each refusal used to report as "no violations found", which is
the failure this whole suite is built against — **an audit that refused and an
audit that found nothing must never read the same in your report.** Say which
one happened.

The project's own documented exception (route-entry wrapper widgets, which may
consume state via context but never instantiate it) is applied by the script
from the rules file. Do not maintain a second copy of that list here or in your
head.

## Step 3 — Report

Same format as every other audit in this suite: 🔴/🟡/🔵 sections, one finding
per bullet with `file:line`, summary count.

- 🔴 Critical: every violation. The check is exact, and each one is a screen
  that cannot be moved or re-adapted without editing it.
- 🔵 FYI: a file the scan skipped by rule (a documented wrapper), worth naming
  so the skip is visible rather than silent.

---

## What you must never do

- Edit a screen's imports to satisfy the audit without confirmation — the fix is
  usually "widen the adapter", which is an API decision, not an import shuffle
- Report exit 2 (refused) as a clean run
- Add a project's directory names or banned roots to this file — they belong in
  `arch-rules.json`, where the script actually reads them
