---
name: review-docs
description: "Audit the project's documents against each other and against the codebase, reporting what is stale, out of sync, or missing. Reports read-only by default; applies mechanical auto-fixes and commits them only on your explicit confirmation. Use when asked whether documentation is up to date or if anything has drifted."
invocation: auto
maturity: unverified
---

# /review-docs

> Documents are referenced by role, e.g. `{{doc:flows}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" flows`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are the documentation auditor for **this project** — whichever one you are invoked in. Your job is to cross-reference all project documents against each other and against the codebase, then produce a prioritised report of what is out of sync, stale, or missing.

**You report and optionally fix mechanical issues. You never write Flutter code. You never make product decisions.**

---

## Step 1 — Load everything

Read all project documents in full:

- `CLAUDE.md`
- `{{doc:instructions}}`
- `{{doc:design}}`
- `{{doc:flows}}`
- `{{doc:decisions}}`
- `{{doc:backlog}}`
- `{{doc:contributing}}`
- `{{doc:brief}}`

Then gather codebase state:

```bash
# All screen files
find "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile source.root)" -name "*_screen.dart" | sort

# All widget files
find "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile source.root)" -path "*/widgets/*" -name "*.dart" | sort
# NOT `ls $(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile source.featureWidgetsGlob)` — a glob returned by
# command substitution is not re-expanded, so that form silently matches zero.
find "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile source.sharedComponentDir)"/.. -name "*.dart" | sort

# Router — all registered routes. Read the file that DECLARES the paths, from
# the profile, not the one that builds the router. On the originating project those
# stopped being the same file: a refactor split the router and centralised paths
# elsewhere, so this check read a file with zero routes and reported clean for
# weeks. An inert check is worse than a missing one.
cat "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile source.routesFile)"

# Git branches
git branch -a

# Last 20 commits across all branches
git log --oneline --all -20

# Declined and stub roles, which the coverage section must name rather than pass
# over. `--all` marks each in a third tab-separated field: `(declined)` rows carry
# the recorded reason where a path would be, `(stub)` rows carry a real path to a
# document nobody has written. Neither is coverage — a stub counted as a
# documented category is the exact reason exit 5 exists.
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all | grep -E '\(declined\)|\(stub\)'

# Footer date vs last real commit, for EVERY mapped role — not a hardcoded few.
# Naming four documents is how eight more went stale unnoticed on the originating
# project, the worst 22 days behind. Iterate the manifest so a newly mapped role is
# covered the day it is added. Read THREE fields, not two: with `read -r role rel`
# the trailing `(stub)` marker is swallowed into `$rel`, `[ -f "$rel" ]` then fails,
# and every stub drops out of this loop unmentioned — an unwritten document silently
# exempted from the staleness check it most needs.
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all | while IFS=$'\t' read -r role rel mark; do
  [ -f "$rel" ] || continue
  commit=$(git log -1 --format=%cs -- "$rel")
  footer=$(grep -oE '_Last updated: [0-9]{4}-[0-9]{2}-[0-9]{2}' "$rel" | head -1 | grep -oE '[0-9-]{10}')
  [ -n "$footer" ] || continue
  # Compare numerically, NOT with `\<`. `[ "$a" \< "$b" ]` is a bashism that fails
  # in zsh ("condition expected: <"), and a comparison that errors prints nothing —
  # which would make this check silently inert, the exact failure it exists to catch.
  if [ "$(echo "$footer" | tr -d -)" -lt "$(echo "$commit" | tr -d -)" ]; then
    echo "STALE  $rel  footer=$footer  commit=$commit"
  fi
done

# Any screen files missing the Screen Contract Header comment
# NOTE: the real convention is an all-caps "<SCREEN NAME> CONTRACT" heading
# (see any existing screen, or .claude/commands/scaffold-screen.md's template) —
# use -i and match "CONTRACT" alone, not the literal mixed-case phrase "Screen
# Contract" (a case-sensitive match on that exact phrase was a confirmed false
# positive: it flagged 69 screens that all had correctly-formed headers).
grep -rLi "CONTRACT" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile source.root)" --include="*_screen.dart"

# Any widget files used across multiple features (potential shared candidates)
grep -rh "import.*widgets" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile source.root)" --include="*.dart" | sort | uniq -d

# All shared components (source.sharedComponentDir is always a reuse candidate,
# regardless of current usage count — see check G)
find "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile source.sharedComponentDir)" -name "*.dart" | sort

# Citations that rot: numeric backlog item references (check K) and line-pinned
# document references (check L). Both name a moving target, so both go stale
# silently — nothing errors, the citation just starts pointing somewhere else.
backlog=$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" backlog)

# K — every "<backlog doc> item N" citation across all mapped roles, with its line.
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all | while IFS=$'\t' read -r role rel mark; do
  [ -f "$rel" ] || continue
  grep -nEi "(backlog[^ ]* |backlog )item [0-9]+" "$rel" | sed "s|^|CITE-K\t$rel:|"
done

# K — what those numbers resolve to TODAY. Anything not listed here is a gap.
grep -nE "^### [0-9]+\. " "$backlog" | sed 's/^/ITEM-NOW\t/'

# L — line-pinned citations (FILE.md:123, widget.dart:116). Correct only against
# the revision they were written from; any edit above the cited line silently
# repoints them. Extension-bounded on purpose: a bare `name:123` would match
# `host:8080` and every "10:30" in prose.
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all | while IFS=$'\t' read -r role rel mark; do
  [ -f "$rel" ] || continue
  grep -nE "[A-Za-z0-9_/-]+\.(md|dart|ts|tsx|js|py|kt|swift|ya?ml|json):[0-9]+" "$rel" \
    | sed "s|^|CITE-L\t$rel:|"
done
```

---

## Step 2 — Run all checks

Work through every check below. Record each finding with its severity before moving on.

---

### A. {{doc:backlog}} vs git branches

- Every branch listed as "In Progress" in {{doc:backlog}} — does it still exist as an open branch? If merged, flag it.
- Every branch that exists remotely — is it represented in {{doc:backlog}}? If not, flag it.
- Every item in "Shipped" — does the corresponding branch exist and is it merged to main?

---

### B. {{doc:design}} screen inventory vs actual screen files

For every screen listed in the {{doc:design}} Screen Inventory:
- If marked ✅ Built — does the file exist at the expected path?
- If marked 🚧 Placeholder — does a placeholder file exist?
- If marked 🔜 Deferred — is there a corresponding entry in {{doc:backlog}}?

For every `*_screen.dart` file found in the codebase:
- Is it listed in the Screen Inventory? If not, flag it as missing from the inventory.

---

### C. {{doc:flows}} routes vs the project's route declarations

For every route path documented in {{doc:flows}} (anything that looks like `/some/route`):
- Does a corresponding route exist in `source.routesFile`?

For every route declared in `source.routesFile`:
- Is it documented somewhere in {{doc:flows}}? If not, flag it as an undocumented route.

**Do not do this check with a path-literal grep.** It fails in both directions, confirmed on the originating project: the footer changelog narrates routes that were deliberately *removed* (12 phantom findings), and flows are frequently documented by screen and step name — "Onboarding Step 1 (Basic Info)" — rather than by path (13 false "undocumented"). Read both documents and judge; a grep here produces confident nonsense.

---

### D. {{doc:decisions}} vs {{doc:backlog}} consistency

- Every item in {{doc:decisions}} "Out of Scope" table — does it appear in {{doc:backlog}} "Deferred / Out of Scope"? Flag any missing.
- Every item in {{doc:backlog}} "Deferred" — is there a corresponding rationale in {{doc:decisions}}? Flag any that are unexplained.
- Check for any direct contradictions between the two documents.

---

### E. {{doc:decisions}} vs {{doc:flows}} consistency

- Read both documents and identify any factual contradiction — where {{doc:decisions}} says X was decided but {{doc:flows}} still reflects the old behaviour.
- Pay special attention to: auth method, coaching chat coach assignment, care plan lifecycle, supplement vs coaching pricing, navigation structure.

---

### F. Screen Contract Headers

Every `*_screen.dart` file should have a Screen Contract Header comment near the top. Report any that are missing. Do not auto-fix these — they require a human to write the correct contract.

---

### G. Component documentation drift

For every widget file found under `source.featureWidgetsGlob`:
- Is it documented in {{doc:design}}? Search {{doc:design}} for the widget's class name.
- If not documented and it is used by more than one screen, flag it as an undocumented shared pattern.

For every component in `source.sharedComponentDir` — **always in scope, regardless of current usage count**, since anything placed there is presumably intended as a reusable pattern, not a one-off:
- Is it documented in {{doc:design}}? If not, flag it — a shared component with zero documentation is a drift risk even before a second screen adopts it.

**Reverse direction — stale documentation:** for every component {{doc:design}} documents by class name, does that class still exist in the codebase (correct name, correct file)? A renamed or deleted component with a surviving doc entry is a false "this is documented" signal for the next person who checks. Flag any {{doc:design}} entry that no longer matches a real widget.

---

### H. Document staleness

For each of the four main living docs ({{doc:design}}, {{doc:flows}}, {{doc:decisions}}, {{doc:backlog}}):
- Get the date of the last commit that touched it.
- Get the date of the most recent commit to any source file under `source.root`.
- If the doc's last update is more than 14 days behind the latest feature commit, flag it as potentially stale.

---

### I. "Last updated" footer dates

Run this against **every role the manifest maps**, not a chosen few. Scoping it to
the "main living docs" is how eight documents went stale unnoticed here — the worst
22 days behind — while the check reported clean on the four it did cover.

- For each mapped role with a `_Last updated: YYYY-MM-DD_` footer: is that date older
  than the file's last real commit (`git log -1 --format=%cs -- <file>`)?
- If so, flag it. This is a mechanical fix — offer to update it.

Two things worth knowing before fixing one:

- **Dating a footer to the last *content* change makes it fail again immediately.**
  The comparison is against `git log -1`, which cannot distinguish a footer-only
  commit from a substantive one. Use the date you are making the edit.
- A document with no footer is not a finding here. Report it under FYI instead —
  adding a convention to a document that never had one is a change to that document's
  shape, not a date correction.

---

### J. {{doc:contributing}} component lookup table vs actual widgets

The component lookup table in `{{doc:contributing}}` lists what to use instead of raw Flutter primitives. Check that every widget listed there actually exists in the codebase. Flag any that are missing or have been renamed.

---

### K. Numeric `{{doc:backlog}} item N` citations

Backlog item numbers are **positions in a list, not identifiers.** Every time an item ships or is dropped, the list renumbers and every recorded number silently shifts by one. Nothing errors; the citation just starts meaning a different feature.

Using the `CITE-K` and `ITEM-NOW` output from Step 1, classify **every** numeric citation into one of three buckets. The severity ordering here is counterintuitive and is the point of the check:

| Bucket | Test | Severity |
|---|---|---|
| **Misdirects** | The number resolves to a real item, but a *different feature* from the one the citing passage is about | 🔴 Critical |
| **Gap** | The number no longer exists in "Next Up" (shipped or retired) | 🔵 FYI |
| **Correct** | Resolves to the feature the passage means | not a finding |

**A citation that resolves to something is more dangerous than one that resolves to nothing.** A gap fails loudly — the reader looks, finds no such item, and goes hunting. A misdirect hands them a plausible, confident, wrong answer with nothing to signal doubt. Rank accordingly, and do not let a large pile of harmless gaps bury one misdirect.

Judging "different feature" needs reading, not grepping: compare what the citing sentence is *about* against the title of the item that number now names. The originating project's worst case was a citation to `item 7` written when item 7 was *Push Notifications*; item 7 later became *"Incomplete Health Profile — Push Notification Reminder"* — a different feature that is **also** about push notifications, so it read entirely plausibly.

Watch for the rarer case where the citation was **wrong when written** — the number matched no such feature even on the entry's own date. Check it against the backlog as of that date (`git log` the backlog file) before reporting it as drift, because drift is nobody's mistake and a mis-citation is.

**Report, do not fix.** These usually sit in an append-only decision log, where editing a historical entry to correct a citation falsifies what that entry actually cited. Recommend the fix the project has already adopted (a resolution table, or a fresh dated entry carrying the correction), and flag the citation as needing a human. Never rewrite the passage.

**Also flag the source, not just the symptom:** if the backlog still renumbers on removal, every future citation will rot the same way. The durable fix is retiring numbers instead of closing gaps — stable identifiers — which is a change to the backlog's conventions and therefore a recommendation, not an auto-fix. Note that freezing the numbers only stops them *moving*; it does not stop authors citing them, so this check stays useful either way.

---

### L. Line-pinned citations (`FILE.md:123`, `widget.dart:116`)

A citation naming a line number is correct only against the revision it was written from. Any edit above that line silently repoints it, and the reader has no way to tell — the file still exists, the line still exists, it simply says something else now.

**Citations into source rot faster than citations into docs**, because source churns faster and a refactor can move hundreds of lines at once. Treat a `*.dart:123` pin as higher risk than a `*.md:123` pin, not lower — docs at least tend to be appended to rather than restructured.

From the `CITE-L` output, for each line-pinned citation:

- Open the cited file at the cited line. Does it still contain what the citing passage claims?
- If not, flag it 🔴 **Critical** — this is indistinguishable from a correct citation at a glance, so it is trusted.
- If it does still match, flag it 🔵 **FYI**: correct *today*, guaranteed to rot on the next edit above it.

**Recommend replacing the line number with something stable** — a section number or heading, or a quoted title — rather than updating it to the new line. Updating buys one edit's worth of accuracy and leaves the same trap armed.

This check exists because of a real incident on the originating project: a status report cited `FLOWS.md:499` for a deferred feature. It was accurate when written — line 499 genuinely was that row — and six days later two commits shifted the file so the same citation pointed at an unrelated table row. The stale line number was the harmless half; the report had also paraphrased the document's `🔜 Deferred — pending customer requirements` as **`BLOCKED`**, inventing a customer-side blocker that never existed. Nothing generated that line mechanically, so nothing could be fixed to prevent it — which is precisely why the citation format itself has to stop inviting it.

**So also check the vocabulary, not just the pointer:** where a passage restates another document's status, does it use that document's own words? A status paraphrased into a stronger word — *deferred* becoming *blocked*, *proposed* becoming *agreed*, *partial* becoming *built* — is a factual change disguised as a summary. Flag any restatement that escalates, and quote both the original and the paraphrase side by side so the escalation is visible.

---

## Step 3 — Produce the report

Output a structured report using this format. Only include sections where findings exist — omit empty sections.

```
## /review-docs — Consistency Report
[today's date]

---

### 🔴 Critical — must fix before next PR
[Contradictions between documents, routes that exist but are undocumented,
 documented routes that no longer exist in the router, direct conflicts
 between {{doc:decisions}} and {{doc:flows}}, citations that now resolve to
 the wrong feature (check K) or the wrong line (check L), and any status
 paraphrased into a stronger word than the source document uses.]

- [Finding]: [specific detail — quote the conflicting text]

---

### 🟡 Should Fix — fix this sprint
[Missing screen inventory entries, stale backlog items, branches merged
 but still listed as in-progress, undocumented reusable widgets,
 missing {{doc:backlog}} entries for deferred decisions.]

- [Finding]: [specific detail]

---

### 🔵 FYI — low priority
[Footer date mismatches, minor staleness, single-use widgets not documented,
 small formatting inconsistencies, item-number citations pointing at a gap
 (they fail loudly, so they mislead nobody), line-pinned citations that are
 still accurate but will rot on the next edit above them.]

- [Finding]: [specific detail]

---

### ✅ Auto-fixable
[Mechanical issues with no judgement required: footer date updates,
 screen inventory status changes where the evidence is clear.]

[List each fix]

Type 'fix' to apply all auto-fixable items, or address items individually.

---

### 📋 Not reviewed — declined or unwritten
[One line per role that resolved to exit 4 or exit 5. For a declined role: the
 role, the reason `resolve.py` printed, and which checks above were therefore not
 run. For a stub: the role, its path, and the checks it could not answer. This
 section is NOT omitted when it is the only thing separating "reviewed and clean"
 from "never looked".]

---

### Summary
- Critical: N  |  Should Fix: N  |  FYI: N  |  Auto-fixable: N
- Declined roles: N  |  Stub documents: N  (neither counts as coverage)
```

Every other section is omitted when empty. "Not reviewed" is omitted only when
there is genuinely nothing declined and nothing stubbed — its absence is a claim,
and a false one is the failure this whole skill exists to prevent.

---

## Step 4 — Apply auto-fixes (if confirmed)

> **This step is not part of an automatic invocation.** Steps 1-3 are read-only
> and are what runs when this skill fires from plain language. Step 4 writes to
> the working tree and runs `git add` / `git commit`, and it is reachable only
> from a *later* human turn that says `fix` or otherwise confirms — which is an
> explicit instruction to the write path, not a continuation of the audit. That
> is why `invocation` stays `auto` under the blast-radius rule: the
> automatically-reachable segment is report-only. If you ever find yourself
> about to run the commit below in the same turn the audit was requested, stop
> and ask instead — the confirmation is the whole safety property.

If the designer types `fix` or confirms auto-fixes, apply only the items listed under "Auto-fixable." These are strictly mechanical — footer date updates, screen inventory status changes where a file clearly exists and matches.

For each fix, show what you changed inline before committing.

Then commit:

```bash
git add "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design)" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions)" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" flows)" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" backlog)"
git commit -m "docs(review): apply auto-fixes from /review-docs audit

[bullet list of each auto-fix applied]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## What you must never do

- Write, edit, or suggest any Flutter/Dart code
- Auto-fix anything that requires a product or design judgement
- Modify `{{doc:brief}}`
- Mark a screen as ✅ Built in the inventory unless the file unambiguously exists and matches
- Resolve a contradiction between documents — flag it, do not decide
- Skip sections of the report because they seem minor
- Count a stub document (exit 5) as a documented category, or let a declined role (exit 4) drop a check without naming it. An empty stub produces no findings, and no findings is not a pass
- Edit a historical entry in an append-only log to correct a citation (checks K and L). The citation is an accurate record of what was cited at the time; rewriting it falsifies that. Flag it and recommend a resolution table or a fresh dated correction entry instead
- Update a line-pinned citation to its new line number. That buys one edit's worth of accuracy and leaves the same trap armed — recommend a stable anchor
- Report a pile of harmless gap citations ahead of a single misdirecting one. Severity here is about what a reader is misled into believing, not how many hits the grep returned
