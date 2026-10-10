#!/usr/bin/env bash
# Phase 0a oracle — capture or verify every audit's output.
#
# The AI design suite is being refactored into a project-agnostic engine plus a
# project profile (see docs/context/plans/ai-design-suite-decoupling.md). That
# refactor must be behaviour-preserving, and "behaviour" here means: every audit
# reports exactly what it reports today. This script is the check.
#
#   ./capture-baselines.sh            verify current output against the baseline
#   ./capture-baselines.sh --update   re-record the baseline (only when a change
#                                     to audit behaviour is intended and reviewed)
#
# Exit 0 = matches baseline. Exit 1 = drift with a diff, or an audit that
# crashed / exited outside the 0/1/2 contract. Exit 2 = an audit skipped itself
# while exiting 0 — see the INERT note below. Exit 3 = an audit was discovered
# that had no baseline; one has now been recorded, but this run verified nothing
# about it.
#
# An audit that REFUSES (exit 2 per the DOC-ROLES exit-code contract: "I could
# not look", e.g. no archRulesFile, no contrast pair list) is a legitimate,
# recordable state of this project, not a broken capture. It is baselined as
#   exit: 2
#   state: REFUSED — could not check; NOT a 0-finding result
# with its stated reason, so a refused baseline and a 0-finding baseline can
# never be byte-identical, and an audit flipping between the two is DRIFT.
# Exit 1 (findings) is likewise recorded, not treated as an error.
#
# The audit list is DERIVED, never written here — see the loop below.
#
# Zero dependencies (stdlib Python + coreutils), matching every other script in
# this repo's tooling.
set -uo pipefail

# Resolve this script's own directory BEFORE cd'ing anywhere. `$0` is relative
# whenever the script is invoked by a relative path — `bash plugins/.../
# capture-baselines.sh`, which is the natural way to run it from the repo root —
# and resolving it after the cd below looked for that path inside the project
# instead. The result was every audit reporting exit=2, which reads as eight
# broken audits rather than one bad line, and is a slow thing to diagnose.
BIN="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$BIN/.." && pwd)"

# Walk up to the project (the directory holding .design-suite/), not to the plugin
# root — installed as a plugin, this script lives somewhere else entirely.
PROJECT="${CLAUDE_PROJECT_DIR:-$PWD}"
while [ "$PROJECT" != "/" ] && [ ! -d "$PROJECT/.design-suite" ]; do
  PROJECT="$(dirname "$PROJECT")"
done
[ -d "$PROJECT/.design-suite" ] || { echo "no .design-suite/ found — run from a configured project" >&2; exit 2; }
cd "$PROJECT" || exit 2
BASE=".design-suite/baselines"
MODE="${1:-verify}"
mkdir -p "$BASE"

# Per-run scratch, not a shared `/tmp/ds-baseline-$name.txt`. The fixed path was
# one filename per audit for the whole machine: two runs at once (two worktrees,
# two agents, a CI job beside a developer) would read each other's captures and
# report OK or DRIFT against another run's output. An oracle that can be silently
# poisoned by a concurrent run is worse than no oracle.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ds-baseline.XXXXXX")" || exit 2
trap 'rm -rf "$WORK"' EXIT

# The audit list is DERIVED, not written here. Do NOT re-add a literal list.
#
# This script used to carry its own array of eight audits with their commands and
# artifact paths. That was a second registry alongside
# `design_suite/engine/audit_discovery`, and second registries drift: by the time
# anyone noticed, `discover()` returned 17 audits, this list still named 8, and
# two of those 8 had been switched off in `audit_discovery.DISABLED` — so they
# exited 2, were reported as ERROR, and the repo's own documented pre-refactor
# check could not complete at all. Nine audits were invisible to the oracle and
# the oracle itself was red. A hand-maintained list is exactly the failure this
# suite's governing principle is about: what it omits is indistinguishable from
# what is clean.
#
# `repo_health.py --list` is the seam (bash cannot import Python). It prints one
# tab-separated row per discovered audit — name, live|disabled, whether it takes
# `--findings`, and the disabled reason — straight off `audit_discovery`, so this
# script and the health dashboard cannot disagree about what exists.
LIST="$(python3 "$BIN"/repo_health.py --list)" || {
  echo "could not enumerate audits (repo_health.py --list failed) — refusing to" >&2
  echo "verify against a list this script cannot vouch for." >&2; exit 2; }
[ -n "$LIST" ] || { echo "audit discovery returned nothing — that is a broken" >&2
  echo "discovery path, not a project with no audits." >&2; exit 2; }
discovered=$(printf '%s\n' "$LIST" | wc -l | tr -d ' ')
printf '%s audit(s) discovered by audit_discovery.discover()\n\n' "$discovered"

fail=0; inert=0; new=0; off=0; refused=0
while IFS=$'\t' read -r name state findings_flag reason relpath envelope; do
  [ -n "$name" ] || continue
  # Not every audit lives in $BIN — audit_mock_api.py lives beside its coupled
  # sibling modules in design_suite/engine/mockapi/ (issue #120). repo_health.py
  # --list now names each audit's actual path; a fifth column read here means
  # discovering an audit outside bin/ and then invoking it there are the same
  # source of truth, not two that can disagree.
  script="$PLUGIN_ROOT/$relpath"

  # A disabled audit is named as disabled, never run, and never counted as a
  # failure or a pass — same treatment, and the same words, as repo_health.py's
  # `disabled` row and run_precommit_audits.py's disabled section. Dropping it
  # would make "switched off because it was measurably wrong" look identical to
  # "this project has no problems of that kind".
  if [ "$state" = "disabled" ]; then
    printf '  DISABLED %-22s %s\n' "$name" "$reason"
    off=$((off + 1)); continue
  fi

  # Every audit is invoked the same way the health dashboard invokes it: bare,
  # plus `--findings` when it supports the common envelope. The envelope's own
  # default path is the artifact — which is also how the four hardcoded consumer
  # paths (token_pipeline/…, copy_pipeline/…, scripts/…) left this file; they
  # were project literals in a universal plugin.
  # Not $name.json — an audit's envelope name is not always its stem with
  # "audit_" stripped (audit_focus_order.py writes "focus-order.json", a
  # hyphen). repo_health.py's --list now names it directly (issue #123's bug,
  # duplicated here because bash cannot call envelope_name() itself).
  artifact="-"
  if [ "$findings_flag" = "yes" ]; then
    artifact=".design-suite/findings/$envelope.json"
    out=$(python3 "$script" --findings 2>&1); rc=$?
  else
    out=$(python3 "$script" 2>&1); rc=$?
  fi

  # An audit that skips itself is a silent pass and must never be baselined as
  # "clean" — it is reported INERT and the run refuses to claim success.
  if printf '%s' "$out" | grep -qiE 'could not resolve|skipping'; then
    printf '  INERT    %-22s %s\n' "$name" "$(printf '%s' "$out" | head -1)"
    inert=1; continue
  fi
  # A real error: a Python traceback (which exits 1 and would otherwise pass
  # for "findings"), or an exit code outside the 0/1/2 contract.
  if printf '%s' "$out" | grep -q '^Traceback (most recent call last)' \
     || [ "$rc" -gt 2 ]; then
    printf '  ERROR    %-22s exit=%s %s\n' "$name" "$rc" "$(printf '%s' "$out" | grep -v '^[[:space:]]*$' | tail -1)"
    fail=1; continue
  fi
  state=""
  if [ "$rc" -eq 2 ]; then
    state="REFUSED"; refused=$((refused + 1))
  fi

  # Record the summary line plus a digest of the artifact. The digest catches a
  # changed finding whose count happens to stay the same.
  {
    printf 'exit: %s\n' "$rc"
    if [ -n "$state" ]; then
      printf 'state: REFUSED — could not check; NOT a 0-finding result\n'
    fi
    printf 'stdout:\n%s\n' "$out"
    # A refused audit wrote no fresh artifact; hashing whatever an earlier run
    # left behind would bake a stale file into the baseline.
    if [ -z "$state" ] && [ "$artifact" != "-" ] && [ -f "$artifact" ]; then
      printf 'artifact: %s\n' "$artifact"
      printf 'artifact_sha256: %s\n' "$(python3 -c "
import hashlib,sys,json
p='$artifact'
raw=open(p,'rb').read()
try:  # canonicalise so key order can't cause false drift
    raw=json.dumps(json.loads(raw),sort_keys=True,separators=(',',':')).encode()
except Exception: pass
print(hashlib.sha256(raw).hexdigest())
")"
    fi
  } > "$WORK/$name.txt"

  target="$BASE/$name.txt"
  if [ "$MODE" = "--update" ]; then
    cp "$WORK/$name.txt" "$target"
    printf '  RECORD   %-22s %s\n' "$name" "$(printf '%s' "$out" | head -1)"
  elif [ ! -f "$target" ]; then
    # Newly discovered, no baseline. Recording it silently would let a brand-new
    # audit join the run as a row that always "matches" — the same invisibility
    # the hardcoded list caused, one layer down. It is recorded AND named AND the
    # run exits non-zero, because nothing about it has actually been verified.
    cp "$WORK/$name.txt" "$target"
    printf '  NEW      %-22s no baseline existed — recorded, NOT verified\n' "$name"
    new=$((new + 1))
  elif diff -q "$target" "$WORK/$name.txt" >/dev/null; then
    if [ -n "$state" ]; then
      printf '  REFUSED  %-22s matches baseline (still refusing — verified nothing): %s\n' "$name" "$(printf '%s' "$out" | head -1)"
    else
      printf '  OK       %-22s %s\n' "$name" "$(printf '%s' "$out" | head -1)"
    fi
  else
    printf '  DRIFT    %-22s\n' "$name"
    diff "$target" "$WORK/$name.txt" | sed 's/^/           /'
    fail=1
  fi
done <<< "$LIST"

echo
printf '%s discovered: %s disabled (did not run at all).\n' "$discovered" "$off"
if [ "$off" -gt 0 ]; then
  echo "Disabled audits tell you NOTHING about this project — read them as a gap in"
  echo "coverage, not as a pass. Reasons above; the path back to each is in"
  echo "design_suite/engine/audit_discovery.DISABLED."
fi
if [ "$refused" -gt 0 ]; then
  echo "$refused audit(s) REFUSED (exit 2) and were baselined as refused, with"
  echo "their reasons. A refused audit checked NOTHING — a matching refusal proves"
  echo "only that it still refuses, not that behaviour was preserved. Configure"
  echo "what it asks for if you need it to cover this change."
fi
if [ "$inert" = 1 ]; then
  echo "One or more audits could not run (see INERT above) — they resolve"
  echo "dependencies this checkout has not installed. Install them and re-run."
  echo "Do not treat an inert audit as passing."
fi
[ "$fail" = 1 ] && { echo "BASELINE FAILED"; exit 1; }
[ "$inert" = 1 ] && exit 2
if [ "$new" -gt 0 ]; then
  echo "$new audit(s) had no baseline and were recorded just now (NEW above). This"
  echo "run verified nothing about them — re-run to compare against what it wrote."
  exit 3
fi
echo "All audits match baseline."
