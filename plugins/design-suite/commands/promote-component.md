---
name: promote-component
description: "Move a component from an application into the shared design system, or demote one back. Use when asked to promote, extract, or push a component into the design system."
argument-hint: "<component name>"
invocation: explicit
maturity: unverified
---

# /promote-component

> Documents are referenced by role, e.g. `{{doc:promoting-components}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" promoting-components`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You move a component from this app into the shared design system — the package
named by `tokens.source.package`, resolved with
`python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile tokens.source` — or —
more often than people expect — you find that it is already there and the app
just never adopted it.

**You never skip Step 0.** The most common correct outcome of this skill is
"delete the private copy and import the real one", and it costs one command to
find out.

Full reasoning lives in `{{doc:promoting-components}}`; the design-system side is
governed by that repository's own `{{doc:contributing}}`, whose gates you must
follow rather than reinvent. `{{doc:contributing}}` resolves to exit 3 —
**external** — when the design system is another repository; the printed URL is
where those gates live, and exit 3 also means you may read it and must never
edit it from here.

Per `{{doc:instructions}}`'s "Autonomous vs. explicit skill invocation": treat
plain-language intent as an invocation. *"This should be in the design system"*,
*"can other screens use this?"*, *"is there already a component for this?"* all
mean this skill.

---

## Step 0 — Is it already solved?

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_reinvented_components.py"
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_promotion_candidates.py"
```

Read both. They ask different questions — name versus shape — and the second
one reports *"possibly already covered by: X (67%)"*.

**Treat that percentage as a lead, not an answer.** It is parameter-name
overlap, not meaning. A private `_InfoRow(icon, label)` scores higher against a
shared `StatCell(icon, value, label)` than against the shared `InfoRow(icon,
text, color)` that it actually is. Open the suggested component and read it
before telling the user it matches.

(Component names here are shape illustrations, deliberately unprefixed. Your
design system's export prefix is `reinventedComponents.exportPrefix` in the audit
config — the audit already reads it from there, and so should you.)

If it already exists → go to Step 4. Say so plainly; do not build a duplicate
because building is more satisfying than searching.

## Step 1 — Should it move?

The test is **"would a different client want this?"** Present your reading to
the user with the reason, and let them decide if it is genuinely ambiguous.

Stays in the app: anything taking a **domain entity** — a type that names
something only this product has, the sort of thing the project's own
`{{doc:design}}` calls an entity or a model — and any product surface that
happens to draw. Moves: layout, state, interaction, typography, and anything
built twice.

If it stays, run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_promotion_candidates.py" --update-baseline`
so the decision is recorded rather than re-litigated every push.

## Step 2 — Generalise it in the move

A component that moves unchanged usually should not have moved. Check every one
of these and report which applied:

- Product nouns in the API — a boolean named after one product role becomes a
  neutral enum (`isFromCoach` → an author enum with `own`/`other`)
- A theme object passed in as a parameter — e.g. a Flutter `ThemeData` — delete
  it and read the theme from context
- A plain string where a child widget/slot would be more useful
- Colour literals (they become a token role; a new role needs an entry in the
  design system's contrast-pair config or it is scored zero times while the
  matrix still says PASS)
- A screen-metrics query where layout constraints are meant — e.g. Flutter's
  `MediaQuery...size` in place of a `LayoutBuilder`
- A fixed horizontal layout that will overflow at 2.0x text scale
- User-visible strings not going through the design system's strings accessor

## Step 3 — Land it in the design system

Work in the design-system repo on a feature branch. Follow its
`{{doc:contributing}}` gates: component, unit test, a `{{doc:gallery}}` use case,
that repository's stress-test harness, and a `{{doc:components}}` entry. Then its
full local suite — the toolchain's static analysis, both test suites, any
generator's `--check` mode, and every audit script it ships.

Read those commands out of its `{{doc:contributing}}` rather than out of this
file. A command named here is one repository's toolchain hardcoded into a plugin
installed on several, and it goes stale where nobody is looking.

**Test the contract, not the appearance.** A golden answers "does this look the
same", never "is this value correct". And when the point is that the new
component fixes something, assert that the old shape was broken too — otherwise
the test only proves that `Wrap` is `Wrap`.

Do not merge or push without the user's go-ahead; `{{doc:pr}}` governs.

## Step 4 — Adopt it here

**Do not stop at Step 3.** Extraction and adoption are two jobs and only the
first one feels finished.

The project this was measured on had **four** components built in the design
system while it kept every private copy. Those four are adopted now, but the
pattern was not a one-off: when `audit_reinvented_components` learned to match
the design system's export prefix (`reinventedComponents.exportPrefix`), it found
**16 more** private widgets shadowing an exported component. Zero of them had
been reported, because the check compared `_BulletList` against `BulletList`
rather than against the *prefixed* export name, and a single-file duplicate is
invisible to `audit_promotion_candidates` too.

Assume adoption has not happened until the audit says so.

Bump the design-system package refs in the project's manifest — the packages named by `tokens.source.package` and whatever brand package re-exports it — delete the
private widget, import the real one, then run this project's own static analysis
and test commands — read them from `{{doc:contributing}}`, not from here.

Then re-run the audit. **The candidate should be gone, not baselined** — a
baseline entry here would record "we decided to keep the duplicate", which is
the opposite of what happened.

## Step 5 — Report

State plainly: what moved, what stayed and why, what the app now imports, and
which audits pass. If you stopped at Step 0 because the component already
existed, say that — it is the best outcome, not a lesser one.

---

## What you must never do

- Build a new design-system component without running Step 0 first
- Assert that a component "already exists" on the strength of a parameter-overlap
  percentage without opening it
- Move a widget that takes a domain entity
- Add a colour literal to the design system, or a colour role without a contrast
  pair
- Baseline a candidate you just promoted — that records the wrong decision
- Merge, push, or force-push without the user asking; `{{doc:pr}}` governs
- Leave Step 4 undone and call the promotion finished
