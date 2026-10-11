#!/usr/bin/env python3
"""Extract one version's section from a Keep-a-Changelog-style CHANGELOG.

    python3 changelog_to_release_notes.py CHANGELOG.md            # top released section
    python3 changelog_to_release_notes.py CHANGELOG.md --version 1.2.0
    python3 changelog_to_release_notes.py CHANGELOG.md --unreleased

Prints the section body (everything under the matched `## [...]` heading, up
to the next `## ` heading) as plain text on stdout, so it can be piped
straight into `gh release create --notes-file -`. Zero project-specific
logic: this only parses the Keep a Changelog heading shape
(`## [X.Y.Z] - YYYY-MM-DD` or `## [Unreleased]`) and does not know anything
about any particular project.

Exit codes: 0 = section found and printed. 2 = file missing, no heading
matched, or the matched section is empty — never prints an empty string on
success, per the "an audit that reports nothing must never look clean"
principle this repo applies to every other script.
"""
import argparse
import re
import sys
from typing import Optional

HEADING_RE = re.compile(r"^##\s+\[([^\]]+)\](?:\s*-\s*(.+))?\s*$")


def find_section(text: str, version: Optional[str]):
    lines = text.splitlines()
    headings = []  # (line_index, label)
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line.strip())
        if m:
            headings.append((i, m.group(1).strip()))

    if not headings:
        return None, None

    if version is None:
        # First heading that isn't "Unreleased" — the top released section.
        target = next((h for h in headings if h[1].lower() != "unreleased"), None)
    elif version.lower() == "unreleased":
        target = next((h for h in headings if h[1].lower() == "unreleased"), None)
    else:
        target = next((h for h in headings if h[1] == version), None)

    if target is None:
        return None, None

    start_idx = headings.index(target)
    start_line = target[0] + 1
    end_line = headings[start_idx + 1][0] if start_idx + 1 < len(headings) else len(lines)
    body = "\n".join(lines[start_line:end_line]).strip("\n")
    return target[1], body


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("changelog", help="Path to the CHANGELOG file")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--version", help="Exact heading label to extract, e.g. 1.2.0")
    group.add_argument("--unreleased", action="store_true", help="Extract the [Unreleased] section")
    args = parser.parse_args()

    try:
        with open(args.changelog, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"error: could not read {args.changelog}: {e}", file=sys.stderr)
        return 2

    version = "unreleased" if args.unreleased else args.version
    label, body = find_section(text, version)

    if label is None:
        target_desc = version or "the top released section"
        print(f"error: no matching '## [...]' heading found for {target_desc!r} in {args.changelog}", file=sys.stderr)
        return 2

    if not body.strip():
        print(f"error: section '{label}' in {args.changelog} is empty — nothing to release", file=sys.stderr)
        return 2

    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
