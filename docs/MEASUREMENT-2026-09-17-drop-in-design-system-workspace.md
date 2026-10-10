# Measurement — drop-in onboarding against a third consumer, 2026-09-17

**A `design-system` archetype that is also a Dart pub workspace.** The first
honest end-to-end onboarding dry run against a real repository neither the
suite's templates nor its recipes were written from.

This is a **measurement, not a fix**. Nothing in `survey.py`, `init.py`,
`resolve.py`, `archetypes.py` or any adapter was touched while taking it. Every
number below is followed by the command that produces it. Where a prior
read-only survey's claim no longer reproduces, that is recorded as a fixed bug,
not corrected silently.

Written in RFC-0002 §2b's style: **name the gaps before anyone builds against
them, so the gaps become the acceptance test.**

---

## 0. The subject, and the read-only rule

The consumer is a separate, client-adjacent repository on this machine. It is
**read-only for this measurement**: it was surveyed in place with commands that
write nothing, and everything that scaffolds was run against a copy in a scratch
directory. Its working tree was verified clean before and after.

Throughout, `$EDS` is that repository's absolute path and `$COPY` is
`/tmp/scratch-<agent-id>/eds-copy`. `$SUITE` is this worktree. Substitute your
own; no path from either repository is committed to the plugin.

Shape, from its own root manifest:

```
$ cat $EDS/pubspec.yaml
name: _ds_workspace
publish_to: none
version: 3.8.0
workspace:
  - packages/ds_flutter
  - packages/ds_tokens_client_a
  - gallery
```

Three workspace members. One root manifest that is a stub. A `tokens/` tree of
JSON that generates Dart, CSS and Figma output. 137 component pages under
`docs/components/`. No `.design-suite/`.

Commit surveyed: `162f3367ce83befde6a8d41dd5fd11c252495a06`, branch `main`,
`workingTreeDirty: false`.

---

## 1. The real onboarding path, read-only

### 1a. `survey.py --stdout`

```
$ python3 $SUITE/plugins/design-suite/bin/survey.py --project-root $EDS --stdout
```

Exit 0. Key values, verbatim from the JSON:

| Field | Value |
|---|---|
| `filesSeen` | `992` |
| `stack.stack` | `"dart/flutter"` |
| `stack.candidateAdapter` | `"dart"` |
| `stack.manifestsFound` | one entry, `pubspec.yaml` |
| `stack.fileCensus` | `dart/flutter: 381`, `python: 38`, `javascript/typescript: 1` |
| `sourceRoots` | `[]` |
| `candidateTokenSources` | 1 entry, confidence `0.5` |
| `documents.documents` | 14 proposals, every one `"provenance": "inferred"` |
| `documents.unmapped` | 245 paths |
| `couldNotDetermine` | 4 entries |

The four refusals, quoted:

```
  ? sourceRoots: pubspec.yaml declares a `workspace:` — this manifest is a stub
  ? sourceRoots: no conventional source directory exists for the detected manifest(s)
  ? tokens.source: token-source detection is the worst-measured signal in the suite
  ? docs.roles: 245 document(s) map to no role in the vocabulary
```

**The `sourceRoots: []` refusal is correct and well-worded.** It names the exact
mechanism (`workspace:` makes the root manifest a stub), states the consequence
("Members hold the real sources"), and cites the limitation rather than hiding it:
"A single `source.root` cannot describe this project; resolve.py hardcodes one
root today (RFC-0002 §3g #3)." It then refuses a second time on the general
grounds that no conventional source directory exists. Two refusals, two reasons,
no guess. This is the governing principle working exactly as intended, and it is
the best-behaved part of the whole run.

### 1b. `survey.py --check`

```
$ python3 $SUITE/plugins/design-suite/bin/survey.py --project-root $EDS --check
survey --check: no .design-suite/ in $EDS — there is no declared side to diff
against. Run the survey first; refusing to report a clean completeness check on
a project that declares nothing.
$ echo $?
2
```

Correct. A zero-finding completeness check on a project that declares nothing
would be exactly the indistinguishable silence the suite exists to prevent.

### 1c. `doctor.py`

```
$ python3 $SUITE/plugins/design-suite/bin/doctor.py --profile $EDS/.design-suite/profile.json
no profile at $EDS/.design-suite/profile.json
$ echo $?
1
```

Correct, though terse — it does not say what to run next, where `survey --check`'s
refusal does.

---

## 2. `init.py --from-survey` against a copy

```
$ cp -R $EDS $COPY
$ python3 $SUITE/plugins/design-suite/bin/init.py --dir $COPY --from-survey
```

### What it seeds

Ten files written: `survey.json`, `profile.json`, `docs.manifest.json`,
`design-audit-config.json`, `exceptions.json`, `arch-rules.json`,
`hooks.map.json`, `known-traps.json`, `component-capabilities.json`,
`.gitignore`, `profile.schema.json`.

**Three profile fields seeded, all `inferred`:**

```
--from-survey: seeded 3 field(s) from survey.json. EVERY one is provenance
`inferred` — a machine proposed it and nobody has reviewed it.
  ~ adapters.lang = 'dart'
  ~ project.framework = 'dart/flutter (inferred from the root manifest — ...)'
  ~ source.fileGlob = '**/*.dart'
  Left as TODO because the survey could not determine them (a visible gap, not a
  guess): source.root
```

Both rules from `init.py`'s own docstring hold: every seeded field is written
`inferred`, and `source.root` is left a visible TODO rather than guessed. Verified
in the written file — `profile.json`'s `provenance.fields` carries exactly three
entries, each `"state": "inferred"`, each with an `evidence` string and a
`verifiedAgainst.commit`.

### What stays TODO

Everything else. `profile.json` ships with `project.name = "TODO_PROJECT_NAME"`,
and TODO placeholders in `project.audience`, `project.singleLocale`,
`source.root`, `source.screensGlob`, `source.featureWidgetsGlob`,
`source.sharedComponentDir`, `source.testRoot`, `tokens.source.path`,
`tokens.accessor`, `tokens.themeAccessor`, `tokens.ownedBy`.

**Zero doc roles are seeded**, although the survey proposed 14 documents with
confidences up to 0.9. `docs.manifest.json` arrives with the fixed four-role
template stub — `design`, `flows`, `decisions`, `backlog` — pointing at
`docs/DESIGN.md`, `docs/FLOWS.md`, `docs/DECISIONS.md`, `docs/BACKLOG.md`. **None
of those four files exists in this repository, and for a design-system package
three of them arguably never should** (RFC-0002 §2c predicted exactly this).
Meanwhile `docs/ACCESSIBILITY.md`, `docs/MOTION.md`, `docs/RESPONSIVE.md`,
`docs/TOKENS.md` and `docs/CONTRIBUTING.md` all exist, were all proposed by the
survey, and none of them is written into the manifest.

So the drop-in's first act is to introduce four doctor errors that are pure
scaffold artifact, while leaving five correct mappings on the floor.

### What `doctor.py` then says

```
$ cd $COPY && python3 $SUITE/plugins/design-suite/bin/doctor.py
doctor: provenance — 0 of 24 field(s) carry a human decision ('declared' or 'approved').
  24 field(s) are UNTRUSTED.
...
design-suite doctor — 12 problem(s):
  ✗ source.root: "TODO: repo-relative source root, e.g. 'lib' or 'src'" does not exist
  ✗ source.sharedComponentDir: 'TODO or delete: ...' does not exist
  ✗ source.testRoot: 'TODO or delete: ...' does not exist
  ✗ tokens.source.path: "TODO: repo-relative path to the token source, ..." does not exist
  ✗ audits.baselineDir: '.design-suite/baselines' does not exist
  ✗ docs.roles.design: 'docs/DESIGN.md' does not exist (delete the role, or move it to externalRoles)
  ✗ docs.roles.flows: 'docs/FLOWS.md' does not exist (delete the role, or move it to externalRoles)
  ✗ docs.roles.decisions: 'docs/DECISIONS.md' does not exist (delete the role, or move it to externalRoles)
  ✗ docs.roles.backlog: 'docs/BACKLOG.md' does not exist (delete the role, or move it to externalRoles)
  ✗ docs.directories.specs: 'docs/specs' does not exist
  ✗ docs.directories.derived: 'docs/derived' does not exist
  ✗ hooks.map.json entry "TODO: ...": fixHint suggests '/audit-tokens', which is not on the
    plugin's safe-repairers allowlist ...
```

**The provenance line: `0 of 24 field(s) carry a human decision`.** That is the
honest post-drop-in state and it reads correctly: three fields are named
`inferred` with their evidence, twenty-one have no provenance entry at all and
are reported as untrusted rather than as approved. The distinction between "a
machine proposed this" and "nobody recorded how this got here" survives into the
output.

Nine of the twelve problems are placeholder text the scaffolder itself wrote.
That is by design — but it means a drop-in's first doctor run is dominated by its
own scaffolding, and the two problems that describe the *project* (no source
root, no token source) are buried among them.

### `preflight.py`

```
$ cd $COPY && python3 $SUITE/plugins/design-suite/bin/preflight.py
preflight against $COPY
7/47 component(s) have every precondition satisfied.
...
40 blocked. Map the missing roles in docs.manifest.json, or accept that those
skills cannot run here.
```

**7 of 47 immediately after a `--from-survey` drop-in.** This is the single most
useful number in this document: it is the honest answer to "what does the drop-in
give you out of the box" for this archetype, and it is 15%.

---

## 3. False-positive measurement on `survey --check`

The first FP measurement on a `design-system` archetype and on a workspace —
both untested shapes. Method follows issue #104's: judge each finding **real** (a
gap a human should close in the profile), **legitimately undeclared** (the
assertion is true, but no profile field exists that could ever declare it), or
**wrong** (the assertion is false).

```
$ cd $COPY && python3 $SUITE/plugins/design-suite/bin/survey.py --check
...
14 finding(s). This is the disk → declared direction; every doctor.py check runs
declared → disk and is blind to additions by construction.
```

Header notes, verbatim: `declared side: 9 config file(s)`, `289 path-valued
declaration(s)`, `capability cross-check: 1 finding(s)`.

| # | Finding | Kind | Verdict | Why |
|---|---|---|---|---|
| 1 | `.github/` (8 files) | undeclared-top-level | legitimately undeclared | CI workflows. No profile field describes CI |
| 2 | `.vale/` (52 files) | undeclared-top-level | legitimately undeclared | Prose-linter vocabularies. No field for them |
| 3 | `overrides/` (1 file) | undeclared-top-level | legitimately undeclared | One mkdocs theme override |
| 4 | `scripts/` (1 file) | undeclared-top-level | legitimately undeclared | A single deploy shell script |
| 5 | `tokens/` (8 files) | undeclared-top-level | **real** | This *is* the token source of truth — 8 JSON files under `core/`, `semantic/`, `brands/`. `tokens.source.path` is still TODO |
| 6 | `tooling/` (60 files) | undeclared-top-level | **real** | Holds the token generator and ~20 baseline JSONs — i.e. this project's own oracle, which `audits.baselineDir` should know about |
| 7 | `docs/javascripts/` | undeclared-sibling | legitimately undeclared | Docs-site assets |
| 8 | `gallery/lib/` | undeclared-sibling | **real** | A workspace member's source root |
| 9 | `gallery/test/` | undeclared-sibling | **real** | A workspace member's test root |
| 10 | `gallery/web/` | undeclared-sibling | legitimately undeclared | Flutter web scaffolding |
| 11 | `packages/ds_flutter/assets/` | undeclared-sibling | **real** | Asset audits scope off a declared asset dir |
| 12 | `packages/ds_flutter/lib/` | undeclared-sibling | **real** | The primary source root |
| 13 | `packages/ds_flutter/test/` | undeclared-sibling | **real** | The primary test root |
| 14 | `source.routesFile` | capability-undetermined | **real** | The `dart` adapter *refused* rather than answering absent, because `source.root` is a TODO string. Verbatim: "A refusal is not a finding of zero — nothing downstream may read this as absent." |

**Wrong-rate: 0 of 14 (0%).** Every assertion is factually true of the tree.

Real: 8 of 14 (57%). Legitimately undeclared: 6 of 14 (43%).

The 43% is not noise so much as a **vocabulary gap**: six directories that a
design-system repo genuinely has and the profile schema has no way to name. A
human reading this report has no action available for them except to ignore them
every time. That is the pressure this measurement puts on the schema.

### The false negatives matter more than the false positives

`--check` reports the disk → declared direction, so a *missed* directory is
invisible to every other check too. Three misses, each with a distinct cause:

**(a) `packages/ds_tokens_client_a/` — the third workspace member — is never
flagged.**

```
$ ls $EDS/packages
ds_flutter
ds_tokens_client_a
$ find $EDS/packages/ds_tokens_client_a -name "*.dart"
.../lib/ds_tokens_client_a.dart
.../lib/src/brand_client_a.g.dart
.../lib/src/client_a_theme.dart
```

Mechanism, from `survey.py`'s `check()`: the sibling rule builds its `parents`
set from `prefix.rsplit("/", 1)[0]` of each declared path. The only declared path
under `packages/` is `packages/ds_flutter/CHANGELOG.md` (contributed by
`survey.json` itself), whose parent is `packages/ds_flutter` — so the scan
descends into `ds_flutter`'s siblings and never into `packages`'s. And the
top-level rule passes `packages/` as covered, because `covered()` accepts an
ancestor match and that one CHANGELOG path starts with `packages/`.

**One CHANGELOG file discharges the completeness claim over an entire workspace.**
`named()`'s docstring argues at length that an ancestor declaration "cannot also
be the thing that discharges it" — that argument is implemented for siblings and
not for top-level entries.

**(b) `dist/` — 13 tracked files — is skipped by name.** `ALWAYS_SKIP` in
`survey.py:105` contains `"dist"`, alongside `build`, `out`, `target`, `vendor`,
`coverage`. In this repository `dist/` is not build noise; it is the published
output of the token pipeline, tracked in git:

```
$ git -C $EDS ls-files dist | wc -l
      13
$ ls $EDS/dist
audit  css  figma  palette  resolved  ts
```

A hardcoded directory-name skip list is a convention encoded as a constant, which
is the same class of thing `CLAUDE.md` forbids for project literals. For a
design-system repo whose whole job is emitting distributable token artifacts,
`dist/` is the last directory that should be invisible.

**(c) `docs_hosting/` and `gallery_hosting/` are suppressed by the survey's own
output.** `config_files()` counts `survey.json` on the declared side — it is one
of the nine — so any path the survey happened to inventory becomes "declared":

```
$ python3 -c "import json; d=json.load(open('.design-suite/survey.json')); \
  print([x['path'] for x in d['documents']['documents'] if 'hosting' in x['path']])"
['docs_hosting/README.md', 'gallery_hosting/README.md']
```

Two README files, inferred and ratified by nobody, silence two top-level
directories. **`survey --check` run after `init --from-survey` is partly
self-confirming**: the machine's own inventory is scored as if a human had
declared it. This is provenance leaking across a boundary the rest of the design
is careful about.

---

## 4. Re-verification of the prior read-only survey (Track E, 2026-09-15)

| Prior claim | Reproduces? | Now |
|---|---|---|
| `sourceRoots: []`, survey refuses because `pubspec.yaml` declares `workspace:` | **Yes** | Refusal intact, well-worded, and cites RFC-0002 §3g #3 by name |
| Real roots are three; `resolve.py` models one | **Yes** | `packages/ds_flutter`, `packages/ds_tokens_client_a`, `gallery`. `grep -n root $SUITE/plugins/design-suite/bin/resolve.py` returns two hits, both `project_root` / `REPO` — no multi-root notion at all |
| Token detection wrong — 1 candidate at 0.5, `docs/stylesheets/tokens.css` | **Yes, exactly** | And the candidate's own first line reads `/* GENERATED by tooling/generate.py from tokens/**.json — DO NOT EDIT. */`. The detector nominated a generated artifact; the real chain is `tokens/**.json` → `tooling/generate.py` → `packages/ds_flutter/lib/src/theme/tokens.g.dart` (483 lines, also generated). Nothing in that chain matches the detector's shapes |
| **231 unmapped docs** | **No — now 245** | Not a fix; the repository grew. Record it as a moving number, not a measurement of the detector |
| **8 top-level doc stems ARE vocabulary roles** | **Yes, exactly 8** | `ADAPTIVE-PATTERNS`, `COMMON-MISTAKES`, `DEPRECATIONS`, `FIGMA`, `GALLERY`, `PATTERNS`, `RELEASE`, `THEMING` — each a file in `docs/`, each a role in `roles.json`, none reachable from `ROLE_BY_STEM` |
| **`ROLE_BY_STEM` lags `roles.json` by 18 roles** | **Yes, exactly 18** | 22 stems reach 18 distinct roles; `roles.json` defines 35. 18 unreachable. One stem maps to `instructions`, which is not a role in `roles.json` |
| ~130 `docs/components/*.md`; need a directory-valued `components` role | **Partly fixed** | Now **137** pages (`ls $EDS/docs/components/*.md \| wc -l`). The `components` role **now exists** in `roles.json`, marked `"archetypes": {"design-system": "expected"}` and `"workspace": "per-member"`, with both a `template` and a `pageTemplate`. But `init.py` does not scaffold it, `--from-survey` does not seed it, and the 137 pages still land in `unmapped` |
| `projectKind` never inferred — `grep projectKind survey.py` returns 0 | **Yes** | `grep -c projectKind $SUITE/plugins/design-suite/bin/survey.py` → `0`. The archetype the whole of RFC-0002 §2c turns on is the one thing the survey does not even guess at, and `init.py` leaves it out of the profile entirely |

Reproduction command for the two role counts:

```
$ cd $SUITE/plugins/design-suite/bin && python3 -c "
import importlib.util, json
spec = importlib.util.spec_from_file_location('s', 'survey.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
vals = {v[0] if isinstance(v, (tuple, list)) else v for v in m.ROLE_BY_STEM.values()}
names = set(json.load(open('../templates/docs/roles.json'))['roles'])
print(len(m.ROLE_BY_STEM), len(vals), len(names), len(names - vals))"
22 18 35 18
```

**One prior claim no longer reproduces as stated**: "231 unmapped docs" is now
245, and the `components` role that was reported missing from the vocabulary now
exists. Neither is an error in the prior survey — the first is repository growth,
the second is a landed fix. The *consequence* of both is unchanged: 245 documents
still map to nothing.

---

## 5. What the suite cannot do here

Concretely, in the order they bite.

**1. Drop-in cannot describe a workspace at all.** `source.root` is a single
string. This project has three source roots and `resolve.py` models one. The
survey detects the workspace, says so in `couldNotDetermine`, and cites the
limitation — and then `init.py` writes a profile with **no `project.workspace`
key**, even though `profile.schema.json:116` defines that key and
`engine/archetypes.py:91` has an `is_workspace(profile)` that reads it. The flag
the entire workspace story depends on is neither scaffolded by the template nor
seeded from a detection that already happened. That is the single highest-value
gap here: the detection exists, the schema exists, the reader exists, and nothing
connects them.

**2. The archetype is never declared, so archetype-aware behaviour never
engages.** No `projectKind` in the survey, none in the scaffolded profile.
`roles.json` already knows `components` is `expected` for `design-system` and
`na` for `app` — that knowledge is unreachable because nothing on the drop-in
path writes the kind. The result is an `app`-shaped manifest stub
(`design`/`flows`/`decisions`/`backlog`) dropped onto a package that has none of
those and 137 component pages that have no role.

**3. Token detection is worse than useless on a generated pipeline.** The one
candidate it offers is a generated CSS file whose first line says it is
generated. There is no shape in the detector for "a directory of JSON compiled by
a script into per-platform outputs" — which is what a modern design system's
tokens usually are. The survey is right to call this the worst-measured signal
and right to refuse to seed it; it is not right that a 0.5-confidence generated
artifact is the only thing on the list.

**4. The doc-role vocabulary is not the bottleneck; the stem table is.** 18 of 35
roles are unreachable from any filename, and 8 of this project's top-level docs
are exact role names that go unmapped. This is the cheapest gap on the list to
close and the one with the largest visible effect on the 245.

**5. Nothing can express a directory-valued role.** `components` declares a
`pageTemplate` for the per-component page, but `docs.manifest.json`'s `roles` map
is path-to-string and its `directories` map is a separate, untyped thing. 137
pages cannot be named by either without one entry each.

**6. `doctor.py --profile <absolute path>` is silently cwd-relative.** Same
profile, same tree, different answers:

```
$ cd $SUITE && python3 plugins/design-suite/bin/doctor.py --profile $COPY/.design-suite/profile.json
design-suite doctor — 9 problem(s):
  ...
  ✗ audits.configFile: '.design-suite/design-audit-config.json' does not exist
  ✗ audits.exceptionsFile: '.design-suite/exceptions.json' does not exist
  ✗ audits.archRulesFile: '.design-suite/arch-rules.json' does not exist
  ✗ docs.manifest: '.design-suite/docs.manifest.json' does not exist

$ cd $COPY && python3 $SUITE/plugins/design-suite/bin/doctor.py
design-suite doctor — 12 problem(s):
```

All four of those files do exist (`ls $COPY/.design-suite/`). Passing
`--profile` an absolute path outside the cwd yields four confidently-wrong "does
not exist" claims and hides the seven docs/hooks problems the in-tree run finds.
An option that accepts an absolute path and then resolves that profile's own
relative paths against something else should refuse, not answer.

**7. `survey --check`'s declared side includes the survey's own output.** See
§3. Inference is being scored as declaration, in the one check whose job is to
catch what the declaration misses.

**8. `dist/` is invisible by constant.** See §3(b).

---

## 6. Suggested acceptance test

Each line is a gap named above, phrased so that it can fail:

1. Surveying a repo whose root manifest declares `workspace:` seeds
   `project.workspace: true` with provenance `inferred`, or explains in
   `couldNotDetermine` why it will not.
2. A profile can name more than one source root, or `resolve.py` refuses by name
   when handed a workspace rather than resolving the first member.
3. `survey.py` proposes a `projectKind` with a confidence and a reason, or lists
   it in `couldNotDetermine`. Zero mentions is neither.
4. `init.py --from-survey` seeds doc roles above a stated confidence threshold,
   all `inferred`, and does not scaffold role paths that do not exist on disk.
5. Every role in `roles.json` is reachable from `ROLE_BY_STEM`, gated the way
   `catalog.py --check` gates the catalog.
6. `docs.manifest.json` can map `components` to a directory, and `survey --check`
   stops reporting 137 pages as unmapped once it is mapped.
7. `survey --check` excludes `survey.json` from the declared side, or labels
   findings it suppressed on inferred evidence.
8. `ALWAYS_SKIP` does not skip a directory that git tracks.
9. `doctor.py --profile <path>` resolves relative paths against that profile's
   own project root, or refuses.

---

## 7. Read-only rule check

```
$ git -C $EDS status --short
(no output)
```

Empty. Nothing was written, staged, committed, or scaffolded inside the subject
repository. All scaffolding ran against `$COPY`.

---

**Verification-Tier: `self-tested`.** Every number here was produced by a command
quoted in the document and re-run at least once by its author. No independent
party has reproduced them.
