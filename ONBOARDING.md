# Onboarding

**For designers. No engineering background assumed.** About 20 minutes to your
first real audit.

If you want the concepts before the commands, read
[docs/CONCEPTS.md](./docs/CONCEPTS.md) first. If you want to know what you're
installing, that's [docs/CATALOG.md](./docs/CATALOG.md).

---

## What you're getting

A set of Claude Code skills that check your project's **code** against your
project's **documents** — and tell you where they've drifted apart.

Not a linter. It has no opinions about your design system. It only knows how to
check whether the app still matches what you already wrote down.

That last part matters, so it's worth saying plainly before you install
anything: **the suite is only as useful as your documents are.** On a project
with a real design doc and flows doc, it's genuinely good. On a project with no
documentation, it will find almost nothing, because there's nothing to check
against. Step 3 below is where you deal with that.

---

## Step 1 — Install (5 minutes)

**Before you start, one thing that is not optional:**

**Python 3.9 or newer**, on your `PATH` as `python3`:

```bash
python3 --version
```

That is the whole dependency list — the scanners are stdlib-only, so there is no
`pip install` step. 3.9 is where the full gate run has actually been executed;
3.10 and 3.11 should work and have not been observed. **3.8 and older will
fail**, partway through an audit rather than at startup, which is why
`doctor.py` (step 3) checks the interpreter and refuses. macOS ships 3.9, so the
system `python3` is usually enough.

Two plugins live in one marketplace. Add the marketplace:

```bash
claude plugin marketplace add irfan-dahir/ai-backend-suite
```

Then install. **Which one you want depends on the project:**

| Project | Install |
|---|---|
| Internal (your org's own) project | Both |
| Client-facing project | `backend-suite` **only** |

```bash
claude plugin install backend-suite@ai-backend-suite
```

```bash
claude plugin install house-style@ai-backend-suite
```

The house-style plugin carries your org's letterhead, our PR process, and
client-readiness reporting. Keeping it out of a client repo keeps our internal
process out of their tooling.

Confirm it worked:

```bash
claude plugin details backend-suite@ai-backend-suite
```

You should see `Skills (41)`, `Agents (4)`, `Hooks (2)` for `backend-suite` — the
counts the plugin's own files carry. Don't trust this sentence over the
plugin: `docs/CATALOG.md` is generated from that same frontmatter
(`python3 plugins/backend-suite/bin/catalog.py`) and states the current totals
across both plugins.

### Committing it for the team

Installing puts the config in *your* settings. To make it automatic for everyone
on the repo, commit these two blocks into the project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "ai-backend-suite": {
      "source": { "source": "github", "repo": "irfan-dahir/ai-backend-suite" }
    }
  },
  "enabledPlugins": {
    "backend-suite@ai-backend-suite": true,
    "house-style@ai-backend-suite": true
  }
}
```

Both are **objects keyed by identifier**, not arrays. Worth stating because
getting this wrong fails quietly — the plugin just doesn't load, with no error.

> **The repo is private, permanently.** Anyone installing — including anyone
> who picks up the repo from this committed config — needs their own read access
> to `irfan-dahir/ai-backend-suite`. Committing the blocks above makes the
> plugin automatic for people who *have* access; it does not grant it. If
> `marketplace add` fails on auth, that's what it is — request access rather
> than debugging the command.

---

## Step 2 — Tell it about your project (10 minutes)

**Usually the suite offers this for you.** Open the project in Claude Code. If it
has code but no `.backend-suite/` folder, Claude offers
`/run-chain understand-existing-project`. That is a guided setup: survey the
project, create the config from the survey, suggest which document plays which
role, then draft any missing docs. It asks before every step that writes. On a
brand-new project with no code yet, it offers `/onboard-new-client` instead. An
already-configured project hears nothing.

Don't want the offer? Add an empty `.backend-suite-onboarding-declined` file at the
project root, or set `DESIGN_SUITE_NO_ONBOARDING=1` to turn it off everywhere.
The steps are described in full in the
[user guide](./docs/USER-GUIDE.md#setting-up-an-existing-project-step-by-step).

The rest of this step is the manual route, and what the guided setup is doing
for you underneath.

Everything project-specific goes in one directory in *your* repo:

```
.backend-suite/
├── profile.json          where things are, which adapter, what's exempt
├── docs.manifest.json    which of your files plays which documentation role
└── baselines/            recorded audit output (created later, not now)
```

Ask Claude:

> set up the design suite for this project

It will read your repo and draft both files. **Review the draft** — this is the
part where being wrong costs you later, and it is guessing about your project
from the outside.

Faster start, same review obligation — scaffold all eight config files (plus a
`.gitignore` and a local copy of the profile schema) from templates instead of
hand-copying them from another project:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --name "My Project"
```

This writes `.backend-suite/profile.json`, `docs.manifest.json`,
`design-audit-config.json`, `exceptions.json`, `arch-rules.json`,
`hooks.map.json`, `known-traps.json`, and `component-capabilities.json`, each
with `TODO` markers instead of a guessed value — it does
not decide anything on your project's behalf, it just gives you the *shape* to
fill in. Templates live at
[`plugins/backend-suite/templates/dot-backend-suite/`](./plugins/backend-suite/templates/dot-backend-suite/).
`--force` overwrites files that already exist; `--only profile.json` writes a
subset. Then check its work:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py"
```

(`${CLAUDE_PLUGIN_ROOT}` is filled in for you when Claude runs a skill. If you're
running it yourself in a plain terminal, ask Claude for the path — it's inside
the plugin cache, not your repo.)

The doctor proves every path in your profile actually resolves. A profile can be
perfectly well-formed and point at three files that were deleted last month —
that has really happened here, which is why the doctor exists.

Fix anything it reports before moving on. **Do not skip this step.** Every audit
downstream reads this profile; a wrong profile produces confident wrong results
rather than errors.

Then find out which skills can actually run here, before trying them one at a time:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/preflight.py"
```

Every skill is checked against your project: each document role it needs, each
directory role, each script. You get a per-skill ✅ or 🔴 with the specific thing
that is missing.

A ✅ means the skill will not stop on a missing precondition. It is **not** a claim
the output is correct — that is what the maturity column means, and preflight does
not upgrade it.

---

## Step 3 — The context layer

This is the concept the whole suite rests on, so it gets a name.

Your **context layer** is the set of documents that are true because a human
decided so: the design doc, the flows doc, the decisions log, the brand voice
guide. Not generated, not derived — written.

Everything the suite does is check the codebase against it, or generate something
from it.

**If your project already has these documents**, map them to roles in
`docs.manifest.json` (Step 2 drafted this) and go to Step 4.

**If it doesn't**, you need to build the context layer first:

```
/bootstrap-design-docs
```

This scaffolds the documents from templates. Two markers appear throughout:

- **DECIDE** — a human has to make this call. It will not be guessed or filled in.
- **DERIVED** — this can be produced from something already decided elsewhere.

Every `DECIDE` is genuinely yours. Working through them *is* building the context
layer, and it's the highest-value hour you'll spend on this — not overhead before
the real work.

> `/bootstrap-design-docs` is marked ⚪ **unverified** in the catalogue: nobody
> has confirmed an end-to-end run of it. It may work fine. Read what it produces
> rather than trusting it.

---

## Step 4 — Your first audit

```
/audit-tokens
```

This finds hardcoded values that should be design tokens — raw hex colours,
literal spacing numbers, one-off radii. It's the best first audit because it's
the one with the most recorded evidence behind it, and it needs nothing from you
but the profile.

You'll get findings grouped by file with line numbers. **It will not fix
anything.** Every audit in the suite reports; fixes are offered and applied only
when you confirm.

Then try asking in plain language, without naming a command:

> is anything in our docs out of sync with the code?

That should just run the documentation audit. Which brings us to the one rule
worth internalising.

---

## You don't need to memorise command names

Every skill declares whether Claude may run it on its own:

- **`auto`** — Claude runs it from plain language, unprompted. Safe because it's
  read-only, or it asks before writing. Say what you want; don't look up a
  command.
- **`explicit`** — you have to name it. Reserved for things that set a
  precedent: brand voice, project-wide conventions, generated content someone
  signs off on.

The line is **blast radius, not difficulty.** An audit reading 500 files is
`auto`. A skill writing three sentences of brand voice is `explicit`, because
those three sentences become the standard every future copy decision is measured
against.

[CATALOG.md](./docs/CATALOG.md) lists the tier for every component — 47 of them
at the time of writing, but read the count there rather than here: that file is
generated from the components' own frontmatter, and this sentence is not.

---

## Read the maturity column

The catalogue marks every component:

| | Means |
|---|---|
| ✅ **proven** | Recorded evidence of a real end-to-end run |
| ⚪ **unverified** | **No such evidence found — not a claim it's broken.** May work fine; nobody has confirmed it |
| ⚠️ **experimental** | Known rough edges. Read its own file first |
| ↗️ **pointer** | Not an implementation. Tells you where the real thing is |

This is on the front page on purpose. **"Installed" and "known to work" are
different facts**, and a green badge over both is how you end up trusting a skill
that has never run.

Honest position today: most of the suite is proven on one project, some on two,
and a real slice is `unverified`.

---

## What to expect on a non-Flutter project

Five language adapters exist. Set yours as `adapters.lang` in the profile —
`/survey` suggests one.

| Adapter | For | Audits that work |
|---|---|---|
| `dart` | Flutter | All source audits (except accessibility and copy, which are switched off for everyone) |
| `tsx` | React / TypeScript | tokens, adapter pattern, layer boundaries, error handling |
| `web` *(unverified)* | React/TS plus Vue, Svelte, CSS/SCSS | tokens, adapter pattern, layer boundaries |
| `swift` *(unverified)* | SwiftUI / UIKit | tokens, reduced motion, adapter pattern |
| `kotlin` *(unverified)* | Jetpack Compose | tokens, reduced motion, adapter pattern |

Every other audit **refuses** on that stack with exit code 2 and a message
saying why, rather than returning nothing.

That refusal is deliberate. **Zero findings and cannot-look are
indistinguishable in a report**, and one means "you're fine" while the other
means "you have no idea." So it errors instead. Exit 2 means "could not check" —
never treat it as a pass.

Details, and what to do when no adapter fits your stack, are in
[docs/ADOPTING.md](./docs/ADOPTING.md).

---

## If something breaks

| Symptom | Cause |
|---|---|
| `marketplace add` fails on auth | The marketplace is public — an auth failure is local credentials or network, not missing access. Check `gh auth status` and retry |
| A script dies on `'str' object has no attribute 'removeprefix'` | `python3` is older than 3.9. Run the backend-suite doctor, which names this directly |
| Plugin installs but no skills appear | `extraKnownMarketplaces`/`enabledPlugins` written as arrays. They're objects |
| An audit reports a path that doesn't exist | Stale `profile.json`. Ask Claude to run the backend-suite doctor |
| A skill says a role is unmapped | That role isn't in `docs.manifest.json`. It exits rather than guessing — add the mapping |
| A skill refuses with a capability message | Your adapter doesn't implement that check. Expected, not a bug — see ADOPTING.md |
| "no .backend-suite/ in this project … nothing is checked on edit" | The project isn't set up, so on-save checks aren't running. Shown once per session. Set the project up to make it go away |
| A tool exits 2 naming two paths | You're in a git repo nested inside another, and the inner one isn't set up. Set it up, or run from the outer project |
| Old `scripts/*_findings.json` or `token_pipeline/findings.json` stopped updating | Reports moved into `.backend-suite/` (git-ignored). See [Upgrading from v0.1.0](./docs/USER-GUIDE.md#upgrading-from-v010) |

---

## Where to go next

| | |
|---|---|
| [docs/CATALOG.md](./docs/CATALOG.md) | Every skill, agent, and hook — with tier and maturity. Generated, never stale |
| [docs/CONCEPTS.md](./docs/CONCEPTS.md) | The vocabulary and the architecture, and why each piece exists |
| [docs/ADOPTING.md](./docs/ADOPTING.md) | Putting it on a stack it hasn't seen |
