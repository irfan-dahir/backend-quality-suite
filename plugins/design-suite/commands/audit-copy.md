---
name: audit-copy
description: "DISABLED pending re-scoping — 73% of its commit-gating findings were wrong, measured on two real projects (issues #104, #109). The backing script refuses with exit 2 rather than running. Do not invoke it expecting a result; read this file for the measured reason and the bar for re-enabling it."
invocation: explicit
maturity: disabled
---

# /audit-copy

> ## ⛔ DISABLED — do not run this expecting a result
>
> `${CLAUDE_PLUGIN_ROOT}/bin/audit_copy.py` **does not run**. It refuses with
> **exit 2** (the CapabilityError convention in
> `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`) and prints why. It is listed as
> disabled — never as clean, never as passing — in `repo_health.py`,
> `design_debt.py`, the MCP audit server and `docs/CATALOG.md`, and a project
> whose `hooks.map.json` still registers it is told so by `doctor.py`, by the
> on-save hook and by the pre-commit runner. If you were about to conclude
> anything about this project's copy from its silence: don't. Nothing was
> scanned.
>
> **The measured reason (issues #104, #109).** Of the 26 findings that would
> actually gate a commit, **19 were wrong (73%)**; 81% of total output was noise.
> Measured independently on a second project, **93%** of findings trace to a
> single cause: `engine/copy.py`'s `classify()` returns `"microcopy"`
> unconditionally as soon as the adapter's keyword matched — but `message:`,
> `hintText:` and `helperText:` routinely carry body copy, so prose gets judged by
> label rules. **13 of the 14 `title_case` findings are multi-sentence prose.**
>
> **It is also narrow.** The four rules that need no label-vs-body judgment
> produced **0 findings across 444 strings** — they carry neither the value nor
> the risk. Only `all_caps` showed true-positive capacity, at **9%** of output.
> So this is not a threshold to tune: the rules encode a distinction between
> label copy and body copy that the checker cannot make, and it guesses, then
> states the guess as a verdict.
>
> **What re-enabling it takes** — all three, in the commit that removes the
> `audit_copy` entry from `design_suite/engine/audit_discovery.DISABLED`:
>
> 1. **The microcopy/content split must stop treating an adapter keyword as proof
>    of chrome.** It needs a real signal, declared by the consumer project in its
>    own `.design-suite/` config — hardcoding field names or file patterns in the
>    plugin violates CLAUDE.md's no-project-literals rule.
> 2. **`all_caps` must be measured separately** from the rules that depend on that
>    split. It is the only rule with demonstrated true-positive capacity, and
>    grading it alongside the others hides both facts.
> 3. **Clearing the bar on both axes**, re-measured on two real consumer projects:
>    ≤5% wrong *and* demonstrated non-zero true-positive capacity. A check that
>    scores 0% wrong because it now finds nothing has been silenced, not fixed.
>
> **The documented path back is issue #109's option 3**: re-scope the failing part
> as a skill under RFC-0002 §3b-ii. The distinction it fails at is semantic — it
> belongs to a reader, not a regex — which is exactly the line that RFC draws
> between a script that surveys and a skill that maps. The checks below marked as
> needing a reader (A, B, E, F) are the starting point for that; the mechanical
> seven are not.
>
> `--run-disabled` exists on the script for the re-measurement in step 3 only, and
> its output is not a result anyone should act on. `--selftest` still runs
> normally: it tests the rules against fixed strings, touches no project, and is
> what keeps the corrupting `title_case` fix of issue #109 from coming back.
>
> Nothing has been deleted. The rules, the per-rule exception mechanism and the
> baseline semantics all stay in the tree, because disabled means switched off and
> reversible.

---

## Everything below describes the audit as designed, for whoever re-scopes it. It is not currently runnable.

> Documents are referenced by role, e.g. `{{doc:brand-voice}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" brand-voice`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are the consistency auditor for the app's user-facing copy.

**Seven of the checks that used to be yours are now a script.** Sentence case, terminal periods, ellipsis characters, filler, apology, curly quotes and pre-shouted labels are decidable, and a decidable rule left to a reader is a rule that holds only when somebody remembers it. Run the gate, report what it says, and spend your own attention on the checks below it — terminology, tone and duplication — which genuinely need a reader.

**You report; you do not edit copy without confirmation. You never write Flutter code. Reference: `{{doc:copy}}`.**

---

## Step 0 — Preconditions

Confirm `python3` is available (no other tooling needed — `extract_copy.py` is stdlib-only, nothing to install, nothing to check like the asset pipeline's Blender/webp/librsvg dependencies).

Check whether `{{doc:brand-voice}}` exists:
- **If it exists** — run the full check set (A–F below).
- **If it doesn't** — tell the user you're running in **reduced "generic hygiene" mode** (checks C and D only; terminology and tone-register checks need a brand voice doc to check against) and suggest `/establish-brand-voice` as a next step, but still produce a useful report from what's checkable today.

## Step 1 — Gather state

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_copy.py"
python3 "${CLAUDE_PLUGIN_ROOT}/bin/extract_copy.py"
cat "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" brand-voice)" 2>/dev/null || echo "(no brand voice doc — running in generic hygiene mode)"
```

The first command is the mechanical gate; it exits non-zero on any **new**
finding. Known findings sit in a baseline, which is a debt register and not an
approval — if it is large, say how large and what the biggest class is, because
a number nobody reports is a number nobody works down.

If the gate reports a false positive — an acronym read as shouting, a proper
noun read as Title Case — the fix is `copy.properNouns` in the exceptions file,
not an exception on the string. A string exception silences one string; the word
list fixes the whole class.

`<pipelines.copy>/inventory.json` is gitignored and regenerable — always regenerate it fresh, never assume a stale copy is current.

## Step 2 — Run every check that is still yours, exhaustively

Checks C's mechanical half (three dots, curly quotes) and anything about case or
punctuation are **already covered by the gate** — do not re-report them. If you
find yourself writing a finding that says "this label ends in a period", the gate
either already said it or the string is classified as content; either way that
bullet is noise.

**This is an end-to-end audit, not a sample.** Every check below runs against **every entry in the inventory** — all `content` entries get a real tone-register read, not just a handful from feature areas you happen to remember; the full AI-tell list from `{{doc:brand-voice}}` gets checked, not a starter subset; verbosity gets swept across the whole distribution, not just the extremes; every high-similarity duplicate candidate gets manually resolved, not just the first one that looks real. "I checked a representative sample" is a different, weaker report than this skill produces — if you did that, say so explicitly and go back and finish the rest before presenting results as the audit.

For each inventory entry:

| # | Check | Requires `{{doc:brand-voice}}`? | Severity if failed |
|---|---|---|---|
| A | Terminology-glossary violation — a banned synonym used where the canonical term should be (e.g. clinical vs. billing language mixed) | Yes | 🔴 Critical — the exact kind of drift the glossary exists to catch |
| B | Tone-register mismatch — a `content`-category string reads noticeably more/less formal than the doc's stated tone for that context, **without** an apparent deliberate reason (a consent/legal screen reading formal is not a violation — flag only unexplained shifts) | Yes | 🟡 Should fix — always show the surrounding context before concluding it's wrong |
| C | AI-tell banned-phrase hit — matches the doc's banned-phrase list, or (generic mode) a starter list: "seamless", "elevate", "unlock", "leverage", "delve", "navigate the complexities of", "whether you're X or Y", "it's important to note", stacked em-dashes, rule-of-three cliché lists, "Let's dive in" | No | 🟡 Should fix |
| D | Verbosity/reading-level budget — `microcopy` entries should be short and direct; `content` entries should stay within a reasonable Flesch Reading Ease range for a general adult audience (lower scores = harder to read; flag notably dense entries, don't just eyeball the number in isolation) | No | 🔵 FYI unless clearly excessive |
| E | Duplicate near-identical microcopy — two or more strings that are almost the same wording for what should be one canonical term/phrase | Yes (glossary helps, but detectable without it too) | 🟡 Should fix |
| F | Mis-categorized entry — `extract_copy.py`'s microcopy/content heuristic is a word-count/keyword guess; spot-check a sample and flag any the report otherwise relied on incorrectly | No | 🔵 FYI |

## Step 3 — Report

Use the same format as `/audit-assets`/`/review-docs`: 🔴 Critical / 🟡 Should Fix / 🔵 FYI sections (omit empty ones), one specific finding per bullet with `file:line`, then a summary count line. Do not include an "Auto-fixable" section — no finding here should be applied without a human writing the actual replacement copy; that's a separate, not-yet-built skill.

---

## What you must never do

- Edit any `.dart` file's copy, even for an "obviously" mechanical fix like a banned-phrase swap
- Treat a tone-register shift as automatically wrong without showing the surrounding context first — some register splits (e.g. consent/legal text) are deliberate
- Claim a full audit ran if `{{doc:brand-voice}}` didn't exist — always state clearly which mode produced the report
- Treat `extract_copy.py`'s microcopy/content categorization as authoritative without spot-checking a sample
- Present a sampled or partial pass as if it were the full audit — this is an end-to-end check of every inventory entry, every time; if time/token pressure forces a partial pass, say so explicitly in the report rather than letting it read as exhaustive
