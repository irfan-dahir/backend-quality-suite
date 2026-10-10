#!/usr/bin/env bash
# Materialise BOTH fixtures into the run base as siblings: ./app and
# ./design-system. The /promote-component cases are the only ones in this suite
# that need two repositories, because the effect they grade is a write that
# crosses a repository boundary.
#
# WHY THIS FILE EXISTS AT ALL — the defect it fixes
#
# `context.scaffold_script` is a PATH to a script inside the case directory. It
# is not a place to inline a shell body. These four cases carried a YAML block
# scalar there, and the harness resolved the whole body as a filename:
#
#   "case \"promote-component-...\": path \"set -euo pipefail cp -R ...\"
#    does not exist"
#
# The cases were therefore never executed — turns 0, cost 0, duration 0, and a
# recorded score of 0.00 on both the with- and without-plugin arms. A score of
# zero that means "never ran" is indistinguishable from one that means "ran and
# failed everything", which is this repository's governing failure reproduced in
# its own test harness. Every one of the other sixteen cases already used
# `scaffold_script: scaffold.sh`; these four were the only exceptions.
#
# The path must also not escape the case directory (`..` or an absolute path is
# rejected outright), which is why the shared fixture builders are reached from
# inside this script rather than named in case.yaml. See
# ../_fixtures/app/scaffold.sh for the same note.
#
# Run only under `--scaffold`. Fails loudly rather than leaving an empty
# workspace, because a skill pointed at an empty directory refuses for reasons
# no grader here can distinguish from a real decision.
set -euo pipefail

fixtures="$(cd "$(dirname "$0")/../_fixtures" && pwd)"

# `app-configured`, not `app`: these cases need a project whose profile and
# arch-rules are actually filled in. The plain `app` fixture leaves every value
# as init.py's literal `TODO:` string — deliberately, because four map-project
# cases exist to watch /map-project propose exactly those fields — and against
# it the command's Step 0 (audit_reinvented_components.py) REFUSES with exit 2
# on an unresolvable `reinventedComponents.package`. Step 0 refusing does not
# fail `did-run-step-0`, which only wants the call in the trace; it is worse
# than that, because the command then reasons about the promotion from no
# evidence and the case grades the result as if it had looked. Same sources,
# same design-system counterpart; see build_fixture.build_app_configured.
mkdir -p app design-system
( cd app            && bash "$fixtures/app-configured/scaffold.sh" )
( cd design-system  && bash "$fixtures/design-system/scaffold.sh" )

# The graders address both trees by these exact prefixes — `design-system/**`
# for the file_exists assertions, `app/` for the adoption Edit. A fixture that
# built into the wrong place would leave them asserting against nothing.
# Rewrite the package resolution map to the run base's REAL absolute path.
#
# The fixture ships `rootUri: "../design-system"`, which is the honest relative
# form — but audit_reinvented_components.py resolves that Path against the
# PROCESS working directory rather than against the config file's directory,
# and a run's working directory is this base, not ./app. Left relative, Step 0
# would resolve nothing and refuse (exit 2) for a reason that has nothing to do
# with the command under test. The absolute path can only be known here, once
# both trees exist: the builder writes into a temp dir that is then copied in.
python3 - "$PWD" <<'PYEOF'
import json, pathlib, sys
base = pathlib.Path(sys.argv[1]).resolve()
cfg = base / "app/.dart_tool/package_config.json"
data = json.loads(cfg.read_text())
for pkg in data["packages"]:
    if pkg["name"] == "example_design_system":
        pkg["rootUri"] = str(base / "design-system")
cfg.write_text(json.dumps(data, indent=2) + "\n")
PYEOF

[ -n "$(ls -A app)" ]           || { echo "scaffold: app fixture left ./app empty" >&2; exit 1; }
[ -n "$(ls -A design-system)" ] || { echo "scaffold: design-system fixture left ./design-system empty" >&2; exit 1; }
