# SWAP-PLAN — the design → backend domain swap ledger

The repo scaffolded from `ai-backend-suite` v0.2.0. This file is the running
ledger of what was **deferred rather than deleted**: tests and gates removed
in the purge phases whose *machinery carries* but whose *fixtures are
design-domain*, and are therefore re-authored against the `php` adapter (and,
later, backend-domain content) before the first release tag. **This file is
deleted in the cleanup commit before the first release tag.**

Status legend: `[ ]` open · `[x]` done (with commit).

## Phase D re-authors (need `adapters/php.py` first)

- [x] (D4b, this commit) `bin/audit_layer_boundaries_test.py` — dart/tsx
  fixtures → php fixture. The file never shipped at all (the design-suite
  cases were purged without a replacement), so it is created fresh: namespace
  roots firing on `use` targets, the `App\Http\` vs `App\HttpExtra\X`
  precision case, path roots via `require`, TODO/empty-dir/missing-dir
  refusals, and the ratchet (refuses to absorb, accepts with `--accept-new`).
  Two real fixes surfaced by the test: `_root()` no longer appends `/` to a
  namespace root (a `App\Http\` rule could never fire before), and
  `--update-baseline` now mkdirs the baselines dir it writes into.
- [x] (D5a, this commit) `bin/structural_refusals_test.py` — recreated fresh:
  the cross-audit refusal contract over all six section-reading audits
  (missing section, undeclared `archRulesFile`, malformed arch-rules file,
  the shipped scaffold never reads clean, absent/unknown `adapters.lang`,
  missing profile input) plus planted-violation control rows. Three real
  defects surfaced and fixed while writing it: `arch.load` TypeError'd
  (exit 1 traceback) on a bare-string arch-rules.json because
  `section in rules` is a substring test on a str; the audits' missing-
  input path raised bare `SystemExit(message)` = exit 1 (this suite's
  findings code) via `project.need` — new `project.need_refused` keeps the
  message, exits 2, and the three audits now use it; and
  `audit_error_handling` reported a confident exit-0 clean over a scaffold
  whose vocabulary was all `TODO:` placeholders (the TODO row now refuses,
  as its own template comment already promised).
- [x] (D5a, this commit) `bin/scan_skip_test.py` (was
  `scan_skip_and_tsx_cache_test.py`) — scan-skip half recreated generic
  over a php fixture (vendor/ beside composer.json, authored `src/build/`
  kept, SKIPPED counted, scanSkipDirs include/add overrides); the tsx
  span-cache half died with the tsx adapter and is not replaced.
- [ ] `bin/survey_ui_roots_test.py` — the init-from-survey e2e (`audit_tokens`
  runs with no edits) → backend equivalent: init → a live php-backed audit runs.
- [x] (D4b, this commit) `bin/propose_config_test.py` — proposes flutter
  layers/adapter-seam/animated-widget sections → backend sections (routes
  file, cache TTLs). 8 cases over a php fixture: the three proposals with
  their measured evidence (including the psr-4 namespace handle), human-fill
  never overwritten, exit 2 when nothing is measurable, unreadable
  composer.json refusal, `--apply` unknown section, and the never-proposed
  listing.
- [ ] `bin/audit_report_paths_test.py` — report-path mechanics
  (`--out` wins, defaults inside `.backend-suite/`, scaffolded .gitignore
  covers them) against adapter-backed audits.
- [ ] `bin/audit_contract_headers_test.py` + `bin/audit_error_handling_test.py`
  — mockapi seed tests built on `adapters.dart` → php fixtures.
- [ ] `bin/scan_skip_and_tsx_cache_test.py` — scan-skip half is generic; the
  tsx cache half dies with the tsx adapter.
- [ ] `bin/audit_findings_envelope_test.py` — the `ApiConsistency` class
  (dart component-contract fixture) — audit itself still ships.
- [ ] `bin/survey_test.py` — capability-seam legs: undeclared-capability
  routing case, the convergence (declared silences) case, the
  `capability-undetermined` refusal kind, and exit-0-on-clean. Current state
  pinned instead: absent adapter ⇒ exit 1 + `capabilities-not-examined`.
- [x] (D5a, this commit) `backend_suite/adapters/verify_seam.py` — measured as
  already re-pointed: the shipped leg discovers `load("php")` and sweeps a
  routes/api.php fixture through the adapter's own checks and globs, and the
  seam gate is green in the current 14/16. The entry described pre-repoint
  state.
- [ ] `bin/survey.py` — the UI-decision path (`ui_adapter`, `UI_DIR_NAMES`,
  `ADAPTER_REFINEMENTS`) decides which language a *design* suite audits when
  server and UI stacks disagree. Backend suite: decide drop vs invert (route
  root, not UI root, decides).
- [x] (D4b, this commit) `bin/propose_config.py` — proposal sections themselves
  (config template keys) are design-domain. Full re-author: the three design
  proposers (adapter seam, animated widgets, colour names) are gone;
  `layerBoundaries` now attributes `use` targets through composer.json psr-4
  (new `engine/psr4.py`) and bans both path globs and namespace roots, so the
  proposed rule is one the audit can fire on; `routeCoverage` measures the
  routes layout, a `Class@method`-only actionPattern (N-of-N over every
  'uses' entry) and controllerDirs located by class file (vendor/ ignored);
  `cacheTtlCoverage` reuses the routes measurement plus the single action-keyed
  `config/` map. NOT_PROPOSED re-authored to the backend sections, with the
  dead sections listed until the template drops them. Measured against the
  jikan-rest probe: controllerDirs and `config/jikan.php` came out identical
  to the hand-authored D3b config, and 76/103 TTL coverage matches D3b's
  103 actions − 27 missing.
- [ ] `bin/verify.py` docstring says "component"; suite terminology — fine,
  but its evidence examples are design-flavoured; light prose pass.

## Known-red until re-pointed (documented in CLAUDE.md)

- [x] `bin/gate_consumer_compat_test.py` + `bin/suite_upgrade_test.py`
  re-point — RESOLVED as a measured partial re-point (not the (b) this entry
  once preferred, because (b) turned out half-impossible). Measured in-repo:
  `audit_discovery.DISABLED` only ever *lost* entries here, so
  `audit-newly-disabled` is unreachable; pre-Phase-B commits live under the
  `plugins/design-suite` prefix the engine refuses; the one comparable range
  (`ec99953..99359f6`) carries zero breaks. So every case whose meaning
  survives a clean range now runs on real revisions (`REAL_OLD_REV,
  REAL_NEW_REV`, or `HEAD..HEAD`) and passes, and only the cases that need a
  *breaking* range stay fixture-pinned (`FIXTURE_OLD_REV,
  FIXTURE_NEW_REV` = upstream `e14048a`/`ba7029e`) per CLAUDE.md rule 3:
  `suite_upgrade_test.py`'s `CompatAgainstTheRealRegression` and
  `test_cli_findings_needs_a_breaking_range`; `gate_consumer_compat_test.py`'s
  `GateBites` and the `unacked` CLI case. Two false-passes closed by the
  re-point: `malformed` (asserted exit 2 while the revision itself was
  unresolvable) and `test_a_filter_matching_nothing_refuses` (matched the
  filter refusal against an unreadable revision).
- [ ] `gate_consumer_compat_test.test_release_tag_is_discoverable_here`,
  the `clean`/`stale` CLI cases, and the consumer-compat CI gate — auto-heal
  once the first `backend-suite--v*` tag is cut, which the SWAP-PLAN deletion
  rule still gates on Phase D. All verified green against a temporary tag.

## Regenerated after the command/agent purge (A3)

- [ ] `docs/CATALOG.md` + `docs/SKILLS.md` + `docs/backend-suite-guide.html`
  regenerated (`catalog.py`, `skills_catalog.py [--html]`) — the
  `skills_catalog_test` stale-doc failures close with this.
- [ ] `.github/workflows/validate.yml` gate count + header comment
  (16 gates now; API-domain gates replace the two dropped design gates).
- [ ] `.backend-suite/claude_md_enforcement.json` — hardcodes "18 of the 18
  gates".

## Phase C/B items

- [ ] CLAUDE.md/README/ONBOARDING/ADOPTING/CONCEPTS/USER-GUIDE/ROADMAP prose:
  backend-suite → backend-quality-suite, plus the ADOPTING.md claim the probe
  disproved ("the documentation half works immediately" — it does not: only
  `survey` + `list` run on an unconfigured project, and `/review-docs` is
  Dart-hardcoded).
- [ ] `review-docs` de-Dart (state-gathering greps `*_screen.dart`).
- [ ] `bin/audit_skill_paths.py` — `ALLOWED_OWNERS = ("anthropics",)`; this
  repo's own skill ownership must be admitted or gate 7 fails once skills
  cite this repo's slug.

## Phase A4 (roles/archetypes/scaffolds swap) — done here, deferred parts below

Completed in this phase (see commit): `roles.json` re-vocabulary (18 roles,
kinds `library`/`service`, groups + externalPlugin `pr` remapped); 18 design
doc templates + 2 fragments + 2 component schemas + 2 dot-templates deleted;
`survey.py` hand `ROLE_BY_STEM` table replaced by the derived
`role_stems.stem_map()` and `role_stem_drift.py` retired (its own docstring
prescribes this end-state); `onboard-new-client` chain re-authored
(survey → doc-suite → propose-config → baseline-debt); docs.manifest template
re-pointed; `init.py` stops scaffolding `design-audit-config.json` /
`component-capabilities.json` and its `seed_token_names` is gone; template
archetype rows + test swapped to `library`/`service`; eval fixtures renamed
`app→service`, `design-system→library`, promo-era `app-configured` and
`docs-site` fixtures deleted.

### Deferred to Phase D (one coherent unit — the tokens/config swap)

- [x] (D4a, this commit) `profile.schema.json` `tokens` property + required entry,
  `profile.json.template` tokens block + design-flavoured TODO examples,
  `survey.py` `detect_token_sources()` + token-candidate plumbing (the
  `candidateTokenSources` report key and summary count with it), `doctor.py`
  tokens.source package-resolution check + `tokens.outputDir` fallback,
  `adapters/__init__.py`/`engine/capabilities.py` `token_accessor` threading
  (the field itself too — no check ever read it), `engine/pipelines.py`
  `DEFAULTS` entries `tokens`/`copy`/`assets` (`mockApi` stays), and the
  `"tokens"` blocks in the test fixtures (doctor_fix_hints_test,
  doctor_hooks_map_test, map_project_test, ratify_test, doctor_provenance_test;
  audit_findings_envelope_test was already clean from D3a). The dangling
  `repair_tokens.py` fix-hint references (schema examples, docstrings) were
  purged in the same commit; ratify_test's tokens.* cases re-authored onto
  project.framework / docs.manifest, init_from_survey_test's control onto
  project.audience, source_roots_test's token-detection section removed with
  the function it tested.
- [x] (D4b, this commit) `bin/propose_config.py` — design-audit-config +
  flutter/tsx sections: full re-author (its test was already deleted in A2;
  the script still named the deleted config file). Done together with the
  entry under Phase D re-authors; see there for the new proposer set.
- [x] (D4a, this commit) `configFile` remnants: schema `audits.configFile`
  property, survey key entry (`PATH_VALUED_KEYS` — `PROPOSED_PROFILE_KEYS` no
  longer existed), `provenance.py` PATH_KEYS entry, plus the one real consumer:
  the `audit_config` loader in `adapters/__init__.py` and its only reader
  (`AdapterContext.minimums()`, accessibility machinery with no callers).
- [x] (D4c, this commit) Eval fixture CONTENT: `_app_sources` /
  `_design_system_sources` now build a PHP/API tree (composer.json,
  `routes/`, controllers, a src/ package with no routes) under the
  service/library fixtures; eval-case prose and graders re-authored to the
  live vocabulary (deployment is the role `na` for `library`; kinds are
  service|library), deleted-case references (promote-component,
  design-auditor) dropped or explicitly framed as history, the
  `review-docs-app-stub-and-decline` shim's deleted `app` fixture fixed,
  README fixture table rebuilt to the 6 live fixtures and the polarity
  paragraph re-measured (1 of 10, was 4 of 12).
- [x] (D4c, this commit) dot-templates content: `arch-rules` (live sections
  only — apiConsistency, contractHeaders, errorHandling with its 8
  snake_case vocabulary keys, layerBoundaries path globs + php namespace
  TODOs), `hooks.map` (one live entry: audit_error_handling, preCommit
  false), `exceptions` (errorHandling.intentionalDeadStates +
  apiConsistency exemptions), `gitignore` (dead-audit entries purged,
  +`scratch/`, mock-api-findings kept for the drift test); `known-traps` /
  `verification-glossary` verified already generic; hooks.map schema
  descriptions de-staled.
