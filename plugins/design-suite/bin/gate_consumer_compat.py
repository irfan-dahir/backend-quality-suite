#!/usr/bin/env python3
"""Fail a merge that changes what a consumer's CI reports, unless it is acknowledged.

    # The gate, as CI runs it: latest release tag -> HEAD
    python3 plugins/design-suite/bin/gate_consumer_compat.py

    # Same, against an explicit range or a different acknowledgement file
    python3 plugins/design-suite/bin/gate_consumer_compat.py --from <rev> --to <rev>
    python3 plugins/design-suite/bin/gate_consumer_compat.py --acks path/to/file.json

    # The full report, for a PR comment or a release note
    python3 plugins/design-suite/bin/gate_consumer_compat.py --json

## Why this is a gate and not a command somebody remembers to run

PR #127 merged carrying eleven critical consumer-breaking changes — among them two
audits that newly exit 2, invoked by path from a live client's CI, and a removed
`--require-resolution` flag that argparse turns into an exit-2 refusal the client
never made. Every existing surface stayed quiet, because every existing surface
was asking a different question: the manifests parsed, Python compiled, the tests
passed. Nothing was asking *what does this do to somebody who already installed
it*. `suite_upgrade.py compat` could answer that the day #127 merged, and nobody
ran it, which is the difference between a capability and a gate.

## Why it is escapable, and why that is the safety property

Consumers pin to a release tag. The pinning contract says a breaking change ships
in a version bump — so a gate that forbade breaking changes outright would
contradict the contract it protects, and would be deleted the first time it was
inconvenient. A deleted gate still reads as a pass, which is worse than no gate.

So the escape hatch is a committed file, `consumer-compat-acks.json`, in which a
human writes down what the break is, which consumer invocation it hits, and what
a consumer must DO about it. The migration note is mandatory: an acknowledgement
that says only "accepted" is a rubber stamp, and this refuses to load one. There
is deliberately no `--acknowledge` flag — acknowledging must be a diff a reviewer
sees next to the change it excuses, never a side effect of running the tool.
`design_suite/engine/ratchet.py` is where that lesson was paid for.

## Exit codes — the contract everything here shares

    0   clean       no unacknowledged critical break
    1   findings    unacknowledged critical break(s) — this is the gate biting
    2   refused     cannot determine: no release tag, unreadable repo, or an
                    acknowledgement file that is malformed or missing a migration
    3   external    unused here
    4   declined    unused here
    5   stub        unused here

**Cannot-determine is 2 and never 0.** The baseline is "the release consumers are
pinned to", and if that cannot be found there is no consumer this gate can speak
for. Passing then would be the governing failure exactly: a gate that reported
nothing because it looked at nothing, indistinguishable from a clean tree.

Stdlib only, like everything else in this directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT  # noqa: E402

from design_suite.engine import compat_gate  # noqa: E402
from design_suite.engine.upgrade import CannotDetermine  # noqa: E402

REPO = PLUGIN_ROOT.parents[1]

# Beside known-traps.json, for the reason that file's own _readme gives: this
# repository IS the plugin source, so its populated instances live at the root
# rather than under a .design-suite/ directory it does not have. A path relative
# to the repo root, resolved at run time — never a literal inside the plugin.
DEFAULT_ACKS = "consumer-compat-acks.json"

CLEAN, FINDINGS, REFUSED = 0, 1, 2

MARK = {"critical": "🔴", "should-fix": "🟡"}


def render(report: dict, acks_path: Path) -> list[str]:
    base, head = report["baseline"], report["head"]
    lines = [
        f"consumer compatibility: {base['rev']} ({base['sha'][:12]}) "
        f"->  {head['rev']} ({head['sha'][:12]})",
        f"  baseline from: {base['derivedFrom']} — the release consumers are "
        f"pinned to",
        f"  acknowledgements: {acks_path}",
        "",
    ]
    for note in report["notes"]:
        lines.append(f"note: {note}")
    if report["notes"]:
        lines.append("")

    if report["acknowledged"]:
        lines.append(f"ACKNOWLEDGED — {len(report['acknowledged'])} break(s) "
                     f"shipping on purpose, each with a migration path:")
        for row in report["acknowledged"]:
            ack, finding = row["ack"], row["finding"]
            lines.append(f"  {MARK.get(finding['severity'], '?')} {ack['id']}: "
                         f"{finding['category']} — {finding['subject']}")
            lines.append(f"      break:      {ack['break']}")
            lines.append(f"      affects:    {ack['consumerInvocation']}")
            lines.append(f"      migration:  {ack['migration']}")
        lines.append("")

    if report["advisory"]:
        lines.append(f"SHOULD-FIX — {len(report['advisory'])} consumer-visible "
                     f"change(s), reported, not blocking:")
        for finding in report["advisory"]:
            lines.append(f"  🟡 {finding['category']}: {finding['subject']}")
        lines.append("")

    if report["stale"]:
        lines.append(f"STALE — {len(report['stale'])} acknowledgement(s) match no "
                     f"current finding. The break was fixed, or the release that "
                     f"carried it has shipped. Not a failure; remove them:")
        for ack in report["stale"]:
            lines.append(f"  ⚪ {ack['id']} ({ack['category']}: {ack['subject']})")
        lines.append("")

    if not report["blocking"]:
        lines.append("No unacknowledged critical break. A consumer pinned to "
                     f"{base['rev']} can repin to this revision, or has been told "
                     f"in writing what it will cost them.")
        return lines

    lines.append(f"BLOCKING — {len(report['blocking'])} unacknowledged critical "
                 f"break(s). Each one changes what a consumer's CI reports on a "
                 f"tree that did not change:")
    lines.append("")
    for finding in report["blocking"]:
        lines.append(f"  🔴 {finding['category']}: {finding['subject']}")
        lines.append(f"     {finding['detail']}")
        if "before" in finding:
            lines.append(f"     before: {finding['before']}")
            lines.append(f"     after:  {finding['after']}")
        lines.append("")
    lines += [
        "Fix them, or — if they are shipping on purpose in the next version bump "
        "— acknowledge each one by adding an entry to",
        f"{DEFAULT_ACKS}, in this same commit, so a reviewer reads the excuse "
        f"next to the change. Skeletons, with the fields you must fill in:",
        "",
        json.dumps([compat_gate.suggested_entry(f) for f in report["blocking"]],
                   indent=2, ensure_ascii=False),
        "",
        "`migration` is mandatory and is checked at load. An entry without it is "
        "refused, not accepted — that is the difference between this and a rubber "
        "stamp.",
    ]
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=str(REPO), help="this suite repository")
    ap.add_argument("--from", dest="from_rev", default=None,
                    help="baseline revision (default: the latest release tag, "
                         "which is what consumers are pinned to)")
    ap.add_argument("--to", dest="to_rev", default="HEAD",
                    help="the revision about to merge (default: HEAD)")
    ap.add_argument("--acks", default=None,
                    help=f"acknowledgement file (default: <repo>/{DEFAULT_ACKS})")
    ap.add_argument("--tag-match", default=compat_gate.DEFAULT_TAG_MATCH,
                    help="glob the release tags are named with")
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = ap.parse_args(argv)

    repo = Path(args.repo)
    acks_path = Path(args.acks) if args.acks else repo / DEFAULT_ACKS

    try:
        acks = compat_gate.load_acks(acks_path)
        report = compat_gate.evaluate(
            repo, acks, old_rev=args.from_rev, new_rev=args.to_rev,
            tag_match=args.tag_match)
    except CannotDetermine as exc:
        # Exit 2, loudly, always. Never 0 — see this module's docstring.
        if args.json:
            print(json.dumps({"status": "cannot-determine", "reason": str(exc)},
                             indent=2))
        print(f"cannot determine: {exc}", file=sys.stderr)
        return REFUSED

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("\n".join(render(report, acks_path)))
    return FINDINGS if report["blocking"] else CLEAN


if __name__ == "__main__":
    sys.exit(main())
