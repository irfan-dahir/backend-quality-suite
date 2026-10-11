# RFC-0002 — The agnostic drop-in: surveying an unknown project, and what a context layer can honestly be

| | |
|---|---|
| Status | Accepted — all five open questions resolved, see §8 |
| Author(s) | Irfan Dahir (direction), drafted by Claude Code |
| Reviewers | Irfan Dahir |
| Date opened | 2026-09-14 |
| Date decided | 2026-09-15 |
| Supersedes / superseded by | Extends roadmap Workstream B (portability). Does not supersede RFC-0001, which stays gated on A1 |

A proposal, not a decision. This document argues for a specific change before
it happens; once a decision is made, the outcome and its reasoning belong in
the decisions log — this document stays as the record of what was proposed
and why.

**Evidence base:** five parallel research tracks, recorded on
**2026-08-10** (recorded in RFC-0002 §1), run
against four real repositories — two consumer projects ([Client A] mobile and web portal),
`<design-system-repo>` (a genuine zero-state case: no `.backend-suite/` at all),
and this repo. Every number below is measured, not estimated.

---

## 0. Why this matters now — the reader is an agent

*Added 2026-09-15. This reframing arrived after the document was accepted, and
it changes the stakes of everything below rather than the mechanisms.*

The context layer's real consumer is no longer a person reading documentation.
**It is the next agent writing code.** That single change reorders the problem:

- An agent writing a feature reads the code around it and infers the pattern. If
  the real pattern was never written down, it infers a *plausible* one — and now
  there are two patterns where there was meant to be one.
- This happens at machine speed, across every feature, in every repository.
  **AI is now the primary cause of design drift, not a cure for it.** Code review
  does not scale to it; by the time drift is visible in the UI, it is spread
  across months of work.
- The design system does not get deliberately abandoned. It gets *bypassed*, one
  reasonable-looking local decision at a time.

So the suite's purpose is not "help a human onboard a project faster." It is:
**make the context layer authoritative and complete enough that agents build
from it rather than from whatever is nearby.** Onboarding cost matters only
because an incomplete context layer is the thing drift grows in.

### The completeness test — and the trap inside it

This thesis needs a falsifiable definition of "complete enough." The obvious one
is *"could this project be rebuilt from its documentation alone?"* — and the
literal form of that question does not work.

**Why not:** generating a project and diffing the artifacts superimposes three
signals — documentation debt, model sampling variance, and drift between model
versions — with no way to separate them. The number moves when nothing changed.
The spec-driven-development literature already reports spec gaps "resurfacing in
unpredictable forms upon regeneration," and the infrastructure-as-code analogy
breaks at the load-bearing point: Terraform's `plan` **never re-creates
anything**; it normalises declared and refreshed state into one typed schema and
diffs that. *Normalise both sides into a common model* — not *regenerate and
compare*.

**The sound form is a reflexion model** (Murphy & Notkin, FSE '95): a declared
model, an explicit mapping onto source, yielding **convergence / divergence /
absence**. Deterministic, no generation step, thirty years of architecture
conformance behind it. `profile.json` + `resolve.py` is already a reflexion
mapping in all but name — and **absence** is the verdict no audit currently
produces, which is §3h's disk → declared gap seen from the other side.

**The measurement that does survive is ablation, not regeneration:** regenerate
one already-shipped feature twice — full context layer versus one document
removed, fixed ticket, model and seed. The delta is that document's measured
load-bearingness. Non-determinism cancels because it is an A/B *within one run*,
which is precisely the argument `bin/golden_local_ab.py`'s docstring already
makes for pixels. It cannot be gamed by writing more documentation: a document
that changes no agent output scores zero however well it reads. The output is a
ranked list of which documents agents actually use — an artefact this project has
never had.

**One firm rule, from the last time this was attempted.** Model-driven
engineering tried round-trip generation in the 2000s and failed
*organisationally* — developers under delivery pressure circumvented it.
**Regeneration stays a measurement and never becomes a delivery path.** The suite
measures whether a specification is sufficient; it does not build the project
from it.

Full working: **recorded in RFC-0002 §2**.

## 1. Summary

The goal as stated is "drop into any project, scope out everything, establish a
context layer, work out of the box." Measured against real repositories, the
literal version of that is not achievable, and the reason is not engineering
effort — it is that **a codebase tells you what it does, never what it meant to
do**, and audits exist precisely to measure the gap between those two.

Under §0's framing that sentence carries more weight, not less: an agent reading
the codebase to infer intent will faithfully reproduce whatever inconsistency is
already there. **Generate the standards from the code and drift stops being a
bug — it becomes the specification.**

What *is* achievable, and worth building:

1. **A survey step** that reads an unknown project and reports what it found,
   what it could not determine, and what it is guessing — as a **derived
   collateral**, never as the context layer.
2. **A candidate profile** generated from that survey with **per-field
   provenance** (`inferred` / `declared` / `approved`), so an inference can
   never masquerade as a human decision.
3. **Project archetypes**, because the current profile silently assumes one
   project kind ("an app consuming a design system") and breaks on a
   design-system package — a gap two independent tracks hit.
4. **An extensible role vocabulary**, because on a real zero-state repo **17 of
   20 top-level documents had no role in the vocabulary at all**, and one
   missing role (`components`) accounts for 83% of the full-tree gap. That is
   not a detection failure; you cannot infer a mapping to a role that does not
   exist.
5. **Figma as a declared external source** — audited *against* the context
   layer, never admitted *into* it.

The honest target is not "zero human work." It is: **nothing the machine guessed
is ever mistaken for something a human decided, and the human's job collapses
from authorship to ratification.**

### The correction that reshaped this RFC

The first draft measured what a **deterministic script** could discover, and
called the remaining 40% "human-authored." That was wrong about who does the
typing. In practice Claude drafts; a human decides. Those are different jobs,
and conflating them understated what is achievable:

| Band | First draft | Corrected |
|---|---|---|
| ~25% | script derives it | unchanged |
| ~35% | script proposes, human confirms | unchanged |
| ~40% | *human authors from scratch* | **Claude drafts it with its reasoning; a human ratifies** |

A script cannot tell which of four candidate files is really the `design` doc.
A model can read all four and argue for one. "Cannot be mechanised" is not the
same as "cannot be done" — and the suite's own architecture already encodes that
distinction, splitting work into **scripts** (mechanical) and **skills** (prose
for a model to reason through). Discovery needs both halves for the same reason
everything else here does (§3b-ii).

One line holds: intent is a statement about what a team *wants*, not about what
exists. Claude can draft it from evidence and an interview; it cannot decide it.
This makes provenance more important, not less — a model-drafted field is
exactly the kind of confident-sounding output that most needs a tag saying a
machine proposed it.

## 2. Motivation

*Read §0 first. The sections below were written when onboarding cost was
believed to be the motivation; they remain accurate as evidence, but the reason
they matter is drift, not effort. §2b's correction is where the two meet.*

### 2a. The measured cost today

Onboarding is 6 scaffolded files and, per consumer, **~140 hand-authored leaf
fields** (mobile 137, portal 144) plus a judgement call on ~20 doc roles.
`docs/ROADMAP.md`'s B2 estimate of "~30 minutes" is optimistic.

### 2b. Hand-authoring at that volume produces silent failures, today, in production

Track 1 compared the two consumer profiles against what is actually on disk.
Divergences are mostly not real project difference — they are mistakes nobody
had a mechanism to catch:

| Finding | Consequence |
|---|---|
| portal declares no `routesFile` despite having a router | `/review-docs` check C is **silently inert** there |
| portal declares no `otherSharedDirs`; four exist on disk | audits skip real shared code |
| portal's profile states it "ships no imagery"; six JPEGs + a CREDITS.md exist | asset audits scope wrongly |
| `tokens` lacks `additionalProperties: false` | `roleSource`/`roleAccessor` validate silently, unschemaed |
| `assets.palette` is `string` in schema, an object in mobile's shipping profile | schema does not describe reality |
| the two consumer `profile.schema.json` copies have drifted | nothing compared them |

The `routesFile` case is the governing principle violated in production: a
check that reports nothing, indistinguishable from a check that passed.

**Correction, 2026-09-15.** An earlier version of this section attributed all six
to hand-authoring. A lifecycle study measured the repositories properly and found
**at least two are drift, not authoring mistakes** — they were *true when
written* and rotted afterwards:

- The portal profile's "no `assets/` directory, ships no imagery" was written
  2026-08-06. `assets/resources/` with six JPEGs landed 2026-09-09 — **34 days
  later.**
- Two of the five undeclared `otherSharedDirs` (`lib/shared/format`,
  `lib/shared/metrics`) also postdate the profile.

The consequence is sharper than the original claim: **fixing §2b's bugs on the
day the profile was last edited would still leave the profile wrong today.** So
the motivation splits in two, and only one half is addressed by everything above:

| Cause | Count | Fixed by |
|---|---|---|
| Hand-authored wrong from the start | ≤4 of 6 | Survey + propose + provenance (§3a–§3d) |
| True when written, rotted since | ≥2 of 6 | **Nothing in this RFC until §3h** |

Onboarding speed was never the real motivation. Correctness is — and correctness
has a time dimension the first draft of this document missed entirely.

### 2c. The profile assumes a project kind, and says so nowhere

`screensGlob`, `routesFile`, `ownedBy`, and the `design`/`flows`/`instructions`
roles have no counterpart in a design-system *package*. Tracks 1 and 2 hit this
independently on `<design-system-repo>`. "Agnostic across stacks" was never the
hard part; **agnostic across project kinds** is.

## 3. Proposal

### 3a. `backend-suite survey` — a derived collateral, not a context layer

A new read-only command that walks an unknown project and writes
`.backend-suite/survey.json`: detected stack and candidate adapter, candidate
source roots, **candidate** token sources (ranked, never singular), the document
inventory with proposed roles and a confidence per proposal, and — load-bearing —
an explicit list of **what it could not determine and why**.

Three rules, inherited from `CONCEPTS.md`'s "Derived collaterals":

- It is **regenerable and disposable**. Deleting it loses nothing.
- It carries a **source stamp** — what produced it, when, against what commit.
- It is **never written back** into `profile.json`, `docs.manifest.json`, or any
  context document.

A survey that cannot determine something says so. It never emits a confident
default, because a profile that "passes validation and points at three files
deleted last month" is the exact failure `CONCEPTS.md` already names.

### 3b. Candidate profile generation, with per-field provenance

`backend-suite init --from-survey` writes a **candidate** profile in which every
field carries how it got there:

```
"inferred"  — the survey derived it; not yet trusted by anything
"declared"  — a human wrote it
"approved"  — a human reviewed an inferred value and ratified it
```

**Nothing downstream may treat `inferred` as authoritative.** `doctor.py` reports
unapproved inferred fields as outstanding work; audits that depend on one refuse
rather than run on a guess.

This is the single most important design move in this RFC. It is Nx's own lesson
from [Project Crystal](https://nx.dev/docs/concepts/inferred-tasks), where
inferred configuration drew a recurring complaint about
[provenance opacity](https://github.com/nrwl/nx/discussions/22097): config that
looks applied but is not. Stated in this project's own terms — **inference
without provenance is indistinguishable from a fact**, which is the governing
principle applied to the profile itself.

The lifecycle follows [Bazel's Gazelle](https://github.com/bazel-contrib/bazel-gazelle):
**generate → human reviews and commits → re-run detects drift.** Not runtime
inference. `docs/CATALOG.md` already has exactly this contract.

### 3b-ii. Two halves of discovery: a script that surveys, a skill that maps

Discovery splits exactly the way the rest of the suite already does.

- **`bin/survey.py` — the mechanical half.** Deterministic, reproducible,
  stdlib. Root manifests, file inventories, candidate token sources, the
  document list. It states facts and refuses where it cannot.
- **`/map-project` — the judgement half.** A skill, not a script: it reads the
  survey plus the candidate documents themselves and *argues* for a mapping —
  "these four files could be `{{doc:design}}`; this one, because it carries the
  screen inventory the other three reference." Its output is a proposal with
  its reasoning attached, written into the candidate profile as `inferred`.

The split is load-bearing. A regex over filenames scored 4 confident of 20 on
the zero-state repo; the ambiguity there is semantic, and semantics is what a
skill is for. But a skill's output is *argument*, not proof — so it lands as
`inferred`, never `approved`, and §3b's rule applies unchanged: nothing
downstream trusts it until a human ratifies.

This also keeps the oracle honest. The script half is reproducible and can be
baselined; the skill half is not, and is never baselined. Separating them means
the reproducible part stays reproducible.

### 3c. Project archetypes

`profile.json` gains `projectKind` — `app`, `design-system`, `docs-site` — with
**`workspace` as an orthogonal axis, not a kind.** A monorepo is a container
*of* archetypes; making it a peer kind would force a repo holding an app and a
package to pick one, and be wrong either way.

The kind selects:

- which roles are **expected** (an `app` expects `flows`; a `design-system`
  package does not, and should not be told it is missing one),
- which discovery strategies run,
- which audits are applicable at all.

`projectKind` is **inferred with provenance, and blocks until approved.** It is
the highest-blast-radius inference in the system — a wrong archetype misroutes
every downstream audit — so the machine proposes it with its reasoning and
*nothing runs* until a human ratifies. That keeps the speed benefit without ever
acting on an unratified guess.

An unknown or unsupported kind is a **refusal**, not a default to `app`. Guessing
`app` on a library is what makes `/bootstrap-api-docs` emit an empty flows
document today — the "clean vs. couldn't look" ambiguity the governing principle
forbids.

### 3d. An extensible role vocabulary

On the zero-state repo, **17 of 20 top-level documents had no role in the
vocabulary**, and `design` alone had four candidate files with no tiebreak.
(An earlier draft said 14 of 20; a full census corrected it — the three extra
mappings did not survive inspection.)

Across the whole documented tree the figure is 58% unmapped (135 of 233) — but
**112 of those are component pages, so a single missing role, `components`,
accounts for 83% of the gap.** That reframes the problem: it is not diffuse
vocabulary drift, it is a handful of specific roles that were never invented
because no design-system project had been onboarded.

The shape: **a small universal core, plus per-archetype extensions.** The core is
settled by evidence, not taste — a role qualifies only if it is present in all
three real repos: **`entry-point`, `documentation-rules`, `decisions`, `backlog`,
`contributing`, `rfc`.** Two candidates an earlier draft named are out:

- **`brief` fails** — absent from `<design-system-repo>`. Two of three is not
  universal.
- **`pr` cannot be core by construction** — `roles.json` already assigns it to
  `house-style` as org scope, not the universal plugin.
- `changelog` (1/3) and `postmortem` (0/3) fail the same test.

A disjoint set per archetype would fit each project better and make every
cross-project skill unportable, which is the one property this suite exists to
have. So:

- Projects may **declare roles beyond the core set**, in their own manifest.
- Documents may **self-declare** their role in frontmatter, with
  `docs.manifest.json` as the override. Both
  [Copilot's `applyTo`](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)
  and Cursor's glob-scoped rules converged on documents declaring their own
  scope; it removes the central mapping as the only source of truth.
- A document present but mapped to **no** role is **reported**, never silently
  ignored. Silence there is how a suite claims doc coverage it does not have.

### 3d-ii. Scaffolding policy: propose per document, never mass-stub

When the survey settles on an archetype, `init` writes **only the universal
core**. Every archetype-specific document arrives as a **proposal, accepted one
at a time** — the same propose-and-ratify shape as role mapping (§3b-ii), for
the same reason.

The alternative — scaffolding every template for the detected archetype as a
TODO stub — fails on this project's own governing principle. **A stub nobody
fills is indistinguishable from a document that does not exist**, except that it
now also reports as present. Mass-stubbing a design-system archetype would
manufacture a dozen of those on day one, and `/review-docs` would count them as
coverage. The suite would have talked itself into believing a project documented
things it has not written a sentence about.

#### A declined role is a decision, not a silence

Proposing per document creates a state the manifest cannot currently express.
Three situations must stay distinguishable:

| State | Meaning | Should the suite raise it? |
|---|---|---|
| Role absent, never offered | Nobody has looked yet | **Yes** — a real gap |
| Role accepted, document empty | Started, unfinished | **Yes** — an open TODO |
| Role **declined, with a reason** | The team decided it does not apply | **No** — it is on record |

Without the third state, "we fold motion into theming deliberately" is
indistinguishable from "we forgot" — the INERT problem wearing a different hat.

The mechanism already has a precedent to copy rather than invent. `docs.manifest.json`
already expresses a **declared non-path state** for a role: `external`, meaning
owned by another repository, which `resolve.py` reports with **exit 3** and
`DOC-ROLES.md` frames as "readable, not writable." A decline is its sibling — a
role mapped not to a path but to a declared absence and a reason:

```json
"motion": { "declined": "folded into THEMING.md §4 — no separate doc",
            "by": "…", "on": "2026-09-15" }
```

**New exit code 4 — declined.** Distinct from every existing code, and the
distinction is the point:

- not **2** (unknown role), because 2 means *a question only a human can answer*
  — this one has been answered;
- not **1** (mapped, file missing), because nothing is missing;
- not **0**, because there is no path to return.

**A skill that hits exit 4 skips the check and says so, with the reason, in its
report.** Declined is not the same as passed. A check that silently vanishes
because a role was declined is the exact failure this suite exists to prevent —
so the reason surfaces in the output where a reader sees it, not only in a
config file nobody opens. The decline is also dated and attributed, so a
three-year-old "does not apply" can be re-examined rather than inherited
forever.

#### A stub is a third state again — exit code 5

The scaffolding census surfaced a failure mode adjacent to the above and easy to
conflate with it: **a document that exists, is registered in the manifest, and
is empty.** `resolve.py` returns its path and exits 0. Sixteen scaffolded stubs
therefore read as sixteen cleanly documented categories, and `/review-docs`
counts them as coverage. This is the same INERT shape as a decline, arriving
from the opposite direction — and it is precisely why §3d-ii forbids
mass-stubbing rather than merely discouraging it.

Declined and stubbed are different states and need different codes:

| Code | State | Meaning |
|---|---|---|
| **4** | declined | *deliberately* has no such document, with a reason |
| **5** | stub | the document exists and is registered, but is **unwritten** |

A stub is detected by `status: stub` frontmatter written at scaffold time and
removed by whoever fills the document. `doctor.py` and `/quality-debt` count
stubs as outstanding work, not as coverage.

**These three mechanisms — `status: stub`, exit 5, and stub-aware debt
counting — gate any future decision to scaffold in bulk.** Until all three
exist, §3d-ii's propose-per-document rule is not a preference; it is the only
safe behaviour.

#### A related gap, smaller than first reported: `components` and `tokens`

The matrix census flagged `{{doc:components}}` as a role in active use but
absent from `roles.json` and `DOC-ROLES.md`, and called it another silent
failure of the `routesFile` class. **Checked directly, that overstated it.**
Both consumers map `components` under `externalRoles`, `resolve.py` reads the
manifest rather than the plugin's vocabulary, and it resolves correctly to
exit 3 with the right message — it even appears in the "known roles" listing as
`components (external)`. Nothing was ever silently skipped.

The real gap was documentation: `DOC-ROLES.md`'s vocabulary table had fallen
behind the vocabulary projects actually use, so a reader would have concluded
`components` was not a real role. The same was true of `tokens`. Both are now
listed, with a note that they are external more often than not. A role with no
template is normal when the document lives in another repository — `roles.json`
maps roles to *scaffolding*, and there is nothing to scaffold for a document
this project does not own.

Worth recording as a finding in its own right: a census that reports a problem
one severity class too high is its own kind of noise, and this one survived
into a merged RFC before being checked.

### 3e. Token-source detection: candidates, never conclusions

Token discovery measured worst of everything tried. The detector matched
`.backend-suite/findings/tokens.json` — **the audit's own output** — on both
consumers, and on both real projects the true token source **is not in the repo
at all** (`package:ds_flutter`, resolved via `package_config.json`).

Therefore: the survey emits a **ranked candidate list with reasons**, and
`tokens.source` stays human-approved. One genuine upgrade is available — the
[W3C Design Tokens format reached its first stable version in October 2025](https://www.w3.org/community/design-tokens/2025/10/28/design-tokens-specification-reaches-first-stable-version/)
with 40+ organisations behind it ([spec](https://www.designtokens.org/tr/drafts/format/)).
A `*.tokens.json` with `$value`/`$type` is a **high-confidence** signal worth
detecting natively. Detect it; never convert anyone to it.

### 3f. Figma: declared, external, audited against — never inside

Verified: the adapter contract is file-*shaped*, not merely file-oriented — a
`Check` is a regex over a text blob and findings are `(path, line)` pairs — so
Figma needs a **fourth seam** (context-source → normalised model), not a fourth
language adapter. Roughly **1.5 of ~20 roles** have any Figma equivalent. Figma
MCP read limits are **6 calls/month** on Starter/View seats and the Variables
REST API is Enterprise-only.

The architectural answer, which matters more than the feasibility one: **prose in
the repo stays canonical and declares which Figma library is authoritative.**
Figma and code are then both measured against the doc, and disagreement becomes
a **finding** rather than a truth conflict. Admitting Figma to the context layer
would create two human-authored canonical sources with no arbiter — the drift
this suite exists to prevent.

Deferred behind four preconditions: the context-source seam; a non-path finding
locator; a **committed, diffable snapshot** to audit instead of a live service;
and `CapabilityError` on a missing or stale snapshot rather than a clean report.

### 3g. Enterprise mechanics

| # | Item | Why | Size |
|---|---|---|---|
| 1 | ~~Regenerable output committed by default~~ | ✅ **Fixed in #93** | — |
| 2 | Version contract: `supportedProfileVersions`, checked in `doctor.py`/`resolve.py` | `profileVersion` is `const: 1` and **nothing** compares plugin↔profile version; skew degrades into a silently narrower audit | S |
| 3 | Upward profile discovery (nearest `.backend-suite/`), optional workspace index | `resolve.py:58` hardcodes the repo-root profile; one adapter, one `source.root`. This repo itself has two plugins and no profile | M |
| 4 | `schemaSyncedFrom` version+sha stamp, `sync_schema.py`, org sweep over `doctor --json` | The 2-repo drift check does not scale to 50. The sweep also derives `PROJECT_NAMES` (at the time a hardcoded one-name tuple at `audit_skill_paths.py:108`, since replaced by a hashed denylist), closing ROADMAP B3 and B5 | M |
| 5 | `exceptions.json` entries require `reason`/`reviewedBy`/`expires`; counts surfaced in `/quality-debt` | No expiry, reviewer, or cap today — an exception list is how audits get silenced permanently | M |

Governance belongs in `house-style` (org floor) over `backend-suite`
(universal). The existing two-plugin split is the right seam; no third layer.

### 3h. Staying accurate: the lifecycle half

Everything above is a day-one mechanism. §2b's correction shows why that is not
enough, and the measurement behind it is stark. Comparing `HEAD` against the
commit that last touched `.backend-suite/`:

| | Portal | Mobile |
|---|---|---|
| Commits since config was last edited | **339** | 40 |
| Files added | 216 (106 under `lib/`) | 46 |
| Tracked files under `lib/` | **77 → 176 (+129%)** | — |
| Directories added / deleted | **26 / 2** | 6 / 0 |

A configuration written against a 77-file tree is now describing a 176-file
tree. Nothing in the suite noticed.

#### The structural blind spot, in one sentence

**All five `doctor.py` checks run declared → disk. Nothing runs disk →
declared.** Every existing check starts from a config entry and asks whether it
still resolves — which catches a deleted or moved target, and is blind by
construction to anything *added* that no config mentions. A new feature
directory is not a broken path; it is an absence of a path, and absences are
invisible to a checker that iterates over what is present.

Three mechanisms close it, smallest first.

**1. `survey --check` — the completeness diff.** Enumerate what is on disk,
subtract everything any config file mentions, report the remainder. That is the
missing direction, and it is a flag on a command §6 already sequences first.
Tested against the measured drift above, it would have caught all three false
assertions. **Size: S–M. This is the highest value-per-unit-of-work item in the
RFC.**

**2. A fourth provenance state: `contradicted`.** §3b's rule — nothing
downstream trusts `inferred` — governs an assertion's *origin*, not its *age*.
A field a human `approved` a year ago is trusted permanently, even once disk
disagrees with it. `contradicted` is **computed, never authored**: the survey
sets it when disk contradicts an approved value, and downstream treats it
exactly as `inferred` (refuse rather than run on it). Re-survey **diffs and
reports; it never re-infers over an `approved` field** — silently overwriting a
human decision because the code moved would invert the whole provenance model.

**3. A commit SHA on every evidence file.** All 43 evidence files written during
this session carry `verified_at` but no commit. A timestamp makes staleness a
calendar guess; a SHA makes it **a diff** — "verified against a tree 339 commits
ago" is a fact, "verified 24 days ago" is an eyebrow-raise. Adding
`verified_against.commit` serves RFC-0001's evidence model and this RFC's
provenance model from one substrate, without merging the two vocabularies (§8.3
keeps them separate deliberately).

Explicitly rejected: **a calendar TTL on approvals.** Expiry by date produces
re-ratification work on a quiet project that has not changed, and stays silent
on a busy one that has changed twice this week. Staleness should be measured in
diffs, not days.

## 4. Alternatives considered

- **Do nothing — keep hand-authoring.** Rejected: §2b shows this is already
  producing silent audit failures in production, and that gets worse per repo
  added, not better.
- **Full auto-generation of the context layer.** Rejected outright. It
  contradicts `CONCEPTS.md`'s founding rule, and structurally: derive intent
  from code and every audit becomes a tautology, checking generated content
  against generated content. The 0-finding-baseline trap, one level up.
- **Runtime inference (infer on every run, never persist).** Rejected — this is
  exactly the Nx provenance-opacity complaint. Also unreviewable: nobody can
  code-review a value that only exists in memory.
- **Adopt `llms.txt` as the context-declaration format.** Rejected on evidence:
  [~5.6% adoption across the top 10k sites, with no major provider confirming
  they read it](https://caseyrb.com/blog/state-of-llms-txt-adoption/). Premature.
- **Expose the context layer via MCP instead of files.** Deferred, not rejected —
  MCP is a transport, not a context layer, and its `resources` primitive has the
  weakest client support of the three. A thin MCP adapter over the existing
  resolver is a cheap later add-on, not a foundation.
- **A central catalog service (Backstage-style) instead of per-repo profiles.**
  Rejected for now: declared catalogs
  [rot when they duplicate facts the repo already states machine-readably](https://riftmap.dev/blog/the-catalog-maintenance-trap/),
  and per-repo files stay reviewable in the PR that changes the code. Revisit at
  fleet scale, per §3g #4.

## 5. Drawbacks and risks

- **Inference that is wrong but plausible is worse than no inference.** A
  confidently mis-mapped `design` role sends every downstream audit at the wrong
  document. Provenance (§3b) is the mitigation, and it is load-bearing: without
  it, this proposal makes the suite *less* trustworthy, not more.
- **The measured ceiling is modest, for scripts.** Track 2's honest numbers:
  **~25% unaided, ~35% propose-for-confirmation, ~40% requiring judgement.**
  Track 1's field-level count was more optimistic (45/35/20) because it
  classified fields rather than attempting to derive them. **Expect the lower
  number for the script half.** The skill half (§3b-ii) addresses the 40% band,
  but produces argument rather than proof — it moves work from authorship to
  ratification, it does not remove the human. Anyone selling this as "works out
  of the box, no review needed" will be wrong.
- **A skill that argues well for a wrong mapping is the sharpest new risk this
  RFC introduces.** A confident, well-reasoned case for the wrong `design` doc
  is harder to catch than a regex guess, precisely because it reads as
  considered. `inferred` provenance plus ratification is the entire mitigation.
- **Doc-role inference scored 20/20 on mobile and 10/12 on portal — and that is
  circular.** Those docs were named by this suite's own convention. The zero-state
  result (4 confident of 20) is the real signal.
- **Naive signals actively mislead.** A file-extension census reads
  `<design-system-repo>` as a JavaScript project — 4,722 `.html` and 910 `.js`
  ahead of 317 `.dart` — entirely from four committed MkDocs builds. Root
  manifests are reliable; censuses are not.
- **`projectKind` is a new taxonomy, and taxonomies calcify.** Four kinds chosen
  now will be wrong for the fifth project. Mitigation: unknown kind refuses
  rather than defaults, so being wrong is loud.
- **Scope.** This touches the profile schema, `init.py`, `doctor.py`, `resolve.py`,
  the role vocabulary, and adds a command. It must be phased (§6).

## 6. Impact

| Area | Impact |
|---|---|
| Backward compatibility | Additive. An existing profile with no `projectKind` and no provenance keeps working; both are optional until a project opts in |
| Existing consumers | Mobile and portal gain nothing until re-surveyed — but §2b's six real bugs are found the moment they are. Recommend surveying both early as the first validation |
| `CONCEPTS.md` | Needs a new section distinguishing **survey** (derived) from **context layer** (authored). Without it the vocabulary collides on "context" |
| RFC-0001 | Unaffected and still gated. §3b's provenance vocabulary is adjacent to RFC-0001's verification tiers but deliberately separate: one is "who decided this", the other "who checked it" |
| Roadmap Workstream B | B2 (`/onboard-new-client` made real) is substantially this RFC. B3/B5 fall out of §3g #4 |
| `/bootstrap-api-docs` | Needs rescoping to archetypes before it can be trusted; today it is app-shaped and `unverified` |
| Security | Improved: §3g #1 shipped in #93. No new external surface |

**Phasing.** Ship in this order, each independently useful:

1. **`bin/survey.py`, read-only, writes nothing but `survey.json`.** Immediately
   valuable as a diagnostic even if nothing consumes it. **Its first real run is
   the validation case:** §2b's six bugs are known and deliberately unfixed, so
   a survey that fails to surface them has failed its own acceptance test.
2. **Provenance fields + `doctor.py` enforcement.** Must land before any
   generated profile is trusted by anything. Includes the `contradicted` state
   and `verified_against.commit` (§3h) — both are small, and both are cheaper to
   design in now than to retrofit.
2b. **`survey --check`, the completeness diff** (§3h). A flag on phase 1, and
   the highest value-per-unit-of-work item here — it closes the disk → declared
   direction that nothing currently covers.
3. **`/map-project`, the judgement half** (§3b-ii). Proposes role mappings with
   reasoning, always as `inferred`. Sequenced after 1–2 so its output lands in a
   provenance system that already refuses to trust it.
4. **`init --from-survey`** (Gazelle contract: generate → review → commit → drift).
5. **Archetypes + the universal-core role vocabulary.**
6. **Enterprise mechanics** (§3g #2–5), opportunistic.
7. **Figma**, only if its four preconditions are met.

## 7. Open questions — all resolved 2026-09-15

- ~~How many archetypes, and is `workspace` one?~~ **Three kinds (`app`,
  `design-system`, `docs-site`) with `workspace` as an orthogonal axis.** A
  monorepo is a container *of* archetypes; making it a peer kind forces a repo
  holding both an app and a package to pick one and be wrong either way.
- ~~Is `survey.json` committed or ignored?~~ **Committed, source-stamped and
  drift-gated like `docs/CATALOG.md`.** Accepts the cost of a fourth file kind
  in exchange for discovery being reviewable in the PR that changes the code. A
  gitignored survey cannot be drift-checked, so it going stale would be
  invisible — the failure this suite is least willing to accept.
- ~~Does `projectKind` belong in the profile, or is it inferable?~~ **Inferred
  with provenance, and it blocks until approved.** Highest-blast-radius
  inference in the system, so it gets the strictest gate: propose with
  reasoning, run nothing until ratified.
- ~~What is the minimum viable role vocabulary?~~ **A small universal core
  (~6 roles) plus per-archetype extensions.** A disjoint set per archetype fits
  each project better and makes every cross-project skill unportable — which is
  the one property this suite exists to have.
- ~~Does the survey run against a dirty working tree?~~ **It runs, and stamps
  the dirty state** — the commit, plus which files differed. Reproducible enough
  to trust, without blocking a survey exactly when it is most useful.

### Still genuinely open

- **Who authorises a new archetype?** Three are fixed now; the fourth will be
  argued for by a real project that fits none. No process for that yet.
- **How does a `/map-project` proposal get reviewed at volume?** Ratifying ~20
  role mappings one at a time is fine once and tedious at fleet scale.

## 8. Decision

**Accepted. Decided 2026-09-15.** All five §7 questions resolved above; three
further decisions taken alongside them:

1. **Discovery splits into a script and a skill** (§3b-ii) — the single largest
   change from the first draft. It follows from correcting who does the
   authoring: Claude drafts, a human decides. The 40% "human-authored" band was
   never a measure of what needs a human to *type* it, only of what needs a
   human to *decide* it.
2. **The six known bugs in §2b stay unfixed, deliberately** — they are the
   survey's acceptance test. A survey that does not surface them has not earned
   trust. Accepted cost: `/review-docs` check C stays silently inert on portal
   until then, and two of the six are schema holes in *this* repo, so any
   project onboarding meanwhile validates silently too. Revisit if onboarding
   starts before the survey ships.
3. **Provenance and RFC-0001's verification tiers stay separate vocabularies**,
   with the distinction written into `CONCEPTS.md`: provenance answers *who
   decided this*, verification answers *who checked it*. Merging them would blur
   a line both rely on.

Amended 2026-09-15, after the archetype × role scaffolding question surfaced:

4. **Scaffolding proposes per document; it never mass-stubs** (§3d-ii). `init`
   writes the universal core only; archetype-specific documents are accepted one
   at a time. A stub nobody fills reports as coverage the project does not have.
5. **A declined role is recorded with a reason, and gets exit code 4** (§3d-ii).
   Modelled on the existing `external`/exit-3 precedent rather than invented. A
   skill hitting it skips the check *and says so, with the reason, in its
   report* — declined is not passed.
6. **A stub gets exit code 5, and counts as debt** (§3d-ii). A registered but
   unwritten document currently resolves as exit 0 and reads as coverage.
   `status: stub` frontmatter, exit 5, and stub-aware counting in `doctor.py`
   and `/quality-debt` are the three mechanisms that must exist before bulk
   scaffolding could ever be reconsidered.

Amended again 2026-09-15, after three lifecycle/value research tracks:

7. **§2b's attribution was wrong and is corrected.** At least two of the six
   bugs are drift, not authoring mistakes — true when written, false now. The
   sharpest line in the research: fixing them on the day the profile was last
   edited would still leave it wrong today.
8. **The lifecycle half is now in scope** (§3h): `survey --check`, a computed
   `contradicted` provenance state, and a commit SHA on evidence. A calendar TTL
   on approvals is explicitly rejected — staleness is measured in diffs, not days.
9. **Delivery and repair move to RFC-0003.** Diff-time delivery, fix-generation
   and exception aggregation are about what the suite *does*, not about dropping
   in, and belong in their own document rather than bloating this one.

**Scaffolding matrix** (full working: **recorded in RFC-0002 §3**):
36 roles, up from 22 — 6 universal core, 13 `app`, 16 `design-system` (3 shared
back to `app`), 4 any-archetype, and deliberately **0 for `docs-site`**, since no
real example exists to ground it; the kind stays declarable so it refuses rather
than defaults. **12 templates are missing**: 10 new full templates, 1 new
fragment, 1 fragment promotion, plus 1 rename (`instructions` → `entry-point`).
Six existing templates need archetype-neutral rewrites, and three of those —
`DESIGN`, `INSTRUCTIONS`, `DOCUMENTATION` — carry neutral names over app-shaped
content, so they actively mislead.

Implementation is phased per §6 and starts at phase 1. Nothing here is gated on
RFC-0001, which remains separately gated on Workstream A1.

---

_Last updated: 2026-09-15 (amended: scaffolding policy, §3d-ii)_
