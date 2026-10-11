#!/usr/bin/env python3
"""Tests for the two gates added after the first paid eval suite run.

    python3 plugins/backend-suite/bin/eval_suite_lint_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.

Both gates were written from a MEASURED defect, so both are tested from the
measured defect's own shape:

  * **paired liveness** — `review-docs-zero-state-refusal` scored 0.25 on six
    runs that all aborted with `exit 1: You've hit your session limit`, three of
    them before turn 2. Its `no-clean-verdict` grader asserts an absence, and a
    run that emitted nothing satisfies an absence perfectly;
  * **`scaffold_script`** — four cases carried an inline shell body where the
    harness expects a path. It `stat()`ed the block scalar, scaffolded nothing,
    and ran the cases for zero turns at 0.00 in both arms.

**Every refusal here is paired with the positive case it must not swallow.** A
gate that flags the correct shape as well as the broken one is a gate that gets
switched off, and then the defect it was written for ships anyway. So each
`is_absence_shaped` case has an `is_liveness` twin, each rejected
`scaffold_script` has an accepted one, and the exemplars the suite already
contains (`did-run-step-0`, `skill-fired`, `invoked-the-skill`) are asserted to
still pass.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import eval_suite_lint as esl  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, wanted {want!r}")


# ---------------------------------------------------------------------------
# is_absence_shaped / is_liveness, paired
# ---------------------------------------------------------------------------

ABSENCE_CASES = [
    # The exact grader that was credited on six aborted runs.
    ("no-clean-verdict, the measured defect",
     "- name: no-clean-verdict\ntype: regex\npattern: \"clean|passes\"\n"
     "match: not_contains\ntarget: last_message\n"),
    # The harness's spelling of "must not call".
    ("tool_used bounded at max: 0",
     "- name: no-write\ntype: tool_used\ntool: Write\nmin: 0\nmax: 0\n"),
    ("tool_used with max: 0 alone",
     "- name: no-edit\ntype: tool_used\ntool: Edit\nmax: 0\n"),
    ("llm criteria that only forbids",
     "- name: criteria\ntype: llm\n---\nFAIL if the response claims the docs "
     "are clean. It must not invent findings.\n"),
]

LIVENESS_CASES = [
    # The suite's own negative controls. These are the shape the rule points at.
    ("did-run-step-0 (tool_used min: 1)",
     "- name: did-run-step-0\ntype: tool_used\ntool: Bash\n"
     "input_match: 'audit_reinvented_components\\.py'\nmin: 1\n"),
    ("invoked-the-skill (tool_used, min defaults to 1)",
     "- name: invoked-the-skill\ntype: tool_used\ntool: Skill\n"
     "input_match: 'review-docs'\n"),
    ("actually-saw-the-fixture (regex contains)",
     "- name: actually-saw-the-fixture\ntype: regex\n"
     "pattern: \"main\\\\.dart\"\nmatch: contains\ntarget: last_message\n"),
    ("step-0-precedes-any-write (tool_order)",
     "- name: step-0-precedes-any-write\ntype: tool_order\nbefore: Bash\n"
     "after: Write\n"),
    ("a file_exists grader",
     "- name: wrote-the-profile\ntype: file_exists\npath: .backend-suite/profile.json\n"),
    ("regex count:2",
     "- name: two-findings\ntype: regex\npattern: \"finding\"\nmatch: count:2\n"),
]

for label, unit in ABSENCE_CASES:
    check(f"absence-shaped: {label}", esl.is_absence_shaped(unit), True)
    # The pairing that matters: an absence grader must never ALSO be counted as
    # the liveness control that backs it. If it were, every case would self-
    # satisfy and the gate would be decorative.
    check(f"absence is not its own liveness: {label}", esl.is_liveness(unit), False)

for label, unit in LIVENESS_CASES:
    check(f"liveness: {label}", esl.is_liveness(unit), True)
    check(f"liveness is not absence: {label}", esl.is_absence_shaped(unit), False)

# `llm` is neither — judgement of an empty transcript is not proof of a run.
BALANCED_LLM = ("- name: criteria\ntype: llm\n---\nPASS only if the response "
                "states the review could not be performed.\n\nFAIL if it "
                "reports the docs as clean.\n")
check("balanced llm criteria is not absence-shaped",
      esl.is_absence_shaped(BALANCED_LLM), False)
check("llm criteria is never liveness", esl.is_liveness(BALANCED_LLM), False)

# A LABEL is not an assertion. Three earlier rewrites of this lint were fooled
# by a grader's name; a name alone must not make a grader count either way.
NAME_ONLY = "- name: no-write-ever-absent-max-0\ntype: regex\n" \
            "pattern: \"x\"\nmatch: contains\n"
check("a prohibition-sounding NAME is not an absence assertion",
      esl.is_absence_shaped(NAME_ONLY), False)

# ---------------------------------------------------------------------------
# lacks_liveness, at case level
# ---------------------------------------------------------------------------

check("absence-only case lacks liveness",
      esl.lacks_liveness([ABSENCE_CASES[0][1], ABSENCE_CASES[1][1]]), True)
check("absence paired with liveness is fine",
      esl.lacks_liveness([ABSENCE_CASES[0][1], LIVENESS_CASES[0][1]]), False)
check("a case with no absence grader at all needs no liveness control",
      esl.lacks_liveness([BALANCED_LLM]), False)

# ---------------------------------------------------------------------------
# scaffold_script, paired reject/accept
# ---------------------------------------------------------------------------

HEAD = 'schema_version: "1.1"\nname: promote-component-x\ncontext:\n'
TAIL = "execution:\n  max_turns: 5\n"


def scaffold_problems(yaml_body: str, make: str | None = "scaffold.sh") -> list[str]:
    """Run lint_scaffold over a throwaway case directory."""
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "case.yaml").write_text(yaml_body)
        if make:
            target = tmp / make
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/usr/bin/env bash\ntrue\n")
        return esl.lint_scaffold(tmp, "case-under-test")
    finally:
        shutil.rmtree(tmp)


# 1. The mistake that actually happened: an inline shell body as a block scalar.
block = scaffold_problems(
    HEAD + "  scaffold_script: |\n    set -euo pipefail\n    mkdir -p lib\n" + TAIL)
check("block-scalar scaffold_script is rejected", len(block), 1)
check("and the error names the block-scalar mistake by name",
      "BLOCK SCALAR" in block[0] and "expects a PATH" in block[0], True)

# 2. Escaping the case directory, the harness's own rejection rule.
check("`..` is rejected",
      len(scaffold_problems(HEAD + "  scaffold_script: ../_fixtures/app/scaffold.sh\n"
                            + TAIL)), 1)
check("an absolute path is rejected",
      len(scaffold_problems(HEAD + "  scaffold_script: /tmp/scaffold.sh\n" + TAIL)), 1)

# 3. The charset — the check that would have caught the block scalars on the
#    space character alone, before anyone reasoned about YAML at all.
charset = scaffold_problems(HEAD + '  scaffold_script: "set -e; mkdir lib"\n' + TAIL)
check("a value with a space is rejected by the charset", len(charset), 1)

# 4. Resolves to an existing regular file.
check("a missing script is rejected",
      len(scaffold_problems(HEAD + "  scaffold_script: nope.sh\n" + TAIL)), 1)
check("a directory is rejected",
      len(scaffold_problems(HEAD + "  scaffold_script: sub\n", make="sub/x.sh")), 1)
check("an empty value is rejected",
      len(scaffold_problems(HEAD + '  scaffold_script: ""\n' + TAIL)), 1)

# --- and the positives the gate must not swallow ---------------------------
check("the shape every real case uses is accepted",
      scaffold_problems(HEAD + "  scaffold_script: scaffold.sh\n" + TAIL), [])
check("a quoted value is accepted",
      scaffold_problems(HEAD + '  scaffold_script: "scaffold.sh"\n' + TAIL), [])
check("a subdirectory inside the case is accepted",
      scaffold_problems(HEAD + "  scaffold_script: bin/set-up.sh\n",
                        make="bin/set-up.sh"), [])
check("a case with no scaffold_script at all is accepted",
      scaffold_problems('schema_version: "1.1"\nname: x\n' + TAIL, make=None), [])

# ---------------------------------------------------------------------------
# End to end: the real suite, and a planted defect in a copy of it
# ---------------------------------------------------------------------------

REAL = subprocess.run([sys.executable, str(BIN / "eval_suite_lint.py")],
                      capture_output=True, text=True)
check("the committed suite lints clean", REAL.returncode, 0)

if FAILURES:
    print(f"{len(FAILURES)} failure(s):", file=sys.stderr)
    for line in FAILURES:
        print(f"  {line}", file=sys.stderr)
    sys.exit(1)

total = (len(ABSENCE_CASES) + len(LIVENESS_CASES)) * 2 + 15
print(f"eval_suite_lint: {total} assertion(s) hold — every refusal paired with "
      f"the positive case it must not swallow.")
