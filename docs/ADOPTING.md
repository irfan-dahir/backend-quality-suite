# Adopting the suite on a new stack

For putting this on a project it has never seen. Assumes you've read
[ONBOARDING.md](../ONBOARDING.md) and know what the
[context layer](./CONCEPTS.md#context-layer) is.

**The honest summary:** documentation tooling and doc-role resolution are stack-
agnostic today and work anywhere. Source scanning depends on a language adapter,
and five exist (`dart`, `tsx`, `web`, `swift`, `kotlin`). If yours isn't one of them, you get the documentation half
immediately and the scanning half after writing an adapter.

---

## Install outside Claude Code

In Claude Code the suite arrives as a plugin and nothing below is needed. In any
other agent tool — Codex, Cursor, Copilot, Gemini CLI, Zed, Aider, or a plain
terminal — install the `design-suite` command instead. It needs Python 3.9 or
newer and nothing else.

```bash
pipx install /path/to/ai-design-suite      # or: uv tool install /path/to/ai-design-suite
design-suite list                          # every command, and the script it runs
design-suite doctor                        # run from inside your project
design-suite audit tokens                  # any audit: design-suite audit <name>
```

Without installing, from a checkout: `PYTHONPATH=plugins/design-suite python3 -m design_suite list`.

Every command runs the same script the Claude Code skill runs, with the same
arguments and the **same exit code** — 0 clean, 1 findings, 2 refused (and the
3/4/5 some scripts document). `design-suite <command> --help` works anywhere,
even outside a project.

**How it finds itself.** Files written for other tools cannot use
`${CLAUDE_PLUGIN_ROOT}` — only Claude Code fills that in. The suite is located
in exactly this order, and `design-suite where` tells you which one answered:

1. the installed `design-suite` (or the checkout you ran `python3 -m design_suite` from);
2. the `DESIGN_SUITE_HOME` environment variable, pointing at `plugins/design-suite`;
3. `CLAUDE_PLUGIN_ROOT`, when running under Claude Code;
4. otherwise it stops with exit 2 and lists what it tried. It never guesses.

A variable that is set but points at the wrong place is also a stop, not a
reason to try the next step. In a hook or instruction file for another tool,
prefer calling `design-suite <command>`; if it may not be installed, set
`DESIGN_SUITE_HOME` and call `python3 "$DESIGN_SUITE_HOME/bin/<script>.py"`.

Which tools read which instruction, skill, hook and MCP files is in
[research/harness-support-matrix-2026-10-08.md](./research/harness-support-matrix-2026-10-08.md).

## What actually depends on your stack

| Capability | Stack-dependent? |
|---|---|
| Doc roles, `resolve.py`, `doctor.py` | **No.** Pure JSON + paths |
| `/review-docs`, `/sync-docs`, `/bootstrap-design-docs` | **No.** Read documents, not source |
| PR drafting, client-readiness reporting | **No** |
| Token auditing | **Yes** — every adapter does it |
| Reduced-motion, adapter-pattern, layer-boundary, error-handling audits | **Yes** — some adapters; see the table below |
| Accessibility auditing, copy extraction | **Yes** — `dart` only, and both audits are currently switched off |
| Screen scaffolding, asset registration | **Yes** — adapters exist for Flutter and for bundler-driven stacks |

So the first question isn't "is my language supported" — it's "which half do I
need first."

---

## Step 1 — Pick your adapter

`adapters.lang` in `.design-suite/profile.json`:

| Value | Implements | Doesn't |
|---|---|---|
| `dart` | Tokens, reduced motion, focus order, adapter pattern, layer boundaries, error handling, API consistency, unused tokens, unwired roles, widget-shape audits (accessibility and copy are implemented but switched off) | — |
| `tsx` | Tokens (`.tsx/.ts/.jsx/.js`), adapter pattern, layer boundaries, error handling; focus order and semantics from JSX tags *(unverified)* | Accessibility, copy, reduced motion, API consistency, contract headers, token enumeration, widget-shape audits |
| `web` *(unverified)* | Tokens — everything `tsx` does, plus `.vue`/`.svelte` (`<style>` blocks, `style="…"`) and `.css/.scss/.sass/.less`; adapter pattern, layer boundaries; error handling (script and SFC files); focus order and semantics from JSX/Vue/Svelte tags | Same as `tsx` |
| `swift` *(unverified)* | Tokens (`.swift` — `Color(red:…)`/`UIColor`/hex, `.padding(N)`/`spacing:`, `cornerRadius`, animation durations), reduced motion (config-driven, `accessibilityReduceMotion`), `adapter_pattern` (module imports) | Layer boundaries (imports are modules, not paths), error handling, API consistency, focus order, semantics, copy, token enumeration/repair, widget-shape audits |
| `kotlin` *(unverified)* | Tokens (`.kt` — `Color(0x…)`, `N.dp`, `N.sp`, `RoundedCornerShape`, `tween`/`durationMillis`), reduced motion (config-driven, animator-scale signals), `adapter_pattern` (package imports) | Same as `swift` |

Every adapter refuses (exit 2, named) every capability in their "Doesn't" column — never a zero. `survey.py` proposes `swift` for a root `Package.swift` or `*.xcodeproj`, and `kotlin` for a Gradle build only when a build file enables Compose. `audit_tokens` also refuses a zero-finding sweep when files of a stack its adapter does not read sit under the scan root (a Vue tree on `tsx`); name `web`, or record the choice in `exceptions.json` `acknowledgedUnscanned`.

**If neither fits**, still install and configure the profile. Set
`adapters.lang` to the nearest thing or leave it unset: the documentation skills
work regardless, and the source-scanning skills will **refuse with a message
naming the missing capability** rather than reporting zero findings. That
refusal is the designed behaviour — see
[capability negotiation](./CONCEPTS.md#capability-negotiation).

---

**You may not need Steps 2 onward by hand.** Opening an unconfigured project in
Claude Code makes the suite offer `/run-chain understand-existing-project`, which
surveys the project (including suggesting `adapters.lang`), scaffolds the config
from the survey, and asks before every write. See the
[user guide](./USER-GUIDE.md#setting-up-an-existing-project-step-by-step). The
steps below are what it does underneath, and what to check afterwards.

## Step 2 — Write the profile

`.design-suite/profile.json`. Every project-specific fact the tooling needs,
and the only place any of them may live.

```
project      name, audience, framework, singleLocale
adapters     lang, assets, scaffold, schema, mock, doc
source       root, fileGlob, screensGlob, featureWidgetsGlob,
             sharedComponentDir, otherSharedDirs, testRoot
tokens       source, accessor, themeAccessor, generated, ownedBy
audits       configFile, exceptionsFile, baselineDir, archRulesFile
docs         manifest
pipelines    tokens, copy, assets, mockApi
assets       root, palette
verification goldensDir, goldensUpdateCommand, goldensCheckCommand
```

Only the sections your project actually has. `verification` is what
`/golden-local-ab` renders and compares; a project with no golden corpus omits
it, and the skill is then simply unavailable rather than aimed at nothing.

`profile.schema.json` describes it and **rejects absolute paths** — those work on
the author's machine and nowhere else. `doctor.py` enforces the structural half of
it (unknown sections, missing required ones); until it learned to, the schema was
shipped, documented as the thing that validates the profile, and executed by
nothing.

Then, always:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py"
```

The schema proves the profile is well-*formed*. The doctor proves it is *true* —
that every declared path resolves. Both are necessary: a schema-valid profile
pointing at three deleted files is a profile that lies confidently, and that has
happened here.

---

## Step 3 — Map your documents

`.design-suite/docs.manifest.json`. Roles → your paths. Full vocabulary and the
exit-code contract in
[`plugins/design-suite/docs/DOC-ROLES.md`](../plugins/design-suite/docs/DOC-ROLES.md).

Map only the roles you have. An unmapped role makes `resolve.py` exit 2 and the
skill stop and ask — which is correct. **Do not map a role to a file that doesn't
play that part** just to silence it; you'll get confident output about the wrong
document.

Roles owned by another repo (a design-system package, say) go in
`externalRoles`. Those resolve to a URL and exit 3: readable, never writable.

When the mapping is done, check what it bought you:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/preflight.py"
```

This is the fastest way to see the consequence of a partial manifest. On a project
mapping only a couple of the 36 roles, nearly every component reports blocked
with the exact role each
one is missing — so you can decide which roles are worth mapping rather than
guessing.

---

## Step 4 — Record the oracle before you change anything

If you're going to refactor, move, or exempt anything, capture baselines first:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/capture-baselines.sh"
```

Then you can prove a change was behaviour-preserving instead of hoping. Two
warnings the reference project learned the hard way:

- **A 0-finding baseline proves nothing.** 0-before and 0-after is the same
  output whether the check works or not. Plant a deliberately-broken file and
  confirm the audit catches it.
- **The script refuses to baseline a self-skipping audit**, marking it `INERT`.
  If you see that, fix the audit — don't record it as clean.

---

## Step 5 — Wire read-only audits into your own CI

This plugin's own `.github/workflows/validate.yml` deliberately does not run
the design audits — it has no consuming project to point them at (see the
comment at the top of that file). **Wiring them into CI is your project's
job, not something adopting the suite does for you.** Skipping this step
means every audit only ever runs when someone remembers to run it by hand.

Per `CLAUDE.md`'s tier table, an audit that is read-only and report-only
(`tier: auto`) belongs running automatically — on every push or PR — not
only on demand. Add each audit you rely on as a step in your project's CI,
the same way `validate.yml` lists its own gates.

One audit needs a flag to do this safely: `audit_reinvented_components.py`
compares against `ds_flutter`'s resolved package, and if that dependency
can't be resolved (e.g. `flutter pub get` was never run on the runner) it
now refuses with exit code `2` rather than reporting a clean run — per the
suite's governing principle, "could not compare anything" must never look
like "found nothing". Make sure your CI step treats any non-zero exit as a
failure:

```yaml
- name: No private widget reinvents a ds_flutter component
  run: |
    flutter pub get
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_reinvented_components.py"
```

Do not swallow that exit code (`|| true`, `continue-on-error: true`,
grepping stdout for a substring) — doing so silently turns "the dependency
never resolved" back into the same false-clean result this fix removed.

### Pin the version your CI runs

A CI step that checks the suite out with no `ref:` tracks whatever is on the
suite's `main` at the moment the job runs. That is not a dependency — it is a
live deploy into your repo on every merge someone else makes. **Every
consumer checkout pins a tag.**

```yaml
- uses: actions/checkout@v4
  with:
    repository: irfan-dahir/ai-design-suite
    ref: design-suite--v0.2.0   # <sha the tag resolves to> — pin, never track main
    token: ${{ steps.suite-token.outputs.token }}
    path: _design_suite
```

The SHA goes in the comment so a reader can resolve the tag exactly without
fetching. A tag can be moved; the SHA beside it is the record of what was
tested against.

**What the version promises.** Within a minor version, two things do not
change:

- **The exit contract.** An audit that exits `0`/`1`/`2` for a given state
  keeps doing so. New findings may appear from a bug fix; the meaning of an
  exit code does not move.
- **The disabled set.** An audit that is `disabled` stays disabled, and one
  that runs stays running. A component switching off is a behaviour change
  your CI would read as silence, so it needs a minor bump and a line in the
  release notes — per the governing principle, silence must never be
  mistakable for a pass.

Anything else — new audits, new adapters, wider detection inside an existing
audit — can land in a patch. Below `1.0.0` a minor bump is the suite's
breaking-change signal.

**Upgrading.** Read the release notes for the new tag, change the `ref:` and
its SHA comment in one commit, run the audits on that branch, and merge only
if the diff in findings is one you accepted. One commit, one tag, reviewable.

**The local path is not pinned by this.** Pinning `ref:` fixes CI only.
Locally the plugin is installed from a marketplace and resolves to whatever
`claude plugin update` last fetched — see
[USER-GUIDE.md](./USER-GUIDE.md#which-version-you-are-running).

### Upload findings to GitHub code scanning (SARIF)

`bin/export_sarif.py` turns the findings envelopes into one SARIF 2.1.0 log —
one run per audit — that GitHub code scanning (or any SARIF viewer) can ingest.
**This is for your project's CI, not this repo's**: the suite's own GitHub
Actions are unavailable, so nothing below has run in this repository's CI; the
export itself is tested locally against the vendored official schema
(`bin/export_sarif_test.py`).

The property worth knowing before you rely on it: an audit that refused, was
INERT, crashed, or is disabled does **not** disappear from the log. It gets a
run with `invocations[0].executionSuccessful: false` and a
`toolExecutionNotifications` entry naming the reason, so "could not check" is
in the uploaded file rather than looking like "no alerts". How prominently
GitHub's UI surfaces those notifications is GitHub's choice and is not verified
here — check the tool status page for your repository after the first upload.

Pass `--health` with a fresh `repo_health.py --json` document; without it the
export can only say an audit has "no envelope collected", not *why*.

```yaml
permissions:
  contents: read
  security-events: write        # required by upload-sarif

steps:
  # … checkout your project and the pinned suite (see "Pin the version your CI runs" above) …
  - name: Run every audit, record each one's status
    id: audits
    run: |
      set +e
      python3 _design_suite/plugins/design-suite/bin/repo_health.py --json > health.json
      echo "status=$?" >> "$GITHUB_OUTPUT"
  - name: Export SARIF (refusals included as failed invocations)
    run: |
      python3 _design_suite/plugins/design-suite/bin/export_sarif.py \
        --health health.json --validate --out design-suite.sarif
  - uses: github/codeql-action/upload-sarif@v3
    with:
      sarif_file: design-suite.sarif
  - name: A crashed audit fails the job — after the upload, not instead of it
    if: steps.audits.outputs.status != '0'
    run: exit 1
```

Each run carries its own `automationDetails.id` (`design-suite/<audit>/`) and
tool name, so you do not need a `category:` input. Severity maps critical →
`error`, should-fix → `warning`, fyi → `note`; rule ids are
`<audit>/<category>`; file paths are relative to `%SRCROOT%`. A finding with no
file has no location, and GitHub may not display it — the run's notifications
say how many. Verify the action version and permissions against GitHub's
current code-scanning docs before relying on this snippet.

For a PR comment rather than code-scanning alerts, see
[`/design-review-pr`](../plugins/design-suite/commands/design-review-pr.md).

---

## Step 6 — Turn a CHANGELOG entry into a GitHub release

This step is deliberately small and generic: it is the "read a CHANGELOG
section, cut a GitHub release from it" slice of releasing, not a full release
script. Signing, versioning strategy, changelog authorship, and distribution
stay yours — see the C4 row in [ROADMAP.md](./ROADMAP.md), which is why
`/cut-release` stays a per-project component rather than moving into this
plugin.

**Assumption: your `CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/)
heading style** —

```markdown
## [Unreleased]

## [1.2.0] - 2026-09-14
### Added
- ...
### Fixed
- ...
```

Given that shape, cutting a release is two commands:

```bash
# 1. Extract the section for the version you're releasing as plain text.
python3 "${CLAUDE_PLUGIN_ROOT}/bin/changelog_to_release_notes.py" CHANGELOG.md \
  --version 1.2.0 > /tmp/release-notes.txt

# 2. Turn that section into a GitHub release. Tag convention below is an
#    example — use whatever your project already tags with.
gh release create v1.2.0 --title v1.2.0 --notes-file /tmp/release-notes.txt
```

Releasing what is still under `[Unreleased]` (e.g. moving it under a new
version heading is your own step, done first) works the same way with
`--unreleased` instead of `--version <x.y.z>`.

The script does exactly one thing — find a `## [...]` heading in a Keep a
Changelog file and print the body under it — and refuses (exit `2`) rather
than printing nothing on success, per this repo's governing principle: no
matching heading, or an empty section, is an error, not a silent empty
release. It contains no project name, no path, and no assumption about your
tag format; it only knows the Keep a Changelog heading shape.

This is documentation, not automation you're expected to wire into CI —
`gh release create` is a one-way, externally visible action, so run it by
hand at release time rather than triggering it unattended.

---

## Release checklist — composing the small tools, not one release.sh

Issue #79 asked whether the suite should ship a single `release.sh` covering
version checks, audits, tagging, deploy, and a smoke check. The research
posted on that issue (worth reading in full there) concluded **no** — split
it. Version consistency is generic; audits are already `gates.py`'s job;
tagging is a one-line `git`/`gh` call not worth a component; "deploy" only
generalizes for a docs/static site (a Flutter app has a
build+sign+store-submission pipeline instead, which is `/cut-release`'s
job, near-zero reuse — see the C4 row in [ROADMAP.md](./ROADMAP.md)). Bundling
these behind one script would hide that the one attractive-sounding
piece — "deploy" — is precisely the piece that does not generalize.

So this is a **documented recipe composing independent, small, exit-code
scripts** — run by hand, in order, at release time — not a single command:

1. **Check every version source agrees.**

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/check_version_consistency.py"
   ```

   Reads `release.versionSources` from `.design-suite/profile.json` — the
   files this project considers authoritative for its own version number
   (`package.json`, `pubspec.yaml`, the top `CHANGELOG.md` heading, ...) and
   how to read a version out of each. Exits `1` the moment two disagree,
   printing which file has which version. Exits `2` — a refusal, not a
   pass — if no sources are configured at all: a release-safety check that
   silently no-ops on an unconfigured project would read as "consistent"
   for the wrong reason.

2. **Run this project's own audits.**

   ```bash
   python3 plugins/design-suite/bin/gates.py
   ```

   Not reimplemented here — `gates.py` (or whatever a project has declared
   as its own equivalent audit runner) already is "run the gates, exit
   non-zero if red." A release recipe that wrapped its own copy of that
   logic would just be restating a list that already exists in one place.

3. **Turn the CHANGELOG entry into release notes.**

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/changelog_to_release_notes.py" CHANGELOG.md \
     --version 1.2.0 > /tmp/release-notes.txt
   ```

   Step 6 above, unchanged.

4. **Tag.** Deliberately not its own script — a one-line `git`/`gh`
   invocation isn't worth a component or config surface of its own:

   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```

   (Convention shown; use whatever your project already tags with.)

5. **Deploy the docs site — docs-site projects only.**

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/deploy_docs_site.py"
   ```

   Reads a "site-assembly recipe" from `release.docsSite` in
   `.design-suite/profile.json`: a `buildCommand`, a `deployCommand` — both
   argv lists your project owns (`rsync`, the `gh-pages` CLI, `netlify
   deploy`, `aws s3 sync`, a local publish script, whatever you already
   use — this suite hardcodes no hosting provider), and `smokeCheckRoutes`.
   It runs the build, then the deploy, **then the post-deploy smoke check
   as part of this same script** — GETs each declared route and checks its
   status (200 by default), failing loudly if any command or any route
   fails. There is no separate smoke-check step: folding it into this
   script is what makes a deploy something other than "ran a command and
   hoped." Exits `2` if `release.docsSite` isn't configured — this is a
   docs-site-only tool, and projects with no docs site to deploy (a mobile
   app, say) simply skip this step.

   ```json
   "release": {
     "docsSite": {
       "buildCommand": ["npm", "run", "build:docs"],
       "deployCommand": ["npx", "gh-pages", "-d", "docs/dist"],
       "smokeCheckRoutes": [
         {"url": "https://your-project.example/docs/", "expectedStatus": 200}
       ]
     }
   }
   ```

6. **Cut the GitHub release.**

   ```bash
   gh release create v1.2.0 --title v1.2.0 --notes-file /tmp/release-notes.txt
   ```

Nothing above is wired into CI, and none of it should be run unattended:
tagging, deploying, and creating a release are one-way, externally visible
actions, so this stays a checklist a person runs, not a background job.

---

## Accessibility pre-flight

Issue #80 asked for an "accessibility pre-flight bot for PRs." The research
posted on that issue (worth reading in full there) concluded **no new
mechanism is needed** — every mechanically-checkable a11y surface this suite
can reach is already covered by three existing audits, and the "pre-flight"
behaviour being asked for is already what `bin/run_precommit_audits.py`
(issue #46) does with any `hooks.map.json` entry marked `"preCommit": true`.
"Bot" was marketing language for that existing composition, not a gap. A
real PR-commenting bot would need CI, which is dead per `CLAUDE.md` rule 3 —
not something to build around.

> 🔴 **`audit_accessibility` is currently DISABLED and this recipe cannot be
> followed as written.** It was measured at 100% false positives on two real
> projects (issue #104) and switched off in PR #107: it exits 2, and every
> reporting surface names it as "NOT RUN — not a clean result" rather than
> letting the silence read as a pass. The other two audits below are live.
> The re-enabling bar is in `design_suite/engine/audit_discovery.DISABLED`;
> until it is met, adding the first entry buys a gate that checks nothing and
> says so on every commit.

So turning on an accessibility gate is a config change, not a new
component. Add these entries to your project's
`.design-suite/hooks.map.json` (see
[`hooks.map.schema.json`](../plugins/design-suite/templates/hooks.map.schema.json)
for the full field contract):

```json
{
  "entries": [
    {
      "name": "Accessibility audit",
      "glob": ["lib/**/*.dart"],
      "command": ["python3", "${CLAUDE_PLUGIN_ROOT}/bin/audit_accessibility.py",
                  "--out", ".design-suite/scratch/hook-a11y.json"],
      "scopeMode": "dir",
      "scopeArg": "--dir",
      "reportWhen": "findings",
      "findingsPath": ".design-suite/scratch/hook-a11y.json",
      "fixHint": "/audit-accessibility",
      "_disabled": "audit_accessibility exits 2 (issue #104). Leave preCommit false until the DISABLED registry's re-enabling bar is met.",
      "preCommit": false
    },
    {
      "name": "Focus order audit",
      "glob": ["lib/**/*.dart"],
      "command": ["python3", "${CLAUDE_PLUGIN_ROOT}/bin/audit_focus_order.py",
                  "--out", ".design-suite/scratch/hook-focus-order.json"],
      "scopeMode": "dir",
      "scopeArg": "--dir",
      "reportWhen": "findings",
      "findingsPath": ".design-suite/scratch/hook-focus-order.json",
      "fixHint": "/audit-focus-order",
      "preCommit": true
    },
    {
      "name": "Reduced-motion audit",
      "glob": ["lib/**/*.dart"],
      "command": ["python3", "${CLAUDE_PLUGIN_ROOT}/bin/audit_reduced_motion.py",
                  "--out", ".design-suite/scratch/hook-reduced-motion.json"],
      "scopeMode": "dir",
      "scopeArg": "--dir",
      "reportWhen": "findings",
      "findingsPath": ".design-suite/scratch/hook-reduced-motion.json",
      "fixHint": "/audit-reduced-motion",
      "preCommit": true
    }
  ]
}
```

Adjust the `glob` to your own `source.root` (these three audits all default
`--dir` to the profile's `source.root` when it is omitted, but a hook needs
a glob to know which staged files to scope the run to at all). Each entry
writes its findings to a scratch path under `.design-suite/scratch/`, never
to the whole-repo findings file an unscoped `/audit-*` run owns — a
narrowed pre-commit run replacing a full sweep's artefact would make
`/design-debt` grade the project on a fraction of it, the same failure mode
`hooks.map.schema.json`'s `command` field warns about for `audit_tokens.py`.

**What this trio does not cover: colour contrast.** That is a deliberate,
documented exclusion — `/audit-contrast` is a `maturity: pointer` entry
redirecting to the org's design-system repo's (`<design-system-repo>`) own
`tooling/scripts/audit_contrast.py --matrix`, because contrast needs real
rendered-colour maths against a shared palette, not a text scan. See
[`/audit-contrast`](../plugins/design-suite/commands/audit-contrast.md) for
where to run it. A pre-commit a11y gate built from this recipe is
intentionally silent on contrast; that is this suite staying out of a check
it does not own, not a hole in the recipe.

Once the entries are in place, install the gate:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/install_precommit_hook.py"
```

From then on, `git commit` blocks on any accessibility, focus-order, or
reduced-motion finding in the files you staged — the same fail-closed
behaviour every other `preCommit: true` entry gets, and no new script.

---

## Case study: a real TypeScript codebase

The portability claim was tested rather than asserted. Target:
[`calcom/cal.com`](https://github.com/calcom/cal.com) — real, actively
developed, MIT, ~47k stars, TypeScript/React/Tailwind. Read-only: a local shallow
clone, never pushed to, no fork, no PR. Scope: `packages/ui`, **142 `.tsx`
files**, no test or story files excluded.

### What worked

| | Result |
|---|---|
| `resolve.py` / `doctor.py` | **Caught a real mistake.** The profile I wrote named a token-source path that didn't exist in that repo. The doctor rejected it on a codebase it had never seen — exactly the job |
| `audit_tokens.py` | **20 genuine findings across 7 files.** Real hex colours (`#111827`, `#FF0000`), real `borderRadius`/`width`/`height` literals. Not zero, not garbage |
| `audit_accessibility.py`, `extract_copy.py` | **Correctly refused.** `tsx` implements neither capability. Capability negotiation exercised against an unfamiliar project |

### The gap it found, stated rather than hidden

cal.com styles almost entirely with **Tailwind utility classes**
(`className="h-4 w-4 …"`). In the 142-file scope, only **2** files contain any
raw hex colour and only **13** use an inline `style={{}}` object at all.

`tsx.py`'s regexes target inline style objects. **So on a Tailwind-first project,
most of the styling is outside what the adapter can currently see.** The adapter
isn't wrong; it's incomplete for that styling paradigm. 20 real findings is a
true result and also not the whole picture.

If your project is Tailwind-first, calibrate accordingly: a low token-audit count
means "few inline styles," not "few hardcoded values."

### What this does not prove

- **The asset and scaffold seams.** No adapter exists, so there was nothing to
  test.
- **Tailwind-class-level auditing.** That needs a new check, not a bigger sample.
- **Anything about a third language.** Two adapters is evidence of a working
  seam, not proof of universality.

---

## Writing an adapter

`design_suite/adapters/base.py` defines the contracts: `AdapterContext`,
`Check`, `CheckSet`, `CapabilityError`, plus `AssetAdapterProtocol` and
`ScaffoldAdapterProtocol` — all three seams now have implementations to read
alongside the contract.

Start with `assets/bundler.py`. It is the shortest adapter here and the clearest
statement of the rule: it implements the two questions it can answer and raises
`CapabilityError` for the three it cannot. Then `tsx.py` for a language adapter
that audits two paradigms while still declining accessibility and copy.

Two rules:

1. **Declare only capabilities you implement.** A capability that returns empty
   is worse than one that refuses, because empty reads as "clean."
2. **Never reach back into the engine for language logic.** The engine takes
   checks as a parameter and imports no adapter — that's what keeps the seam
   real.

Then prove the seam still holds:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/adapters/verify_seam.py"
```

This runs in CI on every change. Without it the seam would silently rot back
into Dart-shaped assumptions within a few commits.

---

## Client-facing projects

**Install `design-suite` alone.** Skip `house-style`.

House-style carries the org's letterhead, our internal PR process, and
client-readiness reporting. None of that belongs baked into tooling that lives in
a client's repository.

Also, per standing practice: keep client names, hostnames, account IDs, and
infrastructure detail out of `profile.json` and out of any generated collateral.
Use placeholders.

---

## PR verification-tier trailer (house-style projects)

A project that installs `house-style` inherits a `Verification-Tier:` /
`Verified-By:` trailer in its PR description template (§6 of
[`PR.md.template`](../plugins/house-style/templates/docs/PR.md.template)),
mirroring the `Co-Authored-By:` commit trailer convention. Vocabulary —
`unverified` / `self-tested` / `cross-verified` / `human-reviewed` — comes from
[`verification-tier.schema.json`](../plugins/design-suite/templates/verification-tier.schema.json)
(issue #55); a PR takes the **lowest** tier among its bundled commits.

The rule that matters most: **an agent may self-report `unverified` or
`self-tested`, never `cross-verified` or `human-reviewed`** — those two require
an actual independent party, not the drafting agent's own say-so. `/draft-pr-description`
leaves the trailer's value blank rather than guessing it. This is a body trailer, not
a label or a CI check — checking a PR body's shape doesn't fit `gates.py`'s
tree-on-disk model, and a truthfulness check needs a human in the loop regardless.
`plugins/design-suite/bin/check_pr_verification_trailer.py` spot-checks presence
(not truthfulness) against merged PRs on request; it is a manual script, not
wired into CI or `gates.py`.

Ships in `PR.md.template` itself, so a project that customises its `pr` doc role
keeps the trailer unless it deliberately deletes it — the same load-bearing-fenced-block
mechanism that keeps the rest of that template from drifting from what
`/draft-pr-description` actually copies.

---

## Using the suite from a harness other than Claude Code (MCP tools)

The plugin ships one MCP server, `plugins/design-suite/mcp/audit_server.py`
(stdlib Python, stdio transport). Research on 2026-10-08
(`docs/research/harness-support-matrix-2026-10-08.md`, on branch
`docs/issue-0-harness-support-matrix`) found that MCP **tools** are the only MCP
feature every MCP-capable harness supports, so onboarding and chains are exposed
as tools rather than prompts. Every tool runs an existing `bin/` script; it does
not decide anything those scripts do not.

**What the tools do, in plain language**

| Tool | Writes? | What it does |
|---|---|---|
| `project_status` | nothing | Says whether this project is configured, new, existing, partially set up, declined, or could not be told — the same answer the Claude Code start-of-session hook gives — and, if configured, which audits work, which refuse and why, and which are switched off. The agent is told to *offer* onboarding, never to start it. |
| `survey` | only `.design-suite/survey.json` (`check: true` writes nothing) | Looks at the project and records what it found. |
| `resolve_role` | nothing | Says which file plays a document role (e.g. the design doc). |
| `doctor` | nothing | Checks the configuration and lists what is unresolved or still a machine guess. |
| `repo_health` | audit report files only | Runs every audit and reports clean / findings / refused / disabled. |
| `init_from_survey`, `map_project` | yes — previewed first | Create or fill in `.design-suite/` from the survey. |
| `chain_status`, `chain_next` | nothing | Where a guided chain (e.g. `onboard-new-client`) has got to and what comes next. |
| `chain_checkpoint` | yes — previewed first | Records a chain step as done or skipped. A checkpoint step needs two confirmed calls: one records the run, the second records the user's sign-off. |
| `audit_*` | audit report files only | One tool per audit. Disabled audits stay listed and say they are disabled. |

**How writing tools protect you.** Called normally, a writing tool changes
nothing: it shows exactly which files it would write and their contents, plus a
`preview_id`. Only a second call with `confirm: true` and that same `preview_id`
writes — and it writes precisely the previewed bytes. If the arguments differ,
the id is unknown or already used, or any file in the project changed since the
preview, the call is refused with the reason. Every refusal comes back as an
error result naming why, never as a quiet success. `propose_config` has no MCP
tool yet; run it from a terminal with `design-suite propose-config` (it
previews by default).

**Registering the server.** The easiest way is `design-suite harness` (preview)
then `design-suite harness --apply`: it writes these entries for you. Every
entry starts the server with `design-suite mcp`, so no machine-specific path
ends up in a committed file; install the CLI first (see "Install outside Claude
Code"). Claude Code needs nothing: the plugin registers the server itself.
Formats below are from each vendor's docs as read on
2026-10-08; none of these harnesses has been tested against this server — only
the stdio JSON-RPC test in `bin/mcp_onboarding_test.py` has run, so treat every
row as **UNVERIFIED in practice**. Rows marked UNVERIFIED were also not
confirmed in the vendor docs.

| Harness | Where | Shape |
|---|---|---|
| Claude Code | plugin install registers it automatically; or project `.mcp.json` | `{"mcpServers": {"design-suite": {"command": "design-suite", "args": ["mcp"]}}}` |
| VS Code Copilot (agent mode) | `.vscode/mcp.json` (`"servers"`) or root `.mcp.json` (`"mcpServers"`) | same command/args |
| Copilot cloud coding agent | repository Settings UI (JSON); a `tools` allowlist is required | same command/args; tools only |
| Cursor | `.cursor/mcp.json` | `mcpServers` as above |
| Codex | `.codex/config.toml` (trusted projects) or `~/.codex/config.toml` | `[mcp_servers.design-suite]` with `command = "design-suite"`, `args = ["mcp"]`. Codex reads the server's `instructions`, which restates the offer-don't-start and INERT rules |
| Gemini CLI | `.gemini/settings.json` | `mcpServers` with stdio `command`/`args` |
| Zed | `.zed/settings.json` | `context_servers` entry with the command (exact keys UNVERIFIED) |
| Amp | `.amp/settings.json` (workspace, needs approval) | `amp.mcpServers` |
| opencode | `opencode.json` | `mcp` entry, `type: "local"`, `command: ["design-suite", "mcp"]` |
| Roo Code | `.roo/mcp.json` | format UNVERIFIED |
| Devin Desktop (formerly Windsurf) | user-level only: `~/.config/devin/mcp_config.json` | add it yourself; the suite never writes to your home directory |
| Cline | user-level only: `cline_mcp_settings.json` | add it yourself |
| Aider | no MCP support | use the `design-suite` CLI directly |

In harnesses without a session-start hook, nothing calls `project_status` for
you. `design-suite harness` writes this rule into your `AGENTS.md`; if you
write it yourself, use: "At the start of a session, call the
design-suite `project_status` tool; if it reports new, existing or partial,
offer onboarding — do not start it."

## Exchanging tokens with Figma, Tokens Studio and Style Dictionary (DTCG)

Two scripts speak the W3C Design Tokens Community Group format —
[Design Tokens Format Module 2025.10](https://www.designtokens.org/tr/2025.10/format/),
a *Final Community Group Report* (stable, but a Community Group report rather
than a W3C Recommendation). Style Dictionary v4+ reads it natively. Both are
`maturity: unverified`: tested on synthetic token sets only.

| Script | Invocation | What it writes |
|---|---|---|
| `bin/export_tokens_dtcg.py` (`/export-tokens-dtcg`) | explicit | Nothing by default (stdout preview). `--out PATH` writes that one `.tokens.json`; `--report PATH` a JSON summary. Never source. |
| `bin/import_tokens_dtcg.py` (`/import-tokens-dtcg`) | auto | Nothing by default. `--write-report [PATH]` writes one drift report (default `.design-suite/dtcg-drift.json`). Never source, never the DTCG file. |

To point the drift check at a file without passing `--file` every time, add
to the profile:

```json
"tokens": { "source": { ... }, "accessor": "...", "dtcg": { "path": "design/figma.tokens.json" } }
```

What to expect per stack: Dart reads `tokens.source` through the adapter's
existing value enumerator; TSX/web read CSS custom properties (`@theme` or
`:root`) from a `.css` `tokens.source.path` and **refuse** a JS Tailwind config
(it is never executed); Swift and Kotlin read `static let` / `val`
declarations from `tokens.source.path`. A declaration with no faithful DTCG
form (an `EdgeInsets`, an `oklch()` colour, a `calc()`) is listed by name — on
stderr, in the report, and inside the exported file's root `$extensions` — and
the export exits 1, never 0. The drift check counts the same tokens as
`uncomparable`, never as matching.

Files from older tools in the draft-era shape (hex-string colours, `"16px"`,
unprefixed `value`/`type`) are refused with exit 2 unless you pass
`--accept-draft-forms`. Not supported, refused rather than ignored: JSON
Pointer `$ref` and `$extends`. Not done: making `/audit-tokens` treat the DTCG
file as its token source — see `commands/import-tokens-dtcg.md`.

## Known limits, in one place

| Limit | Status |
|---|---|
| Accessibility + copy extraction are `dart`-only | Real gap. `tsx` refuses by name rather than under-reporting |
| Tailwind-class styling largely invisible to `tsx` | Named, tracked gap — see the case study |
| Tailwind token *enumeration* | `tsx.token_names()` returns None — arbitrary values are audited, but nothing parses `tailwind.config.*` to enumerate the scale |
| styled-components / Emotion | Hex and duration literals inside template literals are caught; property-level checks tuned for JS object syntax under-report there |
| house-style duplicates ~40 lines of role resolution | Deliberate. It cannot reach design-suite's resolver across the plugin cache's per-plugin version hashes. `bin/resolve_role.py` is parity-tested against the real one; extend `resolve.py`, never this |
| Much of the suite is ⚪ `unverified` | Read the maturity column in [CATALOG.md](./CATALOG.md) before relying on a skill |

### Generated per-harness files

`design-suite harness` previews the files other harnesses need (an `AGENTS.md`
block, project-level MCP configs, a `.agents/skills/` mirror with
`${CLAUDE_PLUGIN_ROOT}` rewritten to `${DESIGN_SUITE_HOME}`). Every MCP config
runs `design-suite mcp`, so the CLI must be on PATH (preview warns if it is not)
and the configs stay current when the suite moves. `.mcp.json` and
`.claude/skills/` are skipped unless you pass `--include-claude` — the Claude
plugin already provides both. `--apply` writes
them (explicit tier: it writes into the project root); `--check` exits 1 when
they are stale and 2 when it cannot tell. Harnesses that are configured only at
user level, and formats the harness research leaves unverified, are printed as
instructions instead of written. `doctor` and `repo-health` list any harness
whose own instruction file SHADOWS `AGENTS.md`.
