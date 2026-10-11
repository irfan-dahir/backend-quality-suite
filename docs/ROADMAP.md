# Roadmap

> **Proposal, dated 2026-08-10 — not a record of work.** Nothing here is built.
> **All four open questions were resolved the same day** — see §Decisions for each
> answer and its reasoning, which is what stops them being re-litigated. Verify
> anything factual against the repos before relying on it; this document will go
> stale the way every other plan in this project has.

What to build next, and why in this order. Written after a session that ran five
components end-to-end against real projects and found a defect in four of them.

---

## The finding that shapes everything

Five components were exercised against two real consumer
projects ([Client A] mobile and [Client A] web portal). Four contained a check that **reported nothing while looking
healthy**:

| Component | The defect |
|---|---|
| `/audit-assets` | A check grepped a directory that no longer held its subject |
| `/review-docs` | One check read a file with zero routes; another covered 4 of 20 documents |
| `/promote-component` | Name matching missed the `Ds` prefix — 16 duplicates invisible |
| `design-auditor` | Three dead pointers, all inside config *comments* |
| `mock-api-auditor` | None — the first clean run |

Two things follow, and they pull in opposite directions.

**Running a component finds defects that reading it cannot.** Every one of the four
was invisible to review. Each had been "working" for weeks.

**Mechanising the check produces confident nonsense.** The same session generated
roughly as many false positives as real findings — prose read as regex, a `_readme`
explaining a removal read as the removal, an exemption list for a case the regex
could not match. Every one was caught by opening the file, and none by a script.

So the goal is not "automate verification". It is **make the mechanical half cheap
and the judgement half explicit**, and stop pretending the second half is the first.

One more pattern worth carrying: all four defects had a target that **moved** — a
directory, a router, a name prefix, a script path. `mock-api-auditor`'s target is a
registry that has not moved, and it held up. That is a usable predictor for which of
the remaining components to distrust.

---

## What is already in flight

A concurrent session is mid-build on a substantial change. **This roadmap deliberately
avoids all of it.** As of 2026-08-10 that work is uncommitted and includes:

| Area | Files |
|---|---|
| A unified findings model | `engine/findings.py`, plus 13 audit scripts modified to emit it |
| Aggregation | `design_debt.py`, `/design-debt` — one per-category debt view |
| Composition | `engine/chains.py`, `bin/chain.py`, `/run-chain`, `chain.schema.json` |
| Triggering | `hooks/audit_on_edit.py`, `hooks.map.schema.json` |
| Critique and capture | `design-critic`, `session-decisions`, `log-decision`, `capture-backlog` |

That is *findings → aggregation → automation → triggering*, in a sensible order, and
it is the right spine. **Phase 0 of this roadmap is to let it land and review it**,
not to build alongside it.

One open question for that work, in §Questions below: whether the chain runner
subsumes A1.

---

## Workstream A — Verification, made first-class

The highest-value stream, because it unblocks the other three.

| # | Item | Reasoning |
|---|---|---|
| **A1** | ✅ **`bin/verify.py <component>`** — run a component's mechanical parts against the current project, write evidence to `.backend-suite/evidence/<name>.json`. Built 2026-09-14 | Hand-rolled five times in one session, differently each time. Until this exists, verifying one component is an hour of bespoke work, which is why 26 remain unverified |
| **A2** | **Maturity backed by evidence, not assertion.** `proven` requires a matching evidence file naming what ran, when, and against which project. `catalog.py` gates it | `proven` is currently a word someone typed. Twice it was set with real caveats that only the commit message carries — invisible to anyone reading the catalogue |
| **A3** | **Generalise the zero-result guard.** A check that scans 0 files, matches 0 patterns, or reads a missing target fails loudly rather than passing | `audit_tokens` already has this and it works. The four defects above are all the same shape, and all in checks that lack it |
| **A4** | **The oracle should record what changed, not only how much.** | A `145 → 144` drift was unresolvable: `findings.json` is gitignored and the baseline stores a summary line and a sha256. The oracle can say *that* something changed and never *what* |
| **A5** | **One local command that runs everything CI would.** | CI is unavailable on billing grounds for the foreseeable future. Hand-verification is the primary path now, not the fallback, and it should not be five commands remembered from a transcript |

**A1 was the keystone; it's built.** A2 (below) is now unblocked. Workstream B's third
adapter can prove itself against it. Closing the 8-unverified-components gap is now an
hour of running `verify.py --all` per consumer project, not five bespoke hours.

### What A1 actually does, and does not do

Per its own docstring: output is three-way, never a boolean — **verified**, **refused**
(no backing script, an ambiguous one, or the script's own CapabilityError-style refusal),
**failed** (ran, found something wrong). It refuses in full on any component that mixes
a mechanical check with judgement (`design-auditor`'s prose `token_categories`, most of
`/review-docs`'s B/D/E/G checks) rather than partial-crediting the mechanical slice —
"ran the easy 20% and reported success" is the exact defect this suite exists to prevent,
in the tool built to prevent it. Tested against a scratch fixture, not the real consumer
repos, across all three outcomes before merging.

**Not yet done, now unblocked:** A2 (gate `catalog.py`'s `proven` label on a real evidence
file existing) hasn't been built — `verify.py` writes the evidence, but nothing yet
requires it. `verify.py` **has** now run for real against both consumers — 44 records each,
dated 2026-09-14 (mobile 10 verified / 6 failed / 28 refused; portal 8 / 9 / 27). What
blocks A2 is not missing evidence but where it lives: gitignored inside the consumer
repos, unreadable from here. And a mechanical verify run is not the end-to-end run
`proven` means, so it would not by itself justify a tier change.

### Accepted follow-on: RFC-0001

[RFC-0001](proposals/RFC-0001-evidence-and-tool-promotion.md) (accepted 2026-09-14,
tracked in issue #75) extends A1/A2's scope to a project's own bespoke tooling, plus a
gated promotion pipeline for tools that prove themselves via that evidence. Per its own
§8, it stays gated — it does not begin until A1 (now built) has actually run against real
project tooling and surfaced at least one real promotion candidate, not synthetic data.

---

## Workstream B — Portability, actually proven

| # | Item | Reasoning |
|---|---|---|
| **B1** | ~~A third language adapter~~ **Deferred — finish `tsx` instead (see ✅ 2)** | Both consumers are Flutter. Two adapters where one is a seam-proof is a coincidence, not a seam. The cal.com validation was read-only and immediately found a structural blind spot |
| **B2** | **`/onboard-new-client` made real** — empty repo to working profile and manifest in one command | Adopting on the portal took ~30 minutes of manual role-mapping, and that repo was already half-configured. The drop-in promise fails at step one |
| **B3** | **Cross-consumer profile drift check** | Two consumers now. Their profiles are diverging with nothing comparing them, which is how the design system drifted before `audit_reinvented_components` existed |
| **B4** | ~~Revisit the two-plugin split~~ **Resolved: stays two (✅ 3)** | It has cost a duplicated resolver (`resolve_role.py`, ~40 lines) and a cross-plugin gate exemption. The client-facing/internal separation is real; whether it needs two *plugins* is the question |
| **B5** | **Derive `PROJECT_NAMES` rather than hand-maintaining it** | Rule 4 needs a human to add each new consumer. A gate that requires manual feeding will eventually miss one, and its whole purpose is catching the thing humans miss |

---

## Workstream C — Carrying the rest over

| # | Component | Verdict | Reasoning |
|---|---|---|---|
| **C1** | `skeleton-auditor` agent | **Move** | Read-only and already config-driven via `skeleton-patterns.json` — the exact shape that ported cleanly four times |
| **C2** | `check_asset_registration.py` hook | **Move** | The asset adapter now exists, which is what it was waiting for |
| **C3** | Asset pipeline render layer | **Audit first** | The Blender drivers were agnostic and the registration seam has moved. Worth measuring what is genuinely still coupled rather than assuming |
| **C4** | `/cut-release` | **Stays** | Signing and store distribution are stack- and account-specific. Near-zero reuse |
| **C5** | `mock_api/config.json` unreachable by `doctor` | **Fix** | It is not in the profile's `audits` list, so the script-pointer check cannot see it. Dead pointers there would be invisible |

---

## Workstream D — Known defects

| # | Item | Blocked on |
|---|---|---|
| **D1** | `token_categories.sizing` has no `violation_pattern` | **Unblocked — pattern decided in ✅ 4**, measured at 14 occurrences |
| **D2** | styled-components property-level under-report | — |
| **D3** | JSX text over-reports (`<p>Set padding: 16px;</p>`) | Won't fix without a parser. Documented; over-reporting is the safe direction |
| **D4** | `promotion_candidates` 9 → 10, now baselined | Whoever landed the consumer (mobile) PRs #136–#140 |
| **D5** | 12 baselined duplicate widgets | Per-component adoption. The design system's own source already documents which three of four `_SectionHeader`s should move |

---

## Sequencing

| Phase | Contents | Gate to proceed |
|---|---|---|
| **0** | Let the findings/chains work land. Review it | ✅ Done — that work merged |
| **1** | A1 ✅ done (2026-09-14), A2, A3 | A1: ✅ produces real evidence — tested on a fixture, and run against both consumer projects on 2026-09-14 (see Phase 2). A2/A3 not started |
| **2** | Close the 26 unverified components using A1 | Partly run — `verify.py` executed against both consumers on 2026-09-14 (44 records each). Not closed: the evidence is unreadable from this repo, and a verify run is not the end-to-end run `proven` requires |
| **3** | B1, B2 | A third adapter passes `verify_seam.py` |
| **4** | C1–C3, D1–D2 | — |
| **—** | A4, A5, B3–B5, C5 | Opportunistic; none blocks another |

Phase 2 is where the value is. Phase 1 exists to make Phase 2 cost hours instead of days.

---

## Decisions (were 🔴, resolved 2026-08-10)

All four were resolved on 2026-08-10. Recorded here with the reasoning, because a
decision without its reasoning gets re-litigated.

### ✅ 1 — No, chains do not subsume `verify.py`. Build both.

`chain.py`'s own docstring settles it: *"This never invokes a skill. The assistant
runs the skill in conversation; this records where the sequence got to, so a chain
survives a session ending halfway."* The schema agrees — *"a chain records the
sequence and where a run got to; it never invokes a skill."*

They are orthogonal, and they compose:

| | Job |
|---|---|
| `chain.py` | Sequence and remember. Survives a session ending mid-way |
| `verify.py` (A1) | Execute the mechanical half and record evidence |

The natural shape is a `verify-all-components` chain that sequences the 26 unverified,
`chain.py` tracking which are done, and `verify.py` doing each execution. **Phase 1 is
unchanged**, and A1 should be written to be callable as a chain step.

### ✅ 2 — Hypothetical. B1 is deprioritised; finish `tsx` instead.

Both consumers are Flutter. The portal was expected to be the portability proof and
turned out to be Flutter Web. No non-Flutter project is named. The cal.com validation
was read-only and, correctly, proved only that the seam holds — not that anyone is
using it.

Adding a third half-finished adapter would widen a claim nobody is relying on. The
better use of the same effort is **finishing `tsx`**, which is the one non-Flutter
adapter that exists and still has two known gaps (styled-components property-level
under-reporting, D2; and Tailwind token enumeration only landing recently). That makes
the existing portability claim true rather than making a broader one shakier.

B1 moves to "revisit when a non-Flutter consumer is actually committed".

### ✅ 3 — The two plugins stay two.

The split has cost ~40 duplicated lines (`resolve_role.py`) and one gate exemption.
Both are documented, and both were one-time costs.

What it buys is not convenience: **a client-facing repository installs `backend-suite`
alone and inherits no org PR process, no letterhead, no client-readiness
reporting.** That is a real boundary, and merging the plugins to recover 40 lines
would trade it for very little. Keep them separate; keep `resolve_role.py`'s docstring
explaining why the duplication exists.

### ✅ 4 — A sizing violation is a raw height literal equal to a declared token value.

Proposed `violation_pattern` for `token_categories.sizing`:

> a raw `height:` / `minHeight:` / `maxHeight:` / `minimumSize:` whose value equals a
> declared sizing token (`buttonHeight` 52, `inputHeight` 56, `minTouchTarget` 48)

Measured against a real consumer project (mobile) before proposing: **14 occurrences**, e.g.
`height: 52` where `AppTokens.buttonHeight` is 52.

Deliberately narrow. It fires only on an *exact* match with a token value, so a screen
that legitimately needs 51 or 60 is never flagged — the finding is always "there is a
token for this exact number and you did not use it", which is actionable rather than
arguable. Genuine exceptions go in `exceptions.json` like every other category's.

---

## Deliberately not on this roadmap

**Anything the concurrent session is building.** Findings unification, debt
aggregation, chains, edit-time hooks, critique and session capture are all in flight.
Building near them is how two sessions produce four collisions in a day — which is
what happened on 2026-08-10, and worktrees are the reason none of it landed badly.

**Re-running CI as a verification strategy.** GitHub Actions is unavailable on
billing grounds. That is a constraint to design around, not to wait out — hence A5.

**Deployment automation.** Deploys stay manual by decision, because no hosting
target is settled — and the deploy credential a pipeline would need is left
unconfigured on purpose rather than half-wired.

---

_Written 2026-08-10. Supersedes nothing; the decoupling plan it follows from lives in
the first consumer project's own planning docs and is complete. The link that was here
pointed into that repository's internal plan document — a reader without access to that
engagement gets a 404, and one with access gets a document that is not ours to publish._
