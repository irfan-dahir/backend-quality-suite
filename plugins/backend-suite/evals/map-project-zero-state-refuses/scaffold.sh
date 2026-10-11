#!/usr/bin/env bash
# Delegating shim, not a fixture.
#
# `context.scaffold_script` must name a path INSIDE the case directory — the
# harness rejects `..` and absolute paths outright — so a case cannot point
# straight at the shared fixture builder. This one-line shim is how a case
# uses a shared fixture without owning a copy of it, which is the whole point
# of `evals/_fixtures/` existing once rather than per case.
#
# Fixture: zero-state
#
# Source files and no `.backend-suite/` at all. This is the state
# `commands/map-project.md` Step 0 and `bin/map_project.py`'s "refusing: no
# profile at …" exist for, and nothing tested it until this case.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$here/../_fixtures/zero-state/scaffold.sh" "$@"
