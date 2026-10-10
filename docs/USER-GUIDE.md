# User guide

For the person using the suite on a project, rather than working on the suite
itself. It assumes you have a repository, a terminal, and Claude Code.

Other documents, so you know when to leave this one:
[ONBOARDING.md](../ONBOARDING.md) is the 20-minute install;
[CATALOG.md](./CATALOG.md) is the full generated list of what ships;
[CONCEPTS.md](./CONCEPTS.md) explains why the suite is built the way it is;
[ADOPTING.md](./ADOPTING.md) covers a stack it has not seen before.

---

## What this is

A set of Claude Code skills that read your code and compare it to your own
design documents. Where the two disagree, you get a list.

It finds things like a hex colour written by hand instead of a token, a screen
that does not match the design doc, a mock API whose fixture and docs have
drifted apart, a component nobody documented.

Three things it deliberately does not do:

- **It does not fix anything.** Audits print findings. You decide.
- **It has no opinions of its own.** It checks your code against your documents.
  If you did not write it down, there is nothing to check against.
- **It never says "clean" when it could not look.** If a check cannot run here,
  it says so and stops. See [When it refuses](#when-it-refuses-to-run).

---

## Do I need this?

Four questions. If you answer no to all four, the suite will find almost
nothing, and you should not adopt it.

1. **Do you have design documents, or want them?** The suite checks code against
   documents. No documents, nothing to check against.
2. **Is more than one person writing UI code?** A single author holds the
   conventions in their head. A team does not, and that is the gap this fills.
3. **Do you have design tokens, or a palette, or a component library?** If every
   colour in the codebase is written by hand on purpose, a token audit is noise.
4. **Does the project outlive the current sprint?** The value is in catching
   drift over months. On a two-week prototype there is no drift yet.

It is **not** the right tool for: linting (use your linter), formatting (use your
formatter), runtime accessibility testing against a rendered tree (the suite reads
source only), visual regression testing of screenshots (see `/golden-local-ab`,
which compares renders you already produce, not a hosted service), or deciding
what your design system should be. It has no opinions of its own — see
[What this is](#what-this-is).

If you try it and it is not for you, [Removing it](#removing-it) is two commands.

---

## Your first five minutes

If you open an unconfigured project in Claude Code, the suite offers to set it
up for you — see [What happens when you open a project](#what-happens-when-you-open-a-project).
This section is the manual route.

There is no zero-configuration run. The suite refuses to guess which directory
holds your UI code or which language adapter reads it, because a wrong guess
produces a confident clean report on the wrong files — see
[When it refuses to run](#when-it-refuses-to-run). So the shortest honest path is
one install, one scaffold, three fields, one audit.

```bash
claude plugin marketplace add irfan-dahir/ai-design-suite
claude plugin install design-suite@ai-design-suite
python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --name "My Project"
```

Open `.design-suite/profile.json` and fill in exactly three things. Leave every
other `TODO` alone for now:

| Field | Example value |
|---|---|
| `adapters.lang` | `"tsx"` |
| `source.root` | `"src"` |
| `source.fileGlob` | `"**/*.tsx"` |

Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_tokens.py"
```

Real output, on a project with one component and one token file:

```
Found 3 hardcoded-value findings across 2 files → .design-suite/tokens-findings.json
```

**What success looks like.** Three specific things, in order:

- **A non-zero exit code.** `1` means it ran and found something. `0` means it
  ran and found nothing. `2` means it could not run, and is not a pass. Check it
  with `echo $?`.
- **A findings file you can open**, naming a file, a line, and the text it
  matched — the shape shown under [Job 1](#job-1--find-hardcoded-design-values).
- **A finding you recognise as true.** Open the first one. If it is a real
  hardcoded value in a file you know, the audit is looking at the right tree.

**Confirm it can actually fail.** A 0-finding result proves nothing on its own,
because a check that is broken and a codebase that is clean print the same thing.
So once, deliberately, paste a hex colour into a file under your source root and
re-run. Findings should go up by one. Then take it out again and watch them go
back down:

```
Found 0 hardcoded-value findings across 0 files → .design-suite/tokens-findings.json
```

That round trip is the whole argument for trusting anything else in this guide.
Five minutes, and you now know the suite can both see your code and tell you when
it cannot.

---

## What happens when you open a project

You do not have to remember a command to get started. When a Claude Code
session starts (or after `/clear`), the suite takes a quick look at the folder
and decides which of these it is. It **reads only — it never writes a file at
this point.**

| What it finds | What you will see |
|---|---|
| **Configured** — `.design-suite/profile.json` exists | Nothing. You are set up. |
| **New** — no source code anywhere yet | Claude offers `/onboard-new-client`, the setup for a brand-new project. |
| **Existing** — source code, but no `.design-suite/` folder | Claude offers `/run-chain understand-existing-project`, a guided setup (below). |
| **Half set up** — `.design-suite/` exists, but no `profile.json` | Claude says most skills will refuse, and suggests `doctor.py` or resuming the guided setup. |
| **Can't tell** — a home folder, an unreadable folder, or one too big to check quickly | Claude says it could not tell and suggests nothing. If you ask about setup, it asks you which case applies. |

It is only an offer. Nothing starts until you say yes. If you say no, Claude
won't bring it up again in that session.

**To switch the offer off for good:**

- **For one project:** create an empty file called
  `.design-suite-onboarding-declined` in the project root. You can also ask
  Claude to stop reminding you, and it will create the file. It never creates it
  unless you ask.
- **For everything on your machine:** set the environment variable
  `DESIGN_SUITE_NO_ONBOARDING=1`.

### The "not configured" notice

The suite's other hooks run after Claude edits a file. In a project that isn't
set up, they now tell you that **once per session**:

```
design-suite: no .design-suite/ in this project — the suite is installed but no
on-save audits are configured, so nothing is checked on edit (this is not a
clean result).
```

This is not an error. It is there so you don't mistake "nothing was checked"
for "nothing was wrong". It goes away once the project is set up and its
`.design-suite/hooks.map.json` lists the audits you want run on save.

---

## Setting up an existing project, step by step

`/run-chain understand-existing-project` runs five steps in order. It stops and
asks before every step that writes. It also remembers where it got to, so you
can stop and pick up in a later session by running the same command again.

| # | Step | What it does | Writes | Asks first? |
|---|---|---|---|---|
| 1 | `/survey` | Works out your stack, where the source lives, which files might hold your design tokens, and which documents you have. It also lists what it *couldn't* work out — read that list. | `.design-suite/survey.json` | Yes |
| 2 | `init.py --from-survey`, then `/map-project` | Creates the `.design-suite/` config, pre-filled from the survey. Then suggests which document is your design doc, what kind of project this is, and which file is the real token source. | `.design-suite/` config files | Yes, for each half |
| 3 | `/bootstrap-design-docs` | Drafts missing context documents from what is already built, one at a time. You accept or decline each one. Skipped if you already have the documents. | The documents you accept | Yes, per document |
| 4 | `/propose-config` | Reads your code and proposes real values for config sections setup left as `TODO` (layer rules, adapter pattern, animated widgets, colour names), each with the evidence behind it. Proposes nothing where the evidence is weak. | Only the sections you approve, marked `inferred` | Yes, per section |
| 5 | `/repo-health` | Runs every audit once and records where the project starts: which audits work, which find things, which refuse. | Reports inside `.design-suite/` only (git-ignored) | No — it only reports |

Everything step 2 fills in is marked **`inferred`**: it is the machine's guess.
No check treats a guess as trusted until a person approves it with `/ratify`.
`doctor.py` lists the fields still waiting for approval.

To check how far you have got without running anything:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/chain.py" status understand-existing-project
```

---

## Which stacks it can read

The documentation skills (`/review-docs`, `/sync-docs`, `/bootstrap-design-docs`,
`/survey`, the resolver) work on any project. Audits that read **source code**
need an adapter for your language, set as `adapters.lang` in
`.design-suite/profile.json`. `/survey` suggests one for you.

| Adapter | For | Audits that work | Trust level |
|---|---|---|---|
| `dart` | Flutter | All source audits, except the two currently switched off (accessibility, copy) | Most tested |
| `tsx` | React / TypeScript (`.tsx`, `.ts`, `.jsx`, `.js`) | tokens, adapter pattern, layer boundaries, error handling | Checked read-only on one large real codebase |
| `web` | React/TS plus Vue, Svelte, CSS/SCSS/Sass/Less | tokens, adapter pattern, layer boundaries | Unverified — measured on 5 public projects, not yet enough |
| `swift` | SwiftUI / UIKit | tokens, reduced motion, adapter pattern | Unverified |
| `kotlin` | Jetpack Compose | tokens, reduced motion, adapter pattern | Unverified |

Any audit not listed for your adapter **refuses** and tells you why. It does not
quietly report zero.

When scanning, audits skip vendor and build folders (`node_modules`, `.next`,
`dist`, and similar). Each skip is printed, so you can see what was left out.

### "Exit 2" or "could not check" — what it means for you

Every audit ends with one of three results:

| Exit code | Means | What to do |
|---|---|---|
| `0` | It ran and found nothing | Nothing. |
| `1` | It ran and found things | Read the report. |
| `2` | **It could not check** | Read the message. It names what is missing. |

Exit 2 is **not a pass, and not a list of problems**. It means the audit didn't
look. The usual reasons:

- **Your stack isn't supported by that audit** (see the table above). Nothing
  is wrong with your project; that audit just can't help you yet.
- **A config section is missing**, for example the `arch-rules.json` section
  the audit reads. Fill it in, or ask Claude to run `doctor.py`.
- **You are in a git repo inside another one, and the inner one isn't set up.**
  Set up the inner repo, or run from the outer one if that's what you meant to
  check.
- **The audit is switched off** (accessibility and copy, for now).

If a script or CI step reads these exit codes, make it treat 2 as a failure you
need to look at, never as a pass.

---

## Where reports go

Audits save their raw reports inside `.design-suite/`, for example:

- `.design-suite/tokens-findings.json`
- `.design-suite/adapter-pattern-findings.json`
- `.design-suite/layer-boundaries-findings.json`
- `.design-suite/reduced-motion-findings.json`
- `.design-suite/findings/` (the common format every audit writes)

These are **ignored by git** through `.design-suite/.gitignore`, which
`init.py` creates. They are kept out of git because reports quote lines of your
source code. You can delete them at any time; the next run makes them again.

What you *do* commit in `.design-suite/` is the config you wrote:
`profile.json`, `docs.manifest.json`, `exceptions.json`, `baselines/`, and the
rest.

---

## Upgrading from v0.1.0

The next release changes a few things that can affect scripts and CI. The full
list, with the reason for each, is in
[CHANGELOG.md — Unreleased › Breaking](../CHANGELOG.md#unreleased). In
practice:

- [ ] **Delete the old report files**, or untrack them with `git rm --cached`:
      `token_pipeline/findings.json` (or `<pipelines.tokens>/findings.json`),
      `scripts/adapter_pattern_findings.json` and
      `scripts/layer_boundaries_findings.json`. The audits no longer update
      them, so they would just go stale.
- [ ] **Update anything that read those paths** (scripts, CI steps, hook
      entries) to the new `.design-suite/…-findings.json` names. Or pass `--out`
      with the old path to keep it.
- [ ] **Add the new names to `.design-suite/.gitignore`** if yours was created
      before this release: `tokens-findings.json`,
      `adapter-pattern-findings.json`, `layer-boundaries-findings.json`. New
      projects already get them.
- [ ] **Treat exit 2 as "could not check"** everywhere you grade audits by exit
      code. Several refusals that used to exit 1 now exit 2.
- [ ] **Nested repos:** if you run the tools from a git repo inside another
      one, the inner repo now needs its own setup, or the tools refuse.
- [ ] Run `doctor.py` once afterwards to confirm the project still resolves.

---

## Does it send my code anywhere?

The short answer: **the scripts do not, and Claude does.**

**The audit scripts are local.** They are standard-library Python that reads files
off your disk and writes findings back to your disk. Exactly one script in the
whole plugin opens a network connection — `deploy_docs_site.py`, which publishes a
documentation site and only runs when you ask it to. No audit, no doctor, no
survey, no preflight makes a request. You can check for yourself:

```bash
grep -rl "urllib\|requests" "${CLAUDE_PLUGIN_ROOT}/bin"
```

**The skills are prompts, so they go through the model.** Most of the suite is not
a script at all: it is instructions for Claude. When you ask Claude to audit a
screen, Claude reads that screen, and that content goes to the model the same way
any other Claude Code session's does. Nothing about the suite changes your
existing data-handling posture — but nothing about it exempts you from it either.
If the rule on a client repository is that source does not go to a model, that
rule applies here, and the script-only paths in this guide are the parts that
still work under it.

**Findings quote your source.** A token finding's `snippet` is a literal line of
your code, and the literals a token audit greps for are the same shape a
hardcoded credential has. That is why the scaffolded `.design-suite/.gitignore`
ignores the findings and evidence directories by default: committing them would
publish code excerpts into the repository's history, which is not a decision a
scaffolder should make on a team's behalf. If you deliberately want a finding to
be durable, that belongs in an authored file — a baseline or an accepted
exception — not in regenerable output that happened to get committed. Read the
comments in that `.gitignore`; they say which files are which.

---

## Getting it onto your project

### 1. Install the plugin

```bash
claude plugin marketplace add irfan-dahir/ai-design-suite
claude plugin install design-suite@ai-design-suite
```

On an internal org project, also install `house-style@ai-design-suite`.
On a client-facing repo, install `design-suite` only — the house-style plugin
carries our letterhead and PR process, which a client repo should not inherit.

### Which version you are running

**In CI, pin a tag.** A checkout of the suite with no `ref:` tracks its `main`,
so every merge into the suite lands in your build unreviewed. Pin it, and put
the resolved SHA in a comment beside the tag:

```yaml
ref: design-suite--v0.1.0   # <sha the tag resolves to> — pin, never track main
```

Within a minor version two things are guaranteed not to move: an audit's
**exit-code contract** (what `0`, `1` and `2` mean), and the **disabled set**
(which audits refuse to run at all). Either one changing is a behaviour change
your CI would otherwise read as silence, so it takes a minor bump and a line in
the release notes. New audits and wider detection inside an existing one can
arrive in a patch. Below `1.0.0`, a minor bump is the breaking-change signal.

To upgrade: read the release notes, change the `ref:` and its SHA comment in
one commit, run the audits on that branch, and merge only if the change in
findings is one you accepted.

**Locally, you cannot pin the same way — and you should know that.** The two
commands in step 1 install from a marketplace, and neither `claude plugin
install` nor `claude plugin update` takes a tag, ref or SHA. What you get is
whatever the marketplace's default branch held when you last updated, which
means your machine and your CI can legitimately disagree about what "the
suite" is. Until the CLI grows a pin, treat CI as the authority: if a local
run and CI disagree, CI is the answer, and the way to reproduce CI by hand is
to clone the suite at the pinned tag and run the engine out of that clone:

```bash
git clone --branch design-suite--v0.1.0 \
  git@github.com:irfan-dahir/ai-design-suite.git /tmp/suite
CLAUDE_PROJECT_DIR="$PWD" python3 /tmp/suite/plugins/design-suite/bin/doctor.py
```

### 2. Create the config

Everything the suite knows about your project lives in one directory in *your*
repo, called `.design-suite/`. Create it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --name "My Project"
```

Real output:

```
wrote .design-suite/profile.json
wrote .design-suite/docs.manifest.json
wrote .design-suite/design-audit-config.json
wrote .design-suite/exceptions.json
wrote .design-suite/arch-rules.json
wrote .design-suite/hooks.map.json
wrote .design-suite/known-traps.json
wrote .design-suite/component-capabilities.json
wrote .design-suite/.gitignore
wrote .design-suite/profile.schema.json
```

Nothing in those files is guessed for you. Every value that matters is the
literal text `TODO`, with a sentence explaining what belongs there.

`${CLAUDE_PLUGIN_ROOT}` is filled in automatically when Claude runs a skill. If
you are typing commands yourself, ask Claude for the path — the plugin lives in
Claude Code's plugin cache, not in your repo.

### 3. Let it read your project first

Before you fill in the TODOs, have the suite look around:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/survey.py"
```

```
survey: wrote .design-suite/survey.json — 3 file(s) seen, stack='javascript/typescript', 0 token candidate(s), 2 thing(s) it could NOT determine.
  ? adapters.lang: stack 'javascript/typescript' has no adapter in this plugin
  ? tokens.source: token-source detection is the worst-measured signal in the suite
```

Read the `?` lines as the useful half. The survey tells you what it could not
work out, because those are exactly the fields you have to decide yourself. It
will not pick a language adapter for you off a `package.json`, and it will not
guess where your design tokens live.

`survey.py --check` runs the opposite direction later on: it looks at what is on
disk and tells you what your config has stopped describing.

### 4. Fill in the profile

Open `.design-suite/profile.json` and replace the TODOs. The fields that matter
most:

| Field | What to put |
|---|---|
| `adapters.lang` | Which language adapter reads your source — see the TODO text for the current values |
| `source.root` / `source.fileGlob` | Where your UI code is, and which files to scan |
| `tokens.source` / `tokens.accessor` | Where your design tokens are defined, and how code refers to them |

Then open `.design-suite/docs.manifest.json` and map your documents. The suite
never refers to a file by name — it asks for a **role**, like `design` or
`flows`, and your manifest says which of your files plays it. Map only the roles
you actually have. Delete the rest.

Check a mapping resolved:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design
DESIGN.md
```

Ask for a role you never mapped and it stops rather than guessing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" motion
unknown role 'motion'. Known roles:
  design
```

### 5. Check your work

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py"
```

The doctor opens every path your config claims exists. A config can be perfectly
well-formed and point at three files that were deleted last month.

```
design-suite doctor — 8 problem(s):

  ✗ audits.baselineDir: '.design-suite/baselines' does not exist
  ✗ docs.roles.design: 'docs/DESIGN.md' does not exist (delete the role, or move it to externalRoles)
  ...
```

Fix those before going further. Everything downstream trusts this file, and a
wrong profile produces confident wrong results rather than an error.

The doctor also prints a provenance line on every run:

```
doctor: provenance — 0 of 16 field(s) carry a human decision ('declared' or 'approved').
  16 field(s) are UNTRUSTED. Not a failure, and not a pass either — an audit scoped by an unratified field is running on a guess
```

That is not an error. It is telling you that nobody has signed off on those
values yet. As you confirm a field is right, you can record who confirmed it, in
the profile's `provenance` block. You can also ignore it entirely — nothing
blocks on it.

### 6. See which skills can run here

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/preflight.py"
```

```
preflight against /path/to/project
20/47 component(s) have every precondition satisfied.

🔴 /audit-assets                proven       2 role(s), 5 script(s)
      ✗ doc role 'assets' is not mapped in docs.manifest.json
      ✗ doc role 'decisions' is not mapped in docs.manifest.json
✅ /audit-claude-md-drift       unverified   0 role(s), 1 script(s)
```

A 🔴 is usually not a bug — it means that skill needs a document you have not
mapped. Map it, or accept that the skill cannot run here.

A ✅ means the skill will not fall over on a missing file. It is **not** a promise
the output is good.

### 7. If you have no design documents

Then the audits have almost nothing to check against, and that is the honest
state of play. Ask Claude for `/bootstrap-design-docs`, which proposes documents
one at a time for you to accept or decline. Expect to do real work in it: the
templates mark decisions as **DECIDE**, and a `DECIDE` is genuinely yours to
make.

---

## The smallest useful adoption

You do not need all of it. Adopting the whole catalogue at once is the most
common way this stalls.

**Start with the documents `init.py` already mapped for you.** The scaffolded
`docs.manifest.json` names four in-repo roles and one external placeholder —
check which, and where it thinks they live:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all
```

```
backlog	docs/BACKLOG.md
decisions	docs/DECISIONS.md
design	docs/DESIGN.md
flows	docs/FLOWS.md
brand-voice	TODO: …	(external)
```

Creating those four files is worth more than any other single step. On a project
with none of them, `preflight.py` reported `7/47 component(s) have every
precondition satisfied`; with the four in place and nothing else changed, the
same command reported `21/47`. Three times the suite, for four files. Run
`preflight.py` yourself rather than trusting those numbers — they are one
project's, and yours will differ.

**Then add three commands to your habits**, and nothing else:

| Command | When |
|---|---|
| `audit_tokens.py` | The one audit that works on the least configuration |
| `doctor.py` | Whenever the config changes, so it fails on a path rather than on a guess |
| `repo_health.py` | Once a month, to see what you are not yet covering |

Everything beyond that is opt-in. The full list of what exists is
[CATALOG.md](./CATALOG.md); the list of what can run *here* is `preflight.py`,
and those are different questions.

**If you have no design documents at all**, do not start by mapping roles to
files that do not exist. Start at
[step 7 above](#7-if-you-have-no-design-documents). Until then, the components
that need no document role are the whole of what you have — the `0 role(s)` rows
in `preflight.py`'s output, seven of them on the project measured above — and
they are mostly
housekeeping rather than design checks. That is the honest state of the tool on
an undocumented project, not a configuration problem to solve.

---

## Two ways in: mid-project and greenfield

These are genuinely different, and running the greenfield path on a five-year-old
codebase is the fastest way to a report nobody reads.

**Adopting mid-project.** The code already exists, the documents mostly do not,
and the first full run will be large. The order that works:

1. Install, `init.py`, fill the three fields, confirm one audit finds something
   true. Nothing else yet.
2. Run `repo_health.py` once to see the shape of the problem — but do not act on
   it. It is a census, not a task list.
3. Write down what is already true, rather than what you wish were true.
   `/bootstrap-design-docs` reverse-engineers a first draft from what is built.
   A design document that describes the codebase you have is checkable; one that
   describes the codebase you want reports every screen as a violation.
4. Baseline the existing findings as accepted debt, and gate only on new ones —
   see [When the first run returns 200 findings](#when-the-first-run-returns-200-findings).
5. Add one more audit per month, not five in a week.

**Greenfield.** You have the opposite problem: nothing to audit yet, and a short
window in which conventions are still cheap to set. Here the
convention-setting skills earn their place first, because they are what later
audits measure against — `/establish-brand-voice` and
`/establish-interaction-spec` are both `explicit` for exactly this reason: they
set project-wide conventions, so they wait for a real decision from you.
`/onboard-new-client` is the ordered playbook for this path rather than a new
capability. `/run-chain` walks a playbook one checkpoint at a time so it survives
being picked up next week, though it is marked `experimental` in
[CATALOG.md](./CATALOG.md) — read its own file before leaning on it. Then wire
the pre-commit gate early, while the
findings count is still zero and keeping it there is free.

**Who should own it.** One person, named, and not "the team". Specifically:

- **A `.design-suite/` owner** — whoever owns the design system, or the most
  senior UI engineer. They own the profile and the exceptions file, and they are
  the reviewer for every new entry in it. An exceptions list that grows without a
  reviewer is an audit that has quietly stopped auditing; the file's own header
  says so.
- **Not a rotating duty.** The judgement calls here — is this finding wrong, or
  is this code wrong — need someone who remembers last month's calls.
- **Not the person who least wants it.** The suite reports; it does not decide.
  If the owner will not make decisions, it produces lists and no change, and the
  team correctly concludes it is not worth running.

---

## What you can ask it to do

You do not need to memorise command names. Most read-only skills run from plain
language — "check whether this screen follows our design system" is enough.
Skills that write something, or that set a project-wide convention, wait for you
to name them.

Some things people actually want, and what answers them:

| What you want | Say something like |
|---|---|
| Find hardcoded colours and spacing | "find hardcoded design values in the app" (`/audit-tokens`) |
| Check a screen against the design system | "audit the settings screen against our design system" (the `design-auditor` agent) |
| Know what documentation has gone stale | "is anything in our docs out of sync with the code?" (`/review-docs`) |
| One overall picture of the project | "what's our design debt?" (`/design-debt`), or `/repo-health` for the raw audit posture |
| Find out whether a component already exists | "is there already a component for a dismissible banner?" (`/suggest-component`) |
| Build a new screen in the house pattern | `/scaffold-screen` |
| Connect a stub to a mocked endpoint | `/wire-endpoint` |
| Check the mock API has not drifted | "is the mock API in sync?" (`/audit-mock-api`) |
| Critique a mockup before it is built | "critique this mockup" (the `design-critic` agent) |
| Record a decision or a backlog item | `/log-decision`, `/capture-backlog` |
| Set brand voice or motion conventions | `/establish-brand-voice`, `/establish-interaction-spec` |

That is a sample, not the list. The full list — with what each one does, whether
Claude may run it unprompted, and how well-tested it is — is
[CATALOG.md](./CATALOG.md), which is generated from the components themselves so
it cannot go stale. Read it before relying on anything.

---

## Three jobs, start to finish

### Job 1 — find hardcoded design values

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_tokens.py"
Found 3 hardcoded-value findings across 2 files → .design-suite/tokens-findings.json
```

The findings file:

```json
[
  {
    "file": "src/Card.tsx",
    "line": 1,
    "kind": "color",
    "snippet": "#3A7BD5"
  },
  {
    "file": "src/Card.tsx",
    "line": 1,
    "kind": "spacing",
    "snippet": "padding: \"17px\""
  }
]
```

File, line, what kind of value, and the text it matched. No severity, no score —
a hardcoded colour is a fact, and whether it matters is your call.

Note the third finding in that run was inside the token definition file itself.
That is expected: the audit scans what your profile tells it to scan. If a path
should be exempt, say so in `.design-suite/exceptions.json` with a reason,
rather than narrowing the scan and forgetting why.

**Fixing them.** For some findings there is a mechanical fix: the literal `16`
where exactly one of your declared spacing tokens is exactly `16`. Ask for
`/repair-tokens`. It writes a patch to your screen and stops:

> Review the diff, then `git apply` it yourself if you agree with it.

It never edits your files, under any flag. And it refuses outright if it cannot
establish what a token is on your project:

```
REFUSING: the 'tsx' adapter cannot read declared token values (no token_declarations capability)

This is a refusal, not a finding of zero repairable values.
```

The repair is worth most on code you are touching right now, where the literal
is new. Run across a whole already-migrated codebase it fixed 0 of 33 findings,
because everything mechanical had already been done.

### Job 2 — one view of the whole project

Starting on an unfamiliar repo, this is the first thing worth running:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repo_health.py"
```

```
AUDIT                        STATUS     FINDINGS  TIME   NOTE
---------------------------  ---------  --------  -----  ----
audit_accessibility          ⛔ disabled        -    0.0s  disabled — 100% false positives measured on two projects
audit_adapter_pattern        ✅ clean           0    0.1s
audit_focus_order            ⚪ refused         -    0.1s  the 'swift' adapter implements no focus-order checks
audit_tokens                 🟡 findings        3    0.1s
...

19 audit(s): 3 clean, 3 with findings, 8 not configured for this project, 3 unclear
(exited nonzero without a findings envelope), 0 crashed, 2 disabled (did not run at all).
```

Read the status column carefully, because four of those five words mean very
different things:

| Status | Means |
|---|---|
| ✅ clean | It ran, it looked, it found nothing |
| 🟡 findings | It ran and found things. This is a result, not a malfunction |
| ⚪ refused | **It could not look.** Not a pass. The note says what was missing |
| ⛔ disabled | Switched off entirely. Tells you nothing about your project |
| ⚠️ unclear | It failed in a way the dashboard could not interpret. Run it directly |

`/design-debt` is the softer version: it reads whatever findings have already
been collected and grades them per category, with no overall score. There is no
composite number on purpose — you cannot honestly average a contrast pass-rate
against a count of hardcoded colours, and one number invites moving the number.

### Job 3 — prove a big refactor changed nothing

Before a large mechanical change — an extraction, an import rewrite, a token
migration — record what every audit currently says:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/capture-baselines.sh"
```

Run it again afterwards. Identical output means you changed no behaviour.
Different output tells you immediately, at the change that caused it.

Two warnings the script itself will give you:

```
19 discovered: 2 disabled (did not run at all).
Disabled audits tell you NOTHING about this project — read them as a gap in
coverage, not as a pass.
```

and, for a check that silently did nothing:

```
INERT    audit_reinvented_components    REFUSING TO RUN
```

An **INERT** audit is one that could not execute. It is not baselined, because a
recorded "clean" for a check that never ran would bless it forever.

And the honest limit: a baseline of 0 findings proves nothing. 0-before and
0-after look identical whether the check works or not. If you are relying on an
audit, plant a deliberately broken file once and confirm it gets caught.

For pixels rather than findings, `/golden-local-ab` renders your golden corpus
before and after and compares byte-for-byte.

---

## When the first run returns 200 findings

This is the normal first result on an existing codebase, and it is where most
adoptions stop. Two hundred findings is not two hundred tasks. It is one task —
sorting them — and then a much smaller number of tasks.

**Do not start fixing.** Sort first. Every finding goes in exactly one of three
buckets, and the suite has a different mechanism for each.

### Bucket 1 — fix now

Findings in code you are already touching this week. That is the whole of the
bucket; resist widening it. A hardcoded colour in a file nobody has opened in a
year is not urgent, and fixing it costs a review and a regression risk for no
behaviour change.

For hardcoded values there is sometimes a mechanical fix — see
[Job 1](#job-1--find-hardcoded-design-values). It emits a patch and stops.

### Bucket 2 — accepted debt: baseline it

You have decided these findings are real but not now. You want them to stop
appearing in every run, and you want to be told the moment a *new* one appears.
That is a baseline, and it is a ratchet rather than a mute button.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/capture-baselines.sh"
```

The first run records what every audit currently says and verifies nothing —
each newly discovered audit is reported as `NEW … no baseline existed —
recorded, NOT verified`. From then on, the same command compares. The output
tells you which audits were baselined, which refused, and which were switched
off:

```
19 audit(s) discovered by audit_discovery.discover()

  NEW      audit_prose_flags      no baseline existed — recorded, NOT verified
  INERT    audit_reinvented_components audit_reinvented_components: REFUSING TO RUN
  DISABLED audit_copy             disabled — 73% of commit-gating findings wrong, measured on two projects
```

The mechanism that makes this safe is worth knowing about, because it will refuse
you one day and the refusal looks like a failure. The audits that keep their own
per-finding baseline — currently the layer-boundaries and reinvented-components
checks — take `--update-baseline`, and that write is guarded. If the current run
contains findings the baseline does not, the write **does not happen**:

```
audit_layer_boundaries: REFUSING TO UPDATE THE BASELINE — 1 NEW violation(s) would be absorbed:

  + src/a.tsx -> src/b.tsx

These are not in the current baseline. Writing now would record them as accepted debt without anyone having decided that.

Fix them, or — if they really are accepted — re-run with --accept-new to say so deliberately.
```

This is the tool working. "Lock in the improvement" and "silently swallow the
regression I just introduced" are the same keystroke otherwise, and afterwards
the two are indistinguishable. `--accept-new` is how you say you meant it, and
it prints what you accepted.

Baselines are authored files: commit them, review changes to them in a pull
request like any other.

### Bucket 3 — it is wrong

Two different cases, and they take two different mechanisms.

**Wrong about this file, right in general** — a vendored file, the token
definition file being flagged for defining tokens, a generated directory. That is
an accepted exception, and it goes in `.design-suite/exceptions.json`, keyed by
the audit category:

```json
{
  "color": {
    "allowlistFiles": [
      {
        "path": "src/tokens.ts",
        "reason": "the token source itself; these are the definitions, not usages"
      }
    ]
  }
}
```

`reason` is not decoration. It is the only record of why a human decided this,
and in six months it is the difference between an accepted exception and an
unexplained hole. Re-run, and the suppression is stated rather than silent:

```
Found 2 hardcoded-value findings across 1 files → .design-suite/tokens-findings.json
Suppressed 1 further finding(s) under 1 documented exception(s):
    1  color.allowlistFiles  src/tokens.ts
```

Note the count of what was suppressed and under which entry. An exceptions file
that quietly reduced the number would be the same failure this suite exists to
prevent.

Three things about that file are worth knowing:

- **Exceptions are scoped to a category.** A file allowed to hold raw colours is
  still held to the spacing rules. An untagged check honours no allowlist at all.
- **`allowlistRegions` reads narrower than it acts.** Its `scope` field is prose
  for a human; the engine applies the entry at path granularity, exactly like
  `allowlistFiles`. If the exempt part is narrower than the file, keep the file
  small — nothing machine-checks that the prose and the path agree.
- **`reportAnyway` outranks both.** Put a path there for a known-open debt that
  must keep appearing in every report, however broad a glob later grows to cover
  it.

**Wrong in general** — the rule itself does not fit your project. Do not
exception it file by file; that is a growing list nobody reviews. Either turn
the check off for this project, or say so as an issue. Two audits are already
switched off for exactly this reason, and their own output says what would have
to change to turn them back on. See
[When it refuses to run](#when-it-refuses-to-run).

### The rule of thumb

If bucket 3 is more than about a fifth of the findings, stop sorting and fix the
configuration instead. A high wrong-rate is almost always one bad field in
`profile.json` — a source root that includes generated code, an adapter that does
not match the stack — rather than two hundred independent mistakes. Run
`doctor.py` and `survey.py --check` before you triage another hundred.

---

## When to run what

A rhythm that survives contact with a real week. Nothing here is wired by
default; you are choosing what to install.

**On save — nothing.** There is no watch mode, and adding one would be a mistake:
these audits sweep a source tree, and a finding you cannot act on mid-keystroke
is an interruption, not information.

**Before a commit — one or two fast, invariant audits, if you want them.** This
is opt-in in two steps, deliberately. Mark the audits you want in
`.design-suite/hooks.map.json` with `"preCommit": true`, then install the hook:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/install_precommit_hook.py"
```

It wires into your real commit path — appending to your existing pre-commit
framework config if you have one, and writing a shell shim into the git hooks
directory if you do not. Until you mark something `preCommit`, it gates on
nothing. Choose only audits that are fast and that you will never legitimately
violate; an audit that blocks a commit it should not have blocked teaches the
team to pass `--no-verify`, and then it gates nothing forever. If the plugin is
later reinstalled somewhere else, re-run the installer — the shim bakes in an
absolute path, because git hooks run outside any Claude Code session.

**Before a pull request — the audits that match what you changed.** Touched
styling, run the token audit. Changed a screen's data, run the mock-API audit.
Changed documents, run `/review-docs`. This is the one point in the cycle where
a finding is cheap to act on, because the code is still in your head.

**Before merging a large mechanical refactor — the oracle, twice.** Capture
baselines before and verify after, as in
[Job 3](#job-3--prove-a-big-refactor-changed-nothing).

**Monthly — the whole picture.** `repo_health.py` for the raw posture,
`/design-debt` for the graded read. Monthly rather than weekly because the number
you are watching moves on the scale of months, and looking at it weekly invites
managing the number.

**After the project changes shape — re-run the survey.** `survey.py --check`
answers the one question no other check asks: what is on disk that your config
has stopped describing. `doctor.py` only walks declared → disk, and is blind to
additions by construction. Run `--check` after any of these:

- a new top-level directory, a new package, a monorepo split
- moving where tokens or components live
- adding a language or a framework to the repo
- a dependency upgrade that relocates generated code

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/survey.py" --check
```

```
survey --check — completeness diff (disk → declared) for /path/to/project

  ✗ scripts/  [undeclared-top-level-directory]
      on disk, and no config file under .design-suite/ declares it as a path
      1 file(s) underneath

3 finding(s). This is the disk → declared direction; every doctor.py check runs
declared → disk and is blind to additions by construction.
```

It writes nothing. An undeclared directory is not automatically a problem — it is
a place no audit is looking, which is worth knowing on purpose rather than by
accident.

---

## It said nothing — is that good?

Usually the first real question anyone has, and you should not have to learn exit
codes to answer it. Read the words:

| It printed | It means |
|---|---|
| A count — "Found 0 … across 0 files" | **It ran and found nothing.** Good news, within what that check covers |
| `REFUSING`, `CANNOT RUN`, `INERT`, `not clean`, `not a finding of zero` | **It could not look.** Not good news, not bad news, no news |
| `DISABLED`, `disabled —` | **It was switched off** before it started. Tells you nothing about your code |
| A traceback | It broke. Run it directly and read the error |

The distinction the whole suite is built around is the second row. A check that
cannot see and a codebase that is clean would otherwise print the same thing, and
a silence you read as a pass is worse than no check at all — it is a check you
now trust. So every path that cannot answer says so in words, loudly enough to be
unmissable in a wall of output, and refuses to be recorded as clean.

The practical version: **never count a report's zero without also counting its
refusals.** `repo_health.py`'s summary line puts both in the same sentence for
exactly that reason:

```
19 audit(s): 3 clean, 3 with findings, 8 not configured for this project, 3
unclear (exited nonzero without a findings envelope), 0 crashed, 2 disabled (did
not run at all).
```

Three clean out of nineteen is the honest reading of that run. Thirteen of them
did not look.

Why it is built this way rather than defaulting to a pass is
[CONCEPTS.md](./CONCEPTS.md#the-finding-that-shapes-everything), not this guide.

---

## When it refuses to run

The suite would rather stop than print a clean report it cannot back up. Most
confusing messages are one of these five.

**"no `.design-suite/` found … Refusing to guess."**
You are not in a project that has been set up, or not in its root. Run
`init.py`, or `cd` to the repository root.

**"unknown role 'motion'"**
A skill asked for a document you have not mapped. Add it to
`docs.manifest.json`, or tell Claude to carry on without it — but expect it to
say in its report that it did.

**"the 'x' adapter implements no … checks"**
That check is not implemented for your language. It could have returned zero
findings and looked like good news; instead it says it cannot see. Nothing is
wrong with your project.

**"REFUSING: … This is a refusal, not a finding of zero."**
Something the check depends on is missing — usually an undeclared token source
or an incomplete config. The message names what.

**"DISABLED — … It refuses (exit 2), not a clean result."**
Two audits are currently switched off because they were wrong far too often on
real projects: the accessibility audit and the copy audit. They tell you nothing
about your project either way. They refuse loudly instead of quietly passing, so
nobody mistakes their silence for a good score. Their own output explains what
would have to change to turn them back on.

If you are scripting around the suite, the exit codes are a stated contract:
**0** ran and found nothing, **1** ran and found something, **2** could not run.
Anything else crashed. The full table, including the resolver's extra codes for
external and declined documents, is in
[DOC-ROLES.md](../plugins/design-suite/docs/DOC-ROLES.md).

---

## Why it reports instead of fixing

The clearest argument for that rule is a thing that actually happened, on a real
project, recently.

The mock-API audit compares a contract's four sides — the model, the fixture, the
API documentation, and the mock server — and reports where they disagree. On that
project it found 9 critical drifts. Each one came with a recommended fix, and the
recommendation ended by naming the sync script: regenerate the mock from the
fixture.

Following it would have destroyed correct data. The fixture was the rotted side,
not the mock. Two of the things it would have deleted were a medication's
weekly-cadence field and an attachment's URL — a real feature and a real link,
present and correct in the mock, absent from the fixture. The sync is one-way by
design, so "make them agree" and "delete the newer side" are the same command.

The bug was never in the comparison. The comparison was right: the two sides
disagree. The bug was in the sentence after it. A check that measures
*disagreement* cannot also pronounce on *authority* — which side is out of date is
a judgement about intent, and intent is not in either file.

So the finding no longer names a direction. It shows both sides and stops:

> Postman example keys … differ from fixture keys … only in mock: … only in
> fixture: … . Update whichever one is out of date.

That is the shape of the whole suite. It is not modesty and it is not an
unfinished feature; it is the one thing the tool is actually able to be right
about. The same bar now applies to every suggested repair anywhere in the plugin,
checked by a gate — and `doctor.py` will tell you if your own
`hooks.map.json` starts recommending a fix that has not cleared it:

```
✗ hooks.map.json entry "…": fixHint suggests '/audit-tokens', which is not on the
plugin's safe-repairers allowlist … A suggested fix is exactly the sentence shape
that deleted correct data in issue #116
```

When an audit tells you two things disagree, the next step is yours. That is not
the tool being lazy. It is the tool declining to guess with your data.

---

## What it will not do for you

Stated plainly, so nothing here is a surprise later.

- **It will not write your design documents.** `/bootstrap-design-docs` makes it
  faster; the decisions are still yours. On a project with no documentation, the
  suite finds very little, because there is nothing to check against.
- **It will not fix your code.** Audits report. The one repair path
  (`/repair-tokens`) emits a patch for you to apply yourself, and only for cases
  where exactly one token matches exactly.
- **It cannot check everything in every language.** Coverage varies by adapter,
  and a check that is not implemented for your stack refuses rather than passing.
  Each adapter's own module docstring is where its limits are recorded.
- **Two audits are switched off** — accessibility and copy. See above.
- **Much of it is not verified.** Every component declares a maturity, and a
  large share are `unverified` — meaning nobody has recorded an end-to-end run,
  not that it is broken. Derive the current split rather than trusting a number
  here:

  ```bash
  grep -o "maturity: [a-z]*" -r plugins/*/commands plugins/*/agents | awk '{print $2}' | sort | uniq -c
  ```

  Per-component, the column in [CATALOG.md](./CATALOG.md) is authoritative.
- **The skills have not been tested behaviourally.** Most skills are prompt-only,
  with no script to execute. An automated eval suite exists but costs model calls
  to run, and "this skill does the right thing" remains a judgement a human makes
  by reading its output.
- **It will not gate your commits unless you ask.** You can map fast audits into
  `.design-suite/hooks.map.json` and install a pre-commit hook, but nothing is
  wired that way by default.
- **A green run is not a guarantee.** It means the checks that could run found
  nothing. Always read how many refused.

---

## Removing it

Trying it and stopping is a legitimate outcome, and it should not cost you a
cleanup afternoon. Everything the suite put in your repository is in one
directory and a couple of generated ones.

If you installed the pre-commit gate, take it out first — it is the only thing
that wrote outside your working tree, into git's hooks:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/install_precommit_hook.py" --uninstall
```

It removes only what it installed: its own shim, or its own entry in your
existing pre-commit framework config, matched by a marker rather than by
byte-diffing your file. Anything else in there is untouched.

Then delete the configuration and the generated output, and uninstall the plugin:

```bash
rm -rf .design-suite
claude plugin uninstall design-suite@ai-design-suite
claude plugin marketplace remove ai-design-suite
```

Two things do not live under `.design-suite/` and are worth a `git status` to
catch: the findings directory an audit writes to, and any design documents
`/bootstrap-design-docs` created. The documents are yours — they are ordinary
markdown describing your project, with no dependency on the suite, and they keep
working as documents after everything above is gone. That is deliberate: the
suite reads your documents, it does not own them.

Nothing else persists. There is no daemon, no cache outside the plugin's own
install directory, and no account.
