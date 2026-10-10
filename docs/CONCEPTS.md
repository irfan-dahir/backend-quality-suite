# Concepts

The vocabulary this suite is built on, and why each term exists.

Read this if you want to understand *why* the suite is shaped the way it is —
before adopting it on a project, or when deciding whether a change fits. For
what is installed, see [CATALOG.md](./CATALOG.md). For getting running, see
[ONBOARDING.md](../ONBOARDING.md).

Every term below is one someone actually reaches for in conversation on these
projects. None is invented for this document.

---

## The finding that shapes everything

The suite began as tooling inside one Flutter app. When we measured how coupled
it really was, the dominant axis was not the language:

| Coupling axis | Count |
|---|---|
| Hardcoded documentation paths in `.claude/` | **252** |
| Dart/Flutter-specific parsing | 3 scanners |

The 252 is itself a correction. The first measurement said **184**, because it
searched for `docs/*` paths and missed every reference phrased another way. One
skill that an early audit called "portable now — zero references" turned out to
carry **20** of them.

That is the finding that shapes the whole design: **the hard part of portability
was never the code. It was the documents the code assumes exist.** Almost every
concept below follows from taking that seriously.

---

## Context layer

**The canonical, human-approved set of project documents. The one thing in the
system that is written by people and answers to nothing else.**

A design brief, a screen inventory, a flows document, a decisions log, a brand
voice guide. Not generated. Not derived. Not linted into shape.

Everything else the suite produces is downstream of it. When Claude audits a
screen, the question it asks is *does this match the context layer* — not *does
this match some rule the tool has an opinion about*. The tool has no opinions
about your product. It only knows how to check the codebase against what you
already decided.

"**Building the context layer**" is the phrase for the first real work on a new
project: getting those documents to exist and to be true. Until they do, the
audits have nothing to audit *against*, and the suite is close to useless. That
is not a limitation to work around — it is the deal. `/bootstrap-design-docs`
exists to make it faster, not to skip it.

### Who actually reads it

*Added 2026-09-15. This does not change what the context layer is. It changes
who it is for, and therefore how complete it has to be.*

The context layer was conceived as documentation for people. Its primary reader
is now **the next agent writing code.**

An agent implementing a feature reads the code around it and infers the pattern
it should follow. Where the real pattern was written down, it follows it. Where
it was not, the agent infers a plausible one — and a second pattern now exists
where one was intended. This happens at machine speed, on every feature, in
every repository. **Design drift is no longer mostly a human failure of
discipline; it is a mechanical consequence of writing code faster than anyone
writes down why.**

Two things follow, and both sharpen rules this document already had.

**First, the prohibition on generating the context layer gets a harder reason.**
It was already true that generated context makes audits tautological. The
sharper version: an agent inferring standards from an existing codebase will
faithfully encode every inconsistency already in it — and every later agent will
then build from that. *Generate the standards from the code and drift stops
being a defect; it becomes the specification.*

**Second, "complete" now has a test.** See below.

---

## Completeness: what "enough documentation" means

The question worth answering is **"could this project be rebuilt from its
context layer alone?"** — but the obvious way to answer it does not work, and
the reason is worth recording so nobody rebuilds it later.

### The literal version is a trap

Generating a whole project from the docs and diffing the artifacts superimposes
three signals with no way to separate them: real documentation debt, the model's
own sampling variance, and drift between model versions. The number moves when
nothing changed. A metric that reports noise as a finding is the exact failure
this document's own governing principle exists to prevent, and the
spec-driven-development literature already reports spec gaps "resurfacing in
unpredictable forms upon regeneration."

The infrastructure-as-code analogy breaks at precisely the load-bearing point.
Terraform's `plan` **never re-creates anything**. It normalises declared state
and refreshed state into one typed schema and diffs *that*. The transferable
lesson is **normalise both sides into a common model** — not *regenerate and
compare*.

### The sound version: a reflexion model

This has a name and thirty years behind it — **software reflexion models**
(Murphy & Notkin, FSE '95): a declared high-level model, an explicit mapping
onto the source, and a comparison yielding three verdicts.

| Verdict | Meaning |
|---|---|
| **Convergence** | The documentation says it, and the code does it |
| **Divergence** | The code does something the documentation contradicts |
| **Absence** | The documentation says it, and **nothing in the code does it** |

Deterministic, incremental, and requiring no generation step. This project is
already close to it without having used the name: `profile.json` plus
`resolve.py` *is* a reflexion mapping. **Absence is the verdict no audit in the
catalogue currently produces** — which is the same hole found from the opposite
direction in [RFC-0002](proposals/RFC-0002-agnostic-drop-in.md) §3h, where every
existing check runs declared → disk and nothing runs disk → declared.

### Measuring a document's worth: ablation, not regeneration

The completeness question survives in a sharper, cheaper form. Instead of asking
"can the whole project be rebuilt," ask of each document:

> **Regenerate one already-shipped feature twice — once with the full context
> layer, once with this document removed. Fixed ticket, fixed model, fixed seed.
> The difference is what that document is actually worth.**

Its virtues are the ones the naive version lacks:

- **Non-determinism cancels**, because it is an A/B *within a single run* rather
  than a comparison against a remembered result. This is exactly the argument
  `bin/golden_local_ab.py`'s own docstring already makes for pixels.
- **It cannot be gamed by writing more documentation.** A document that changes
  no agent output scores zero however accurate and thorough it reads. Only
  documentation that actually determines an outcome scores at all.
- **No cold start.** It works on a project that already exists, using features
  that already shipped.
- **The output is a ranked list of which documents agents actually use** —
  an artefact this project has never had, and one worth having on its own.

### A warning from the last time this was tried

Model-driven engineering attempted round-trip generation at scale in the 2000s
and was judged neither effective nor efficient. It failed *organisationally*:
developers under delivery pressure circumvented it. The rule that follows is
firm — **regeneration stays a measurement and never becomes a delivery path.**
The suite measures whether the specification is sufficient. It does not build
your project from it.

---

## Derived collaterals

**Anything the suite generates from the context layer.** A mock API, an OpenAPI
schema, a client-readiness report, a walkthrough, this repo's own
[CATALOG.md](./CATALOG.md).

Three rules govern all of them:

1. **One direction of truth.** Derived collaterals are read from the context
   layer, never written back into it. If a generated file and a hand-written doc
   disagree, the doc wins and the generator is wrong.
2. **Source stamps.** Every derived file says what produced it and from what.
   A generated file that looks hand-written is worse than no file, because the
   next person edits it and loses the edit on the next regeneration.
3. **Disposable by design.** You can delete any derived collateral and
   regenerate it. If you cannot, it is not derived — it has quietly become part
   of the context layer, and should be moved there deliberately.

The distinction matters because **the two kinds of file need opposite
treatment.** Context layer: review it, argue about it, protect it. Derived:
regenerate it, gate it in CI, never hand-edit it.

---

## Doc roles, and role resolution

**A role is what a document *is for*, independent of where it lives.**

`design`, `flows`, `decisions`, `brand-voice`, `motion`, `pr`, `brief` — 20
roles in all on the reference project.

Skills refer to documents by role, in double-brace notation:

```
Read {{doc:design}} and check the screen inventory against the codebase.
```

Each project maps roles to its own paths in `.design-suite/docs.manifest.json`.
One project calls it `docs/DESIGN.md`; another calls it
`design/design-system.md`; a third splits it in two. The skill does not know or
care. `bin/resolve.py` turns a role into a path at run time:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design
```

This is the mechanism that took 252 hardcoded paths to **0**. It is also the
reason a skill written for a Flutter app runs unchanged on a Next.js one — the
skill never named a file.

**A role with no mapping is a loud failure, not a silent skip.** `resolve.py`
exits non-zero and says which role is unmapped. This has already caught a real
mistake: during the portability validation it rejected an invented token-source
path on a codebase nobody here had seen before, which is exactly the job.

---

## The project profile

**`.design-suite/profile.json` — every project-specific fact, in one file.**

Where the source lives. Which adapter to use. Where design tokens are defined.
Which paths are exempt from which audit, and why. The architecture rules this
project holds itself to.

The rule is: **if a tool needs to know something about your project, it reads it
here.** Nothing project-specific is allowed in a skill, a script, or the engine.
That is what makes the suite a drop-in rather than a fork.

Two things enforce it:

- **`profile.schema.json`** rejects malformed profiles — including absolute
  paths, which would work on the author's machine and nowhere else.
- **`bin/doctor.py`** goes further and proves every declared path actually
  resolves. A schema can only check that a profile is well-*formed*; the doctor
  checks whether it is *true*.

The distinction is the whole point. A profile that passes schema validation and
points at three files that were deleted last month is a profile that lies
confidently. That happened here — see **INERT**, below.

---

## Seams and adapters

**A seam is a place where language- or stack-specific knowledge is allowed to
live. An adapter is an implementation of one.**

The engine (`design_suite/engine/`) knows how to *audit*. It does not know how to
read your language. When it needs to find every colour literal, it asks the
adapter.

Three seams are defined:

| Seam | What it abstracts | Status |
|---|---|---|
| **Language** | Parsing source for tokens, copy, a11y attributes | `dart.py` ✅, `tsx.py` ✅, `web.py`, `swift.py`, `kotlin.py` (unverified) |
| **Asset** | How bundled imagery is registered with the build | `flutter_pubspec.py` ✅, `bundler.py` ✅ |
| **Scaffold** | Generating new screens in the project's idiom | `flutter.py` ✅ |

All three are implemented. The contracts still live in
`design_suite/adapters/base.py`, because a written contract is what an
implementation gets checked against.

`bundler.py` is worth singling out: it is an adapter whose job is to **refuse
correctly**. Bundler-driven stacks have no asset registry — a file is included
because something imports it — so "is this asset registered?" has no answer, and
it raises rather than inventing a boolean. Returning False would be a permanent
false finding on every asset; returning True would hide every real one.

`design_suite/adapters/verify_seam.py` runs in CI and proves the engine still
works through a non-Dart adapter with no engine changes. Without it, the seam
would rot back into Dart-shaped assumptions within a few commits and nobody
would notice until the next project tried to adopt it.

---

## Capability negotiation

**An adapter that cannot do something refuses loudly. It never returns empty.**

`tsx.py` implements token scanning. It does not implement accessibility scanning
or copy extraction. Ask it for those and it fails with a clear message naming
the missing capability.

The alternative — returning zero findings — is the failure mode this rule
exists to prevent, because **zero findings and cannot-look are indistinguishable
to the person reading the report**, and one of them means "you're fine" while
the other means "you have no idea."

This was validated against a codebase the suite had never seen: on
[`calcom/cal.com`](https://github.com/calcom/cal.com), `audit_tokens.py`
returned 20 genuine findings across 7 files, while `audit_accessibility.py` and
`extract_copy.py` correctly refused. Both outcomes were the designed one.

---

## The oracle

**Recorded audit baselines that let you prove a refactor changed nothing.**

Before the suite was pulled apart, every audit was run against the original
project and its exact output recorded to `.design-suite/baselines/` — 8 audits,
one baseline each. The token audit's baseline is 145 findings across 40 files, and
running it from the plugin against that project still reproduces exactly that.

Then, after each stage of the extraction, the same audits were re-run **from the
new location, against the same project.** Byte-identical output means the
refactor was behaviour-preserving. Anything else means it wasn't, immediately,
at the stage that caused it — instead of three phases later when the cause is
unrecoverable.

`bin/capture-baselines.sh` records and verifies. It was the acceptance test for
every phase of the decoupling, and it is the reason the extraction could be
aggressive without being reckless.

**The oracle was not sufficient on its own, twice**, which is worth knowing
before trusting one:

- The accessibility audit has a **0-finding baseline**. 0-before and 0-after
  proves nothing at all. A deliberately-broken probe file had to be planted to
  give the audit something to find — and it caught a real regression the oracle
  had reported as clean.
- A baseline can pin the wrong thing. See below.

---

## INERT, and the governing principle

One audit had been quietly skipping itself. It ran, printed nothing, exited 0.
Baselining it would have recorded "clean" forever and permanently blessed a
check that never executed.

`capture-baselines.sh` now detects this case, marks it **`INERT`**, and refuses
to record a baseline for it. An audit that cannot run is not an audit that found
nothing.

Generalised, this is the principle the whole suite is designed around:

> **An audit that reports nothing must never be indistinguishable from a clean
> codebase.**

It is the same rule as capability negotiation, as `resolve.py` exiting on an
unmapped role, as `doctor.py` proving paths resolve, as `catalog.py` failing when
a hook directory has scripts but no `hooks.json` to register them. Five
mechanisms, one idea: **silence must be impossible.** Every check either produces
a finding or produces an error. Never a shrug.

---

## Invocation tiers — `auto` and `explicit`

**Every skill declares whether Claude may run it on its own.**

- **`auto`** — Claude may invoke it from plain language, without you naming it.
  Allowed only when the skill is read-only, or confirms before it writes. Asking
  "is anything out of sync?" should just run the documentation audit. You should
  not have to know it is called `/review-docs`.
- **`explicit`** — waits for a real decision from you. Brand voice, project-wide
  conventions, generated content someone has to sign off on.

The split is a judgement about **blast radius, not about difficulty.** An audit
that reads 500 files is `auto`. A skill that writes three sentences of brand
voice is `explicit`, because those three sentences become the thing every future
copy decision is measured against.

Both fields are declared in each component's frontmatter, and
[CATALOG.md](./CATALOG.md) is generated from them, so the documented tier and
the real one cannot drift apart.

The design goal behind the tiers: **a designer should never need to memorise
skill names.** Intent in plain language should be enough for anything read-only.
Naming a command should be reserved for the things that deserve a deliberate act.

---

## Maturity — and why it is on the front page

Every component also declares one of:

| | Means |
|---|---|
| ✅ **proven** | Recorded evidence of a real end-to-end run |
| ⚪ **unverified** | **No such evidence was found. Not a claim it is broken.** It may work fine; nobody has confirmed it |
| ⚠️ **experimental** | Known rough edges. Read its own file before relying on it |
| ↗️ **pointer** | Not an implementation. Tells you where the real thing lives |

This is stated prominently rather than buried, because **"installed" and "known
to work" are different facts**, and collapsing them is how a designer ends up
trusting a skill that has never been run.

The honest position of this suite today: a majority of it is proven on one
project, some of it is proven on two, and a meaningful slice is `unverified`.
Saying so is more useful than a green badge.

---

## Three scopes, two plugins, three layers

These are different axes and get confused, so:

**Scopes** — who a thing belongs to:

| Scope | Example |
|---|---|
| Universal | Token auditing. True for any design system anywhere |
| Org | Org letterhead, our PR process, client-readiness reporting |
| Project | This app's screens, tokens, exemptions |

**Plugins** — how scopes ship. Two, not three:

- `design-suite` — universal
- `house-style` — org

Project scope is not a plugin. It is the `.design-suite/` profile in the
consuming repo. **A client-facing project installs `design-suite` alone**, and
gets no org branding or internal process baked into its tooling.

**Layers** — how the code is stacked inside the universal plugin:

```
engine/      knows how to audit, knows no language
adapters/    knows one language, knows no project
profile      knows one project, knows no logic
```

Each layer knows strictly less about specifics than the one below it names.

The stack holds **structurally**, not by discipline: the engine does not import
any adapter. Checks are handed *to* it as a parameter, so there is no code path
by which `engine/` could reach `dart.py` — verified: zero references to
`adapters` anywhere under `engine/`. `verify_seam.py` then proves the same thing
behaviourally in CI by running the engine through a non-Dart adapter.

Worth being precise about the honest limit here: **nothing greps for a forbidden
import.** If someone added `from ..adapters.dart import …` to the engine
tomorrow, `compileall` would pass and `verify_seam.py` would very likely still
pass. The guard is real but it is a behavioural one, not an import gate. (The
separate `bin/audit_layer_boundaries.py` polices the *consuming project's*
layering — its own rules, from `arch-rules.json` — not the plugin's internals.)

---

## DECIDE and DERIVED

Markers used in the documentation templates.

- **DECIDE** — a human must make this call. The template will not guess, and a
  generator will not fill it in.
- **DERIVED** — this can be produced from something already decided elsewhere.

They exist so a half-filled template is legible. Without them, a `TODO` is
ambiguous between "nobody got to this" and "this is genuinely awaiting a
decision" — and the first gets filled in carelessly while the second should
block.

---

## What the suite is not

Stated because the boundary is load-bearing:

- **Not a linter.** It checks the codebase against *your* documents, not against
  a house style it brought with it.
- **Not a decision-maker.** Every audit reports. Fixes are offered, applied only
  on confirmation, and product judgements are always flagged rather than
  resolved.
- **Not a replacement for the context layer.** It makes the context layer
  cheaper to maintain and impossible to quietly drift from. It cannot write it
  for you, and a project without one gets very little from installing this.

---

_See [CATALOG.md](./CATALOG.md) for what ships, [ADOPTING.md](./ADOPTING.md) for
putting it on a new stack._
