# Onboarding

**For developers. No prior knowledge of this suite assumed.** About 20 minutes to your
first real audit.

If you want the concepts before the commands, read
[docs/CONCEPTS.md](./docs/CONCEPTS.md) first. If you want to know what you're
installing, that's [docs/CATALOG.md](./docs/CATALOG.md).

---

## What you're getting

A set of Claude Code skills that check your project's **code** against your
project's **documents** — and tell you where they've drifted apart.

Not a linter. It has no opinions about your API's style. It only knows how to
check whether the code still matches what you already wrote down.

That last part matters, so it's worth saying plainly before you install
anything: **the suite is only as useful as your documents are.** On a project
with a real API doc and API standard, it's genuinely good. On a project with no
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
claude plugin marketplace add irfan-dahir/backend-quality-suite
```

Then install. **Which one you want depends on the project:**

| Project | Install |
|---|---|
| Internal (your org's own) project | Both |
| Client-facing project | `backend-suite` **only** |

```bash
claude plugin install backend-suite@backend-quality-suite
```

```bash
claude plugin install house-style@backend-quality-suite
```

The house-style plugin carries your org's letterhead, our PR process, and
client-readiness reporting. Keeping it out of a client repo keeps our internal
process out of their tooling.

Confirm it worked:

```bash
claude plugin details backend-suite@backend-quality-suite
```

You should see `Skills (28)`, `Agents (2)`, `Hooks (2)` for `backend-suite` — the
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
    "backend-quality-suite": {
      "source": { "source": "github", "repo": "irfan-dahir/backend-quality-suite" }
    }
  },
  "enabledPlugins": {
    "backend-suite@backend-quality-suite": true,
    "house-style@backend-quality-suite": true
  }
}
```

Both are **objects keyed by identifier**, not arrays. Worth stating because
getting this wrong fails quietly — the plugin just doesn't load, with no error.

> **The repo is public.** Anyone can install from `irfan-dahir/backend-quality-suite`
> without an account. Committing the blocks above makes the plugin automatic for
> people who have the repo's `enabledPlugins`/marketplace references in place;
> if `marketplace add` still fails on auth, it is a transient GitHub auth issue,
> not missing access — check `gh auth status` and retry.

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
project root, or set `BACKEND_SUITE_NO_ONBOARDING=1` to turn it off everywhere.
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

> set up the backend suite for this project

It will read your repo and draft both files. **Review the draft** — this is the
part where being wrong costs you later, and it is guessing about your project
from the outside.

Faster start, same review obligation — scaffold all six config files (plus a
`.gitignore` and a local copy of the profile schema) from templates instead of
hand-copying them from another project:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --name "My Project"
```

This writes `.backend-suite/profile.json`, `docs.manifest.json`,
`exceptions.json`, `arch-rules.json`, `hooks.map.json`, and
`known-traps.json`, plus the `.gitignore`, each
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
decided so: the API doc, the API standard, the decisions log, the deprecation
ledger. Not generated, not derived — written.

Everything the suite does is check the codebase against it, or generate something
from it.

**If your project already has these documents**, map them to roles in
`docs.manifest.json` (Step 2 drafted this) and go to Step 4.

**If it doesn't**, you need to build the context layer first:

```
/bootstrap-api-docs
```

This scaffolds the documents from templates. Two markers appear throughout:

- **DECIDE** — a human has to make this call. It will not be guessed or filled in.
- **DERIVED** — this can be produced from something already decided elsewhere.

Every `DECIDE` is genuinely yours. Working through them *is* building the context
layer, and it's the highest-value hour you'll spend on this — not overhead before
the real work.

> `/bootstrap-api-docs` is marked ⚪ **unverified** in the catalogue: nobody
> has confirmed an end-to-end run of it. It may work fine. Read what it produces
> rather than trusting it.

---

## Step 4 — Your first audit

```
/audit-doc-staleness
```

This finds where the code and the documents disagree — an endpoint that exists
but isn't in the API doc, a documented endpoint whose shape changed, a decision
the code never implemented. It's the best first audit because it is the suite's
core idea made concrete, and it needs nothing from you but the profile and the
doc-role map from Step 3.

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
  precedent: the API standard, project-wide conventions, generated content someone
  signs off on.

The line is **blast radius, not difficulty.** An audit reading 500 files is
`auto`. A skill writing three sentences of the API standard is `explicit`, because
those three sentences become the rule every future endpoint is measured
against.

[CATALOG.md](./docs/CATALOG.md) lists the tier for every component — 36 of them
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

Honest position today: this fork's own gate run is the only end-to-end evidence
that exists; no consumer project has been audited yet, so a real slice of the
catalogue is `unverified` — and the maturity column, not this sentence, is the
authority.

---

## What shipped language adapters look like

Three language adapters ship: `php` (Laravel/Lumen, Symfony, plain PHP), `node`
(Express, Fastify, NestJS, Hono, Koa, AdonisJS), and `rust` (Axum, Actix Web,
Rocket, Poem, Warp) — see [docs/ROADMAP.md](./docs/ROADMAP.md). Go and Python
are planned. `/survey` proposes `adapters.lang` for a project when it can
resolve one; a project whose stack has no adapter yet leaves the field unset.

The documentation audits work on any stack today: they read the profile and the
doc roles, not source code — `audit-doc-staleness`, `audit-proposal-status`,
`audit-claude-md-drift`, `audit-prose-flags`. `audit-mock-api` works too, once
a mock-API contract is configured (`/sync-mock-api` scaffolds one).

The code-shape audits — `audit-error-handling`, `audit-api-consistency`,
`audit-contract-headers`, `audit-layer-boundaries` — **refuse with exit 2**
naming the missing adapter, rather than returning nothing.

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
| `marketplace add` fails on auth | The repo is public, so an auth failure is a transient GitHub issue — check `gh auth status` and retry; installs need no elevated access |
| A script dies on `'str' object has no attribute 'removeprefix'` | `python3` is older than 3.9. Run the backend-suite doctor, which names this directly |
| Plugin installs but no skills appear | `extraKnownMarketplaces`/`enabledPlugins` written as arrays. They're objects |
| An audit reports a path that doesn't exist | Stale `profile.json`. Ask Claude to run the backend-suite doctor |
| A skill says a role is unmapped | That role isn't in `docs.manifest.json`. It exits rather than guessing — add the mapping |
| A skill refuses with a capability message | Your adapter doesn't implement that check. Expected, not a bug — see ADOPTING.md |
| "no .backend-suite/ in this project … nothing is checked on edit" | The project isn't set up, so on-save checks aren't running. Shown once per session. Set the project up to make it go away |
| A tool exits 2 naming two paths | You're in a git repo nested inside another, and the inner one isn't set up. Set it up, or run from the outer project |
| An audit printed nothing to a findings file | Most audits write one only when passed `--findings`; the run's last line names the path when it does |

---

## Where to go next

| | |
|---|---|
| [docs/CATALOG.md](./docs/CATALOG.md) | Every skill, agent, and hook — with tier and maturity. Generated, never stale |
| [docs/CONCEPTS.md](./docs/CONCEPTS.md) | The vocabulary and the architecture, and why each piece exists |
| [docs/ADOPTING.md](./docs/ADOPTING.md) | Putting it on a stack it hasn't seen |
