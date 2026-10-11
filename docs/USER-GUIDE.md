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
documents — the API doc, the RFC, the changelog. Where the two disagree, you
get a list.

It finds things like an endpoint the code serves that no doc mentions, a doc
example that no longer matches the response shape, a mock API whose fixture
and contract have drifted apart, a changelog that stopped being updated three
releases ago.

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

1. **Do you have API documents, or want them?** The suite checks code against
   documents. No documents, nothing to check against.
2. **Is more than one person writing backend code?** A single author holds the
   conventions in their head. A team does not, and that is the gap this fills.
3. **Do you have an API contract — an OpenAPI spec, a mock server, a documented
   error envelope?** If the shape of every response lives only in the code, the
   contract audits have nothing to compare against yet.
4. **Does the project outlive the current sprint?** The value is in catching
   drift over months. On a two-week prototype there is no drift yet.

It is **not** the right tool for: linting (use your linter), formatting (use your
formatter), load testing or other runtime behaviour testing (the suite reads
source and documents only), or deciding what your API should look like. It has
no opinions of its own — see [What this is](#what-this-is).

If you try it and it is not for you, [Removing it](#removing-it) is two commands.

---

## Your first five minutes

If you open an unconfigured project in Claude Code, the suite offers to set it
up for you — see [What happens when you open a project](#what-happens-when-you-open-a-project).
This section is the manual route.

There is no zero-configuration run. The suite refuses to guess which directory
holds your source or which language adapter reads it, because a wrong guess
produces a confident clean report on the wrong files — see
[When it refuses to run](#when-it-refuses-to-run). So the shortest honest path is
one install, one scaffold, one audit.

```bash
claude plugin marketplace add irfan-dahir/backend-quality-suite
claude plugin install backend-suite@backend-quality-suite
python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --name "My Project"
```

Then run the audit that needs the least configuration — it reads documents
against themselves, so it works on any project with markdown in it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_proposal_status.py" --findings
```

Real output, on a project with one proposal doc whose header has stopped
agreeing with its own body:

```
CRITICAL — 1 finding(s):

  docs/proposals/001-rfc.md states a status in its header that its body contradicts

audit_proposal_status: 4 file(s) scanned, 1 proposal-shaped, 1 critical, 0 advisory
```

**What success looks like.** Three specific things, in order:

- **A non-zero exit code.** `1` means it ran and found something. `0` means it
  ran and found nothing. `2` means it could not run, and is not a pass. Check it
  with `echo $?`.
- **A findings file you can open**, naming a file, a check, and a sentence of
  detail — the shape shown under [Job 1](#job-1--find-stale-documents).
- **A finding you recognise as true.** Open the first one. If it is a real
  contradiction in a file you know, the audit is reading the right tree.

**Confirm it can actually fail.** A 0-finding result proves nothing on its own,
because a check that is broken and a codebase that is clean print the same thing.
So once, deliberately, write a markdown doc whose header declares a resolved
status while its body still has open questions, and re-run. Findings should go
up by one. Then fix the header and watch them go back down:

```
audit_proposal_status: 4 file(s) scanned, 0 proposal-shaped, 0 critical, 0 advisory
```

That round trip is the whole argument for trusting anything else in this guide.
Five minutes, and you now know the suite can both read your documents and tell
you when it cannot.

---

## What happens when you open a project

You do not have to remember a command to get started. When a Claude Code
session starts (or after `/clear`), the suite takes a quick look at the folder
and decides which of these it is. It **reads only — it never writes a file at
this point.**

| What it finds | What you will see |
|---|---|
| **Configured** — `.backend-suite/profile.json` exists | Nothing. You are set up. |
| **New** — no source code anywhere yet | Claude offers `/onboard-new-client`, the setup for a brand-new project. |
| **Existing** — source code, but no `.backend-suite/` folder | Claude offers `/run-chain understand-existing-project`, a guided setup (below). |
| **Half set up** — `.backend-suite/` exists, but no `profile.json` | Claude says most skills will refuse, and suggests `doctor.py` or resuming the guided setup. |
| **Can't tell** — a home folder, an unreadable folder, or one too big to check quickly | Claude says it could not tell and suggests nothing. If you ask about setup, it asks you which case applies. |

It is only an offer. Nothing starts until you say yes. If you say no, Claude
won't bring it up again in that session.

**To switch the offer off for good:**

- **For one project:** create an empty file called
  `.backend-suite-onboarding-declined` in the project root. You can also ask
  Claude to stop reminding you, and it will create the file. It never creates it
  unless you ask.
- **For everything on your machine:** set the environment variable
  `BACKEND_SUITE_NO_ONBOARDING=1`.

### The "not configured" notice

The suite's other hooks run after Claude edits a file. In a project that isn't
set up, they now tell you that **once per session**:

```
backend-suite: no .backend-suite/ in this project — the suite is installed but no
on-save audits are configured, so nothing is checked on edit (this is not a
clean result).
```

This is not an error. It is there so you don't mistake "nothing was checked"
for "nothing was wrong". It goes away once the project is set up and its
`.backend-suite/hooks.map.json` lists the audits you want run on save.

---

## Setting up an existing project, step by step

`/run-chain understand-existing-project` runs five steps in order. It stops and
asks before every step that writes. It also remembers where it got to, so you
can stop and pick up in a later session by running the same command again.

| # | Step | What it does | Writes | Asks first? |
|---|---|---|---|---|
| 1 | `/survey` | Works out your stack, where the source lives, and which documents you have. It also lists what it *couldn't* work out — read that list. | `.backend-suite/survey.json` | Yes |
| 2 | `init.py --from-survey`, then `/map-project` | Creates the `.backend-suite/` config, pre-filled from the survey. Then suggests which document is your API doc, what kind of project this is (service or library), and which files hold your contract. | `.backend-suite/` config files | Yes, for each half |
| 3 | `/bootstrap-api-docs` | Drafts missing context documents from what is already built, one at a time. You accept or decline each one. Skipped if you already have the documents. | The documents you accept | Yes, per document |
| 4 | `/propose-config` | Reads your code and proposes real values for config sections setup left as `TODO` (source globs, layer rules, doc roles), each with the evidence behind it. Proposes nothing where the evidence is weak. | Only the sections you approve, marked `inferred` | Yes, per section |
| 5 | `/repo-health` | Runs every audit once and records where the project starts: which audits work, which find things, which refuse. | Reports inside `.backend-suite/` only (git-ignored) | No — it only reports |

Everything step 2 fills in is marked **`inferred`**: it is the machine's guess.
No check treats a guess as trusted until a person approves it with `/ratify`.
`doctor.py` lists the fields still waiting for approval.

To check how far you have got without running anything:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/chain.py" status understand-existing-project
```

---

## Which stacks it can read

The documentation skills (`/review-docs`, `/sync-docs`, `/bootstrap-api-docs`,
`/survey`, the resolver, `audit-proposal-status`, `audit-doc-staleness`) work on
any project. Audits that read **source code** need an adapter for your language,
set as `adapters.lang` in `.backend-suite/profile.json`.

No language adapter ships yet. The UI adapters this suite inherited left with
the design domain; `php` is the first one being built (see
[ROADMAP.md](./ROADMAP.md)). Until it lands:

- Leave `adapters.lang` unset and use the documentation half — it is the half
  that works today.
- Every code-shape audit (`audit-error-handling`, `audit-api-consistency`,
  `audit-contract-headers`, `audit-layer-boundaries`) **refuses with exit 2**,
  naming the adapter problem. It does not quietly report zero.

When scanning, audits skip vendor and build folders (`vendor`, `node_modules`,
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
- **A config section is missing**, for example the `mockApi` section
  `audit-mock-api` reads. Fill it in, or ask Claude to run `doctor.py`.
- **You are in a git repo inside another one, and the inner one isn't set up.**
  Set up the inner repo, or run from the outer one if that's what you meant to
  check.

If a script or CI step reads these exit codes, make it treat 2 as a failure you
need to look at, never as a pass.

---

## Where reports go

Audits save their raw reports inside `.backend-suite/`, for example:

- `.backend-suite/findings/doc-staleness.json`
- `.backend-suite/findings/proposal-status.json`
- `.backend-suite/findings/` (the common envelope every audit writes, passed
  with `--findings`)

These are **ignored by git** through `.backend-suite/.gitignore`, which
`init.py` creates. They are kept out of git because reports quote lines of your
source code. You can delete them at any time; the next run makes them again.

What you *do* commit in `.backend-suite/` is the config you wrote:
`profile.json`, `docs.manifest.json`, `exceptions.json`, `baselines/`, and the
rest.

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
a script at all: it is instructions for Claude. When you ask Claude to review
your API docs against the code, Claude reads both, and that content goes to the model the same way
any other Claude Code session's does. Nothing about the suite changes your
existing data-handling posture — but nothing about it exempts you from it either.
If the rule on a client repository is that source does not go to a model, that
rule applies here, and the script-only paths in this guide are the parts that
still work under it.

**Findings quote your source.** A finding quotes a literal line of your code,
and on a backend codebase an audit that greps for literals will point at things
with the same shape as an inline credential. That is why the scaffolded
`.backend-suite/.gitignore`
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
claude plugin marketplace add irfan-dahir/backend-quality-suite
claude plugin install backend-suite@backend-quality-suite
```

On an internal org project, also install `house-style@backend-quality-suite`.
On a client-facing repo, install `backend-suite` only — the house-style plugin
carries our letterhead and PR process, which a client repo should not inherit.

### Which version you are running

**In CI, pin a tag.** A checkout of the suite with no `ref:` tracks its `main`,
so every merge into the suite lands in your build unreviewed. Pin it, and put
the resolved SHA in a comment beside the tag:

```yaml
ref: backend-suite--v0.1.0   # <sha the tag resolves to> — pin, never track main
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
git clone --branch backend-suite--v0.1.0 \
  git@github.com:irfan-dahir/backend-quality-suite.git /tmp/suite
CLAUDE_PROJECT_DIR="$PWD" python3 /tmp/suite/plugins/backend-suite/bin/doctor.py
```

### 2. Create the config

Everything the suite knows about your project lives in one directory in *your*
repo, called `.backend-suite/`. Create it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --name "My Project"
```

Real output:

```
wrote .backend-suite/profile.json
wrote .backend-suite/docs.manifest.json
wrote .backend-suite/exceptions.json
wrote .backend-suite/arch-rules.json
wrote .backend-suite/hooks.map.json
wrote .backend-suite/known-traps.json
wrote .backend-suite/profile.schema.json
wrote .backend-suite/.gitignore
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
survey: wrote .backend-suite/survey.json — 3 file(s) seen, stack='javascript/typescript', 0 token candidate(s), 2 thing(s) it could NOT determine.
  ? adapters.lang: stack 'javascript/typescript' has no adapter in this plugin
  ? tokens.source: token-source detection is the worst-measured signal in the suite
```

Read the `?` lines as the useful half. The survey tells you what it could not
work out, because those are exactly the fields you have to decide yourself. It
will not pick a language adapter for you off a `package.json`, and it flags its
own weakest detections rather than pretending certainty.

`survey.py --check` runs the opposite direction later on: it looks at what is on
disk and tells you what your config has stopped describing.

### 4. Fill in the profile

Open `.backend-suite/profile.json` and replace the TODOs. The fields that matter
most:

| Field | What to put |
|---|---|
| `adapters.lang` | Leave unset until an adapter for your stack ships — see [Which stacks it can read](#which-stacks-it-can-read) |
| `source.root` / `source.fileGlob` | Where your source code is, and which files to scan |

Then open `.backend-suite/docs.manifest.json` and map your documents. The suite
never refers to a file by name — it asks for a **role**, like `api` or
`decisions`, and your manifest says which of your files plays it. Map only the roles
you actually have. Delete the rest.

Check a mapping resolved:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api
docs/API.md
```

Ask for a role you never mapped and it stops rather than guessing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" flows
unknown role 'flows'. Known roles:
  api
```

### 5. Check your work

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py"
```

The doctor opens every path your config claims exists. A config can be perfectly
well-formed and point at three files that were deleted last month.

```
backend-suite doctor — 8 problem(s):

  ✗ audits.baselineDir: '.backend-suite/baselines' does not exist
  ✗ docs.roles.api: 'docs/API.md' does not exist (delete the role, or move it to externalRoles)
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
14/36 component(s) have every precondition satisfied.

🔴 /audit-mock-api              proven       1 role(s), 1 script(s)
      ✗ doc role 'api' is not mapped in docs.manifest.json
✅ /audit-doc-staleness         unverified   0 role(s), 1 script(s)
```

A 🔴 is usually not a bug — it means that skill needs a document you have not
mapped. Map it, or accept that the skill cannot run here.

A ✅ means the skill will not fall over on a missing file. It is **not** a promise
the output is good.

### 7. If you have no documents yet

Then the audits have almost nothing to check against, and that is the honest
state of play. Ask Claude for `/bootstrap-api-docs`, which proposes documents
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
api	docs/API.md
api-standard	docs/API-STANDARD.md
backlog	docs/BACKLOG.md
decisions	docs/DECISIONS.md
pr	TODO: …	(external)
```

Creating those four files is worth more than any other single step. On one
project measured during adoption, going from none of them to all four tripled
the number of components `preflight.py` reported as runnable — with nothing
else changed. Run `preflight.py` yourself rather than trusting that number; it
was one project's, and yours will differ.

**Then add three commands to your habits**, and nothing else:

| Command | When |
|---|---|
| `audit_proposal_status.py` | The one audit that works on the least configuration |
| `doctor.py` | Whenever the config changes, so it fails on a path rather than on a guess |
| `repo_health.py` | Once a month, to see what you are not yet covering |

Everything beyond that is opt-in. The full list of what exists is
[CATALOG.md](./CATALOG.md); the list of what can run *here* is `preflight.py`,
and those are different questions.

**If you have no documents at all**, do not start by mapping roles to
files that do not exist. Start at
[step 7 above](#7-if-you-have-no-documents-yet). Until then, the components
that need no document role are the whole of what you have — the `0 role(s)` rows
in `preflight.py`'s output — and they are mostly housekeeping rather than
doc-vs-code checks. That is the honest state of the tool on an undocumented
project, not a configuration problem to solve.

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
   `/bootstrap-api-docs` reverse-engineers a first draft from what is built.
   A document that describes the API you have is checkable; one that describes
   the API you wish you had reports every endpoint as a violation.
4. Baseline the existing findings as accepted debt, and gate only on new ones —
   see [When the first run returns 200 findings](#when-the-first-run-returns-200-findings).
5. Add one more audit per month, not five in a week.

**Greenfield.** You have the opposite problem: nothing to audit yet, and a short
window in which conventions are still cheap to set. Here the documents come
first, because they are what later audits measure against:
`/bootstrap-api-docs` proposes each one for you to accept or decline, and a
`DECIDE` marker in a template is genuinely yours to make.
`/onboard-new-client` is the ordered playbook for this path rather than a new
capability. `/run-chain` walks a playbook one checkpoint at a time so it survives
being picked up next week, though it is marked `experimental` in
[CATALOG.md](./CATALOG.md) — read its own file before leaning on it. Then wire
the pre-commit gate early, while the
findings count is still zero and keeping it there is free.

**Who should own it.** One person, named, and not "the team". Specifically:

- **A `.backend-suite/` owner** — whoever owns the API contract, or the most
  senior backend engineer. They own the profile and the exceptions file, and they are
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
language — "check whether the docs still match the endpoints" is enough.
Skills that write something, or that set a project-wide convention, wait for you
to name them.

Some things people actually want, and what answers them:

| What you want | Say something like |
|---|---|
| Know what documentation has gone stale | "is anything in our docs out of sync with the code?" (`/review-docs`) |
| One overall picture of the project | "what's our quality debt?" (`/quality-debt`), or `/repo-health` for the raw audit posture |
| Check the mock API has not drifted | "is the mock API in sync?" (`/audit-mock-api`, or the `mock-api-auditor` agent) |
| Connect a stub to a mocked endpoint | `/wire-endpoint` |
| Check a proposal's header still matches its body | "is any RFC's status stale?" (`/audit-proposal-status`) |
| Record a decision or a backlog item | `/log-decision`, `/capture-backlog` |
| Propose the missing config from the code | `/propose-config` |
| See how far setup has got | `/map-project`, or `doctor.py` for the paths |

That is a sample, not the list. The full list — with what each one does, whether
Claude may run it unprompted, and how well-tested it is — is
[CATALOG.md](./CATALOG.md), which is generated from the components themselves so
it cannot go stale. Read it before relying on anything.

---

## Three jobs, start to finish

### Job 1 — find stale documents

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_doc_staleness.py" --findings
```

```
STALE (should fix) — 1 finding(s):

  docs/API.md: footer states 2026-01-04, 281 day(s) ago

audit_doc_staleness: 6 file(s) scanned, 3 with a dated last-updated signal (2 within 90 days, 1 stale), 1 with an unparseable/future value, 2 with no staleness signal at all. Reminder: this is days-since-last-edited, not verification.
```

The findings file (the common envelope every audit writes):

```json
[
  {
    "file": "docs/API.md",
    "check": "stale_by_stated_date",
    "severity": "should_fix",
    "detail": "footer states 2026-01-04, 281 day(s) ago"
  }
]
```

File, which check fired, and a sentence of detail. No composite score, no
ranking — a stale doc is a fact, and whether 281 days matters is your call.

Two honest limits are printed in the output itself. A doc that never carries
the convention (`_Last updated: YYYY-MM-DD_`, a `Date:` field, or a
"dated YYYY-MM-DD" phrase) is **not counted**, and the summary says how many
had "no staleness signal at all". And if nothing in the tree carries the
convention, the audit exits `2` as INERT rather than printing a clean — a
project where every doc still has the unfilled template placeholder looks
exactly like a project the audit cannot read, and it refuses to grade either.

**Fixing them.** There is no repair path for this one, and that is deliberate:
the fix is opening the doc and deciding whether it is still true. A tool that
cannot know whether a document is *true* can still tell you it has not been
*touched* — the second question is yours.

### Job 2 — one view of the whole project

Starting on an unfamiliar repo, this is the first thing worth running:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repo_health.py"
```

```
AUDIT                        STATUS     FINDINGS  TIME   NOTE
---------------------------  ---------  --------  -----  ----
audit_api_consistency        ⚪ refused         -    0.1s  no language adapter ships yet
audit_claude_md_drift        ⚪ refused         -    0.1s  no rule mapping configured — see its --help
audit_contract_headers       ⚪ refused         -    0.1s  no language adapter ships yet
audit_doc_staleness          🟡 findings        4    0.1s
audit_error_handling         ⚪ refused         -    0.1s  no language adapter ships yet
audit_layer_boundaries       ⚪ refused         -    0.1s  no language adapter ships yet
audit_mock_api               ⚪ refused         -    0.1s  no mock-API contract configured
audit_proposal_status        ✅ clean           0    0.1s
audit_prose_flags            ✅ clean           0    0.2s

9 audit(s): 2 clean, 1 with findings, 6 refused (could not check), 0 crashed, 0 disabled.
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

`/quality-debt` is the softer version: it reads whatever findings have already
been collected and grades them per category, with no overall score. There is no
composite number on purpose — you cannot honestly average a doc-staleness count
against a mock-API drift count, and one number invites moving the number.

### Job 3 — prove a big refactor changed nothing

Before a large mechanical change — an extraction, an import rewrite, an
error-shape migration — record what every audit currently says:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/capture-baselines.sh"
```

Run it again afterwards. Identical output means you changed no behaviour.
Different output tells you immediately, at the change that caused it.

Two warnings the script itself will give you. The first, whenever any audit is
disabled:

```
9 discovered: 2 disabled (did not run at all).
Disabled audits tell you NOTHING about this project — read them as a gap in
coverage, not as a pass.
```

and, for a check that silently did nothing:

```
INERT    audit_mock_api             REFUSING TO RUN
```

An **INERT** audit is one that could not execute. It is not baselined, because a
recorded "clean" for a check that never ran would bless it forever.

And the honest limit: a baseline of 0 findings proves nothing. 0-before and
0-after look identical whether the check works or not. If you are relying on an
audit, plant a deliberately broken file once and confirm it gets caught.

---

## When the first run returns 200 findings

This is the normal first result on an existing codebase, and it is where most
adoptions stop. Two hundred findings is not two hundred tasks. It is one task —
sorting them — and then a much smaller number of tasks.

**Do not start fixing.** Sort first. Every finding goes in exactly one of three
buckets, and the suite has a different mechanism for each.

### Bucket 1 — fix now

Findings in code you are already touching this week. That is the whole of the
bucket; resist widening it. A stale doc in a directory nobody has opened in a
year is not urgent, and fixing it costs a review and a regression risk for no
behaviour change.

The mechanical-fix paths are deliberately rare and opt-in; see
[Job 1](#job-1--find-stale-documents) for the shape of a finding and why most
have no repair.

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
9 audit(s) discovered by audit_discovery.discover()

  NEW      audit_proposal_status      no baseline existed — recorded, NOT verified
  INERT    audit_mock_api             audit_mock_api: REFUSING TO RUN
```

The mechanism that makes this safe is worth knowing about, because it will refuse
you one day and the refusal looks like a failure. The audits that keep their own
per-finding baseline — currently the layer-boundaries and reinvented-components
checks — take `--update-baseline`, and that write is guarded. If the current run
contains findings the baseline does not, the write **does not happen**:

```
audit_layer_boundaries: REFUSING TO UPDATE THE BASELINE — 1 NEW violation(s) would be absorbed:

  + app/Http/Controllers/UserController.php -> app/Http/Resources/UserResource.php

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

**Wrong about this file, right in general** — a vendored file, a generated
directory, a fixture the audit cannot know is deliberate. That is
an accepted exception, and it goes in `.backend-suite/exceptions.json`, keyed by
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

(The example uses the scaffolded template's own `color` category —
`init.py` still scaffolds the design-era categories `color`, `spacing` and
`unusedTokens`; they are scheduled to swap to the backend vocabulary with the
`php` adapter workstream. The mechanism below is what matters, and it is
category-generic.)

`reason` is not decoration. It is the only record of why a human decided this,
and in six months it is the difference between an accepted exception and an
unexplained hole. Re-run, and the suppression is stated rather than silent:

```
Found 2 finding(s) across 1 file(s)
Suppressed 1 further finding(s) under 1 documented exception(s):
    1  color.allowlistFiles  src/tokens.ts
```

Note the count of what was suppressed and under which entry. An exceptions file
that quietly reduced the number would be the same failure this suite exists to
prevent.

Three things about that file are worth knowing:

- **Exceptions are scoped to a category.** A file allowed under one category is
  still held to every other category's rules. An untagged check honours no
  allowlist at all.
- **`allowlistRegions` reads narrower than it acts.** Its `scope` field is prose
  for a human; the engine applies the entry at path granularity, exactly like
  `allowlistFiles`. If the exempt part is narrower than the file, keep the file
  small — nothing machine-checks that the prose and the path agree.
- **`reportAnyway` outranks both.** Put a path there for a known-open debt that
  must keep appearing in every report, however broad a glob later grows to cover
  it.

**Wrong in general** — the rule itself does not fit your project. Do not
exception it file by file; that is a growing list nobody reviews. Either turn
the check off for this project, or say so as an issue. The disabled registry
exists for exactly this reason: an audit listed there refuses loudly (exit 2)
instead of quietly passing, so nobody can mistake its silence for a score. See
[When it refuses to run](#when-it-refuses-to-run).

### The rule of thumb

If bucket 3 is more than about a fifth of the findings, stop sorting and fix the
configuration instead. A high wrong-rate is almost always one bad field in
`profile.json` — a source root that includes generated code, an adapter name
nothing implements yet — rather than two hundred independent mistakes. Run
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
`.backend-suite/hooks.map.json` with `"preCommit": true`, then install the hook:

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

**Before a pull request — the audits that match what you changed.** Changed an
endpoint's response shape, run the mock-API audit. Changed documents, run
`/review-docs` and the staleness audit. This is the one point in the cycle where
a finding is cheap to act on, because the code is still in your head.

**Before merging a large mechanical refactor — the oracle, twice.** Capture
baselines before and verify after, as in
[Job 3](#job-3--prove-a-big-refactor-changed-nothing).

**Monthly — the whole picture.** `repo_health.py` for the raw posture,
`/quality-debt` for the graded read. Monthly rather than weekly because the number
you are watching moves on the scale of months, and looking at it weekly invites
managing the number.

**After the project changes shape — re-run the survey.** `survey.py --check`
answers the one question no other check asks: what is on disk that your config
has stopped describing. `doctor.py` only walks declared → disk, and is blind to
additions by construction. Run `--check` after any of these:

- a new top-level directory, a new package, a monorepo split
- moving where your API docs, fixtures, or migrations live
- adding a language or a framework to the repo
- a dependency upgrade that relocates generated code

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/survey.py" --check
```

```
survey --check — completeness diff (disk → declared) for /path/to/project

  ✗ scripts/  [undeclared-top-level-directory]
      on disk, and no config file under .backend-suite/ declares it as a path
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
9 audit(s): 2 clean, 1 with findings, 6 refused (could not check), 0 crashed,
0 disabled (did not run at all).
```

Two clean out of nine is the honest reading of that run. Six of them did not
look.

Why it is built this way rather than defaulting to a pass is
[CONCEPTS.md](./CONCEPTS.md#the-finding-that-shapes-everything), not this guide.

---

## When it refuses to run

The suite would rather stop than print a clean report it cannot back up. Most
confusing messages are one of these five.

**"no `.backend-suite/` found … Refusing to guess."**
You are not in a project that has been set up, or not in its root. Run
`init.py`, or `cd` to the repository root.

**"unknown role 'motion'"**
A skill asked for a document you have not mapped. Add it to
`docs.manifest.json`, or tell Claude to carry on without it — but expect it to
say in its report that it did.

**"the 'x' adapter implements no … checks" / "no language adapter ships yet"**
That check is not implemented for your language — and today no language adapter
ships at all, so every code-shape audit says this. It could have returned zero
findings and looked like good news; instead it says it cannot see. Nothing is
wrong with your project.

**"REFUSING: … This is a refusal, not a finding of zero."**
Something the check depends on is missing — usually an unconfigured mock-API
contract or an incomplete config section. The message names what.

**"DISABLED — … It refuses (exit 2), not a clean result."**
No audit ships switched off today: the disabled registry is empty. (The two
design-domain audits that measured as wrong far too often on real projects left
with the design domain.) An audit listed in that registry refuses loudly instead
of quietly passing, so nobody can mistake its silence for a good score, and its
own output says what would have to change to turn it back on.

If you are scripting around the suite, the exit codes are a stated contract:
**0** ran and found nothing, **1** ran and found something, **2** could not run.
Anything else crashed. The full table, including the resolver's extra codes for
external and declined documents, is in
[DOC-ROLES.md](../plugins/backend-suite/docs/DOC-ROLES.md).

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
✗ hooks.map.json entry "…": fixHint suggests '/wire-endpoint', which is not on the
plugin's safe-repairers allowlist … A suggested fix is exactly the sentence shape
that deleted correct data in issue #116
```

When an audit tells you two things disagree, the next step is yours. That is not
the tool being lazy. It is the tool declining to guess with your data.

---

## What it will not do for you

Stated plainly, so nothing here is a surprise later.

- **It will not write your documents for you.** `/bootstrap-api-docs` makes
  it faster; the decisions are still yours. On a project with no documentation,
  the suite finds very little, because there is nothing to check against.
- **It will not fix your code.** Audits report. A repair path exists only where
  the fix is provably mechanical, and every one of them is gated by an
  allowlist the plugin ships with — which currently holds exactly one
  invocation. Ask for a repair by name; never let a finding turn into an
  unreviewed write.
- **It cannot check everything in every language.** No language adapter ships
  yet; code-shape coverage begins with `php` (see [ROADMAP.md](./ROADMAP.md)).
  A check that is not implemented for your stack refuses rather than passing.
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
  `.backend-suite/hooks.map.json` and install a pre-commit hook, but nothing is
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
rm -rf .backend-suite
claude plugin uninstall backend-suite@backend-quality-suite
claude plugin marketplace remove backend-quality-suite
```

Two things do not live under `.backend-suite/` and are worth a `git status` to
catch: the findings directory an audit writes to, and any documents
`/bootstrap-api-docs` created. The documents are yours — they are ordinary
markdown describing your project, with no dependency on the suite, and they keep
working as documents after everything above is gone. That is deliberate: the
suite reads your documents, it does not own them.

Nothing else persists. There is no daemon, no cache outside the plugin's own
install directory, and no account.
