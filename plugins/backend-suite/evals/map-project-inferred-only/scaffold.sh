#!/usr/bin/env bash
# Delegating shim, not a fixture.
#
# `context.scaffold_script` must name a path INSIDE the case directory — the
# harness rejects `..` and absolute paths outright — so a case cannot point
# straight at the shared fixture builder. This one-line shim is how a case
# uses a shared fixture without owning a copy of it, which is the whole point
# of `evals/_fixtures/` existing once rather than per case.
#
# Fixture: undeclared-kind
#
# WHY NOT `zero-state` (which this shim used until 2026-09-24)
#
# `build_zero_state` is "source files and nothing else — no `.backend-suite/` at
# all". This case's prompt asks for the proposals ON DISK and nine of its
# graders target `.backend-suite/profile.json`. Nothing in the run creates that
# file, and nothing may: `commands/map-project.md` Step 0 forbids the skill
# from inventing a profile ("a profile this skill invented is not a scaffolded
# project, and it converts a visible gap into a file that reads like one"), and
# `bin/map_project.py` enforces the refusal in code (exit 2, "refusing: no
# profile at …"). So the case was unpassable by construction — measured at 0.17
# on BOTH arms, the lowest in the suite, for a fixture reason rather than a
# skill one.
#
# The fix is on the case side, because the skill's refusal is correct. It is
# NOT "make the case's shim run init.py itself": that would be a ninth fixture
# living outside `_fixtures/`, uncovered by `eval_fixture_selftest.py`, free to
# drift from what `init.py` actually produces — the photograph-goes-stale
# failure `build_fixture.py`'s own header exists to refuse. And `--force` must
# never appear in an adoption path.
#
# `undeclared-kind` is the right existing fixture, not a compromise:
#   * it is `app` with `projectKind` removed, so every profile value is still
#     the `TODO:` string `init.py` writes — the state `build_app_configured`'s
#     docstring names as the reason the plain `app` fixture is left alone:
#     "four `map-project-*` cases exist to watch `/map-project` propose exactly
#     those fields". Nothing about "propose fields on an underspecified
#     project" is lost; one more field is underspecified, not one fewer.
#   * its `.backend-suite/profile.json` contains ZERO occurrences of `approved`,
#     `declared`, `"by"`, `"on"`, `verifiedAgainst`, `"value"`, `"evidence"`
#     and `inferred`, and an empty `provenance.fields` — so all nine file
#     graders are live rather than pre-satisfied, and none of them had to be
#     weakened to make the case passable.
#   * it is the one scaffolded fixture no other `map-project-*` case uses
#     (`app` → chat-yes, `pre-ratified` → preserves-ratified, `docs-site` →
#     refuses-tied), and its own docstring calls it the default rather than an
#     edge case: "both real consumer projects are in exactly this state today".
#
# `zero-state`'s role in this suite is testing REFUSAL, which is what it is
# good at — see `map-project-zero-state-refuses`, added alongside this change.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$here/../_fixtures/undeclared-kind/scaffold.sh" "$@"
