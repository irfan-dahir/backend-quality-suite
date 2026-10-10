#!/usr/bin/env python3
"""The seven things about a label that a script can decide.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_copy.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_copy.py" --selftest

**DISABLED (issue #109) — see `design_suite/engine/audit_discovery.DISABLED` for
the measured reason and the bar for re-enabling it.** It refuses with exit 2
rather than running; `--run-disabled` overrides that for re-measurement only. The
registry entry, not this docstring, is the single source of truth every reporting
surface reads. Nothing below is deleted: the rules, the baseline semantics and
the selftest are what whoever re-scopes this has to work from, and a disabled
check is switched off, not removed.

`--selftest` deliberately still runs while disabled. It asserts things about the
rules themselves (including that `title_case` never re-emits the corrupting fix
of issue #109) and needs no project; refusing it would remove the only guard
still standing over code that stays in the tree.

## Why this exists

`/audit-copy` had six checks and every one of them was a model reading strings
and forming a judgement. That is right for tone, terminology and register, and
wrong for *"does this label end in a full stop"* — a question with one answer
that never needs a reader.

The rules below came from the design system's `tooling/scripts/audit_copy.py`,
which was the only place they existed, and which its own docstring justified by
pointing at `min_touch_target_dp: 48` sitting in a config file for years,
described and never executed. Leaving these to a prompt was the same shape of
mistake one layer up: a rule that holds only when somebody remembers it.

So the decidable seven are decided here, and the model's attention goes to the
checks that genuinely need it.

## Microcopy only

A content sentence legitimately ends in a period and legitimately capitalises
after one. A label does neither. Running these over prose would produce a wall
of findings nobody could act on, which is how a gate gets switched off — and it
would take the seven real rules with it.

The microcopy/content split is `engine/copy.py`'s word-count-and-keyword
heuristic, and it is a heuristic: a misclassified content string shows up here
as a false positive. That is the intended failure direction. The alternative —
judging everything — is the noise that made this unenforceable in the first
place.

## The ratchet, and why this one needs it more than most

A codebase that has never had this gate has a lot of Title Case in it — the
mobile app had 268 findings across 529 labels on the first run, and the largest
class was real rather than false. Failing on all of it would mean a gate nobody
could turn on, and exempting all of it would mean a gate that checks nothing.

So known findings sit in a baseline and only NEW ones fail, the same shape as
the layer-boundary and promotion-candidate audits. The baseline is a debt
register, not an approval: working it down is copy work, and deciding whether
"Care Plan" is a product noun or a Title Case slip is a brand-voice decision
that belongs to a person.

Identity is (text, rule), deliberately not including the file. The same label in
two places is one copy decision, and moving a string between files is not a new
finding.

## Exceptions name a rule, not a string

`copy.exceptions` in the project's exceptions file maps a string to the specific
rules it is allowed to break, with the reason. Exempting the whole string would
let a second, real problem hide behind an accepted first one — a credit-card
face label is allowed to shout, and is not thereby allowed to apologise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401,E402  — puts the plugin on sys.path

# Imported, not resolved. `--selftest` proves the rules fire and needs no project
# at all; resolving a repository at import time made the one command that should
# always work the one that refused to run outside a configured checkout.
from design_suite.engine import audit_discovery  # noqa: E402
from design_suite.engine import ratchet  # noqa: E402
from design_suite.engine.copy import (DEFAULT_APOLOGY, DEFAULT_FILLER,  # noqa: E402
                                      DEFAULT_PROPER, build_inventory,
                                      check_microcopy)

AUDIT = Path(__file__).stem


def _refuse_disabled(entry: dict) -> int:
    """Exit 2 — "I could not look" — never 0, and never a findings envelope.

    Exit 2 is this repo's CapabilityError (docs/DOC-ROLES.md's exit-code
    contract). Exiting 0 here would be worse than not shipping the audit at all:
    the gate would go green, `--out` and `--findings` would be baselined as a
    clean copy inventory, and every dashboard and agent downstream would read
    that as "this project's copy has no problems". That is the one outcome this
    suite exists to prevent, so the refusal is loud and the reason travels with
    it.
    """
    print(f"{AUDIT}: DISABLED — {entry['reason']}\n", file=sys.stderr)
    print("Why:", file=sys.stderr)
    print(f"  {entry['detail']}\n", file=sys.stderr)
    print("Path back to enabling it:", file=sys.stderr)
    print(f"  {entry['pathBack']}\n", file=sys.stderr)
    print("This is a refusal (exit 2), not a clean result. Nothing was scanned and no "
          "findings file was written, so nothing can be concluded about this project's "
          "copy from this run. `--run-disabled` runs it anyway, for re-measurement only; "
          "`--selftest` still works and tests the rules, not the project.", file=sys.stderr)
    return 2


def _config(repo: Path) -> dict:
    from design_suite.project import profile
    rel = (profile(repo).get("audits", {}) or {}).get("exceptionsFile")
    if not rel or not (repo / rel).is_file():
        return {}
    try:
        return json.loads((repo / rel).read_text()).get("copy", {}) or {}
    except ValueError as exc:
        raise SystemExit(f"{rel} is not valid JSON: {exc}")


def _vocab(cfg: dict) -> dict:
    """Project additions to the word lists, never replacements.

    A project that replaced the filler list would silently stop checking the
    words it did not think to re-list, and the audit would report a cleaner
    result for having been given less to look at.
    """
    return {
        "proper": tuple(DEFAULT_PROPER) + tuple(cfg.get("properNouns", [])),
        "filler": tuple(DEFAULT_FILLER) + tuple(cfg.get("filler", [])),
        "apology": tuple(DEFAULT_APOLOGY) + tuple(cfg.get("apology", [])),
    }


def selftest() -> int:
    """Prove each rule fires, and that compliant copy stays clean.

    Carried over from the origin script and kept for its reason: every rule here
    is a regex over a short string, and a regex that stops matching reports every
    string as clean. Without this, the gate's success message is unfalsifiable.
    """
    cases = [
        ("all-caps", "PLEASE WAIT", "all_caps"),
        ("Title Case", "Save Changes", "title_case"),
        ("terminal period", "Go back.", "terminal_period"),
        ("three dots", "Type a message...", "three_dots"),
        ("filler", "Simply tap here", "filler"),
        ("apology", "Sorry, that failed", "apology"),
        ("curly quote", "Your’s to review", "curly_quotes"),
    ]
    failed = []
    for label, text, rule in cases:
        got = [i["rule"] for i in check_microcopy(text)]
        if rule not in got:
            failed.append(f"{label}: expected {rule!r}, got {got or 'nothing'}")
        else:
            print(f"  caught  {label}")

    for good in ("More actions", "No data in this period", "Type a message…"):
        hits = check_microcopy(good)
        if hits:
            failed.append(f"false positive on {good!r}: {[h['rule'] for h in hits]}")

    # Exemptions must be per-rule. A string exempted for shouting that also
    # apologises still has to report the apology.
    both = check_microcopy("SORRY IT FAILED")
    rules = {i["rule"] for i in both}
    if not {"all_caps", "apology"} <= rules:
        failed.append(f"expected all_caps AND apology on a string doing both, got {rules}")

    # The title_case rule must not ship a rewritten string (issue #109). The old
    # one lowercased every word after the first, including declared proper nouns
    # and the pronoun 'I', so applying it damaged correct copy. A rule cannot be
    # trusted to stay quiet just because a comment asks it to, so these three
    # measured cases are asserted: if a rewrite comes back, the corrupted form
    # appears in the detail and this fails.
    for text, corrupted in (("Send PDF Report", "Send pdf report"),
                            ("View US Lab Reports", "View us lab reports"),
                            ("Hi, How can I help you?", "Hi, how can i help you?")):
        details = " ".join(i["detail"] for i in check_microcopy(text))
        if corrupted in details:
            failed.append(f"title_case on {text!r} emitted the corrupting fix "
                          f"{corrupted!r} — see engine/copy.py, issue #109")

    if failed:
        print("\nSELFTEST FAILED:\n", file=sys.stderr)
        for f in failed:
            print(f"  {f}\n", file=sys.stderr)
        # A --selftest failure means the checker itself is broken, not that it
        # found a project finding — 1 is reserved for "I looked and this is
        # wrong" about the project's copy. This is "I could not verify I am
        # working", so it gets 2, same as any other could-not-look refusal.
        return 2
    print(f"  {len(cases)} rule(s) fire, 3 compliant strings stay clean, "
          f"and two rules on one string stay separable")
    print("\naudit_copy --selftest: the checks work")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dir", default=None, help="defaults to the profile's source.root")
    ap.add_argument("--out", help="also write findings as JSON here")
    ap.add_argument("--findings", nargs="?", const=True, default=None,
                    help="also write the common findings envelope for /design-debt "
                         "(bare flag uses the default path)")
    ap.add_argument("--update-baseline", action="store_true",
                    help="record current findings as known. Use after fixing copy, "
                         "or on first adoption.")
    ap.add_argument("--accept-new", action="store_true",
                    help="with --update-baseline, deliberately accept findings that "
                         "are not yet baselined. Without it the write is refused "
                         "rather than absorbing a regression nobody was shown.")
    ap.add_argument("--run-disabled", action="store_true",
                    help="run this audit even though it is disabled — for re-measuring "
                         "its false-positive rate, not for reporting a result to anyone")
    args = ap.parse_args()
    if args.selftest:
        # Checked before the disabled gate on purpose: the selftest exercises the
        # rules in isolation and touches no project, so it is exactly what a
        # re-scoping effort needs to keep working.
        return selftest()

    # Checked before anything reads the project, and well before --out,
    # --findings or --update-baseline can write: a refusal that had already
    # overwritten a baseline would have changed the project's recorded debt on
    # the strength of a check we have established cannot be right.
    entry = audit_discovery.disabled_reason(AUDIT)
    if entry and not args.run_disabled:
        return _refuse_disabled(entry)
    if entry:
        print(f"{AUDIT}: DISABLED, running anyway because --run-disabled was passed. "
              f"{entry['reason']}. Treat every finding below as unmeasured.",
              file=sys.stderr)

    from _bootstrap import project_root
    from design_suite.adapters import for_project

    repo = project_root()
    cfg = _config(repo)
    vocab = _vocab(cfg)
    exceptions = cfg.get("exceptions", {}) or {}

    adapter, ctx, _ = for_project(repo)
    inventory = build_inventory(repo, adapter, ctx, args.dir)
    microcopy = [e for e in inventory if e.get("category") == "microcopy"]

    findings = []
    for entry in microcopy:
        allowed = exceptions.get(entry["text"], {})
        for issue in check_microcopy(entry["text"], **vocab):
            if issue["rule"] in allowed:
                continue
            findings.append({
                "file": entry["file"], "line": entry["line"],
                "text": entry["text"], "kind": entry.get("kind"), **issue,
            })

    if args.out:
        (repo / args.out).parent.mkdir(parents=True, exist_ok=True)
        (repo / args.out).write_text(json.dumps(findings, indent=2) + "\n")

    # (text, rule), not (file, line, rule). The same label in two places is one
    # copy decision, and moving a string between files is not a new finding.
    def key(f):
        return f"{f['rule']}\t{f['text']}"

    baseline_rel = cfg.get("baseline")
    baseline_path = (repo / baseline_rel) if baseline_rel else None
    current = {key(f) for f in findings}

    # Read before the write, not after it: --update-baseline cannot refuse to
    # absorb a new finding unless it knows which findings are new.
    known = set()
    if baseline_path and baseline_path.is_file():
        known = set(json.loads(baseline_path.read_text()))

    if args.update_baseline:
        if not baseline_path:
            raise SystemExit("copy.baseline is not set in the exceptions file — "
                             "nowhere to write to")
        refusal = ratchet.refusal("audit_copy", current, known)
        if refusal and not args.accept_new:
            print(refusal, file=sys.stderr)
            return 2
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(sorted(current), indent=2) + "\n")
        print(f"audit_copy: baseline updated — {len(current)} known finding(s)")
        return 0

    new = [f for f in findings if key(f) not in known]
    fixed = sorted(known - current)

    if args.findings:
        from design_suite.engine import findings as F
        # Written after the baseline is loaded, not before, so known debt and new
        # breakage are distinguishable. Both are reported — a debt dashboard that
        # hid the 283 baselined findings would contradict the baseline file's own
        # description of itself as "a debt register, not an approval" — but a
        # baselined finding is FYI and a new one is should-fix, so the gate saying
        # "clean" and the dashboard showing debt are consistent rather than a
        # contradiction someone has to reconcile by hand.
        #
        # Categorised by rule, not by file: rules are the unit a writer acts on,
        # and grading "title_case" apart from "terminal_period" is the difference
        # between a useful row and one that says only "copy".
        F.write(
            F.default_path(repo, "copy") if args.findings is True
            else repo / args.findings,
            "copy",
            [F.make("copy", f["rule"],
                    f"[{f.get('kind') or 'text'}] {f.get('detail', f['rule'])}",
                    severity=F.SHOULD_FIX if key(f) not in known else F.FYI,
                    file=f["file"], line=f["line"], detail=f["text"])
             for f in findings],
            scanned=len(microcopy),
        )

    print(f"  copy entries    {len(inventory)}")
    print(f"  microcopy       {len(microcopy)}  (the rules below apply to these)")
    print(f"  exempted        {sum(len(v) for v in exceptions.values())} "
          f"rule(s) on {len(exceptions)} string(s)")
    if known:
        print(f"  baselined       {len(known)} known finding(s) — a debt register, "
              f"not an approval")
    sys.stdout.flush()

    if fixed:
        print(f"\n{len(fixed)} baselined finding(s) no longer present — nice. "
              f"Run --update-baseline to lock the improvement in.")

    if new:
        print(f"\nNEW COPY PROBLEMS — {len(new)}:\n", file=sys.stderr)
        for f in new:
            print(f"  {f['file']}:{f['line']}  [{f.get('kind') or 'text'}] "
                  f"{f['text']!r} {f['detail']}\n",
                  file=sys.stderr)
        print("If a string breaks a rule on purpose, add it to copy.exceptions in "
              "the exceptions file naming THAT RULE and the reason. An entry is a "
              "decision; an absence is an oversight.", file=sys.stderr)
        return 1

    print(f"\naudit_copy: no new copy problems"
          f"{' (' + str(len(known)) + ' baselined)' if known else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
