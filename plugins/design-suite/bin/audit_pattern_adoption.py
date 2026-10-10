#!/usr/bin/env python3
"""A design-system pattern nothing calls is a claim the system cannot cash.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_pattern_adoption.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_pattern_adoption.py" --selftest

## Why this exists

`audit_unwired_roles` catches a colour *role* nothing reads. This is the same
failure one layer up: a *pattern* nothing calls. Built, documented, listed in a
gallery, and referenced by no product code at all.

The design-system repository's own component-coverage gate (which lives there,
not here) deliberately cannot catch it, and should not try. A gallery use case
satisfies that gate because it answers a real question — "can a designer see
this?" — and a component can pass it while failing this one indefinitely.

## Not the two component audits this suite already ships

`audit_reinvented_components` and `audit_promotion_candidates` both scan the
app's own PRIVATE widgets: the first for one whose name matches a design-system
export, the second for one whose constructor shape is built twice. Both ask what
the app BUILT.

This asks the opposite question, of the other set of symbols: of what the design
system EXPORTS, which does the app never call? A pattern can have zero call
sites with nothing reinvented anywhere — nobody forked it, nobody reached for it
either — and neither of those two audits reports that, because there is no
private widget for them to find. Where they do overlap they agree from opposite
sides: a forked component is also a component with no call sites.

## Which half this is, and why the other half is not here

The design system's own `audit_pattern_adoption.py` is two things: a mechanical
derivation of in-package composition, and a **ledger gate** over hand-counted
adoption in the consuming apps, with a staleness trigger on the package version.

Only the first idea ported. The ledger gate belongs to a *package* that has
consumers elsewhere, and porting it here would have produced an engine no
project in this suite can run — the design system is not a suite consumer, it
has no `.design-suite/` profile, and a consuming app has no ledger to gate. An
engine aimed at nothing is the failure this suite exists to prevent, not an
achievement.

What ported is the question asked **from the consumer's side**, which is the one
the design system explicitly cannot answer: *does this project actually use the
patterns it depends on?* That is mechanically derivable here, because the
project being audited is the one on disk.

## Comments are stripped first, and that is not a detail

Every one of these symbols is *discussed* in the architecture notes of the apps
that use them — a consuming app's own docs routinely name the very components it
is being audited for. Counting those reports adoption that does not exist. A comment is a
mention, not a use, and the comment rule lives in the language adapter so this
and `audit_api_consistency` cannot end up measuring different things.

This deliberately uses the adapter's `blank_comments`, which is string-aware: a
`'https://…'` literal contains `//`, and a naive line-comment regex eats the rest
of that line as if it were a comment. An adapter without one refuses rather than
scanning raw source, because counting mentions inside comments reports adoption
that does not exist — and silence is the failure mode this suite exists to
prevent.

## Call sites, not references

`Symbol(` — a construction or an invocation. A bare type annotation or an `is`
test is a reference, not an adoption. The optional type-argument group is what
makes `ExampleTable<Staff>(` count; without it, every generic component reads as
zero adoption, and a generic component is exactly the kind most likely to be one.

Both numbers are reported, because a symbol with references and no call sites is
worth looking at: it is usually a type annotation on a field nothing ever fills.

## Zero adoption is allowed. Silent zero adoption is not.

A pattern may legitimately ship ahead of its consumer. So a project declares
which patterns it holds itself to; the rest are reported and never fail — the
same split `audit_unwired_roles` draws, and for the same reason. An empty
`requiredPatterns` list means "report, do not fail" and is a different statement
from the key being absent, which means "all of them".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import _bootstrap  # noqa: F401,E402  — puts the plugin on sys.path
from design_suite.engine.refusal import Refused  # noqa: E402


def call_sites(symbol: str, bodies: list[str]) -> dict:
    """Call sites, references and touched files for one symbol."""
    call = re.compile(rf"\b{re.escape(symbol)}\s*(?:<[^>()]*>)?\s*\(")
    ref = re.compile(rf"\b{re.escape(symbol)}\b")
    return {
        "call_sites": sum(len(call.findall(b)) for b in bodies),
        "refs": sum(len(ref.findall(b)) for b in bodies),
        "files": sum(1 for b in bodies if ref.search(b)),
    }


def selftest() -> int:
    """The counting rules are the whole method, so prove each one.

    Every rule here is a regex, and a regex that stops matching reports zero
    adoption — which is indistinguishable from a project that genuinely uses
    nothing, and is the exact shape of failure this suite keeps finding.
    """
    from design_suite.adapters import dart

    cases = [
        ("a plain call counts",
         "ExampleSplitPane(master: x);", "ExampleSplitPane", 1),
        ("a generic call counts — the subtle one",
         "ExampleTable<Staff>(rows: r);", "ExampleTable", 1),
        ("a type annotation is a reference, not a call",
         "final ExampleBreakpoint bp = x;", "ExampleBreakpoint", 0),
        ("a doc comment is a mention, not a use",
         "/// Use ExampleSplitPane( here.\nfinal x = 1;", "ExampleSplitPane", 0),
        ("a line comment is a mention, not a use",
         "// ExampleSplitPane(master: x);", "ExampleSplitPane", 0),
        ("a longer symbol does not match a shorter one",
         "ExampleTableHeader(x);", "ExampleTable", 0),
    ]
    failed = []
    for label, src, symbol, expected in cases:
        got = call_sites(symbol, [dart.blank_comments(src)])["call_sites"]
        if got != expected:
            failed.append(f"{label}: expected {expected} call site(s), got {got}")
        else:
            print(f"  ok  {label}")

    # And references still counted where calls are not — the pair is the point.
    refs = call_sites("ExampleBreakpoint", [dart.blank_comments("final ExampleBreakpoint b = x;")])
    if refs["refs"] != 1:
        failed.append(f"a type annotation must still count as a reference, got {refs}")

    if failed:
        print("\nSELFTEST FAILED:\n", file=sys.stderr)
        for f in failed:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    print(f"\naudit_pattern_adoption --selftest: {len(cases)} counting rule(s) hold")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", help="also write the counts as JSON here")
    ap.add_argument("--findings", nargs="?", const=True, default=None,
                    help="also write the common findings envelope for /design-debt "
                         "(default .design-suite/findings/pattern-adoption.json)")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    from _bootstrap import project_root
    from design_suite.adapters import for_project
    from design_suite.adapters.base import CapabilityError
    from design_suite.engine import findings as F
    from design_suite.engine.arch import load
    from design_suite.project import need, profile

    repo = project_root()
    rules = load(repo, "patternAdoption")
    adapter, _, _ = for_project(repo)
    prof = profile(repo)

    patterns = rules.get("patterns") or []
    if not patterns:
        raise Refused(
            "patternAdoption.patterns is empty — an adoption audit with no "
            "patterns to look for reports nothing and passes, which is "
            "indistinguishable from a project that adopted everything.")

    scan_root = repo / need(prof, "source.root", "is the tree searched for call sites")
    file_glob = need(prof, "source.fileGlob", "is how this audit finds sources")
    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    files = [p for p in sorted(scan_root.glob(file_glob))
             if not p.name.endswith(generated)]
    if not files:
        raise Refused(f"{file_glob!r} matched nothing under source.root — an "
                         f"empty sweep would report zero adoption of everything")

    blank = getattr(adapter, "blank_comments", None)
    if blank is None:
        raise CapabilityError(
            "audit_pattern_adoption", getattr(adapter, "NAME", "unknown"),
            "this adapter cannot blank comments, so a symbol merely discussed in "
            "a doc comment would be counted as adopted; refusing rather than "
            "reporting adoption that does not exist")
    bodies = [blank(p.read_text(errors="ignore")) for p in files]
    counts = {s: call_sites(s, bodies) for s in patterns}

    # Absent means all of them; an empty list means report-but-do-not-fail.
    # `.get(k) or patterns` would conflate the two, which is the bug this suite
    # already shipped once in audit_unwired_roles.
    declared = rules.get("requiredPatterns")
    required = set(patterns) if declared is None else set(declared)

    unused = sorted(s for s, c in counts.items() if c["call_sites"] == 0)
    failing = sorted(s for s in unused if s in required)
    allowed = sorted(s for s in unused if s not in required)
    referenced_only = sorted(
        s for s in unused if counts[s]["refs"] > 0)

    if args.out:
        (repo / args.out).parent.mkdir(parents=True, exist_ok=True)
        (repo / args.out).write_text(json.dumps(
            {"files_scanned": len(files), "symbols": counts}, indent=2) + "\n")

    if args.findings:
        # A claimed-but-uncalled pattern and an available-but-unused one are
        # different facts and must not share a grade: the first is the project
        # failing a claim it made, the second is usually a form factor. Category
        # keeps them in separate rows of /design-debt.
        records = (
            [F.make("pattern-adoption", "unadopted",
                    f"{s_} is claimed in requiredPatterns and called nowhere",
                    severity=F.SHOULD_FIX,
                    detail=f"{counts[s_]['refs']} reference(s), 0 call sites")
             for s_ in failing]
            + [F.make("pattern-adoption", "unused-here",
                      f"{s_} is available and never called here",
                      severity=F.FYI,
                      detail="not claimed by this project — see "
                             "patternAdoption.requiredPatterns")
               for s_ in allowed])
        F.write(
            F.default_path(repo, "pattern-adoption") if args.findings is True
            else repo / args.findings,
            "pattern-adoption", records,
            # Files, not patterns: zero findings from a sweep that matched no
            # files is not adoption, it is an audit that never ran.
            scanned=len(files),
        )

    adopted = len(patterns) - len(unused)
    print(f"  patterns        {len(patterns)}")
    print(f"  adopted         {adopted}  ({len(files)} file(s) scanned)")
    for s in sorted(counts, key=lambda k: -counts[k]["call_sites"])[:5]:
        c = counts[s]
        if c["call_sites"]:
            print(f"      {s:<28} {c['call_sites']:>3} call site(s) in {c['files']} file(s)")
    if allowed:
        print(f"  unused here     {len(allowed)}: {', '.join(allowed)}")
        print("                  (available, not claimed by this project — see "
              "patternAdoption.requiredPatterns)")
    if referenced_only:
        # Worth surfacing separately: usually a type annotation on a field
        # nothing ever fills, which reads as adoption in a grep and is not.
        print(f"  referenced but never called: {', '.join(referenced_only)}")
    sys.stdout.flush()

    if failing:
        print(f"\nUNADOPTED — {len(failing)} pattern(s) this project claims and "
              f"calls nowhere:\n", file=sys.stderr)
        for s in failing:
            print(f"  {s}  ({counts[s]['refs']} reference(s), 0 call sites)",
                  file=sys.stderr)
        print("\nEither call it, or drop it from patternAdoption.requiredPatterns. "
              "A pattern the product never reaches for is a claim the design "
              "system cannot cash.", file=sys.stderr)
        return 1

    print("\naudit_pattern_adoption: every claimed pattern is called somewhere")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
