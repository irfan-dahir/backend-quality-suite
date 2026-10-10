#!/usr/bin/env python3
"""Ratify one profile field — move it from a machine's guess to a human decision.

RFC-0002 §3b's provenance vocabulary shipped with its whole reading half and no
writing half. `doctor.py` refuses to trust `inferred`, derives `contradicted`,
and prints the ratified-of-total count on a clean run; the schema describes
`by`, `on`, `value`, `evidence` and `verifiedAgainst.commit`. But the only way
to actually approve anything was to hand-edit `.design-suite/profile.json` — the
same producer-shaped hole `decline_doc.py` was written to close.

That matters more here than convenience. The RFC's own risk section says the
mitigation for "a skill that argues well for a wrong mapping" is *`inferred`
provenance plus ratification*. Half a mitigation is the failure this repo is
built against: a profile everyone believes was reviewed, because the mechanism
for reviewing it exists on paper.

So this is a deliberate act with a record, and it refuses in every case where
the record would be less true than it looks:

  * a field the profile does not have        — ratifying nothing
  * `--approve` with nothing proposed        — there is no argument to review
  * re-approving an already-trusted field    — success printed for no change
  * an identical re-run                      — the silent no-op, exactly
  * a path that is not there                 — writes a CONTRADICTED on sight
  * no readable HEAD                         — exit 2, staleness never computable

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/ratify.py" --list
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/ratify.py" source.root --by NAME
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/ratify.py" tokens.accessor --declare --by NAME
                                      [--evidence "..."] [--on YYYY-MM-DD]
                                      [--profile PATH] [--dir .] [--force]

Exit 0 = ratified (or listed). 1 = refused, fixable by the caller.
2 = refused, cannot be answered here. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402

from design_suite.engine import provenance  # noqa: E402

DEFAULT_PROFILE = ".design-suite/profile.json"


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except OSError:
        sys.exit(f"no profile at {path} — run init.py first")
    except ValueError as exc:
        sys.exit(f"{path} is not valid JSON ({exc})")


def report_outstanding(profile: dict) -> int:
    """Print what is awaiting ratification — including when the answer is none.

    A ratification tool whose listing is empty on an unreviewed profile and on a
    fully-reviewed one is the governing failure in miniature, so the three cases
    print differently: no provenance block at all, a block with nothing
    outstanding, and a list.
    """
    inferred, unattributed = provenance.awaiting_ratification(profile)
    total = len(provenance.profile_leaves(profile))
    if "provenance" not in profile:
        print(f"this profile has NO provenance block: all {total} field(s) are "
              f"unattributed. Nothing here has been ratified, and nothing records how "
              f"any of it got its value.")
    for dotted in inferred:
        entry = provenance.entries(profile)[dotted]
        why = entry.get("evidence")
        print(f"  inferred      {dotted}" + (f"  — {why}" if why else ""))
    for dotted in unattributed:
        print(f"  unattributed  {dotted}")
    ratified = sum(1 for d, e in provenance.entries(profile).items()
                   if not d.startswith("_") and isinstance(e, dict)
                   and e.get("state") in provenance.TRUSTED_STATES)
    print(f"{len(inferred)} inferred, {len(unattributed)} unattributed, "
          f"{ratified} of {total} field(s) carry a human decision.")
    if inferred:
        print("approve one with:  ratify.py <field> --by NAME")
    if unattributed:
        print("record authorship with:  ratify.py <field> --declare --by NAME")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("field", nargs="?",
                    help="Dotted profile path, e.g. source.root")
    ap.add_argument("--by", default=None,
                    help="Who is ratifying. Required: an unsigned approval "
                         "cannot be re-examined.")
    ap.add_argument("--declare", action="store_true",
                    help="Record 'declared' (a human wrote this value) rather "
                         "than 'approved' (a human reviewed a machine's).")
    ap.add_argument("--evidence", default=None,
                    help="What was reviewed. Defaults to keeping the proposal's own.")
    ap.add_argument("--on", default=None, help="Date of the decision (YYYY-MM-DD).")
    ap.add_argument("--list", action="store_true",
                    help="Show every field awaiting ratification, and stop.")
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--dir", default=None, help="Project root (default: detected).")
    ap.add_argument("--force", action="store_true",
                    help="Re-stamp a field that is already trusted, or overwrite "
                         "an inferred entry with your own authorship.")
    args = ap.parse_args(argv)

    repo = Path(args.dir).resolve() if args.dir else project_root()
    profile_path = repo / args.profile
    profile = load(profile_path)

    if args.list:
        return report_outstanding(profile)
    if not args.field:
        print("name a field to ratify, or pass --list to see what is outstanding.",
              file=sys.stderr)
        return 1
    if not args.by:
        print("--by is required: an approval nobody signed cannot be re-examined, "
              "and reads downstream exactly like one that was.", file=sys.stderr)
        return 1

    commit, dirty = provenance.head_stamp(repo)
    try:
        _, summary = provenance.ratify(
            profile, args.field,
            state="declared" if args.declare else "approved",
            by=args.by, repo=repo, commit=commit, dirty=dirty,
            evidence=args.evidence, on=args.on, force=args.force)
    except provenance.RatificationRefused as refusal:
        print(f"refusing: {refusal}", file=sys.stderr)
        return refusal.exit_code

    profile_path.write_text(json.dumps(profile, indent=2) + "\n")
    print(f"ratified: {summary}")
    inferred, unattributed = provenance.awaiting_ratification(profile)
    print(f"recorded in {profile_path.relative_to(repo)}. "
          f"{len(inferred)} inferred and {len(unattributed)} unattributed field(s) "
          f"remain untrusted; run doctor.py to see them in context.")
    if dirty:
        print("note: the working tree was dirty, and the entry says so. A "
              "confirmation against uncommitted files is not reproducible by "
              "anyone else at that commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
