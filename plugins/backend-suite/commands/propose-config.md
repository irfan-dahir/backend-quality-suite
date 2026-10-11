---
name: propose-config
description: "Propose real values for the TODO sections init.py scaffolds (layer rules, the routes and TTL-map locations), each measured from this project's code with its evidence, and write a section only after the user confirms it. Writes .backend-suite/ config, so it is never invoked without an explicit instruction. Use after /map-project when /repo-health shows audits refusing on TODO placeholders."
invocation: explicit
maturity: unverified
---

# /propose-config

After onboarding, most audits refuse (exit 2) because the config sections
`init.py` scaffolds are still `TODO`. Some of those are facts a code scan can
measure. This proposes **only** those, and writes nothing until the user says
yes to each section.

## What it writes — be exact with the user

| Section | File | Inferred from | Proposed only when |
|---|---|---|---|
| `layerBoundaries` | arch-rules file | the import graph — `use` targets attributed through composer.json psr-4, `require`d paths by prefix; the two forms `audit_layer_boundaries.py` matches | a top-level source dir is imported by >= 5 files elsewhere and imports none of its importers; no tie. The rule bans both forms (path glob + namespace root), so it is one the audit can actually fire on |
| `routeCoverage` | arch-rules file | the adapter's routes layout (`routes/*.php`), the 'uses' entries in those files, and where every controller class they name lives | every 'uses' entry spells `Class@method`, and every named controller resolves to exactly one file outside installed code |
| `cacheTtlCoverage` | arch-rules file | the same routes measurement, plus the action-keyed entries under `config/` | exactly one `config/` file carries action-shaped keys, and every key spells `Class@method` |

Each written section carries `_provenance: {"state": "inferred", "evidence": "..."}`
— the same entry `map_project.py` writes, and nothing else. It is an observed
invariant ("true of the code today"), not a stated design rule. A section a human
has already filled in is never overwritten.

It never proposes `errorHandling`, `contractHeaders`, `apiConsistency`,
`errorShape`, `endpointParity`, `rateLimit`, `versioning`, `toolchainGates` or
`testNetworkCoupling` — those are this project's own names, its stated
conventions, or decisions about what CI owes the release. The preview lists
them with the reason; say so to the user rather than guessing.

## Steps

1. Preview (writes nothing):
   `python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py"`
   Exit 2 means nothing could be inferred — report every `NO PROPOSAL` reason;
   do not treat it as success.
2. **Checkpoint per section.** For each `PROPOSE` line, show the user the value
   and the evidence, and ask. Never batch the confirmations.
3. For each section the user accepts, and only those:
   `python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py" --apply <section>`
   (`--apply all` only if the user explicitly accepted every proposal.)
4. Run the matching audit (`audit_layer_boundaries.py`,
   `audit_route_coverage.py` or `audit_cache_ttl_coverage.py`) and report its
   exit code. Exit 0/1 means it now runs; remind the user that a clean run
   against an inferred rule only proves the code matches what it already did.
