#!/usr/bin/env python3
"""Build, deploy, and smoke-check a project's own docs site — nothing else.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/deploy_docs_site.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/deploy_docs_site.py" --skip-deploy   # build + smoke-check only
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/deploy_docs_site.py" --project-root /path/to/other-repo

Reads a "site-assembly recipe" from `release.docsSite` in
`.backend-suite/profile.json`: a build command, a deploy command, and a list
of routes to smoke-check afterward. Runs build, then deploy, then GETs each
route and checks its status code. Fails loudly (non-zero exit) the moment
any command exits non-zero or any route returns the wrong status.

## Why this is scoped to docs sites, and why it takes shell commands

Issue #79's research (see the issue thread) is explicit that "deploy" does
not generalize past a static docs site: a mobile app has a build+sign+store
pipeline with near-zero cross-project reuse, which is exactly what
`/cut-release` already owns per the ROADMAP's C4 row. A docs site, by
contrast, is "assemble some files, push them somewhere that serves static
files" — genuinely generic, provided the project supplies its own build and
deploy commands rather than this script guessing a hosting provider. There
is deliberately no provider-specific code here (no S3 SDK call, no Netlify
API client): `release.docsSite.buildCommand` /
`release.docsSite.deployCommand` are each an argv list the project owns —
`rsync`, the `gh-pages` CLI, `netlify deploy`, `aws s3 sync`, or a local
project script, whatever that project already uses to publish its own docs.

## The refusal, not the pass

If `release.docsSite` is absent, this script exits 2 with a clear message —
it is a docs-site-only tool and says so, rather than silently doing nothing
and exiting 0 as if a deploy with nothing to check had "succeeded". Per this
repo's governing principle: an audit (or, here, a release step) that reports
nothing must never be indistinguishable from a clean run.

## Smoke check

`smokeCheckRoutes` is a list of `{"url": ..., "expectedStatus": 200}`
entries (status defaults to 200 when omitted). Each is fetched with a plain
GET; a route list is required once `docsSite` is configured — a deploy step
with zero routes to check would be silently unverifiable, which is the same
failure shape this whole script exists to avoid.

Stdlib only (`urllib.request` for the smoke check, `subprocess` for the
commands) — no `requests`, same reasoning the rest of `bin/` gives for
staying dependency-free.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from backend_suite.project import need, profile  # noqa: E402

DEFAULT_TIMEOUT_SECONDS = 10


def run_command(argv: list[str], cwd: Path, label: str) -> None:
    if not argv:
        raise SystemExit(f"release.docsSite.{label} is an empty command list")
    print(f"$ {' '.join(argv)}")
    proc = subprocess.run(argv, cwd=cwd)
    if proc.returncode != 0:
        print(f"\nFAIL  {label} exited {proc.returncode}: {' '.join(argv)}", file=sys.stderr)
        raise SystemExit(1)


def smoke_check(route: dict, timeout: int) -> Optional[str]:
    """Return None on success, or an error message describing the failure."""
    url = route.get("url")
    if not url:
        return f"route {route!r} has no 'url'"
    expected = route.get("expectedStatus", 200)

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except urllib.error.URLError as exc:
        return f"{url}: could not connect ({exc.reason})"

    if status != expected:
        return f"{url}: expected status {expected}, got {status}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-root", metavar="PATH",
                     help="project root to deploy, overriding auto-detection "
                          "(that root must still contain .backend-suite/profile.json)")
    ap.add_argument("--skip-build", action="store_true", help="skip buildCommand")
    ap.add_argument("--skip-deploy", action="store_true", help="skip deployCommand")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS,
                     help=f"per-route smoke-check timeout in seconds (default {DEFAULT_TIMEOUT_SECONDS})")
    args = ap.parse_args()

    repo = project_root(args.project_root) if args.project_root else REPO
    data = profile(repo)

    docs_site = need(
        data, "release.docsSite",
        "declares the build command, deploy command, and routes to "
        "smoke-check for this project's docs site — without it this "
        "script has nothing to build, deploy, or verify, and that must "
        "fail loudly rather than exit 0 as if a deploy with nothing to do "
        "had succeeded",
        default=None,
    )

    if not docs_site:
        print(
            "no release.docsSite configured in .backend-suite/profile.json — "
            "this is a docs-site-only release step and refuses to run "
            "without a build command, deploy command, and smoke-check "
            "routes to verify against. If this project has no docs site to "
            "deploy, don't run this script.",
            file=sys.stderr,
        )
        return 2

    if not isinstance(docs_site, dict):
        print("release.docsSite must be an object", file=sys.stderr)
        return 2

    build_command = docs_site.get("buildCommand")
    deploy_command = docs_site.get("deployCommand")
    routes = docs_site.get("smokeCheckRoutes")

    if not build_command:
        print("release.docsSite.buildCommand is missing or empty", file=sys.stderr)
        return 2
    if not deploy_command:
        print("release.docsSite.deployCommand is missing or empty", file=sys.stderr)
        return 2
    if not routes:
        print(
            "release.docsSite.smokeCheckRoutes is missing or empty — a "
            "deploy with no routes to check afterward is silently "
            "unverifiable, which is exactly what this script exists to "
            "avoid",
            file=sys.stderr,
        )
        return 2

    if not args.skip_build:
        run_command(build_command, repo, "buildCommand")
    else:
        print("(skipping buildCommand)")

    if not args.skip_deploy:
        run_command(deploy_command, repo, "deployCommand")
    else:
        print("(skipping deployCommand)")

    print(f"\nsmoke-checking {len(routes)} route(s):")
    failures = []
    for route in routes:
        err = smoke_check(route, args.timeout)
        if err is None:
            print(f"  ok    {route.get('url')} -> {route.get('expectedStatus', 200)}")
        else:
            print(f"  FAIL  {err}", file=sys.stderr)
            failures.append(err)

    if failures:
        print(f"\nFAIL  {len(failures)} of {len(routes)} smoke check(s) failed.", file=sys.stderr)
        return 1

    print(f"\nok — deployed and all {len(routes)} smoke check(s) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

