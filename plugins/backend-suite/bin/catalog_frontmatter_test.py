#!/usr/bin/env python3
"""Tests for catalog.frontmatter(), the plugin's hand-rolled YAML-ish parser.

It is worth testing twice over: it backs a CI gate (`catalog.py --check`, which
fails the build when a component is missing its declared fields), and it is
imported as a *library* by `verify.py`, which uses the parsed `name` to decide
which script each component is verified against. So a parse regression does not
error — it changes which component is checked against which script, and reports a
pass for a pairing nobody made.

The distinction that carries the most weight here is `None` versus `{}`. `None`
means "there is no frontmatter block", which callers report as a problem; `{}`
means "a block, containing nothing", which is a different defect. A parser that
collapsed the two would make an unterminated block — the shape a half-finished
edit leaves behind — read as a component that simply declares no fields.

    python3 plugins/backend-suite/bin/catalog_frontmatter_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import catalog  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def parse(tmp: Path, name: str, text: str):
    path = tmp / name
    path.write_text(text)
    return catalog.frontmatter(path)


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        print("check: a valid block yields every declared field")
        meta = parse(tmp, "valid.md", (
            "---\n"
            "name: audit-tokens\n"
            "description: 'Audit, quoted: because the value has a colon in it.'\n"
            "invocation: auto\n"
            "maturity: proven\n"
            "---\n\n"
            "# Body\n"
            "maturity: this line is prose, not frontmatter.\n"
        ))
        expect(meta is not None, "a well-formed block parses")
        expect((meta or {}).get("name") == "audit-tokens", "reads name")
        expect((meta or {}).get("invocation") == "auto", "reads invocation")
        expect((meta or {}).get("maturity") == "proven", "reads maturity")
        # The value contains a colon, so a naive split(":") would truncate it —
        # and a truncated description still looks like a description.
        expect((meta or {}).get("description", "").endswith("in it."),
               "a quoted value keeps everything after its first colon")
        expect(not (meta or {}).get("description", "").startswith("'"),
               "surrounding quotes are stripped, not kept as part of the value")

        print("check: the body is not read as frontmatter")
        # The negative control for the case above: a parser that scanned the
        # whole file would find the same keys and pass every assertion so far.
        expect((meta or {}).get("maturity") == "proven",
               "a `key: value` line in the body does not overwrite the block's value")

        print("check: missing and malformed blocks are told apart")
        expect(parse(tmp, "none.md", "# Just a heading\n\nNo block at all.\n") is None,
               "a file with no leading --- yields None, so the caller can report it")
        expect(parse(tmp, "unterminated.md", "---\nname: x\nmaturity: proven\n") is None,
               "an UNTERMINATED block yields None, not a half-parsed dict — a "
               "half-finished edit must not read as a documented component")
        expect(parse(tmp, "empty.md", "---\n---\n\nBody.\n") == {},
               "an empty-but-terminated block yields {}, which is not None — "
               "'declares nothing' and 'has no block' are different defects")

        print("check: noise inside a block is ignored rather than stored")
        meta = parse(tmp, "noisy.md", (
            "---\n"
            "# a comment\n"
            "\n"
            "name: thing\n"
            "a line with no separator\n"
            "---\n"
        ))
        expect(meta == {"name": "thing"},
               f"comments, blanks and separator-less lines are dropped, got {meta!r}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("catalog.frontmatter: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
