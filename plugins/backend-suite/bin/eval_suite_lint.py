#!/usr/bin/env python3
"""Refuse an eval case for a *writing* skill that could pass by omission.

    python3 plugins/backend-suite/bin/eval_suite_lint.py
    python3 plugins/backend-suite/bin/eval_suite_lint.py --list

Exit 0 when every case carries its mandatory guards, 1 when one does not,
2 when the eval directory itself is malformed. Stdlib only — no PyYAML, same
rule as every other script here.

## Why

An eval case is a grader list. Graders are additive: a case with one grader
saying "the report mentions the declined role" scores 1.0 on a run where the
skill also silently rewrote a human's ratified provenance field to `inferred`,
because nothing asked. The case is green, the suite is green, and the single
worst thing the skill can do is unmeasured.

**A suite that can pass by omission is the exact failure this repo exists to
prevent.** So for any case whose skill WRITES, four guards are mandatory:

  1. a `not_contains` guard against `approved` — the provenance state a skill
     may never author. `init.py` is already built so it cannot (its
     SEEDED_STATE assertion); a model has no such constraint, and the only way
     to know it did not is to assert it did not;
  2. a **negative** `tool_used` assertion (`min: 0, max: 0`) — the tool the
     skill must never reach for. A suite made only of positive assertions can
     never catch a skill doing something extra, and "extra" is where the
     damage is;
  3. at least one **result** grader — did it produce the right answer;
  4. at least one **process** grader — did it get there the right way. A
     result-only case passes on a right answer reached by a forbidden route,
     which is precisely the run you most want to fail.

## Which skills count as "writing"

Not a list maintained here — that would be a second copy to drift. It is read
off each component's own `invocation` frontmatter, which CLAUDE.md already
defines by blast radius: *read-only and report-only run automatically
(`auto`), content-generating and convention-setting stay explicit
(`explicit`)*. `explicit` IS the writing tier, it is already gated by
`catalog.py --check`, and reusing it means a skill that changes tier changes
what its case must prove on the same day.

A case is matched to its skill by directory name: the longest component name
that is a prefix of the case directory's name. `map-project-undeclared-kind`
is a `map-project` case. A case matching no component is a failure, not a
skip — an unattributable case is one nobody can tell is guarded.

## What is the harness's, and what is ours

From the harness (Claude Code 2.1.273), and asserted against here:

  * a case is `<eval dir>/<case>/prompt.md` (frontmatter `name`, `tags`,
    `runs`, `max_turns`, `timeout_seconds`, `allowed_tools`, `model`, `env` —
    `env` keys must be `EVAL_*`) plus `graders/<name>.md`; an optional
    `case.yaml` (`schema_version: "1.1"`, `name`) carries what prompt.md
    cannot, including `context.scaffold_script`;
  * the six grader `type` values are `regex`, `tool_used`, `tool_order`,
    `file_exists`, `llm`, `baseline`;
  * `tool_used` takes `tool`, `input_match`, `min` (default 1) and `max`, and
    **"must not call" is spelled `min: 0, max: 0`** — which is exactly the
    negative assertion this gate requires, not an invention of ours;
  * `not_contains` is a value of `regex`'s `match:` key, NOT a grader type.

Ours, and marked as ours:

  * **the result/process split is inferred from the `type`**, because the
    harness defines no such key. Inventing a frontmatter key it does not know
    risks it being rejected, so nothing new is written into a case;
  * **the four mandatory guards** themselves, and the rule that they apply to
    `invocation: explicit` components;
  * **matching is textual and lenient** — keys are found by line, not by a
    YAML parse (stdlib only, no PyYAML), so a guard counts whether it lives in
    `case.yaml`'s inline list or in a grader file of its own. The cost is that
    this lints for *presence*, never truthfulness — the same contract as
    `check_pr_verification_trailer.py`.

## Paired liveness (measured, not theorised)

The first real suite run (20 cases, $30.59) scored
`review-docs-zero-state-refusal` at 0.25 on six runs that ALL aborted with
`exit 1: You've hit your session limit` — three of them before turn 2, with the
Skill never called. Its `no-clean-verdict` grader asserts the ABSENCE of a
pattern, and a run that emitted nothing satisfies "pattern absent" perfectly.
A run that proved nothing was credited as a partial pass.

That is the governing principle (docs/CONCEPTS.md, "the finding that shapes
everything") failing inside the harness this project uses to verify everything
else: silence indistinguishable from a clean result.

So: **a case carrying any absence-shaped grader must also carry at least one
positive liveness grader** — a lower-bound assertion an empty run cannot
satisfy. Several cases already do this by hand and say so in their own prose
(`did-run-step-0`, `skill-fired`, `provenance-was-written`, each labelled
NEGATIVE CONTROL); the pattern existed, it just was not enforced.

`llm` graders count as neither. A model's judgement of an empty transcript is
not a mechanical proof that the run happened, and a criteria file that is all
prohibition is not a liveness control either.

Existing unbacked cases are ratcheted, not grandfathered silently: they are
listed in `LIVENESS_BASELINE` below, printed on every run, and a new one fails
the gate. A case that gains a liveness grader must leave the baseline — the
list is asserted to be exact, so it cannot rot into a permanent excuse.

## scaffold_script validation

Same run, second defect: four `promote-component` cases carried an inline shell
body where the harness expects a PATH. The harness `stat()`ed the YAML block
scalar, found nothing, and the cases ran zero turns and scored 0.00 in both arms
— $30 of suite time measuring nothing. `eval_fixture_selftest.py` did not catch
it because it walks fixture->scaffold, never case->scaffold.

Four filesystem-only checks, no eval run needed: no newline (the block-scalar
mistake, named explicitly), not absolute and no `..` segment (the harness's own
rejection rule, documented in `evals/_fixtures/app/scaffold.sh`'s header), the
harness's path charset, and resolves to an existing regular file inside the
case directory.

There is no public docs page for the eval format yet. If the schema moves, the
fix is here, in one file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
PLUGIN_ROOT = BIN.parent
PLUGINS = BIN.parents[1]

# Directories under the eval dir that are not cases. `_fixtures` holds the
# scaffold scripts, `results` is output, `mocks` is MCP stand-ins (named in
# `--mocks`'s own help as `<eval dir>/mocks/`).
NOT_CASES = {"_fixtures", "results", "mocks"}

# The provenance state no skill may ever author. Named once; the guard a case
# must carry is a `not_contains` naming this.
FORBIDDEN_STATE = "approved"

# Grader `type` values, split by what they judge.
#
# The SIX type values are the harness's, not ours: `regex`, `tool_used`,
# `tool_order`, `file_exists`, `llm`, `baseline`. Note that `not_contains` is
# NOT among them — it is a value of `regex`'s `match:` key
# (`match: contains|not_contains|count:N`), which is why the guard below
# searches for the token rather than for a grader of that type.
#
# The result/process SPLIT is ours, inferred from the type: a grader reading
# the produced artefact judges the result, a grader reading the tool trace
# judges the route taken. See the module docstring.
RESULT_TYPES = {"regex", "file_exists", "llm", "baseline"}
PROCESS_TYPES = {"tool_used", "tool_order"}
GRADER_TYPES = RESULT_TYPES | PROCESS_TYPES

# The harness's own charset for `context.scaffold_script`. Note it has no space
# in it — which alone would have rejected the four block scalars that cost the
# first suite run $30 of zero-turn cases.
SCAFFOLD_CHARSET = re.compile(r"^[A-Za-z0-9_./:\\-]+$")

# Cases that carry an absence-shaped grader and no positive liveness control
# TODAY. A ratchet, not an exemption: new offenders fail, these stay visible and
# are printed on every run. Asserted EXACT — a case that gains a liveness grader
# and stays listed fails too, so the list cannot rot into a standing excuse.
#
# Populated by measurement, not by hand:
#   python3 plugins/backend-suite/bin/eval_suite_lint.py --liveness-report
LIVENESS_BASELINE: set[str] = set()


def eval_dir() -> Path:
    """The eval directory, from the manifest's `experimental.evals` or `evals/`.

    Read rather than hardcoded because `--eval-dir`'s own help says the default
    is "the manifest's experimental.evals value, else evals/" — so a manifest
    that sets it and a gate that assumes `evals/` would disagree silently, and
    the gate would lint an empty directory and report success.
    """
    manifest = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    name = "evals"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text())
            name = (data.get("experimental") or {}).get("evals") or "evals"
        except ValueError:
            pass
    return PLUGIN_ROOT / name


def writing_components() -> set[str]:
    """Component names whose `invocation` frontmatter is `explicit`."""
    names: set[str] = set()
    for md in sorted(PLUGINS.rglob("commands/*.md")) + sorted(PLUGINS.rglob("agents/*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        head = text[:text.find("\n---", 3) if "\n---" in text[3:] else 400]
        if re.search(r"^invocation:\s*explicit\s*$", head, re.M):
            name = re.search(r"^name:\s*(\S+)", head, re.M)
            names.add(name.group(1).strip("\"'") if name else md.stem)
    return names


def all_components() -> set[str]:
    names: set[str] = set()
    for md in sorted(PLUGINS.rglob("commands/*.md")) + sorted(PLUGINS.rglob("agents/*.md")):
        names.add(md.stem)
    return names


def find_cases(root: Path) -> list[Path]:
    """Every directory holding a `case.yaml` or a `prompt.md`."""
    if not root.is_dir():
        return []
    cases = set()
    for marker in ("case.yaml", "case.yml", "prompt.md"):
        for path in root.rglob(marker):
            if any(part in NOT_CASES for part in path.relative_to(root).parts):
                continue
            cases.add(path.parent)
    return sorted(cases)


def case_text(case: Path) -> str:
    """Every byte a case is defined by: its case/prompt file and its graders.

    Concatenated on purpose. A guard is equally valid in `case.yaml`'s inline
    grader list or in a `graders/*.md` of its own, and a lint that only
    understood one shape would fail the suite for choosing the other.
    """
    parts = []
    for name in ("case.yaml", "case.yml", "prompt.md"):
        path = case / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    for grader in sorted((case / "graders").glob("*.md")):
        parts.append(grader.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def declared_types(text: str) -> set[str]:
    """Every grader `type:` value the case declares."""
    return {m.group(1) for m in re.finditer(r"^\s*-?\s*type:\s*[\"']?([a-z_]+)",
                                            text, re.M)}


def grader_units(case: Path) -> list[str]:
    """Each grader's own text, whichever of the two shapes it is written in.

    A grader is either an entry in `case.yaml`'s inline list (delimited by
    `- name:`) or a whole `graders/*.md` file with its own frontmatter. The
    first version of this split concatenated everything and looked for
    `- name:` boundaries, which the standalone-file shape does not have — so
    every `graders/*.md` assertion was invisible and four correctly-guarded
    cases were reported as unguarded. `case_text` deliberately supports both
    shapes; the unit-splitting has to as well.
    """
    units: list[str] = []
    for name in ("case.yaml", "case.yml"):
        path = case / name
        if not path.is_file():
            continue
        current: list[str] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lstrip().startswith("- name:"):
                if current:
                    units.append("\n".join(current))
                current = [line]
            elif current:
                current.append(line)
        if current:
            units.append("\n".join(current))
    for grader in sorted((case / "graders").glob("*.md")):
        # A standalone grader file carries no `name:` key — its filename IS its
        # name. Synthesised here so an error can say WHICH grader is unbacked.
        # `_assertion_operands` never reads a `name:` line, so this cannot be
        # mistaken for an assertion.
        units.append(f"- name: {grader.stem}\n"
                     + grader.read_text(encoding="utf-8", errors="replace"))
    return units


def _uncommented(block: str) -> str:
    """The block with `#` comment lines dropped — a comment naming the state is
    documentation, not an assertion, and must not satisfy the rule."""
    return "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("#"))


def _assertion_operands(unit: str) -> str:
    """Only the lines that carry what a grader ASSERTS — not its name, not its
    prose, not its comments.

    Three rewrites of this lint failed by matching the wrong text: a comment
    explaining a guard, and then a grader NAMED `no-approved-or-declared-state`,
    each satisfied a rule whose actual assertion had been deleted. A label is
    not an assertion. Only `pattern:`, `tool:`, `min:`, `max:` and `match:`
    decide what a grader checks, so only those lines are read here.
    """
    keep = []
    for line in unit.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.match(r"(pattern|tool|min|max|match|type)\s*:", stripped):
            keep.append(stripped)
    return "\n".join(keep)


def has_forbidden_state_guard(units: list[str]) -> bool:
    """A `not_contains` grader whose own PATTERN names the forbidden state."""
    for unit in units:
        ops = _assertion_operands(unit)
        if not re.search(r"match:\s*not_contains", ops):
            continue
        for line in ops.splitlines():
            if line.startswith("pattern:") and re.search(rf"\b{FORBIDDEN_STATE}\b", line):
                return True
    return False


def has_negative_tool_assertion(units: list[str]) -> bool:
    """A grader asserting something does NOT happen, in the same grader.

    `max: 0` alone IS the assertion — the load-bearing half; `min: 0` is
    redundant since every count is already at least zero. The rule exists to
    catch `min: 0` written ALONE, the shape of an inverted bound.

    A `not_contains` regex counts too, but only when it is that grader's own
    assertion — an earlier version accepted a `not_contains` anywhere in the
    case, so neutering a `max: 0` in one grader was excused by an unrelated
    content check in another.
    """
    for unit in units:
        ops = _assertion_operands(unit)
        if "tool_used" in ops and re.search(r"^max:\s*0$", ops, re.M):
            return True
        if re.search(r"match:\s*not_contains", ops) and \
           any(l.startswith("pattern:") for l in ops.splitlines()):
            return True
    return False


def unit_type(unit: str) -> str:
    """The grader `type` this unit declares, or "" if it declares none."""
    m = re.search(r"^type:\s*[\"']?([a-z_]+)", _assertion_operands(unit), re.M)
    return m.group(1) if m else ""


def _is_prohibition_only_llm(unit: str) -> bool:
    """An `llm` grader phrased purely as a prohibition.

    A criteria file that says only what must NOT appear is satisfied by a
    transcript containing nothing at all — the same hole as `not_contains`, one
    layer up in natural language. A criteria file that ALSO states what must
    hold ("PASS only if…") is not absence-shaped: an empty transcript fails it.
    """
    body = _uncommented(unit)
    forbids = re.search(r"\bFAIL\b|must not|never|does not|no\s+\w+\s+verdict",
                        body, re.I)
    requires = re.search(r"PASS (?:only )?if|must (?:state|say|report|name|"
                         r"identify|include|contain)\b", body, re.I)
    return bool(forbids) and not bool(requires)


def is_absence_shaped(unit: str) -> bool:
    """Whether this grader asserts that something did NOT happen.

    Three shapes, all of which an empty run satisfies for free:
      * `match: not_contains` — the pattern is absent because nothing was said;
      * a `tool_used` bounded at `max: 0` — the tool was not called because no
        tool was called;
      * an `llm` criteria file phrased only as a prohibition.
    """
    ops = _assertion_operands(unit)
    if re.search(r"match:\s*not_contains", ops):
        return True
    if unit_type(unit) == "tool_used" and re.search(r"^max:\s*0$", ops, re.M):
        return True
    if unit_type(unit) == "llm" and _is_prohibition_only_llm(unit):
        return True
    return False


def is_liveness(unit: str) -> bool:
    """Whether this grader is a LOWER bound an empty run cannot satisfy.

    The paired half of `is_absence_shaped`. Deliberately mechanical: a grader
    counts only if something must have actually happened for it to hold.

      * `tool_used` with `min >= 1` — and `min` DEFAULTS to 1 in the harness, so
        a bare `tool_used` counts, while one bounded at `max: 0` never does;
      * `tool_order` — both named tools must have run for an order to exist;
      * `file_exists` — a file had to be produced;
      * `regex` with `match: contains` (or `count:N`, N >= 1) — something had to
        be emitted for a pattern to be found in it.

    `llm` counts as neither absence nor liveness: a model's opinion of an empty
    transcript is judgement, not proof that the run happened. `baseline` is a
    comparison, not an assertion of its own.
    """
    kind = unit_type(unit)
    ops = _assertion_operands(unit)
    if kind == "tool_used":
        if re.search(r"^max:\s*0$", ops, re.M):
            return False
        m = re.search(r"^min:\s*(\d+)$", ops, re.M)
        return int(m.group(1)) >= 1 if m else True  # min defaults to 1
    if kind == "tool_order":
        return True
    if kind == "file_exists":
        return True
    if kind == "regex":
        if re.search(r"match:\s*contains", ops):
            return True
        m = re.search(r"match:\s*[\"']?count:\s*(\d+)", ops)
        return bool(m) and int(m.group(1)) >= 1
    return False


def unit_name(unit: str) -> str:
    """A grader's own name, for naming it in an error. Label only, never read
    as an assertion — `_assertion_operands` exists because three rewrites of
    this lint were fooled by a label."""
    m = re.search(r"^\s*-?\s*name:\s*(.+)$", unit, re.M)
    if m:
        return m.group(1).strip().strip("\"'")
    return "<unnamed>"


def lacks_liveness(units: list[str]) -> bool:
    """A case that asserts an absence and never asserts that anything happened."""
    return any(is_absence_shaped(u) for u in units) and \
        not any(is_liveness(u) for u in units)


def scaffold_script_value(case: Path) -> tuple[str, bool] | None:
    """`context.scaffold_script`'s raw value, and whether it is a block scalar.

    Hand-parsed, like everything else here — stdlib only, no PyYAML. A block
    scalar (`scaffold_script: |`) is returned WITH its body, newlines and all,
    because the newline is the evidence: it is exactly what the harness
    `stat()`ed and exactly what this check exists to name.
    """
    for name in ("case.yaml", "case.yml"):
        path = case / name
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"^(\s*)scaffold_script:\s*(.*?)\s*$", line)
            if not m:
                continue
            indent, value = len(m.group(1)), m.group(2)
            if value.startswith("|") or value.startswith(">"):
                body = []
                for nxt in lines[i + 1:]:
                    if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= indent:
                        break
                    body.append(nxt.strip())
                return "\n".join(body).strip(), True
            return value.strip().strip("\"'"), False
    return None


def lint_scaffold(case: Path, name: str) -> list[str]:
    """Four filesystem-only checks on `context.scaffold_script`. See module doc."""
    found = scaffold_script_value(case)
    if found is None:
        return []  # a case may legitimately scaffold nothing
    value, block = found
    if block or "\n" in value:
        return [f"{name}: `context.scaffold_script` is a YAML BLOCK SCALAR "
                f"(`scaffold_script: |`), i.e. an inline shell body. The harness "
                f"expects a PATH and will stat() the script text itself, find no "
                f"such file, and run the case for zero turns at a score of 0.00 "
                f"without reporting an error. Put the body in a file beside "
                f"`case.yaml` and name it here, e.g. `scaffold_script: scaffold.sh`."]
    if not value:
        return [f"{name}: `context.scaffold_script` is empty. Name a script, or "
                f"drop the key — an empty path silently scaffolds nothing."]
    if value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value):
        return [f"{name}: `context.scaffold_script` {value!r} is absolute. The "
                f"harness rejects an absolute path outright; it must be relative "
                f"to the case directory."]
    if ".." in Path(value).parts:
        return [f"{name}: `context.scaffold_script` {value!r} contains a `..` "
                f"segment. The harness rejects any path escaping the case "
                f"directory — put a shim inside the case that execs outward, the "
                f"way `evals/_fixtures/app/scaffold.sh`'s header describes."]
    if not SCAFFOLD_CHARSET.match(value):
        return [f"{name}: `context.scaffold_script` {value!r} has characters "
                f"outside the harness's path charset "
                f"{SCAFFOLD_CHARSET.pattern}."]
    target = case / value
    if not target.exists():
        return [f"{name}: `context.scaffold_script` {value!r} does not exist. "
                f"The harness scaffolds nothing and the case measures the empty "
                f"workspace it was not written for."]
    if not target.is_file():
        return [f"{name}: `context.scaffold_script` {value!r} is not a regular "
                f"file."]
    return []


def lint_empty_ranges(units: list[str], name: str) -> list[str]:
    """A `tool_used` grader whose min/max range is empty can never pass.

    The harness defaults `min` to 1 when it is unset, so `max: 0` alone asserts
    the range 1..0 -- unsatisfiable, whatever the model does. It fails both arms
    of every run and reports `Bash called 0x (expected 1..0)`, which reads as the
    model having done the forbidden thing rather than as an assertion that was
    never evaluated.

    Measured 2026-09-18: eight graders across five bootstrap cases were in this
    state, four of them the weight-5 headline assertion of their own case. The
    whole of `bootstrap-design-docs-anti-loop-guard` -- four graders, 17 of its
    points, the entire reason the case exists -- had never once been evaluated.
    It does not move a delta, because it fails both arms equally, so nothing in
    a results summary distinguishes it from a case the plugin simply failed.

    The proof was a contrast, not a reading of the harness: every grader that
    set `min: 0` explicitly passed at zero calls, and every grader that omitted
    it failed. `min: 0, max: 0` is the correct spelling of "never called".
    """
    problems = []
    for unit in units:
        if unit_type(unit) != "tool_used":
            continue
        mx = re.search(r"^\s*max:\s*(\d+)", _uncommented(unit), re.M)
        if not mx:
            continue
        mn = re.search(r"^\s*min:\s*(\d+)", _uncommented(unit), re.M)
        low = int(mn.group(1)) if mn else 1   # the harness's own default
        high = int(mx.group(1))
        if low > high:
            spelled = f"min: {low}" if mn else "min unset, so the harness reads 1"
            problems.append(
                f"{name}: grader {unit_name(unit)!r} asserts the empty range "
                f"{low}..{high} ({spelled}, max: {high}) and can never pass. "
                f"An absence assertion is spelled `min: 0` WITH `max: 0`; "
                f"`max: 0` alone is a check that reports a verdict it never "
                f"measured. If the intent is 'at most one', write `min: 0` "
                f"with `max: 1`.")
    return problems


def writes_provenance(component: str) -> bool:
    """Whether this component's own markdown says it writes provenance.

    Derived, not listed: a hardcoded set here would be a second registry of
    which skills touch provenance, and this repo has been bitten three times
    by exactly that shape (docs/CATALOG.md's header says why).
    """
    for md in sorted(PLUGINS.rglob("commands/*.md")) + sorted(PLUGINS.rglob("agents/*.md")):
        if md.stem != component:
            continue
        return "provenance" in md.read_text(encoding="utf-8", errors="replace").lower()
    return False


def lint(case: Path, root: Path, writing: set[str], known: set[str]) -> list[str]:
    name = case.relative_to(root).as_posix()
    text = case_text(case)
    units = grader_units(case)

    # Longest component name that prefixes the case directory's own name. A
    # case for `map-project` may be `map-project-undeclared-kind`; longest-wins
    # keeps `audit-tokens-exceptions` from being read as `audit-tokens`'s if a
    # component by the longer name exists.
    stem = case.name
    matches = sorted((c for c in known if stem == c or stem.startswith(c + "-")),
                     key=len, reverse=True)
    if not matches:
        return [f"{name}: matches no component. Name the case directory after the "
                f"skill it evaluates (`<skill>` or `<skill>-<variant>`) — a case "
                f"nobody can attribute is a case nobody can tell is guarded."]
    component = matches[0]

    # Checked for EVERY case, writing or not: a typo'd type is a grader the
    # harness cannot run, and a case that silently loses a grader is a case
    # that quietly stops asserting what its author wrote down.
    unknown = declared_types(text) - GRADER_TYPES
    if unknown:
        return [f"{name}: unknown grader type(s) {sorted(unknown)}. Known: "
                f"{sorted(GRADER_TYPES)}. A type the harness does not know is a "
                f"grader that does not run."]

    # Checked for EVERY case, writing or not. A broken scaffold path costs the
    # same $30 of zero-turn runs whichever tier the skill is in.
    problems_all = lint_scaffold(case, name)

    # A tool_used range the harness can never satisfy (see lint_empty_ranges).
    problems_all += lint_empty_ranges(units, name)

    # Paired liveness, for EVERY case. An absence-based grader on a run that
    # produced nothing is credited as a pass — measured, at 0.25, on six aborted
    # runs. See the module docstring.
    if lacks_liveness(units) and name not in LIVENESS_BASELINE:
        absent = [unit_name(u) for u in units if is_absence_shaped(u)]
        problems_all.append(
            f"{name}: absence-based grader(s) {absent} with no positive liveness "
            f"grader. A run that aborted before doing anything satisfies every "
            f"one of them and is credited as a pass — the governing principle's "
            f"own failure mode, inside the harness. Pair them with a lower-bound "
            f"assertion an empty run cannot satisfy: a `tool_used` with "
            f"`min: 1`, a `tool_order`, a `file_exists`, or a "
            f"`regex`/`match: contains`. The suite's own `did-run-step-0` and "
            f"`skill-fired` graders are the pattern.")

    if component not in writing:
        return problems_all  # a read-only skill: the rest is about writes

    problems = []
    # Scoped to components that can actually write provenance, derived from the
    # component's own markdown rather than a hardcoded list. `promote-component`
    # is `explicit` and writes plenty, but never touches a provenance field —
    # demanding an `approved` guard there asserted a rule its skill has no way
    # to break, which is noise that teaches people to ignore the gate.
    if writes_provenance(component) and not has_forbidden_state_guard(units):
        problems.append(f"no `not_contains` guard naming {FORBIDDEN_STATE!r} — "
                        f"a skill that writes provenance must be asserted NOT to "
                        f"author the one state only a human may write")
    if not has_negative_tool_assertion(units):
        problems.append("no negative `tool_used` assertion (`min: 0` AND `max: 0`) — "
                        "a suite of only positive assertions can never catch the "
                        "skill doing something extra")
    types = declared_types(text)
    if not types & RESULT_TYPES:
        problems.append(f"no result grader (one of {sorted(RESULT_TYPES)}) — "
                        f"nothing judges what it produced")
    if not types & PROCESS_TYPES:
        problems.append(f"no process grader (one of {sorted(PROCESS_TYPES)}) — "
                        f"a result-only case passes on a right answer reached by a "
                        f"forbidden route")
    return problems_all + \
        [f"{name} ({component}, invocation: explicit): {p}" for p in problems]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-dir", help="override the eval directory")
    ap.add_argument("--list", action="store_true",
                    help="print each case and the skill it was attributed to")
    ap.add_argument("--liveness-report", action="store_true",
                    help="print each case's absence-shaped and liveness graders, "
                         "and the LIVENESS_BASELINE literal that matches the tree")
    args = ap.parse_args()

    root = Path(args.eval_dir).resolve() if args.eval_dir else eval_dir()
    writing, known = writing_components(), all_components()
    if not writing:
        print("no component declares `invocation: explicit`, so this gate has no "
              "writing skill to hold any case to. That is a broken read of the "
              "frontmatter, not a suite with nothing to check.", file=sys.stderr)
        return 2

    cases = find_cases(root)
    if args.liveness_report:
        unbacked = []
        for case in cases:
            units = grader_units(case)
            name = case.relative_to(root).as_posix()
            absent = [unit_name(u) for u in units if is_absence_shaped(u)]
            live = [unit_name(u) for u in units if is_liveness(u)]
            if absent and not live:
                unbacked.append(name)
            print(f"{name}\n  absence : {absent or '-'}\n  liveness: {live or '-'}")
        print(f"\n{len(unbacked)} unbacked case(s). LIVENESS_BASELINE literal:")
        print("LIVENESS_BASELINE: set[str] = " +
              ("{\n" + "".join(f'    "{n}",\n' for n in sorted(unbacked)) + "}"
               if unbacked else "set()"))
        return 0

    if args.list:
        for case in cases:
            stem = case.name
            matches = sorted((c for c in known if stem == c or stem.startswith(c + "-")),
                             key=len, reverse=True)
            attributed = matches[0] if matches else "UNATTRIBUTED"
            tier = "writing" if attributed in writing else "read-only"
            print(f"{case.relative_to(root).as_posix():44} {attributed:26} {tier}")
        return 0

    if not cases:
        # Deliberately exit 0, and deliberately loud. The suite legitimately
        # does not exist yet — the fixtures and gates land first, the cases
        # land after — so failing here would block the layer that makes the
        # cases checkable. What must never happen is this reading as a pass, so
        # it says, in the one line a reader will see, that it checked nothing.
        print(f"NOTHING CHECKED: no eval case under {root}. This gate asserted "
              f"nothing — it is not a clean suite, it is an absent one.")
        return 0

    problems: list[str] = []
    for case in cases:
        problems += lint(case, root, writing, known)

    # The ratchet, asserted EXACT in both directions. A baselined case that has
    # since gained a liveness grader, or one that no longer exists, must leave
    # the list — otherwise the baseline quietly becomes a standing excuse that
    # would also absolve a future regression in the same case.
    names = {c.relative_to(root).as_posix() for c in cases}
    stale = sorted(n for n in LIVENESS_BASELINE
                   if n not in names or not lacks_liveness(grader_units(root / n)))
    if stale:
        problems.append(
            f"LIVENESS_BASELINE lists {stale}, which no longer need it — the case "
            f"is gone, or it now carries a liveness grader. Remove them: a "
            f"baseline entry that is not earning its place would also excuse a "
            f"future regression in the same case.")
    elif LIVENESS_BASELINE:
        print(f"{len(LIVENESS_BASELINE)} case(s) baselined as absence-only, "
              f"visible and not clean: {sorted(LIVENESS_BASELINE)}")

    if problems:
        print(f"{len(problems)} problem(s) in {len(cases)} case(s):\n", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        print("\nA suite that can pass by omission measures nothing it did not "
              "think to ask.", file=sys.stderr)
        return 1

    writing_cases = sum(
        1 for c in cases
        if any(c.name == k or c.name.startswith(k + "-") for k in writing))
    print(f"{len(cases)} case(s) lint clean ({writing_cases} for writing skills, "
          f"each carrying all four mandatory guards).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
