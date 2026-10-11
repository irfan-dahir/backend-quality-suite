---
name: generate-client-readiness
description: "Derive a client-facing production-readiness summary from the internal checklist and export it to PDF. A derived collateral: regenerate it rather than hand-editing the output."
invocation: explicit
maturity: proven
---

# /generate-client-readiness

> Documents are referenced by role, e.g. `{{doc:production-readiness}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve_role.py" production-readiness`. See the backend-suite plugin's `docs/DOC-ROLES.md` for the role vocabulary and exit-code contract.

You derive a **client-facing** production-readiness summary from **`{{doc:production-readiness}}`** (the internal checklist), then export it to PDF. This is a **derived collateral** per `{{doc:documentation-rules}}` §4: one direction of truth, source-stamped, disposable, regenerate-don't-hand-edit.

**You transform and export. You never author new findings here** — if the internal doc is missing something the client needs to know, fix `{{doc:production-readiness}}` first (that's a real engineering/product judgment call, reviewed like any other doc change), then re-run this skill to regenerate the client version. This skill's job is *reframing*, not *analysis*.

---

## Why this exists, and why it's separate from the internal doc

`{{doc:production-readiness}}` is written for the delivery team — file-and-line references, git commit hashes, internal tool names (`/quality-debt`, `bin/audit_api_consistency.py`), CI workflow filenames, and a running edit history in its footer. None of that belongs in front of the client, and none of it is actionable to them. What the client actually needs is: what's the overall picture, what do *they* need to decide or provide, and what's a normal part of any software project versus something specific to this one.

Producing that by hand each time invites drift — the two documents disagree the moment someone updates one and forgets the other. Deriving it mechanically from the internal doc, the same way `/generate-walkthrough` derives from `{{dir:derived}}/demo-flow-catalog.md` or `/audit-mock-api` derives its report from `contracts.json`, keeps them honest.

---

## Step 1 — Read the source fresh

Read `{{doc:production-readiness}}` in full, every time — never work from memory of a prior run. Note its current commit (`git log -1 --format=%H -- {{doc:production-readiness}}`) for the source stamp.

## Step 2 — Transform, section by section

Apply these rules uniformly. When a rule and the source content conflict, prefer omission over guessing at client-safe wording — ask rather than invent.

**Strip entirely — internal-only, no client value:**
- File/line references (`[app/Repositories/AuthRepository.php:22]`), git commit hashes, branch names
- Named internal tools/skills/scripts (`/quality-debt`, `bin/audit_api_consistency.py`, workflow filenames)
- The document's own edit-history footer and §22 Sources
- The "How to read this" severity-marker legend's internal framing — replace with a simpler client-facing key (see Step 3)

**Compress heavily — standard practice, not specific to this project:**
Anything that's true of *any* production software project, not particular to this project, gets reduced to a one-line "in place" / "planned" / "needs your input" rather than explained. Examples: CI/CD existing, test coverage practice, dependency scanning, standard security hygiene, standard release engineering. The client doesn't need a tutorial on why crash reporting matters — they need to know whether it exists yet.

**Reframe, don't strip — anything that names a client decision, dependency, or blocker:**
This is the majority of the document's actual value to them. Keep the substance, translate the register:
- `{{doc:production-readiness}}` §16 (what the client needs to provide) → becomes the spine of the client doc, not a buried section
- §17 (SRS deviations needing sign-off) → reframe as "confirm these decisions," not "deviations requiring written sign-off"
- Each gate's 🔴/🟠 items that name a **client-side dependency** (a vendor to select, a policy to write, a determination only their counsel can make) → keep, in plain language, without the internal severity-marker jargon
- Gate-internal engineering detail that's *our* problem to solve, not theirs → compress to one line: what it is, current status, nothing more

**Tone:** direct, plain, no hedging softened into vagueness. "Not started" stays "not started" — don't euphemize a real gap to be polite. But drop the internal document's occasional wry/editorial asides (e.g. "an all-red checklist misrepresents the project") — those read as internal commentary, not something written for a client relationship.

## Step 3 — Structure the output

```markdown
> Derived from `{{doc:production-readiness}}` @ <short-hash> on <date> — regenerate, don't hand-edit.

# <Client> — Production Readiness Summary

[One-paragraph plain-language headline: what exists today, what it isn't yet.]

## What "production ready" means for this launch
[The launch-tier framing from the internal doc §1, reframed as a client question:
which of the three tiers do they mean, since it changes almost everything else.]

## Current state, in brief
[A compact table or short list: area → status → one line. Maps to the internal
gates but collapsed — group related gates rather than presenting 13 separately.]

## Decisions we need from you
[The internal doc's §16a + §17, merged and reframed as direct questions with
what each one blocks, in plain terms — no gate numbers, no file paths.]

## Things you'll need to arrange
[§16b–d: vendor accounts, legal/compliance content, operational readiness —
framed as a checklist with rough lead-time notes where the internal doc has them.]

## What's already solid
[§21, kept — this is reassurance the client should hear, and it's already
client-safe in the internal doc's own wording, mostly unchanged.]

## Suggested next steps
[A short, non-technical version of §18's sequencing — three or four bullets,
not the internal doc's full critical-path table.]
```

Keep the whole thing well under half the internal doc's length. If a client reader needs the engineering detail behind any line, that's what the internal doc and a live conversation are for — this artifact's job is the executive/decision layer, not the full record.

## Step 4 — Write the MD as a derived collateral

Write to **``$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve_role.py" --dir derived)`/production-readiness-client.md`**, following `{{doc:documentation-rules}}` §4's rules for this directory: the source stamp above is mandatory, and the file must never carry information that isn't traceable back to `{{doc:production-readiness}}`. If in drafting you find yourself wanting to add a fact the internal doc doesn't have, stop — that fact belongs in the internal doc first.

## Step 5 — Export to PDF

### Step 5a — Preflight: verify dependencies before exporting

**Don't assume pandoc/typst/poppler are installed — this skill runs on any designer's machine, not just the one it was built on.** Run this check first, every time, before the export command:

```bash
missing=()
command -v pandoc  >/dev/null 2>&1 || missing+=(pandoc)
command -v typst   >/dev/null 2>&1 || missing+=(typst)
command -v pdftoppm >/dev/null 2>&1 || missing+=(poppler)   # pdftoppm ships in the poppler formula

if [ ${#missing[@]} -eq 0 ]; then
  echo "All PDF export dependencies present."
else
  echo "Missing: ${missing[*]}"
  if command -v brew >/dev/null 2>&1; then
    echo "Installing via Homebrew: ${missing[*]}"
    brew install "${missing[@]}"
  else
    echo "Homebrew not found. Install it first from https://brew.sh, then re-run this check."
    echo "(Installing Homebrew itself needs an interactive shell and, on first run, an admin"
    echo " password — that's the designer's own machine setup, not something to script around.)"
  fi
fi
```

This is a **regular, reversible, non-destructive install** (`brew uninstall <formula>` undoes it cleanly) — proceed with `brew install` for whichever formulas are missing without needing to ask first, but always state plainly what's being installed and why (`pandoc` converts the markdown, `typst` is the PDF engine, `poppler` gives `pdftoppm` for the mandatory visual-verification step below). The one thing this skill cannot do on the designer's behalf is install Homebrew itself, since that needs an interactive terminal and admin credentials on their machine — if `brew` itself is missing, stop and point them to https://brew.sh rather than trying to script it.

**Font check — macOS-specific, silent-failure risk:** the style include (`client-readiness-style.typ`) sets `mainfont="Helvetica Neue"` and uses `Avenir Next` for headings, both macOS system fonts. Typst does not error when a font is missing — it silently substitutes its own default, so a designer on Linux, Windows, or a stripped-down macOS install (or CI) could get a working PDF that quietly doesn't match the intended look. Check before exporting:

```bash
typst fonts | grep -qi "Helvetica Neue" && echo "Helvetica Neue: found" || echo "Helvetica Neue: MISSING — output will silently fall back to typst's default font"
typst fonts | grep -qi "Avenir Next"    && echo "Avenir Next: found"    || echo "Avenir Next: MISSING — output will silently fall back to typst's default font"
```

If either is missing, say so before exporting rather than after — the render-and-inspect step in Step 5c will still catch a wrong font visually, but flagging it up front saves a wasted export/inspect cycle. This is informational only; there's no reasonable auto-install for a proprietary Apple system font on a non-Apple machine — if it's missing, the honest options are: export anyway with typst's fallback (acceptable, just not pixel-identical to the reference renders in this skill's own gotcha notes), or run the export on a Mac that has these fonts.

### Step 5b — Run the export

```bash
# Export (run from repo root) — filename follows the naming standard below
pandoc "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve_role.py" --dir derived)"/production-readiness-client.md \
  -o /tmp/<Org>-<Client>-Production-Readiness-Summary-<YYYY-MM-DD>.pdf \
  --pdf-engine=typst \
  --include-in-header=.claude/commands/letterhead.typ \
  --include-in-header=.claude/commands/client-readiness-style.typ \
  -V mainfont="Helvetica Neue"
```

### Client-facing PDF file naming — project-wide standard

**`<Org>-<Client>-<Document Title>-<YYYY-MM-DD>[-vN].pdf`** — every client-facing PDF exported from this repo (not just this skill) uses this filename, not a generic name like `report.pdf` or `production-readiness-client.pdf`.

- **`<Org>`** — your organisation's name, a fixed prefix. A client's downloads folder or inbox holds files from many vendors; leading with the firm name makes the source unambiguous at a glance, before the file is even opened.
- **`<Client>`** — the client/project name, title-cased, no spaces (`AcmeHealth`, not `Acme Health` or `acmehealth`).
- **`<Document Title>`** — human-readable, title-cased, matching the document's own displayed title as closely as filename characters allow (`Production-Readiness-Summary` for a doc titled "AcmeHealth — Production Readiness Summary"). Never an internal/jargon name (`prod-readiness-v2-final`, `client-doc-latest`) — the client sees this filename.
- **`<YYYY-MM-DD>`** — export date, ISO order, so alphabetical sort is also chronological sort. Compute it fresh at export time; don't reuse a stale date from a prior run.
- **`[-vN]`** — omit for the first export of a given day. Add `-v2`, `-v3`, … only if the same document is re-exported the same calendar day (e.g. a same-day correction after client feedback) — this keeps a visible trail rather than silently overwriting a file the client may already have open or forwarded.
- **Hyphens throughout, no spaces, no underscores.** Spaces break cleanly in some email clients and terminal copy-paste; hyphens are the safe universal choice across OS, email, and Slack.

This applies to the delivered PDF filename only — it has no bearing on the derived markdown's path, which stays governed by `{{doc:documentation-rules}}` §4's derived-collateral conventions (`{{dir:derived}}/<name>.md`).

**`.claude/commands/letterhead.typ` is a project-wide standard, not specific to this skill.** It puts every client-facing export on your org's letterhead (logo or org-name header, office-list/URL/page-number footer, an accent rule) — fill in its `org*` values once per org. **Any future pandoc+typst export meant for a client should pass this file as an `--include-in-header`, composed alongside that document's own content-styling include** (order shown above: letterhead first, then content styling — the letterhead only touches page header/footer, so order between the two doesn't functionally matter, but keeping it consistent avoids confusion). Don't copy the logo asset or redraw the footer text per skill — reuse this one file and the single logo it points at (`orgLogoPath`).

Don't pass `--metadata title=...` — the markdown's own top-level `#` heading already is the title; adding the metadata flag renders it twice (confirmed by testing).

`typst` was chosen over `wkhtmltopdf` (Homebrew cask no longer exists) and over a full LaTeX distribution (multi-GB, unnecessary for this document's needs). Confirmed working end-to-end on the real document — headings, lists, tables, bold, blockquotes, and the code-styled source stamp all render correctly.

**`.claude/commands/client-readiness-style.typ`** is a small typst include that gives the PDF real visual hierarchy — distinct size/weight/color per heading level (Avenir Next, an accent-colored rule under H1s), a clean sans body face (Helvetica Neue), an accent-colored bullet marker, and bolded/colored table header rows — closer to how the source markdown's own hierarchy reads than pandoc's default typst template, which renders every heading level in the same weight. Both fonts are macOS system fonts; if exporting on a machine without them, typst falls back to its default font silently rather than erroring — check the output if the fonts look wrong.

**Two real gotchas found while producing the first real export, both fixed by editing the markdown, not the pipeline:**

1. **A markdown table that spans a page break renders corrupted** — rows overlap and text is lost right at the break. Tables that fit entirely within one page render perfectly. If a table in the draft has more than ~6–8 rows with substantial cell text, convert it to a bulleted list (`- **Label** — description`) instead — lists break across pages cleanly. Keep short tables (like the numbered decisions list, which fit on one page) as tables; they read better with the `#`/`Why it matters` columns.
2. **A bold intro line immediately followed by a list, with no blank line between them, renders as literal hyphens run into the paragraph** instead of an actual bullet list. Always leave a blank line between an intro sentence and the list that follows it.
3. **Typst's `#table()` defaults to center-aligned cell text**, not left, whenever the source markdown table has no explicit `:---` column-alignment markers (which pandoc translates to `align: auto` — and `auto` resolves to *center* in typst, not left, despite what that name suggests). Every table in this doc's markdown is plain `|---|---|`, so without an explicit override every cell renders centered — reads as unstructured/unprofessional in a business document. `client-readiness-style.typ` forces this with `#show table.cell: set align(left)`; if a future draft of the style file drops that rule, tables silently go back to centered. Always visually confirm table cells are left-flush, not just that the table itself is present.
4. **A leading `#`-style index column renders the same width as the content columns next to it** — pandoc has no way to express per-column width from plain markdown pipe-table syntax, so it always emits an equal-percentage `columns: (33.33%, ...)` regardless of how short or long each column's content actually is. A one-or-two-digit index column ends up as wide as a paragraph-length column beside it, which looks broken. Fix at the source: for any table with a numeric `#`/index-style first column, replace the markdown table with a raw typst passthrough block (a `` ```{=typst} `` fenced code block containing a literal `#table(columns: (narrow%, wide%, ...), table.header(...), ...)` call) specifying explicit column widths — e.g. `(6%, 47%, 47%)` for a 3-column table with a short index column. The global `#show table.cell` rules in `client-readiness-style.typ` still apply to these raw tables (they target the element, not how the table was constructed), so styling stays consistent — only the `columns` widths need to be hand-specified. Don't bother with this fix for tables that have no unusually short column; the equal-width default is fine when all columns hold comparable amounts of text.

### Step 5c — Render and visually verify every page

After drafting, **always render the PDF and visually inspect every page** (e.g. `pdftoppm -png -r 90 <file>.pdf <prefix>` then view each `<prefix>-N.png`) before treating the export as done — both bugs above look fine in the source markdown and only show up in the rendered output. If the font check in Step 5a flagged a missing font, this is also where a silent fallback would show up visually — check the headings/body text actually look like the intended sans-serif hierarchy, not typst's generic default.

**The PDF is a binary artifact and must never be committed to the repo**, per `{{doc:documentation-rules}}` §4's rule that binary collaterals stay out of git. Deliver it to the user directly (e.g. via a file-send mechanism) or leave it in scratch space — it regenerates from the MD in seconds, so there's nothing lost by not keeping it around.

## Step 6 — Hand off

Tell the user: which internal-doc commit this was derived from, where the MD landed, and that the PDF was generated and delivered (not committed). If this is a re-run because the internal doc changed, say what changed in the summary at a high level — don't make them diff it themselves.

---

## What you must never do

- Add a finding, fact, or claim to the client doc that doesn't trace back to `{{doc:production-readiness}}` — if something's missing, fix the source doc first
- Commit the exported PDF to the repository
- Leave the client doc without its source stamp, or let it silently drift out of sync — if the internal doc's last-commit date is newer than the stamp, treat the client doc as stale and regenerate
- Soften a genuine "not started" into vague reassurance — directness with the client is the point of this document, not a reason to avoid it
- Carry over internal tool names, file paths, or commit hashes into the client-facing text
