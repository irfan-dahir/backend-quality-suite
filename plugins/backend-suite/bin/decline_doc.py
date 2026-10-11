#!/usr/bin/env python3
"""Record that this project has DECLINED one doc role, with a reason.

The producer for the other half of the pair `scaffold_doc.py` opened. Exit code
4, `decline_reason()` and stub-aware debt counting all shipped with consumers
and no writer, so the only way to decline a role was to hand-edit
`docs.manifest.json` — and a contract enforced by instructions is a contract
that holds until someone is in a hurry.

The reason is not optional, and that is the whole point of this script existing.
`decline_reason()` returns "" rather than a stand-in precisely so a reasonless
decline stays detectable, and `doctor.py` reports it; making the reason a
required argument here means the detectable-but-broken state mostly stops being
produced in the first place. A skill that hits exit 4 prints this reason in its
report, so a missing one degrades "declined, because X" into a silent skip,
which is the failure the state was invented to prevent.

Declining is not the same as never having looked. An absent role means nobody
has considered it, and the suite is supposed to keep saying so; a declined role
means the question was answered. Neither counts as coverage, and `design_debt`
counts declines in neither direction.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/decline_doc.py" <role> --reason "..."
                                                       [--by NAME] [--on YYYY-MM-DD]
                                                       [--dir .] [--force]

Exit 0 on success. Exit 1 on a refusal the caller can fix.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402
from backend_suite.engine import archetypes  # noqa: E402
from backend_suite.engine import doc_roles  # noqa: E402

DEFAULT_MANIFEST = ".backend-suite/docs.manifest.json"


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except OSError:
        sys.exit(f"no manifest at {path} — run init.py first")
    except ValueError as exc:
        sys.exit(f"{path} is not valid JSON ({exc})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("role")
    ap.add_argument("--reason", required=True,
                    help="Why this project does not need the document. Printed "
                         "verbatim by every skill that hits exit 4.")
    ap.add_argument("--by", default=None, help="Who decided. Optional but recommended.")
    ap.add_argument("--on", default=None, help="Date of the decision (YYYY-MM-DD).")
    ap.add_argument("--dir", default=None, help="Project root (default: detected).")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing decline for this role.")
    args = ap.parse_args(argv)

    repo = Path(args.dir).resolve() if args.dir else project_root()
    manifest_path = repo / DEFAULT_MANIFEST
    manifest = load_manifest(manifest_path)

    role = archetypes.canonical_role(args.role)

    # An empty or whitespace reason is refused rather than stored. argparse only
    # guarantees the flag was passed, and `--reason ""` is exactly what someone
    # types to get past a required argument they do not want to answer.
    reason = args.reason.strip()
    if not reason:
        print(f"refusing to decline {role!r} with an empty reason — the reason is "
              f"what a skill prints when it skips a check, and without one the skip "
              f"is indistinguishable from the check passing.", file=sys.stderr)
        return 1

    known = archetypes.roles()
    if role not in known:
        print(f"unknown role {role!r} — declining a role the vocabulary does not "
              f"have records a decision about nothing. Known roles: "
              f"{', '.join(sorted(known))}", file=sys.stderr)
        return 1

    # Declining a role that is already mapped would leave the manifest asserting
    # both "here is the document" and "we decided not to have one". resolve.py
    # checks declines first, so the mapping would silently stop resolving.
    mapped = (manifest.get("roles") or {})
    if role in mapped and not args.force:
        print(f"refusing: {role!r} is already mapped to {mapped[role]!r}. Declining a "
              f"mapped role would make that mapping unreachable without deleting it. "
              f"Remove the mapping first, or pass --force if the document is gone.",
              file=sys.stderr)
        return 1

    declined = manifest.setdefault(doc_roles.DECLINED_KEY, {})
    if role in declined and not args.force:
        existing = doc_roles.decline_reason(declined[role]) or "NO REASON RECORDED"
        print(f"{role!r} is already declined: {existing}\n"
              f"pass --force to replace that reason.", file=sys.stderr)
        return 1

    entry = {"declined": reason}
    if args.by:
        entry["by"] = args.by
    entry["on"] = args.on or dt.date.today().isoformat()
    declined[role] = entry

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"declined: {role} — {reason}")
    print(f"recorded in {manifest_path.relative_to(repo)}. Every skill that needs this "
          f"role now skips its check with exit 4 and reports the reason; declined is "
          f"not passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
