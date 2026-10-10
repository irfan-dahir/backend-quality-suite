#!/usr/bin/env python3
"""Tests for gates.py's hand-rolled workflow parser.

This is the highest value-per-line test in the repo, because of how the parser
fails. It has no dependency and no schema: if a workflow shape stops matching one
of its regexes, the affected step is not reported as unparseable — it simply
stops appearing in the list, and `gates.py` prints "all 8 gate(s) passed" where it
used to print 10. The count is the only signal a reader would ever see, and
nobody checks a count they did not know had changed. CLAUDE.md rule 3 makes this
parser the authority — `attest.py`'s whole verdict is built on the step list it
returns — so a silent parse regression drops gates for everyone at once.

So every case is paired with the negative control that makes it mean something: a
count assertion beside the actual content of a parsed `run:` block (a parser that
returned N empty tuples would pass a count-only test), and a `run: |` block beside
a one-line `run:` scalar (they take different branches).

    python3 plugins/design-suite/bin/gates_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only, no filesystem beyond one
temporary fixture file — the parser is a pure function of text.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import gates  # noqa: E402

FAILURES: list[str] = []

# Every shape the real workflow uses, in one fixture: `uses:` steps with and
# without a `with:` mapping, a multi-line `run: |` block, a one-line `run:`
# scalar, a comment between `name:` and `run:` (the real file has several, and a
# parser that treated a comment as the end of a step would lose the step), and a
# top-level `name:` at indent 0 that must NOT be counted as a step.
FIXTURE = """\
name: validate
on:
  push: { branches: [main] }
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Block step
        # A comment between the name and the run block.
        run: |
          echo one
          echo two
      - name: Scalar step
        run: python3 something.py --check
      - name: Install step
        run: |
          pip install --quiet pyyaml
          echo after
      - name: Absent dependency step
        run: |
          pip install --quiet definitely_not_an_installed_package_9f3a
          echo never reached
      - name: Install only step
        run: |
          pip install --quiet pyyaml
"""


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "validate.yml"
        fixture.write_text(FIXTURE)
        # The parser reads a module-level path. Pointing it at the fixture is the
        # only way to test it without asserting against the real workflow, which
        # would make this test fail every time a gate is legitimately added.
        original = gates.WORKFLOW
        gates.WORKFLOW = fixture
        try:
            parsed = gates.steps()
        finally:
            gates.WORKFLOW = original

    by_name = dict(parsed)
    print("check: every step in the fixture is found, and nothing extra is")

    # 7 = two `uses:` steps + five named `run:` steps. The workflow's own
    # top-level `name: validate` is not one of them; counting it was a real bug
    # this parser already carries a comment about.
    expect(len(parsed) == 7, f"7 steps parsed, not {len(parsed)}")
    expect("validate" not in by_name,
           "the workflow's own top-level name: is not reported as a step")
    expect(by_name.get("actions/checkout") is None,
           "a uses: step is listed with no run command")
    expect("actions/setup-python" in by_name,
           "a uses: step carrying a with: mapping is still found")

    print("check: run blocks keep their contents, not just their names")

    # The count alone proves nothing: a parser returning five empty entries would
    # satisfy every assertion above. This is what makes the count meaningful.
    block = by_name.get("Block step")
    expect(block is not None, "a `run: |` block step is found")
    expect(block == "echo one\necho two",
           f"the block's lines are captured verbatim and dedented, got {block!r}")

    scalar = by_name.get("Scalar step")
    expect(scalar == "python3 something.py --check",
           f"a one-line `run:` scalar is captured, got {scalar!r}")

    print("check: an install preamble is stripped, not used as a veto")

    # The defect this replaced: `SKIP_RUN = ("pip install",)` vetoed any step whose
    # text merely contained that substring, without ever asking whether the package
    # was already there. The frontmatter gate — the one about components being
    # silently dropped — was itself dropped on every local run, for its whole life.
    install = by_name.get("Install step")
    expect(install is not None and "pip install" in install,
           "an install step's text is captured — a step whose run block went "
           "missing would be silently 'not an install step'")
    exe, why = gates.executable_form(install or "")
    expect(exe == "echo after" and why is None,
           f"pyyaml is importable here, so the step runs with the install line "
           f"stripped; got {exe!r} / {why!r}")

    print("check: a dependency that really is absent is skipped, with a reason")

    exe, why = gates.executable_form(by_name["Absent dependency step"])
    expect(exe is None, "a step needing an uninstalled package does not run")
    expect(why is not None and "definitely_not_an_installed_package_9f3a" in (why or ""),
           f"the skip names the missing package rather than a bare 'skipped'; "
           f"got {why!r}")

    exe, why = gates.executable_form(by_name["Install only step"])
    expect(exe is None and "nothing left to run" in (why or ""),
           f"a step that is only an install has nothing to run and says so, "
           f"rather than running an empty command and reporting ok; got {why!r}")

    print("check: package names map to the module they actually provide")

    expect(gates._packages("--quiet pyyaml") == ["yaml"],
           "pyyaml resolves to `yaml`, and the --quiet flag is not a package")
    expect(gates._packages("requests>=2.0 python-dateutil") == ["requests", "dateutil"],
           "version specifiers are stripped and known aliases are mapped")

    print("check: a plain step is handed through untouched")

    exe, why = gates.executable_form("python3 something.py --check")
    expect(exe == "python3 something.py --check" and why is None,
           "a step with no install line is unchanged")

    print("check: the real workflow's frontmatter gate is not skipped here")

    # The regression guard for the actual bug. This gate needs no third-party
    # package any more, so on any machine with a stdlib Python it must be
    # runnable. If it ever goes back to being skipped, that is the defect
    # returning and this fails rather than a count quietly dropping by one.
    real = dict(gates.steps())
    gate = next((c for n, c in real.items()
                 if c and "parseable frontmatter" in n), None)
    expect(gate is not None, "the frontmatter gate is present in the real workflow")
    if gate:
        exe, why = gates.executable_form(gate)
        expect(exe is not None,
               f"the frontmatter gate can actually run here; got skip reason {why!r}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("gates.py: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
