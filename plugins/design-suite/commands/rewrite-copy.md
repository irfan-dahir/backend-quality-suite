---
name: rewrite-copy
description: "Draft or rewrite user-facing copy so it is on-brand and on-terminology, and does not read as machine-written. Never applies a change without showing it first. Brand-sensitive: let the user decide rather than invoking autonomously."
argument-hint: "<string, finding, or screen>"
invocation: explicit
maturity: unverified
---

# /rewrite-copy

> Documents are referenced by role, e.g. `{{doc:copy}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" copy`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You draft or rewrite user-facing copy — a specific string, a set of `/audit-copy` findings, or new copy for a screen/flow being built — so it's on-brand, on-terminology, and doesn't read as AI-written. You never apply a change without showing it and getting approval first. Full system: `{{doc:copy}}`.

**Requires `{{doc:brand-voice}}` to exist.** Without it there's no defined "on-brand" to draft against — run `/establish-brand-voice` first and stop here if it's missing.

---

## Step 0 — Preconditions (self-bootstrapping)

1. Read `{{doc:copy}}`.
2. Confirm `{{doc:brand-voice}}` exists. If it doesn't, tell the user and stop — recommend `/establish-brand-voice`. Do not improvise a voice from general good-writing instinct; that's exactly the "sounds like AI" failure mode this skill exists to avoid.
3. Confirm you are on a feature branch (never `demo`/`main`) if this run will edit and commit code.

## Step 1 — Identify the target

Ask (if not already clear from the request):

- **Rewrite existing copy** — a specific string, a file/screen, or a batch of `/audit-copy` findings to work through. If working from audit findings, ask which severity tier to start with (usually 🔴 then 🟡).
- **Draft new copy** — for a screen/flow that doesn't have copy yet (e.g. being built alongside a new feature).

## Step 2 — Classify before drafting

For each target string, classify **microcopy vs. content copy** (see `{{doc:copy}}` §6) — this determines the register and length budget:

- **Microcopy**: draft to the terminology glossary in `{{doc:brand-voice}}` first — consistency beats cleverness. Keep it as short as the existing pattern for that UI element (don't lengthen a button label "for warmth").
- **Content copy**: draft to the matching tone attribute for this context (status copy vs. consent/legal text may call for different registers — check `{{doc:brand-voice}}`'s notes on when each tone applies, don't default to one register for everything).

## Step 3 — Draft against the voice doc, not general instinct

While drafting, actively check against `{{doc:brand-voice}}`:
- No banned AI-tell phrases from its list.
- Canonical terminology only — no banned synonyms from the glossary.
- Within the stated reading-level target for content copy.
- Matches the tone attribute that applies to this context.

**Consent, legal, and clinical-disclosure text is a special case:** drafting it on-brand doesn't make it compliant. Flag explicitly that legally sensitive copy should get a human (legal/clinical) review before shipping — this skill improves voice and clarity, it does not substitute for that review.

## Step 4 — Show the diff, get approval

For every string, show **before → after** side by side with a one-line reason ("shorter, matches the app's usual button-label length" / "replaces banned synonym X with the canonical term Y" / "softened register to match status-copy tone"). Never present a rewrite as already-decided. Iterate on feedback before touching any file.

## Step 5 — Apply and verify

1. Once approved, edit the actual source file(s) with the confirmed text.
2. Re-run the extraction + a quick spot-check: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/extract_copy.py"` then confirm the new string appears correctly in `<pipelines.copy>/inventory.json` (categorized as expected, no stray interpolation).
3. If this was working off `/audit-copy` findings, note which findings are now resolved.
4. Commit per `{{doc:pr}}` conventions.

---

## What you must never do

- Apply any copy change to a source file before the user has seen and approved the before/after diff
- Draft copy without `{{doc:brand-voice}}` existing — recommend `/establish-brand-voice` instead of improvising
- Use a banned synonym from the terminology glossary, even if it reads more naturally in isolation
- Present drafted consent/legal/clinical-disclosure copy as ready to ship without flagging it needs a human legal/clinical review
- Lengthen microcopy "for warmth" at the cost of consistency with the existing UI pattern
- Batch-apply multiple rewrites without showing each one — approval is per-string, not blanket
