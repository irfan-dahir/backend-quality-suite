#!/usr/bin/env python3
"""Check that a merged PR's body carries a `Verification-Tier:` trailer.

    python3 plugins/design-suite/bin/check_pr_verification_trailer.py <pr-number> [more...]
    python3 plugins/design-suite/bin/check_pr_verification_trailer.py --since <ref>

Checks PRESENCE only, not truthfulness — the same limit gates.py's other checks
accept: a trailer that says `human-reviewed` when nothing was reviewed passes this
just as easily as an honest `unverified` does. That is a known, accepted gap, not
an oversight: truthfulness needs a human or a second party in the loop, which is
exactly what issue #59's research concluded a CI gate cannot supply on its own
(see the issue #59 comment thread). This script exists only to catch the cheap
failure mode — a PR merged with the trailer silently missing entirely, e.g.
because the template's HTML comment was deleted along with the fields it wraps.

## Why this is not wired into gates.py or CI

gates.py runs gates parsed out of `.github/workflows/validate.yml` against *this
checkout* — every one of them is a property of the tree on disk. Whether a PR
body contains a line is a property of GitHub's PR object, not of the tree, so it
does not fit that model, and per CLAUDE.md rule 3 CI is dead here anyway. This is
a separate, manual, `gh`-backed script: run it by hand, occasionally, against
recent merges — not a gate that blocks anything.

Requires the `gh` CLI to be authenticated.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

TRAILER_RE = re.compile(r"^Verification-Tier:\s*(\S.*)?$", re.MULTILINE)


def check_one(pr: str) -> tuple[bool, str]:
    proc = subprocess.run(
        ["gh", "pr", "view", pr, "--json", "number,title,body,state"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return False, f"PR {pr}: could not fetch ({proc.stderr.strip()[:200]})"

    data = json.loads(proc.stdout)
    m = TRAILER_RE.search(data.get("body") or "")
    if not m:
        return False, f"PR {pr} ({data.get('title', '?')!r}): no Verification-Tier trailer found"
    value = (m.group(1) or "").strip()
    if not value:
        return False, f"PR {pr} ({data.get('title', '?')!r}): Verification-Tier trailer present but blank"
    return True, f"PR {pr} ({data.get('title', '?')!r}): Verification-Tier: {value}"


def prs_since(ref: str) -> list[str]:
    proc = subprocess.run(
        ["gh", "pr", "list", "--state", "merged", "--search", f"base:{ref}", "--json", "number",
         "--limit", "50"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"could not list merged PRs: {proc.stderr.strip()}")
    return [str(p["number"]) for p in json.loads(proc.stdout)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("prs", nargs="*", help="PR numbers to check")
    ap.add_argument("--since", metavar="BASE_BRANCH",
                     help="check merged PRs targeting this base branch instead of listing numbers")
    args = ap.parse_args()

    prs = list(args.prs)
    if args.since:
        prs += prs_since(args.since)
    if not prs:
        ap.error("give at least one PR number, or --since <base-branch>")

    failures = 0
    for pr in prs:
        ok, msg = check_one(pr)
        print(("ok   " if ok else "FAIL ") + msg)
        if not ok:
            failures += 1

    if failures:
        print(f"\n{failures} of {len(prs)} PR(s) missing a Verification-Tier trailer.",
              file=sys.stderr)
        return 1
    print(f"\nall {len(prs)} PR(s) carry a Verification-Tier trailer (presence only, not checked for truthfulness).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
