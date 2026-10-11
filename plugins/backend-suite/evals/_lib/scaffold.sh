#!/usr/bin/env bash
#
# HOW TO RUN THE CASES THAT USE THIS
#
#   claude plugin eval plugins/backend-suite \
#     --eval-dir plugins/backend-suite/evals \
#     --scaffold --allow-tools Bash \
#     --case 'review-docs-*' --runs 1 --ablation none -j 1
#
# Both flags are mandatory, for reasons that are not obvious:
#
#   --scaffold       `context.scaffold_script` runs ONLY under this flag. Without
#                    it every case runs in an empty workspace, and every refusal
#                    case passes for the wrong reason.
#   --allow-tools    Bash is NOT grantable through a case's `allowed_tools` — the
#     Bash           harness strips it along with Write/Edit unless granted on the
#                    command line. These components are read-only, but read-only
#                    is not the same as Bash-free: both of them reach the project
#                    exclusively through `bin/resolve.py`, so without Bash they
#                    cannot read an exit code at all and the exit-4/5 assertions
#                    measure nothing.
#
# Shared scaffold body for every eval case in this suite.
#
#   ../_lib/scaffold.sh <fixture-name>
#
# A case's own `context.scaffold_script` is a one-liner that execs this with the
# fixture it needs. The harness runs that script **in the empty workspace**, as
# the user, and only when `--scaffold` is passed — so this script's job is to
# turn that empty workspace into the named fixture, or to fail loudly.
#
# Failing loudly is the whole point. If this script quietly did nothing, every
# refusal case in the suite would still pass: a skill pointed at an empty
# directory refuses for the same reason it refuses on `zero-state`, and the
# graders could not tell the two apart. That is this repo's governing failure
# (silence indistinguishable from a result) reproduced inside the test harness.
# So: `set -euo pipefail`, an explicit check that the builder exists, and an
# explicit check that the workspace is non-empty afterwards.
#
# The refusal cases additionally assert on a file that only the fixture
# provides, so a scaffold that somehow succeeds-but-empty still fails the case.
set -euo pipefail

fixture="${1:?usage: scaffold.sh <fixture-name>}"
workspace="$PWD"

# $0 is the case's own scaffold.sh, in <eval-dir>/<case>/. The builder is at
# <eval-dir>/_fixtures/build_fixture.py. Resolve from the *caller's* path so
# this keeps working wherever the eval directory is rooted.
case_dir="$(cd "$(dirname "${BASH_SOURCE[1]:-$0}")" && pwd)"
builder="$case_dir/../_fixtures/build_fixture.py"

if [ ! -f "$builder" ]; then
  # Second chance: this file's own location, for a caller that sourced us.
  builder="$(cd "$(dirname "${BASH_SOURCE[0]}")/../_fixtures" && pwd)/build_fixture.py"
fi

if [ ! -f "$builder" ]; then
  echo "scaffold: cannot find build_fixture.py (looked beside the case and beside _lib)" >&2
  exit 1
fi

# Build into a scratch directory and copy in, rather than pointing the builder
# at $PWD. `build_fixture.py --force` rmtree()s its target before rebuilding it,
# and rmtree()ing the shell's own working directory leaves this script running
# in a deleted inode — every relative path after that point behaves differently
# on different platforms. A scratch build sidesteps the question entirely.
scratch="$(mktemp -d "${TMPDIR:-/tmp}/ds-eval-fixture-XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
python3 "$builder" "$fixture" --dir "$scratch/f" --force
# Dotfiles included: `.backend-suite/` IS the fixture for most of these cases.
cp -R "$scratch/f/." "$workspace/"

# A fixture that built into the wrong place leaves the workspace empty, which
# would read as a legitimate zero-state to every grader downstream.
if [ -z "$(ls -A "$workspace")" ]; then
  echo "scaffold: fixture '$fixture' left the workspace empty" >&2
  exit 1
fi
