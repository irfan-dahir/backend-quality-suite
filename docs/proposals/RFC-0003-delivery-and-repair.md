# RFC-0003 — Delivery and repair: when a finding arrives, and whether it fixes itself

| | |
|---|---|
| Status | Draft |
| Author(s) | Irfan Dahir (direction), drafted by Claude Code |
| Reviewers | |
| Date opened | 2026-09-15 |
| Date decided | |
| Supersedes / superseded by | Complements RFC-0002 (the drop-in). Independent of RFC-0001, which stays gated on Workstream A1 |

A proposal, not a decision.

**Evidence base:** three research tracks run 2026-09-15 —
[#98](https://github.com/irfan-dahir/ai-design-suite/issues/98) (report vs.
fix),
[#99](https://github.com/irfan-dahir/ai-design-suite/issues/99) (lifecycle),
[#100](https://github.com/irfan-dahir/ai-design-suite/issues/100) (fleet) —
measured against the same four repositories as RFC-0002.

---

## 0. The author of the change is increasingly an agent

*Added 2026-09-15, alongside RFC-0002 §0.*

RFC-0002 §0 establishes that the context layer's reader is the next agent writing
code, and that AI is therefore the primary cause of design drift rather than a
cure for it. This document inherits that framing, and it sharpens both questions
below:

- **Delivery.** If the author of a change is an agent, "deliver the finding to
  the author while they still hold the context" stops being a nicety about human
  attention spans and becomes something stronger: an agent *acts on* a finding
  delivered into its loop, immediately and without ego, in a way no human review
  queue matches. Diff-time delivery is not merely the higher-fix-rate channel —
  it is the only channel an agent is actually in.
- **Repair.** An agent that receives "this literal should be `AppTokens.space8`"
  can apply it in seconds. The bottleneck stops being the fixing and becomes
  *knowing which fixes are safe* — which is exactly what §3b's three bands
  encode.

The uncomfortable corollary, stated plainly: **drift is created at machine speed,
so it has to be caught at machine speed.** A weekly report cannot keep up with a
codebase where a dozen features land between readings.

## 1. Summary

RFC-0002 answers *how the suite learns a project*. This one answers two questions
it deliberately left alone, both of which turn out to matter more than any
remaining accuracy work:

1. **When does a finding arrive?** Today: in a report, on demand. The evidence
   says that is where findings go to die.
2. **Does anything get fixed?** Today: no. All 18 audits are report-only; across
   40 shipped skills exactly one touches existing source at all.

The headline finding of the whole research round did not come from a track about
delivery. It came from outside research on fleet tooling:

> **Meta's Infer moved from batch reports to diff-time delivery and went from a
> ~0% to a ~70% fix rate — with an unchanged analysis.**

Same checks. Same findings. Same quality. The only variable was *when* a
developer saw them. That single result reorders this project's priorities: an
analysis improvement multiplies a fix rate, and the fix rate is currently being
set by delivery, not by analysis.

## 2. Motivation

### 2a. The suite reports, and stops

Counted across `docs/CATALOG.md` and `plugins/design-suite/bin/`:

| | Count |
|---|---|
| Audits that report findings | **18** |
| Audits with a fix path, or even a stub | **0** |
| Skills that modify existing source | **1 of 40** (`/promote-component`) |

This is not an oversight — it is the tier rule working as designed (read-only
runs automatically; content-generating stays explicit). But the consequence is a
hard ceiling on value. "Here are 33 hardcoded values across 11 files" is worth
considerably less than "here is a reviewed diff removing 19 of them."

### 2b. And what it reports arrives at the wrong moment

A report is read when someone chooses to run it, about code written days or weeks
earlier, in a context the author has left. A diff comment arrives while the
author is still holding the problem in their head, on the lines they just wrote,
with the change still cheap. Infer's 0% → 70% is the measurement of exactly that
gap, and it was achieved without improving a single check.

The corollary is uncomfortable and worth stating plainly: **every dashboard,
portfolio view and fleet rollup this project might build starts at a 0% fix
rate** unless it also lands somewhere a change is being made.

### 2c. A structural falsehood found on the way

`dart.checks()` falls back to `ctx.token_accessor or "AppTokens"`. A token audit
run with no declared token source therefore *appears to work* — it reports raw
literals as though it knew a token existed for them. It does not. This is
RFC-0002 §3b's exact failure mode, live in shipped code, and it constrains §3c
below.

## 3. Proposal

### 3a. Diff-time delivery becomes the default channel

Findings are delivered **on the change that caused them**, scoped to changed
files (see §7 — lines was tried and reverted), and the batch report becomes the
secondary surface rather than the primary one.

Three delivery points, in order of what is available today:

1. **Pre-commit** — already built (`run_precommit_audits.py`, `hooks.map.json`
   with `preCommit: true`). This is diff-time delivery that works right now, with
   no CI, and it is the honest answer to the constraint that GitHub Actions is
   unavailable on billing grounds.
2. **PR comment** — the Infer shape proper. Blocked on CI, so designed now and
   built when billing allows.
3. **Editor-time** — the existing `audit_on_edit.py` hook, the earliest and
   cheapest moment of all.

**Scoping to the change is the whole point.** A pre-commit hook that reports
every finding in the repository recreates the batch report, one
commit at a time, and gets switched off within a week. The delivery must answer
"what did *this change* introduce", which is also what makes the baseline/oracle
machinery already in the repo the right substrate for it.

### 3b. Repair, in three bands

Findings are not equally fixable, and pretending otherwise is how an auto-fixer
loses trust permanently. Three bands, with a hard rule at each:

| Band | Condition | Action |
|---|---|---|
| **1 — deterministic** | A literal exactly matching **exactly one** declared token of the right category | **Generate the rewrite** |
| **2 — ambiguous** | Near-match, multiple candidates, or a value close to but not equal to a token | **Propose, never apply** — show the candidates and ask |
| **3 — absent** | No matching token exists | **Never auto-fix.** Creating a token is a convention decision |

Band 3 is the load-bearing refusal. A tool that invents `colorNeutral450` because
it found an unmatched grey has quietly started authoring the design system — the
intent stratum RFC-0002 reserves permanently for humans.

### 3c. Generated changes are handed over, never applied

A repair component **emits a unified diff and stops.** It does not write to the
working tree, does not stage, does not commit.

This satisfies the tier rule without weakening it: the component is
content-generating, so it stays `explicit`; but "explicit" covering *generate a
reviewable diff* rather than *silently rewrite source* is a meaningful and safe
middle state. Precedent already exists in this repo — `sync_mock_api.py`
generates rather than reports, using anchored regions and a `--check` mode, and
`golden-local-ab` provides the oracle to prove a mechanical rewrite changed
nothing it should not have.

Per §2c, band 1 is only available where a token source is genuinely declared. With
no declared source there is no "exactly one matching token" to match against, and
the correct output is a refusal, not a guess.

### 3d. Aggregate exceptions, not findings

The strongest fleet-scale idea, and the only one requiring no new architecture:
**when six of eight projects exempt the same rule, the rule is wrong.**

`exceptions.json` is authored, committed context — not generated output — so
aggregating rule IDs, counts and stated reasons across repositories fits
RFC-0002's read-time model exactly. No central store, no synced file.

Prior art is direct: Google's **Tricorder** treats an unhelpful finding as a bug
filed *against the analyzer author*, holds analyzers to a false-positive ceiling,
and removes ones that do not improve. And the opportunity is unclaimed — **Snyk
and Sonar both delete suppressed items from reporting**, so this model runs on
precisely the data the portfolio tools discard.

This inverts the usual audit relationship: findings stop being only a judgement
on the code and start being evidence about the standard.

**Hard confidentiality boundary.** Findings records are `{file, line, kind,
snippet}` and the snippet is verbatim client source — which is why PR #93
gitignored them. Any cross-project aggregation may carry **rule IDs, counts and
stated reasons only. Never snippets. Never client file paths.** Aggregating
findings across separate clients' repositories would reopen the disclosure hole
that fix deliberately closed.

## 4. Alternatives considered, and two rejections

- **Keep reports as the primary channel.** Rejected on the Infer evidence. It is
  the current design, and it is measurably the low-fix-rate one.
- **Auto-apply band 1 fixes.** Rejected. The tier rule keeps content-generating
  work explicit, and a tool that edits source unprompted has to be right every
  time forever to keep that permission.
- **Zero-config first run** — audits that work before any profile exists.
  **Deprioritised, not rejected.** Only 5 of 18 audits could run honestly with no
  config, and three of those need shipped universal defaults. It buys a better
  *first impression*, not a better tool, and it is blocked behind `survey.py`
  regardless.
- **Fleet health scores / portfolio dashboards.** **Rejected outright**, on three
  independent grounds: this repo already decided it (`engine/findings.py`: *"No
  composite score, by decision"*); a team games its grade by growing
  `exceptions.json`, destroying the exact signal §3d depends on; and no evidence
  was found that any portfolio dashboard changed behaviour. A dashboard is also
  the archetypal 0%-fix-rate delivery surface.

## 5. Drawbacks and risks

- **A wrong band-1 rewrite is worse than any false positive.** A bad finding
  wastes a minute; a bad rewrite enters the codebase. Mitigated by exact-match-only,
  diff-not-apply, and the golden oracle — and by band 1 refusing when no token
  source is declared.
- **Diff-time delivery is a noise amplifier.** A report nobody reads is harmless;
  a hook that fires on every commit and is wrong 20% of the time gets disabled,
  and takes the trustworthy checks with it. Tricorder's false-positive ceiling is
  the relevant discipline, and it should apply here before anything is wired to
  pre-commit by default.
- **§3d makes the standard itself falsifiable.** Aggregating exemptions will
  eventually produce evidence that a rule this team wrote is wrong. That is the
  feature — but it is a different relationship with the standard than the suite
  has had until now, and it should be entered deliberately.
- **CI remains unavailable**, so the highest-fidelity delivery point (PR comments)
  cannot be built yet. Pre-commit is a real answer, not a placeholder, but it
  reaches one developer rather than a review conversation.

## 6. Impact and phasing

| Area | Impact |
|---|---|
| Tier policy | No exception requested. Repair stays `explicit`; delivery of read-only findings stays `auto` |
| Existing audits | Unchanged. Delivery and repair wrap them; no check is rewritten |
| RFC-0002 | Independent. §3d's aggregation assumes RFC-0002's read-time model and does not alter it |
| RFC-0001 | Independent. Still gated on Workstream A1 |
| Confidentiality | Tightened: §3d states the snippet/path boundary explicitly for cross-project work |
| CI | One path (PR comments) blocked on billing; two paths available today |

**Phasing:**

1. **Scope existing pre-commit delivery to changed files.** Smallest possible
   first step, uses machinery that already exists, and tests the central claim
   cheaply.
2. **Band-1 repair for design tokens**, emitting a diff. ~2–3 days. The narrowest
   case with the clearest correctness argument.
3. **Exception aggregation** across the projects already onboarded.
4. **PR-comment delivery**, when CI billing is resolved.

## 7. Open questions

- ~~What false-positive ceiling do we hold ourselves to?~~ **Resolved 2026-09-15,
  from measurement rather than precedent** ([#104](https://github.com/irfan-dahir/ai-design-suite/issues/104)).
  The bar is **≤5% wrong, ≤20% total noise, and 0% for band-1 repair** — stricter
  than Tricorder's 10%, and deliberately so: per §0, the reader is an agent that
  *acts* on a finding rather than a human who glances at one, so a ceiling
  calibrated for skeptical humans is the wrong instrument. A finding an agent
  acts on wrongly costs a change, not a moment's attention.

  **A documented exception the engine cannot apply counts as a false positive.**
  `audit_tokens` is 0% wrong but 30% unactionable purely because `_allowlists()`
  never reads the `allowlistRegions` the project documented. From the user's
  side that is indistinguishable from the tool being wrong, so it is scored as
  wrong.

  **Measured state at the time the bar was set: 5 of 18 audits clear it**
  (`doc_staleness` 0%, `tokens` 0%, `mock_api` 0%, `reinvented_components` 4.8%,
  `error_handling` 6.7%). Two do not fail on tuning but are structurally broken —
  `audit_accessibility` (100% wrong, and blind: every `fontSize:` literal in the
  measured project sits in PDF-generation code) and `audit_claude_md_drift`
  (audits the plugin's own repository and reports the result to consumers as
  theirs). Both were fixed the same day: the first disabled with a stated bar for
  re-enabling, the second retargeted to the consumer project.
- ~~Does "scoped to changed lines" mean changed lines only, or changed files?~~
  **Files. Decided 2026-09-15 (issue #104), after lines was built, measured and
  reverted.** Lines is stricter, and on this codebase it is also wrong: findings
  are anchored at the *matched expression*, not the offending literal.
  `engine/scan.py` records `line_of(source, match.start())`, and an adapter
  pattern such as `adapters/dart.py`'s `EDGE_INSETS_RE` matches a whole
  `EdgeInsets.symmetric( … )` call across newlines — so a wrapped call anchors on
  its opening line while the literal sits 1–4 lines below. A commit that edits
  only the literal's line then produces a finding outside its own changed range,
  and line scoping files it as pre-existing and hides it. A dropped finding that
  prints as a clean commit is the one failure mode §2c and the governing
  principle forbid, and no amount of extra noise ranks beside it. **Lines becomes
  correct the day findings anchor at the literal** — i.e. when adapter checks
  report a sub-match offset and `scan_source` uses it instead of `match.start()`;
  until then the file is the smallest honest unit. The cost is bounded and
  visible: the suppressed count is printed on every run.

### Still genuinely open

- **Who owns a rule that fleet evidence says is wrong?** §3d produces the
  evidence but names no one to act on it, and an unowned signal is a dashboard by
  another name.
- **Is band 2 worth building at all,** or does "propose a fix you must then
  evaluate" cost a reader more than a plain finding plus the token list?

## 8. Decision

<!-- Filled in when status moves out of Draft. -->

---

_Last updated: 2026-09-15 (amended: false-positive bar set from measurement, §7)_
