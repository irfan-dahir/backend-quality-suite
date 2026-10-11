#!/usr/bin/env python3
"""Run a project's fast/invariant audits before a commit is allowed through.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/run_precommit_audits.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/run_precommit_audits.py" --list

Exit 0 = every pre-commit-eligible gate passed (including "none configured").
Exit 1 = at least one gate found something, or (default) at least one REFUSED.

## Refusals (exit 2 from an audit)

An audit that exits 2 checked nothing — missing config, an adapter without the
capability, an empty sweep. It is never counted as a pass. It is listed in its
own REFUSED section on stderr, separate from findings, so "could not check" is
never read as "found something" either. Whether it blocks the commit is the
project's choice: `--refusals block` (default) blocks, `--refusals warn`
reports just as loudly and lets the commit through, saying that nothing was
verified by those entries. `backend-suite hooks --git --refusals warn` bakes the
choice into the installed hook.

## Why a second runner instead of reusing hooks/audit_on_edit.py

`audit_on_edit.py` already reads `.backend-suite/hooks.map.json` and already knows
how to run one entry's command and read its verdict. It is deliberately advisory:
it never blocks a tool call, because it fires on every keystroke-adjacent Write/Edit
and a hook that can fail a tool call turns every save into a gate the audits were
never scoped to be. A commit is a different, much rarer event with a real "should
this go through" question attached to it — the two need opposite failure modes on
the same config, so one runner cannot honestly be both. This script is that second
half: same map, same entry shape, same pass/fail semantics as `reportWhen`
(`nonzero` reads the command's exit code, `findings` reads `findingsPath`), but it
propagates failure with a non-zero exit instead of swallowing it into a
systemMessage.

## Entries pointing at a disabled audit

A project's map can outlive the audit it registers. An entry whose command invokes
an audit in `backend_suite/engine/audit_discovery.DISABLED` is not run and is not
counted as a pass or a failure: it is listed by name, with the measured reason and
the path back, in its own section on stderr. Letting it run would surface exit 2
as "could not read the findings envelope" — a broken hook, when the truth is a
decommissioned check — and the developer would go fix the wrong thing.

Only entries with `"preCommit": true` run here — see that field's description in
`templates/hooks.map.schema.json`. Everything else in the map keeps firing only
through audit_on_edit.py, unaffected.

## Scoped to changed files, not changed lines

By default every finding is filtered to the *files* this commit actually touched,
per RFC-0003 §3a. The reason is the whole point of diff-time delivery: a hook that
reports every finding in the whole repository recreates the batch report one
commit at a time, and gets switched off within a week. Meta's Infer went from a
~0% to a ~70% fix rate on an unchanged analysis purely by moving reports to diff
time.

Two rules keep that from becoming its own silent failure:

  * **The suppressed count is always printed.** "3 findings in changed files;
    47 elsewhere, not shown." Dropping findings quietly would make a filtered run
    indistinguishable from a clean one, which is the exact thing this suite keeps
    designing against.
  * **An entry that emits no findings envelope cannot be scoped at all**, and says
    so. `reportWhen: "nonzero"` gives the runner an exit code and nothing else —
    there are no `{file, line}` records to filter — so such an entry is reported
    whole and explicitly labelled unscoped. Reporting it as clean because it
    could not be filtered would be the INERT failure in miniature.

`--unscoped` restores the unfiltered behaviour.

## Repair, offered here and only here

An entry may declare a `repair` command (see hooks.map.schema.json). When the
audit finds something in a file this commit touched, that command is handed *only
those files* and its unified diff is printed. Three invariants, each of them the
reason this is wired at diff time rather than anywhere else:

  * **Nothing is applied, ever.** RFC-0003 §3c: the repairer emits a diff and
    stops. This runner prints it. The developer applies it or ignores it.
  * **Only the on-change bucket is offered a repair.** Whole-repo band-1 repair
    fixed 0 of 33 findings on an already-migrated codebase — the deterministic
    cases were long gone and the survivors were band 2/3 by construction. Repair
    pays on lines being written right now, and nowhere else.
  * **A finding with no offered fix says so, loudly.** Every on-change finding is
    listed either with its offer or with the band that denied it. Pre-existing
    findings keep their place in the suppressed count regardless; a repair offer
    can never make one disappear.

## Scope

Mirrors bin/gates.py's shape ("run N checks, report clearly") rather than
audit_on_edit.py's single-file shape, because a commit can stage many files at
once. For a glob entry, the command runs once per distinct scope (the matched
file, or its containing directory when scopeMode is "dir") among the staged
files — not once per file, and not whole-repo, for the same reason a hooks.map
entry needs scopeArg at all: re-running a whole-project audit on every commit
re-does CI's job on a much tighter loop for no added signal. A wholeRepo entry
runs exactly once, as declared.

Stdlib only, like everything else here.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import project_root  # noqa: E402

from backend_suite.engine import audit_discovery  # noqa: E402

MARKER = ".backend-suite"
MAP_FILE = f"{MARKER}/hooks.map.json"

# Generous relative to audit_on_edit.py's 30s: this runs once per commit, not once
# per keystroke, but it still must not turn `git commit` into a coffee break — an
# audit this slow on a handful of staged files is mis-scoped, not merely unlucky.
TIMEOUT_SECONDS = 60


def load_entries(repo: Path) -> list[dict]:
    path = repo / MAP_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        print(f"{MAP_FILE} is not valid JSON ({exc}) — no pre-commit audits ran. "
              f"Fix the file or remove the pre-commit hook.", file=sys.stderr)
        raise SystemExit(2)
    entries = data.get("entries", [])
    return [e for e in entries
            if isinstance(e, dict) and not e.get("disabled") and e.get("preCommit")]


def staged_files(repo: Path) -> list[str]:
    """Repo-relative paths of staged additions/copies/modifications/renames.

    Deletions are excluded (diff-filter ACMR) — an audit command taking a path
    argument that no longer exists would fail for the wrong reason.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=repo, capture_output=True, text=True, timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in result.stdout.splitlines() if line]


def _relative(repo: Path, file: str) -> str:
    """A finding's file path as the diff spells it: repo-relative, POSIX."""
    candidate = Path(file)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(repo.resolve())
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def partition_findings(records: list[dict], repo: Path,
                       changed_files: set[str]
                       ) -> tuple[list[dict], list[dict], list[dict]]:
    """Split findings into (in changed files, pre-existing, unattributable).

    ## Why files and not lines — do not "improve" this back to lines

    Line granularity was built first (PR #105), measured, and reverted (issue
    #104). It is not stricter-but-equivalent; on this codebase it is *wrong*, and
    wrong in the one direction this suite refuses to be wrong in: it silently
    drops real findings.

    The cause is finding-anchor imprecision, not diff parsing. `engine/scan.py`
    records a finding's line as `line_of(source, match.start())` — the start of
    the *matched expression*. Adapter patterns match whole calls that routinely
    wrap: `adapters/dart.py`'s `EDGE_INSETS_RE` is
    `EdgeInsets\\.(all|symmetric|only|fromLTRB)\\(([^)]*)\\)`, and `[^)]*` spans
    newlines, so

        padding: const EdgeInsets.symmetric(   <- line 6, where the finding anchors
          horizontal: 16,                      <- line 7, the actual violation
          vertical: 24,                        <- line 8, the actual violation
        ),

    anchors at line 6. A commit that edits only line 7 produces a changed range of
    {7} and a finding at 6 — so line scoping files it as pre-existing and hides it.
    The literal can sit 1-4 lines below its anchor in ordinary formatted Dart, so
    this is the common case, not a corner one.

    Lines become the correct granularity the day findings anchor at the offending
    literal rather than the enclosing expression (i.e. when adapter checks report
    a sub-match offset and `scan_source` uses it). Until then, widening to the
    file is what keeps a dropped finding from looking like a clean commit. The
    noise this costs is bounded and visible: the suppressed count below is printed
    on every run, pass or fail.

    The third bucket is the honest one: a record with no `file`, or with a file the
    staged diff does not mention, cannot be judged either way. It is reported
    rather than suppressed — a finding this runner cannot place is not evidence
    that the change is clean.
    """
    changed, pre_existing, unattributable = [], [], []
    for record in records:
        file = record.get("file")
        if not file:
            unattributable.append(record)
        elif _relative(repo, file) in changed_files:
            changed.append(record)
        else:
            pre_existing.append(record)
    return changed, pre_existing, unattributable


BAND_MEANING = {
    1: "deterministic — exactly one declared token has this value",
    2: "ambiguous — several candidate tokens; proposing one would be a guess",
    3: "absent — no declared token has this value; authoring one is a human call",
    "unsupported": "no literal to replace (a token used in the wrong place)",
    "undeterminable": "this project declares no naming prefix for that category",
}


def offer_repairs(entry: dict, repo: Path, records: list[dict]) -> str:
    """A repair offer for the on-change findings only. Returns text; writes nothing.

    ## Why this runs here and nowhere else

    Band-1 repair run across a whole already-migrated codebase fixed **0 of 33**
    findings (RFC-0003 §3a, measured). On cold code the deterministic cases have
    already been migrated and the survivors are band 2 and band 3 by
    construction. Repair pays at diff time, on lines someone is touching now — so
    the repair command is handed *only* the files this commit changed, and only
    ever the on-change bucket. Widening it back to the pre-existing bucket would
    reproduce the 0-of-33, and would also mean offering to rewrite code this
    commit never touched.

    ## Two things it must never do

    * **Apply anything.** The repair command emits a unified diff and stops
      (RFC-0003 §3c). This function captures that diff and prints it. Nothing
      here writes to the working tree, stages, or commits.
    * **Let an unrepaired finding read as a repaired one.** Every on-change
      finding is listed with either its offered replacement or the explicit
      reason there is none. A silent omission would make "we could not fix this"
      look exactly like "we fixed this", which is the governing principle's
      failure mode wearing a friendlier hat.
    """
    spec = entry.get("repair")
    if not isinstance(spec, dict) or not spec.get("command"):
        return ""
    files_arg = spec.get("filesArg")
    if not files_arg:
        return ("  repair: declared without filesArg — refusing to run a repairer "
                "repo-wide from a pre-commit hook. No fix was offered for any "
                "finding above.")

    command = spec["command"]
    argv = command.split() if isinstance(command, str) else list(command)
    argv = [os.path.expandvars(a) for a in argv]

    files = sorted({_relative(repo, r["file"]) for r in records if r.get("file")})
    if not files:
        return ""
    argv.append(str(files_arg))
    argv.extend(files)

    bands_arg = spec.get("bandsArg")
    # Not repo/".git" — in a git worktree (and in a submodule) .git is a *file*
    # pointing at the real gitdir, so writing a child of it fails with ENOTDIR.
    # The bands file is transient and unlinked below, so a temp file is both
    # correct and simpler than resolving the gitdir via `git rev-parse`.
    bands_path = Path(tempfile.mkstemp(prefix="backend-suite-repair-bands-",
                                       suffix=".json")[1]) if bands_arg else None
    if bands_path is not None:
        argv.extend([str(bands_arg), str(bands_path)])

    try:
        proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return f"  repair: could not run ({exc}) — no fix was offered for any finding above."

    if proc.returncode == 2:
        why = (proc.stderr or "").strip().splitlines()
        why = why[0] if why else "the repairer refused"
        return (f"  repair: none offered for any finding above — {why}")

    bands = {}
    if bands_path is not None:
        try:
            for record in json.loads(bands_path.read_text()).get("bands", []):
                bands[(_relative(repo, record.get("file", "")),
                       record.get("line"), record.get("kind"))] = record.get("band")
        except (OSError, ValueError):
            bands = {}
        finally:
            bands_path.unlink(missing_ok=True)

    lines = ["  repair (RFC-0003 band 1) — a diff, never applied:"]
    for record in records:
        where = f"{record.get('file', '?')}:{record.get('line', '?')}"
        # A raw scan record calls the check kind "kind"; the common findings
        # envelope calls the same string "category". Accept both rather than
        # silently failing to match, which would label every finding unclassified.
        band = bands.get((_relative(repo, record.get("file", "")), record.get("line"),
                          record.get("kind") or record.get("category")))
        if band == 1:
            lines.append(f"    fix offered  {where}  "
                         f"{record.get('snippet') or record.get('summary', '')}")
        elif band is None:
            lines.append(f"    NO FIX       {where}  (the repairer did not classify "
                         f"this finding — treat it as unfixed)")
        else:
            lines.append(f"    NO FIX       {where}  band {band}: {BAND_MEANING.get(band, '?')}")

    diff = proc.stdout
    if diff.strip():
        lines.append("")
        lines.append("  Nothing was written. Copy the diff between the markers,")
        lines.append("  read it, and `git apply` it yourself if you agree.")
        # Printed unindented and between markers on purpose: an indented diff is
        # not a diff any more, and the point of emitting one is that it applies.
        lines.append("----8<---- repair diff ----8<----")
        lines.extend(diff.splitlines())
        lines.append("---->8---- repair diff ---->8----")
    else:
        lines.append("    (no band-1 repair was available for this change — "
                     "every finding above is still yours to fix)")
    return "\n".join(lines)


def scopes_for(entry: dict, staged: list[str]) -> list[str] | None:
    """Distinct scope arguments to run this entry against, or None to skip it.

    An empty list is a valid, meaningful result: a glob entry with no staged match
    has nothing to say this commit. None means "run with no scope arg at all"
    (wholeRepo).
    """
    if entry.get("wholeRepo"):
        return [None]

    globs = entry.get("glob")
    if not globs:
        # commandPattern-only entries key off a Bash command, which a commit does
        # not have — nothing here for them to trigger on.
        return []
    patterns = [globs] if isinstance(globs, str) else globs
    matched = [f for f in staged if any(fnmatch.fnmatch(f, p) for p in patterns)]
    if not matched:
        return []

    mode = entry.get("scopeMode", "file")
    scopes = {f if mode == "file" else str(Path(f).parent) for f in matched}
    return sorted(scopes)


def run_once(entry: dict, repo: Path, scope: str | None,
             changed_files: set[str] | None) -> tuple[bool, str, dict]:
    """Run one (entry, scope) pair.

    Returns (ok, detail-for-failure, stats). `changed_files` is None for an
    unfiltered run (--unscoped). `stats` carries what the run suppressed and
    whether it could be scoped at all, so main() can report both honestly.
    """
    stats: dict = {"suppressed": 0, "shown": 0, "unscoped": False, "repair": "",
                   "refused": False}
    command = entry.get("command")
    if not command:
        return True, "", stats
    argv = command.split() if isinstance(command, str) else list(command)

    scope_arg = entry.get("scopeArg")
    if scope is not None:
        if not scope_arg:
            return False, (f"'{entry.get('name', '?')}' matched staged files but has no "
                            f"scopeArg — refusing to guess how to pass {scope!r}."), stats
        if scope_arg is not True:
            argv.append(str(scope_arg))
        argv.append(scope)
    elif not scope_arg and not entry.get("wholeRepo"):
        return False, (f"'{entry.get('name', '?')}' has neither scopeArg nor wholeRepo — "
                        f"refusing to run it repo-wide by accident. See {MAP_FILE}."), stats

    argv = [os.path.expandvars(a) for a in argv]

    try:
        proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True,
                               timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False, (f"exceeded {TIMEOUT_SECONDS}s. A pre-commit entry this slow is "
                        f"mis-scoped — narrow it or unset its preCommit flag."), stats
    except (OSError, ValueError) as exc:
        return False, f"could not run: {exc}", stats

    if proc.returncode == 2:
        # The suite-wide exit contract: 2 is "refused / cannot determine". Not a
        # finding and not a pass — main() reports it in its own section.
        stats["refused"] = True
        detail = (proc.stderr or proc.stdout or "").strip() or "exit 2 (refused)"
        return False, detail, stats

    if entry.get("reportWhen") == "findings":
        findings_path = entry.get("findingsPath")
        if not findings_path:
            return False, "reportWhen is 'findings' but no findingsPath is set.", stats
        try:
            envelope = json.loads((repo / findings_path).read_text())
            records = envelope.get("findings", [])
        except (OSError, ValueError):
            # The command ran; if it did not write the envelope it promised, that
            # is itself a failure worth surfacing, not a silent pass.
            return False, f"expected findings at {findings_path} but could not read it.", stats

        note = ""
        if changed_files is not None:
            shown, suppressed, unattributable = partition_findings(
                records, repo, changed_files)
            stats["suppressed"] = len(suppressed)
            # Only the on-change bucket is ever offered a repair, and offering one
            # cannot remove anything from any bucket: `suppressed` is already
            # counted above and is reported whatever the repairer says.
            if shown:
                stats["repair"] = offer_repairs(entry, repo, shown)
            if unattributable:
                note = (f"\n    ({len(unattributable)} finding(s) carried no file this "
                        f"runner could place against the diff — shown, not filtered.)")
            records = shown + unattributable

        stats["shown"] = len(records)
        if not records:
            return True, "", stats
        preview = "\n".join(
            f"    {r.get('file', '?')}:{r.get('line', '?')} — {r.get('category', '?')}"
            for r in records[:5])
        more = f"\n    …and {len(records) - 5} more" if len(records) > 5 else ""
        return False, f"{len(records)} finding(s)\n{preview}{more}{note}", stats

    # No findings envelope: `nonzero` hands back an exit code and nothing more, so
    # there is nothing to filter. Say that out loud rather than letting an unscoped
    # result pass for a scoped one.
    stats["unscoped"] = changed_files is not None

    if proc.returncode == 0:
        return True, "", stats
    detail = (proc.stdout or proc.stderr or "").strip()
    if stats["unscoped"]:
        detail = ((detail or f"exit {proc.returncode}") +
                  "\n    (not scoped to changed files: this entry uses reportWhen "
                  "'nonzero' and emits no findings envelope, so some of the above may "
                  "predate this change. Reported whole, deliberately.)")
        return False, detail, stats
    return False, detail or f"exit {proc.returncode}", stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                     help="show which entries are preCommit-eligible, run nothing")
    # Renamed from --all-lines when the default moved from lines to files: a flag
    # called --all-lines that toggles file scoping would misdescribe itself. The
    # old spelling stays as a hidden alias so an existing hook or script keeps
    # working rather than dying on an unrecognised argument mid-commit.
    ap.add_argument("--unscoped", "--all-files", "--all-lines", dest="unscoped",
                     action="store_true",
                     help="report every finding the audit emits, not just those in "
                          "files this commit touched (the pre-RFC-0003 behaviour)")
    ap.add_argument("--refusals", choices=("block", "warn"), default="block",
                     help="whether an audit that refuses (exit 2) blocks the commit; "
                          "reported loudly either way (default: block)")
    args = ap.parse_args()

    repo = project_root()
    entries = load_entries(repo)

    # Split before anything runs. An entry pointing at a disabled audit is not a
    # gate that failed and not a gate that passed — it is a gate that is switched
    # off, and it gets said in those words. Left to run, it would exit 2 and
    # surface as either "could not read the findings envelope" or a bare exit
    # code, i.e. a broken hook rather than a decommissioned check.
    off = [(e, *hit) for e in entries
           if (hit := audit_discovery.disabled_in_command(e.get("command")))]
    off_names = {id(e) for e, _, _ in off}
    entries = [e for e in entries if id(e) not in off_names]

    def report_disabled() -> None:
        if not off:
            return
        print(f"\n{len(off)} pre-commit entrie(s) in {MAP_FILE} point at a DISABLED "
              f"audit. They were NOT run, and their silence is not a pass:\n",
              file=sys.stderr)
        for entry_cfg, audit, reason in off:
            print(f"  {entry_cfg.get('name', '?')} -> {audit}: {reason['reason']}",
                  file=sys.stderr)
            print(f"    path back: {reason['pathBack']}\n", file=sys.stderr)
        print("Remove these entries from the map, or leave them and keep reading this "
              "notice — but do not read their absence from the results above as a "
              "clean bill of health for what they used to check.\n", file=sys.stderr)

    if args.list:
        if not entries and not off:
            print(f"no entries in {MAP_FILE} have \"preCommit\": true.")
            return 0
        print(f"{len(entries)} pre-commit-eligible entrie(s) in {MAP_FILE}:\n")
        for e in entries:
            print(f"  {e.get('name', '?')}"
                  f"{'  [wholeRepo]' if e.get('wholeRepo') else ''}")
        for entry_cfg, audit, reason in off:
            print(f"  {entry_cfg.get('name', '?')}  [DISABLED: {audit} — "
                  f"{reason['reason']}]")
        return 0

    if not entries:
        # Absence of config is not the same as a passing gate — say so, rather
        # than exiting 0 the same way a real pass would, which is exactly the
        # "audit that reports nothing" this suite keeps designing against. The
        # same holds when the only entries there were are disabled: that is the
        # loudest version of this case, not a quieter one.
        if off:
            print(f"run_precommit_audits: every \"preCommit\": true entry in {MAP_FILE} "
                  f"points at a disabled audit — NOTHING was checked. Commit allowed, "
                  f"but nothing about it has been verified.")
        else:
            print(f"run_precommit_audits: no entries in {MAP_FILE} declare "
                  f"\"preCommit\": true — nothing ran, commit allowed. To gate commits "
                  f"on an audit, add preCommit: true to its hooks.map.json entry.")
        report_disabled()
        return 0

    staged = staged_files(repo)
    changed = None if args.unscoped else {_relative(repo, f) for f in staged}
    if changed is not None and not changed:
        # No staged paths came back. Filtering on an empty set would suppress
        # every finding and print a clean run — the failure this file argues
        # against. Report whole instead, and say why.
        print("could not read the staged file list — refusing to scope against an "
              "empty set, because that would silently hide every finding. Falling "
              "back to unscoped reporting for this run.", file=sys.stderr)
        changed = None

    failures: list[tuple[str, str]] = []
    refusals: list[tuple[str, str]] = []
    repairs: list[tuple[str, str]] = []
    ran = 0
    total_suppressed = 0
    total_shown = 0
    unscoped_entries: list[str] = []

    scope_note = ("every finding, unfiltered (--unscoped)" if changed is None
                  else "changed files only")
    print(f"running pre-commit audits from {MAP_FILE} — scope: {scope_note}\n")
    for entry in entries:
        name = entry.get("name", "?")
        scopes = scopes_for(entry, staged)
        if not scopes:
            continue
        for scope in scopes:
            ran += 1
            t0 = time.time()
            ok, detail, stats = run_once(entry, repo, scope, changed)
            label = f"{name}{f' ({scope})' if scope else ''}"
            total_suppressed += stats["suppressed"]
            total_shown += stats["shown"]
            if stats["unscoped"] and label not in unscoped_entries:
                unscoped_entries.append(label)
            mark = "REFUSED" if stats["refused"] else ("ok  " if ok else "FAIL")
            print(f"  {mark} {label[:66]:68} {time.time() - t0:5.1f}s")
            if stats["repair"]:
                repairs.append((label, stats["repair"]))
            if stats["refused"]:
                refusals.append((label, detail))
            elif not ok:
                failures.append((label, detail))

    if ran == 0:
        print(f"no staged file matched a preCommit-eligible entry — nothing to check, "
              f"commit allowed.")
        report_disabled()
        return 0

    # Always, pass or fail: the developer must know the suppressed number exists
    # and was deliberately not shown. A filtered run that looks identical to a
    # clean one is the failure mode this whole file is arguing against.
    if changed is not None:
        print(f"\n{total_shown} finding(s) in changed files; {total_suppressed} "
              f"elsewhere, not shown "
              f"(re-run with --unscoped to see them).")
    if unscoped_entries:
        print(f"{len(unscoped_entries)} entrie(s) could not be scoped to changed files "
              f"— no findings envelope (reportWhen 'nonzero'), so they were run and "
              f"reported whole: {', '.join(unscoped_entries)}")

    # Printed on stdout, in full, and never folded into the failure detail above —
    # that detail is truncated to its last 12 lines, and a diff with its head cut
    # off is worse than no diff at all.
    for label, block in repairs:
        print(f"\n--- {label}: repair offer")
        print(block)

    report_disabled()

    if refusals:
        blocking = args.refusals == "block"
        print(f"\n{len(refusals)} pre-commit audit(s) REFUSED (exit 2) — they checked "
              f"NOTHING. This is not a pass:\n", file=sys.stderr)
        for label, detail in refusals:
            print(f"--- {label}", file=sys.stderr)
            for line in detail.splitlines()[-12:]:
                print(f"    {line}", file=sys.stderr)
        if blocking:
            print("\nRefusals block this commit (--refusals block, the default). Fix "
                  "the audit's configuration, or install the hook with "
                  "`--refusals warn` to report without blocking.", file=sys.stderr)
        else:
            print("\nCommit NOT blocked by these refusals (--refusals warn) — but "
                  "nothing those entries cover has been verified.", file=sys.stderr)

    if refusals and args.refusals == "block" and not failures:
        return 1

    if failures:
        print(f"\n{len(failures)} pre-commit gate(s) failed:\n", file=sys.stderr)
        for label, detail in failures:
            print(f"--- {label}", file=sys.stderr)
            for line in detail.splitlines()[-12:]:
                print(f"    {line}", file=sys.stderr)
            fix = next((e.get("fixHint") for e in entries if e.get("name") in label), None)
            if fix:
                print(f"    Fix with: {fix}", file=sys.stderr)
        print(f"\nCommit blocked. Use `git commit --no-verify` to bypass in an emergency "
              f"— but that skips the invariants this hook exists to protect.",
              file=sys.stderr)
        return 1

    # Qualified when something was switched off: "all gates passed" is true of the
    # gates that ran and misleading about the ones that did not.
    passed = ran - len(refusals)
    print(f"\n{passed} of {ran} pre-commit gate(s) that are still enabled passed"
          f"{f'; {len(refusals)} REFUSED and checked nothing' if refusals else ''}"
          f"{f' ({len(off)} disabled, reported above — not checked)' if off else ''}."
          if refusals else
          f"\nall {ran} pre-commit gate(s) that are still enabled passed"
          f"{f' ({len(off)} disabled, reported above — not checked)' if off else ''}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
