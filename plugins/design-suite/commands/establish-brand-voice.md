---
name: establish-brand-voice
description: "Establish or update the project's brand voice and terminology glossary — the source of truth copy audits check against. Never rewrites existing copy. Brand-sensitive: surface it as an option, but let the user decide rather than invoking autonomously."
invocation: explicit
maturity: unverified
---

# /establish-brand-voice

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

You are establishing (or updating) the project's brand voice and terminology glossary — the source of truth `/audit-copy` checks everything against. You produce `{{doc:brand-voice}}`. **You never rewrite existing app copy in this skill** — that's a separate, deferred capability.

**Authoritative workflow doc: `{{doc:copy}}`. Read it before starting.**

---

## Step 0 — Preconditions (self-bootstrapping)

1. Read `{{doc:copy}}`.
2. Confirm `python3` is available (it always is on this machine — `${CLAUDE_PLUGIN_ROOT}/bin/extract_copy.py` has zero external dependencies, nothing to install).
3. Confirm you are on a feature branch (never `demo`/`main`) — this skill commits a new doc.
4. Check whether `{{doc:brand-voice}}` already exists. If it does, this is an **update**, not a first establishment — show the user the existing content and ask what's changing before touching anything.

## Step 1 — Ask which mode

Ask the user directly:

- **Reverse-engineer from existing copy** (the default, and the right choice when no brand document exists) — proceed to Step 2.
- **Ingest an existing brand document** (a style guide, brand book, or prior copy deck the user provides) — skip to Step 2b.

If there is a live client/stakeholder to talk to — most first-time onboarding
— use `${CLAUDE_PLUGIN_ROOT}/templates/docs/fragments/BRAND-ONBOARDING-INTERVIEW.md.template`
as a structured question set alongside whichever mode above applies. It does
not replace Step 2's extraction or Step 2b's ingestion; it structures the
conversation that happens before or alongside them, and gives §1's tone
questions and §4's Do/Don't examples a consistent shape to land in before
Step 3 drafts from them. Asking those questions commits nothing — the
brand-sensitive part is still this skill's Step 3 draft and sign-off.

## Step 2 — Gather evidence from real copy

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/extract_copy.py"
```

Then, rather than reading all ~137 files, sample a representative cross-section across feature areas (home, health/care plan, onboarding, questionnaire, shared components, and anything with consent/legal text) — read the actual widget files behind a handful of `content`-category inventory entries per area, not just the extracted string in isolation, so you see real surrounding context.

Also check `{{doc:decisions}}` for any copy/terminology rules already logged (e.g. grep for "copy", "terminology", "tone" — there's a known existing rule that billing/commercial language must stay separated from clinical "Care Plan" language) and `{{doc:design}}` for the stated audience and accessibility bar (reading-level implications, not just type size).

From this, identify:
- The tone(s) actually in use, and where each applies (don't average away a genuine, defensible register split — e.g. plain/reassuring status copy vs. formal/precise consent text is likely intentional, not inconsistent).
- Recurring vocabulary that should be canonicalized (a term used two or three different ways that should collapse to one).
- Sentence/paragraph patterns typical of the app's current content copy (length, formality, use of exclamation points, spelling convention, etc.).

## Step 2b — Ingest an existing brand document (alternate path)

If the user provides a brand document instead: read it in full, then translate its content into the same `{{doc:brand-voice}}` shape (Step 3) rather than inventing structure — the schema is fixed so `/audit-copy` and any future project can rely on it, but the content comes from the provided document, not from reverse-engineering.

## Step 3 — Draft `{{doc:brand-voice}}`, attribute by attribute

Propose a draft with this shape:

```markdown
# Brand Voice — <Project Name>

## Audience & context
[Pulled from {{doc:design}} — who this app is for, any constraints that shape tone]

## Tone attributes
[Adjective + when it applies, e.g. "Plain and reassuring — status updates, empty states,
error messages." / "Formal and precise — consent, legal, and clinical-disclosure text."]

## Reading-level target
[Tied to the existing accessibility bar in {{doc:design}}, not just type size]

## Do's / Don'ts
[Real examples pulled from the app, not invented]

## AI-tell banned phrases
[Concrete list — e.g. "seamless", "elevate", "unlock", "leverage", "delve",
"navigate the complexities of", "whether you're X or Y", "it's important to note",
stacked em-dashes, rule-of-three cliché lists, "Let's dive in", exclamation-point
stacking. Starting list — refine after /audit-copy has run against real findings.]

## Terminology glossary
[Canonical term -> banned synonyms. Seed with any rule already in {{doc:decisions}}.]
```

**Present this attribute by attribute and get explicit confirmation or edits on each — never accept a first draft wholesale, and never present it as already-decided.** This mirrors how `{{doc:design}}` itself was built: grounded in what's actually shipping, not invented, but also not rubber-stamped.

## Step 4 — Write, register, and commit

1. Write the confirmed content to `{{doc:brand-voice}}`.
2. Check `{{doc:instructions}}`'s companion-document table (§1) — if `{{doc:brand-voice}}` and `{{doc:copy}}` aren't both listed there yet, add rows for them now. An unregistered doc is invisible per this repo's own rule.
3. Add a dated entry to `{{doc:decisions}}` under a "Copywriting & Brand Voice" section (create the section if it doesn't exist) recording what was established/changed and why.
4. Commit per `{{doc:pr}}` conventions.

---

## What you must never do

- Invent a tone attribute that isn't grounded in real evidence from the app or explicit user input
- Accept any attribute into the final doc without the user's explicit confirmation
- Overwrite an existing `{{doc:brand-voice}}` without first showing the user what's changing
- Rewrite or edit any actual app copy — that's a different, deferred skill
- Skip registering the doc in `{{doc:instructions}}`
