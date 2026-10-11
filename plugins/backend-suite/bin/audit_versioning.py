#!/usr/bin/env python3
"""The API's version is declared in three places; keep them the same number.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_versioning.py" [--out …] [--findings]

## Why this exists

A versioned API usually states its version more than once — in the route
file's name, in the URL prefix the framework mounts it under, and in the
controller namespace the handlers resolve through. The three drift
independently: a v5 routes file gets required under the v4 prefix (callers
on /v5 get 404s while /v4 serves v5 code), or the namespace keeps `V4DB`
while the prefix says v5 (handlers resolve through the old tree, or fail
to resolve at all). Nothing fails at boot; the mismatch surfaces as the
wrong API on the right URL.

Measured on the first validation target (jikan-rest, Lumen, probed
2026-10-11): coherent today — `bootstrap/app.php` mounts
`routes/web.v4.php` under `'prefix' => 'v4'` with `'namespace' =>
'App\Http\Controllers\V4DB'`, and the unversioned group mounts its routes
inline with no versioned file to disagree with. The clean direction is
measured honestly, and the audit is regression detection: the next version
bump is exactly when this drifts.

## What it checks, and how it associates

For every route file whose name carries a version (the project's
`routeFilePattern`), the group that requires it must declare a prefix with
the same version and — when `namespacePattern` applies — a namespace whose
version segment matches. Association is by **nearest preceding group
declaration**, not full brace tracking: the routing style this was written
against declares one group per require in a flat file, and a nesting-aware
parser that pretends otherwise would be a longer way to be wrong. A routing
file that nests groups should not wire this audit until the association
grows up with it.

## What it refuses to do

Run with no versioned route file found (nothing to compare), with a
bootstrap glob matching nothing, or with patterns that extract nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
from backend_suite.engine import findings as F  # noqa: E402
from backend_suite.engine.arch import load  # noqa: E402
from backend_suite.engine.refusal import Refused  # noqa: E402

RULES = load(REPO, "versioning")

ENVELOPE = "versioning"


def _compiled(key: str, why: str) -> re.Pattern:
    pattern = RULES.get(key)
    if not pattern:
        raise Refused(f"versioning.{key} is not set — {why}",
                      audit="audit_versioning")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise Refused(f"versioning.{key} is not a valid regex: {exc}",
                      audit="audit_versioning")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for "
                             "/quality-debt (bare flag uses the default path)")
    args = parser.parse_args()

    file_re = _compiled("routeFilePattern",
                        "how a versioned route file is named (capture = the "
                        "version)")
    prefix_re = _compiled("prefixPattern",
                          "how a group declares its URL prefix (capture = the "
                          "version)")
    namespace_re = _compiled(
        "namespacePattern",
        "how a group declares its controller namespace (capture = the full "
        "namespace)")
    ns_version_re = _compiled(
        "namespaceVersionPattern",
        "the version segment inside the namespace (capture = the version)")

    bootstrap_glob = RULES.get("bootstrapGlob")
    if not bootstrap_glob:
        raise Refused("versioning.bootstrapGlob is not set — where route "
                      "groups are declared", audit="audit_versioning")
    bootstraps = sorted(REPO.glob(bootstrap_glob))
    if not bootstraps:
        raise Refused(
            f"versioning.bootstrapGlob ({bootstrap_glob!r}) matched no "
            f"files — the mount points cannot be found, so no version can "
            f"be compared.", audit="audit_versioning")

    records = []
    mounts = 0
    for path in bootstraps:
        rel = path.relative_to(REPO).as_posix()
        lines = path.read_text().splitlines()
        # Group declarations in order, each carrying its config window — the
        # lines between `group(` and the closure signature, which is where
        # this style declares prefix/namespace/middleware. A require is
        # associated with the nearest group above it (the flat-file
        # convention, stated in the module docstring).
        groups: list[str] = []
        in_config = False
        for line_no, line in enumerate(lines, 1):
            if "group(" in line:
                groups.append("")
                in_config = True
                continue
            if in_config:
                if "function" in line:
                    in_config = False
                else:
                    groups[-1] += "\n" + line
                    continue
            require = re.search(r"routes/([\w.\-]+\.php)", line)
            if not require:
                continue
            fname = require.group(1)
            versioned = file_re.search(fname)
            if not versioned:
                continue  # unversioned mounts are out of this audit's subject
            version = versioned.group(1)
            mounts += 1
            group_text = groups[-1] if groups else ""
            prefix = prefix_re.search(group_text)
            where = f"{rel}:{line_no} loads {fname} (v{version})"
            if not prefix:
                records.append(F.make(
                    ENVELOPE, "prefix_version_mismatch",
                    f"{where} under a group with no version prefix — the "
                    f"file says v{version} and the URL says nothing.",
                    severity=F.SHOULD_FIX, file=rel, line=line_no))
            elif prefix.group(1) != version:
                records.append(F.make(
                    ENVELOPE, "prefix_version_mismatch",
                    f"{where} but the group prefix is v{prefix.group(1)} — "
                    f"callers reach v{version} code on the v"
                    f"{prefix.group(1)} URL.",
                    severity=F.CRITICAL, file=rel, line=line_no))
            namespace = namespace_re.search(group_text)
            if namespace:
                ns_version = ns_version_re.search(namespace.group(1))
                if ns_version and ns_version.group(1) != version:
                    records.append(F.make(
                        ENVELOPE, "namespace_version_mismatch",
                        f"{where} but the group namespace is "
                        f"{namespace.group(1)!r} (v{ns_version.group(1)}) — "
                        f"handlers resolve through the wrong version's tree.",
                        severity=F.SHOULD_FIX, file=rel, line=line_no))

    if not mounts:
        raise Refused(
            f"no versioned route file is required under "
            f"{bootstrap_glob!r} — either the mount points moved or this "
            f"API is not versioned in the file name. Comparing nothing is "
            f"not clean.", audit="audit_versioning")

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"mounts_checked": mounts,
             "violations": [r["summary"] for r in records]}, indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "versioning") if args.findings is True
            else REPO / args.findings,
            ENVELOPE, records,
            scanned=len(bootstraps),
        )

    print(f"  versioned mounts    {mounts}")
    print(f"  bootstrap files     {len(bootstraps)}")
    if not records:
        print(f"\naudit_versioning: filename, prefix and namespace agree on "
              f"every versioned mount")
        return 0

    print(f"\nVIOLATIONS ({len(records)}):", file=sys.stderr)
    for record in records:
        print(f"  [{record['category']}] {record['summary']}", file=sys.stderr)
    if args.out:
        print(f"\nFindings written to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
