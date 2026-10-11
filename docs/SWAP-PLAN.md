# SWAP-PLAN — the design → backend domain swap ledger

The repo scaffolded from `ai-backend-suite` v0.2.0. This file is the running
ledger of what was **deferred rather than deleted**: tests and gates removed
in the purge phases whose *machinery carries* but whose *fixtures are
design-domain*, and are therefore re-authored against the `php` adapter (and,
later, backend-domain content) before the first release tag. **This file is
deleted in the cleanup commit before the first release tag.**

Status legend: `[ ]` open · `[x]` done (with commit).

## Phase D re-authors (need `adapters/php.py` first)

- [ ] `bin/audit_layer_boundaries_test.py` — dart/tsx fixtures → php fixture
  (routes/ or app/ tree with a planted layering violation).
- [ ] `bin/structural_refusals_test.py` — every refusal case pairs a live
  audit with `adapters.lang: tsx`; re-authored against php, dead-audit cases
  dropped.
- [ ] `bin/survey_ui_roots_test.py` — the init-from-survey e2e (`audit_tokens`
  runs with no edits) → backend equivalent: init → a live php-backed audit runs.
- [ ] `bin/propose_config_test.py` — proposes flutter layers/adapter-seam/
  animated-widget sections → backend sections (routes file, cache TTLs,
  error-shape policy…).
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
- [ ] `backend_suite/adapters/verify_seam.py` — gate "the engine still runs a
  non-Dart adapter" runs the engine over a React fixture with the tsx adapter.
  Re-author: PHP fixture + `php.py`. Gate is red until then.
- [ ] `bin/survey.py` — the UI-decision path (`ui_adapter`, `UI_DIR_NAMES`,
  `ADAPTER_REFINEMENTS`) decides which language a *design* suite audits when
  server and UI stacks disagree. Backend suite: decide drop vs invert (route
  root, not UI root, decides).
- [ ] `bin/propose_config.py` — proposal sections themselves (config template
  keys) are design-domain.
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

- [ ] `profile.schema.json`: `tokens` is still a REQUIRED section and an
  `additionalProperties: false` top level means removing it invalidates every
  fixture that still carries it. Remove as ONE unit: schema `tokens` property
  + required entry; `profile.json.template` tokens block (and its
  design-flavored TODO examples); `survey.py` `detect_token_sources()` +
  token-candidate plumbing; `doctor.py` tokens.source package-resolution check
  (~line 940), `tokens.outputDir` fallback (~line 652), and the fix-hint table's
  `repair_tokens.py` entry (script deleted in A2 — the hint is dangling);
  `backend_suite/adapters/__init__.py` + `engine/capabilities.py`
  `token_accessor` threading; `engine/pipelines.py` `DEFAULTS` entries
  `tokens`/`copy`/`assets` (their pipeline dirs were deleted in A1; `mockApi`
  stays); and the `"tokens"` blocks in ~7 test fixtures (doctor_fix_hints_test,
  doctor_hooks_map_test, map_project_test, audit_findings_envelope_test,
  ratify_test, doctor_provenance_test).
- [ ] `bin/propose_config.py` — design-audit-config + flutter/tsx sections:
  full re-author (its test was already deleted in A2; the script still names
  the deleted config file).
- [ ] `configFile` remnants: schema `audits.configFile` property, survey
  `PROPOSED_PROFILE_KEYS` entry, `provenance.py` ratifiable list entry —
  harmless while absent from every profile; purge with the tokens swap.
- [ ] Eval fixture CONTENT: `_app_sources` / `_design_system_sources` still
  build a Flutter-shaped tree (widgets, pubspec) under the renamed
  service/library fixtures; the bootstrap/map-project eval cases' prose and
  graders are still design-domain. Re-author to PHP/API content in Phase D,
  together with the case prose that mentions deleted cases
  (promote-component/design-auditor) and stale `build_fixture.py` comments.
- [ ] dot-templates content: `arch-rules.json.template` (widget layering),
  `exceptions`/`known-traps`/`hooks.map`/`verification-glossary` examples —
  names are generic, contents are design-era.
