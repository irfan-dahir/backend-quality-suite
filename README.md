# AI Design Suite

A drop-in Claude Code plugin marketplace that checks a project's **code** against
its **documents** — and tells you where they've drifted apart.

Design-system and accessibility auditing, documentation scaffolding that stays
truthful, copy and brand-voice work, and mock-API contract automation. Built to
be installed on any project, in any language.

Two plugins — including the full 3D asset pipeline. For how much of what, read
the counts at the top of **[docs/CATALOG.md](./docs/CATALOG.md)**: they are
generated from the plugins' own frontmatter and gated by
`catalog.py --check`. A hand-written count here has now been wrong four times,
and this is the one file no gate covers, so the number lives where it can be
derived rather than being copied to a front page that cannot be checked.

---

## Start here

| | |
|---|---|
| **[ONBOARDING.md](./ONBOARDING.md)** | Designer-first. Zero to your first audit in ~20 minutes |
| **[docs/CATALOG.md](./docs/CATALOG.md)** | Every skill, agent and hook — with invocation tier and maturity. Generated from the plugins themselves, so it cannot go stale |
| **[docs/CONCEPTS.md](./docs/CONCEPTS.md)** | The vocabulary and architecture: context layer, derived collaterals, doc roles, the oracle, seams |
| **[docs/ADOPTING.md](./docs/ADOPTING.md)** | Putting it on a stack it hasn't seen, plus the real portability case study |
| **[docs/ROADMAP.md](./docs/ROADMAP.md)** | What to build next and why — a dated proposal, not a record |

---

## Install

### Requirements

**Python 3.9 or newer**, on `PATH` as `python3`. Nothing else — engine scanners
are stdlib-only, and there is no install step or dependency file. Verified
range, and how:

| Version | Status |
|---|---|
| **3.9** | The real floor, and **executed** — the full gate run (`bin/attest.py`, all 18 gates) passes on 3.9.6 |
| 3.10 | **Inferred, not executed.** Nothing in the source is incompatible, but no run has been observed |
| 3.11 | **Inferred, not executed.** `.github/workflows/validate.yml` targets it, but Actions billing is off, so that workflow is not running — see [Contributing](#contributing) |
| 3.8 and older | **Unsupported.** `str.removeprefix` is used in the engine and in `bin/`, and it does not exist before 3.9 |

3.9 is the *measured* floor rather than a declared preference: `removeprefix` is
the highest-versioned construct in the tree, and every `X | Y` annotation sits
behind `from __future__ import annotations`, so none is evaluated at runtime.
`bin/doctor.py` checks the running interpreter against this floor and refuses
rather than letting an audit die partway through on a missing stdlib method.

### Then

```bash
claude plugin marketplace add irfan-dahir/ai-design-suite
```

```bash
claude plugin install design-suite@ai-design-suite
```

| Plugin | Scope | Install into |
|---|---|---|
| **`design-suite`** | Universal engine — audits, doc scaffolding, screen scaffolding, adapters | Any project |
| **`house-style`** | Org-level conventions — client-readiness reporting, letterhead, PR reminders | Internal projects only |

Split deliberately: **a client-facing repo takes the engine without inheriting
org branding.**

Then open your project in Claude Code. The suite checks whether the project is
set up, and if not, **offers** the right next step. It writes nothing until you
say yes:

- **Existing code, not set up yet** → `/run-chain understand-existing-project`,
  a five-step guided setup that asks before every write.
- **Brand-new project** → `/onboard-new-client`.
- **Already set up** → you hear nothing.

Don't want the offer? Add an empty `.design-suite-onboarding-declined` file to
the project root, or set `DESIGN_SUITE_NO_ONBOARDING=1`.

Prefer to do it by hand? See [ONBOARDING.md](./ONBOARDING.md) step 2. Which
stacks are supported, where reports go, and how to upgrade from v0.1.0 are in
the [user guide](./docs/USER-GUIDE.md#what-happens-when-you-open-a-project).

### Outside Claude Code

Using Codex, Cursor, Copilot, Gemini CLI or another tool? Install the
`design-suite` command with `pipx install .` (or `uv tool install .`) from a
checkout — Python 3.9+, no other dependencies — then run `design-suite list`.
Same scripts, same exit codes. Details, including how it locates itself without
`${CLAUDE_PLUGIN_ROOT}`: [docs/ADOPTING.md](./docs/ADOPTING.md#install-outside-claude-code).

---

## The idea in one paragraph

Your **context layer** is the set of documents that are true because a human
decided so — design doc, flows, decisions log, brand voice. The suite never
hardcodes a path to any of them; it refers to them by **role** and resolves the
role per project. That indirection is the whole trick. It's why a skill written
for a Flutter app runs unchanged on a Next.js one, and it's what took the
reference project from **252 hardcoded documentation paths to 0** — a bigger
obstacle to reuse than anything language-specific.

Everything the suite generates is a **derived collateral**: read from the context
layer, never written back, source-stamped, and safe to delete and regenerate.

Full vocabulary in [docs/CONCEPTS.md](./docs/CONCEPTS.md).

---

## Design invariants

New components are expected to honour these:

1. **Report, never auto-fix.** Audits produce findings; a human decides. Anything
   touching brand, visual design, or copy requires an explicit decision point.
2. **One direction of truth.** Skills read the context layer and write derived
   artifacts, never the reverse.
3. **Zero dependencies.** Engine scanners are stdlib-only Python. No install step.
4. **No project literals.** A path, token name, or accepted exception in engine
   code is a bug. Everything project-specific lives in the consuming repo's
   profile.
5. **Silence must be impossible.** Every check either produces a finding or
   produces an error — never a shrug. An audit that reports nothing must never be
   indistinguishable from a clean codebase.

That fifth one is the load-bearing one, and it's enforced in five separate
places. See [the governing principle](./docs/CONCEPTS.md#inert-and-the-governing-principle).

---

## Architecture — three layers

```
plugins/design-suite/
├── commands/  agents/  hooks/  docs/   skill, agent, hook definitions + runtime refs
├── bin/                                CLI entry points; hold no language knowledge
└── design_suite/
    ├── engine/     LAYER 1  stdlib-only, zero project literals, imports no adapter
    ├── adapters/   LAYER 2  the stack seams — dart.py, tsx.py, web.py, swift.py, kotlin.py
    └── project.py           resolves the project under audit

<consuming repo>/.design-suite/         LAYER 3  data only, no code
├── profile.json           adapter choice, source globs, token source, exemptions
├── docs.manifest.json     role → path map
└── baselines/             recorded audit output (the oracle)
```

Each layer knows strictly less about specifics than the one below it names. The
engine takes checks as a parameter and imports no adapter, so there's no path by
which it could reach `dart.py`; `verify_seam.py` proves that behaviourally in CI.

---

## Honest status

- **All three seams implemented.** Language (`dart`, `tsx`, `web`, `swift`, `kotlin`), asset
  (`flutter_pubspec`, `bundler`), scaffold (`flutter`). `dart` does tokens,
  focus order and reduced motion; `tsx` does tokens — including Tailwind arbitrary
  values — and **refuses the rest by name** rather than returning empty. `web`
  (unverified — measured once on five public projects, see
  [the measurement](./docs/MEASUREMENT-2026-10-08-web-adapter.md)) extends `tsx` to Vue/Svelte SFCs and
  CSS/SCSS stylesheets. `swift` (SwiftUI/UIKit) and `kotlin` (Jetpack Compose),
  also unverified, do tokens, reduced motion and the adapter-pattern audit, and
  refuse the rest by name.
- **Two audits are switched off**, and the README says so rather than letting
  them pad the list above. `audit_accessibility` and `audit_copy` are `disabled`
  in `design_suite/engine/audit_discovery.DISABLED` — measured false-positive
  rates of 100% and 73% on real consumer projects (issues #104, #109). They
  **refuse with exit 2** rather than exiting 0, so nothing baselines them as
  clean. `dart` still implements `a11y_checks` and copy extraction; the audits
  on top of them are off, and that is the honest way round to state it. Each
  entry carries its measured evidence and the bar for re-enabling it.
- **One adapter exists to refuse correctly.** `bundler` covers stacks with no asset
  registry, where "is this registered?" has no answer, and raises instead of
  inventing a boolean.
- **Validated on a second, real codebase** — read-only against
  [`calcom/cal.com`](https://github.com/calcom/cal.com): 20 genuine token
  findings, two skills correctly refusing, and one real coverage gap found and
  named. That gap — Tailwind utility classes being invisible to `tsx.py` — is now
  closed: arbitrary values like `h-[17px]` are audited, while scale references like
  `h-4` are correctly left alone. Details in
  [docs/ADOPTING.md](./docs/ADOPTING.md#case-study-a-real-typescript-codebase).
- **Maturity is declared per component**, and a meaningful slice is ⚪
  `unverified` — meaning no evidence of an end-to-end run was found, not that
  it's broken. Read the column in [docs/CATALOG.md](./docs/CATALOG.md) before
  relying on a skill. "Installed" and "known to work" are different facts.
- **`house-style` carries its own minimal resolver.** It cannot call
  `design-suite`'s — the plugin cache nests each plugin under its own version
  hash, so no sibling-relative path is stable. `bin/resolve_role.py` re-reads the
  manifest and mirrors the exit-code contract; it is parity-tested against the
  real resolver, and its docstring explains why the duplication is deliberate.

---

## Contributing

CI (`.github/workflows/validate.yml`) gates every change. The gates are each a
named step in that file, and it is the list itself that is authoritative — this
paragraph deliberately does not restate it or count it, because a second copy of
a list is a second thing to keep in sync. To see what runs, and to run it:

```bash
python3 plugins/design-suite/bin/gates.py          # -k filters; a filter matching nothing exits 2
```

It parses the workflow, so it names every gate and says which it could not run
rather than dropping it. 🔴 Actions billing is off, so CI itself is not running —
a missing check is not a pass; run the gates locally.

Two of those gates exist because the failure already happened here — a catalogue
claim that was wrong three times, and a release where every skill in the plugin
cited a script path that had moved. Read the comments in the workflow before
removing either.

**One known-red, documented:** two test files pin regression fixture revisions
from this suite's upstream lineage that this repository's history does not
carry, so they fail here rather than silently skipping — the cases and the
reason are named in [CLAUDE.md](./CLAUDE.md) rule 3. Every other gate must
pass; those named failures are this fork's clean.

Regenerate the catalogue after adding or changing a component:

```bash
python3 plugins/design-suite/bin/catalog.py
```

---

## Licence

MIT — see [LICENSE](./LICENSE). Copyright (c) 2026 Irfan Dahir. Both plugin
manifests carry `"license": "MIT"`.
