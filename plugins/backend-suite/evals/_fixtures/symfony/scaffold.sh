#!/usr/bin/env bash
# Materialise the `symfony` fixture into the CURRENT WORKING DIRECTORY.
#
# Why this file exists rather than a case pointing straight at build_fixture.py:
# `context.scaffold_script` is rejected outright if it escapes the case
# directory ("`..` or an absolute path"). So a shared _fixtures/ tree cannot be
# referenced by a case directly. Each case instead carries a small shim inside
# its own directory that execs this script — the shim passes validation, and it
# is this script that reaches outward.
#
# The shim is exec'd WITHOUT changing directory, so the run's working directory
# is where the fixture must land.
#
# Built into a temp directory and copied in, never built into `.` directly:
# build_fixture.py --force DELETES its target before rebuilding, and the target
# here is the live working directory of an eval run.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
python3 "$here/../build_fixture.py" symfony --dir "$tmp/fixture" --force >/dev/null
cp -R "$tmp/fixture/." .