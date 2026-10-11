#!/usr/bin/env python3
"""Check that every declared version source agrees, before a release is cut.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/check_version_consistency.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/check_version_consistency.py" --project-root /path/to/other-repo

Reads `release.versionSources` from `.backend-suite/profile.json` — a list of
files this project considers authoritative for its own version number, and
how to pull a version string out of each one. Compares them and fails loudly
(exit 1) the moment two disagree, printing a diff-style table rather than a
vague "mismatch" so the operator can see which file is stale.

## Why this is config-driven rather than a fixed file list

Issue #79's research (see the issue thread) found this slice genuinely
generic: reading a version out of `package.json`/`pubspec.yaml`/`CHANGELOG.md`
and diffing them is pure string/regex work with no project literal in it, the
same shape as `changelog_to_release_notes.py`. But which files carry a
version, and where in each, is a fact about one project, not about every
stack this suite runs on — so it belongs in the profile, not in this script.

## The refusal, not the pass

If `release.versionSources` is absent, or present but empty, this script
exits 2 with a clear message rather than exit 0 — a release-safety check
that silently no-ops on an unconfigured project reports "consistent" for the
wrong reason, and that reads exactly like a real pass. Per this repo's
governing principle: an audit that reports nothing must never be
indistinguishable from a clean codebase. Configure at least one source, or
don't run this check — never leave it running against nothing.

Two version sources are the practical minimum for "consistency" to mean
anything; one source trivially "agrees with itself", which is why a
single-entry list still exits 0 rather than being rejected — a project
adding its second source later is not blocked by this script in the
meantime.

## Supported extraction kinds

  - `jsonKey`    — dotted key path into a JSON file, e.g. `version` or
                   `packageInfo.version`.
  - `regex`      — first capture group of a regex matched against the file's
                   text. For formats this suite has no parser for
                   (`pubspec.yaml`, a `VERSION` file, a Dart `const`) rather
                   than adding a YAML/TOML dependency for one field.
  - `changelogTop` — the label of the first non-`[Unreleased]` `## [...]`
                   heading in a Keep a Changelog file, reusing the same
                   heading shape `changelog_to_release_notes.py` parses.

Stdlib only, like the rest of `bin/` — no PyYAML, same reasoning gates.py
gives for not requiring a parser dependency to check for missing ones.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from backend_suite.project import need, profile  # noqa: E402

CHANGELOG_HEADING_RE = re.compile(r"^##\s+\[([^\]]+)\](?:\s*-\s*(.+))?\s*$")


class SourceError(RuntimeError):
    """A declared version source could not be read — a hard stop, not a skip."""


def _get_json_key(data, dotted: str, file_label: str):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise SourceError(f"{file_label}: no key {dotted!r} in the JSON document")
        cur = cur[part]
    if not isinstance(cur, str):
        raise SourceError(f"{file_label}: key {dotted!r} is not a string ({cur!r})")
    return cur


def _extract_changelog_top(text: str, file_label: str) -> str:
    for line in text.splitlines():
        m = CHANGELOG_HEADING_RE.match(line.strip())
        if m and m.group(1).strip().lower() != "unreleased":
            return m.group(1).strip()
    raise SourceError(
        f"{file_label}: no released '## [x.y.z]' heading found "
        "(only [Unreleased], or no heading at all)"
    )


def extract_version(repo: Path, source: dict) -> str:
    """Pull the version string out of one declared source, or raise SourceError."""
    if "file" not in source:
        raise SourceError(f"version source {source!r} has no 'file'")
    rel = source["file"]
    path = repo / rel
    if not path.is_file():
        raise SourceError(f"{rel}: file does not exist")

    kind = source.get("kind")
    if not kind:
        raise SourceError(f"{rel}: version source has no 'kind'")

    text = path.read_text(encoding="utf-8")

    if kind == "jsonKey":
        key_path = source.get("keyPath")
        if not key_path:
            raise SourceError(f"{rel}: kind 'jsonKey' needs a 'keyPath'")
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise SourceError(f"{rel}: not valid JSON: {exc}") from exc
        return _get_json_key(data, key_path, rel)

    if kind == "regex":
        pattern = source.get("pattern")
        if not pattern:
            raise SourceError(f"{rel}: kind 'regex' needs a 'pattern'")
        m = re.search(pattern, text, re.MULTILINE)
        if not m:
            raise SourceError(f"{rel}: pattern {pattern!r} did not match")
        if not m.groups():
            raise SourceError(f"{rel}: pattern {pattern!r} has no capture group")
        return m.group(1)

    if kind == "changelogTop":
        return _extract_changelog_top(text, rel)

    raise SourceError(
        f"{rel}: unknown version source kind {kind!r} "
        "(expected 'jsonKey', 'regex', or 'changelogTop')"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-root", metavar="PATH",
                     help="project root to check, overriding auto-detection "
                          "(that root must still contain .backend-suite/profile.json)")
    args = ap.parse_args()

    repo = project_root(args.project_root) if args.project_root else REPO
    data = profile(repo)

    sources = need(
        data, "release.versionSources",
        "lists the files this project considers authoritative for its own "
        "version number and how to read a version out of each — with no "
        "sources configured, there is nothing for this check to compare, "
        "and that must fail loudly rather than exit 0 as if everything "
        "agreed",
        default=None,
    )

    if not sources:
        print(
            "no release.versionSources configured in .backend-suite/profile.json — "
            "this check has nothing to compare and refuses to report a silent "
            "pass. Add at least one source (see check_version_consistency.py's "
            "docstring for the supported 'kind' values), or don't run this "
            "check.",
            file=sys.stderr,
        )
        return 2

    if not isinstance(sources, list):
        print("release.versionSources must be a list", file=sys.stderr)
        return 2

    results: list[tuple[dict, Optional[str], Optional[str]]] = []
    for source in sources:
        try:
            version = extract_version(repo, source)
            results.append((source, version, None))
        except SourceError as exc:
            results.append((source, None, str(exc)))

    errors = [r for r in results if r[2] is not None]
    if errors:
        print("could not read every declared version source:\n", file=sys.stderr)
        for source, _version, err in errors:
            print(f"  ERROR  {source.get('file', '?')}: {err}", file=sys.stderr)
        return 1

    versions = {v for _s, v, _e in results}

    print("version sources:")
    for source, version, _err in results:
        print(f"  {version:<15} {source['file']} ({source.get('kind')})")

    if len(versions) > 1:
        print(
            f"\nFAIL  {len(versions)} distinct versions across "
            f"{len(results)} declared source(s) — these must agree before a "
            "release is cut:",
            file=sys.stderr,
        )
        for source, version, _err in results:
            print(f"    {version!r}  <-  {source['file']}", file=sys.stderr)
        return 1

    print(f"\nok — all {len(results)} version source(s) agree on {versions.pop()!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
