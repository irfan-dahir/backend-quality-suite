#!/usr/bin/env python3
"""Does CLAUDE.md's prose still match what actually runs?

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_claude_md_drift.py"

## Why this exists

A project's CLAUDE.md states rules in prose — "9 of the 10 gates run",
"no project literal may appear in the universal plugin", "never commit
directly to main" — on the understanding that some of those are mechanically
enforced elsewhere. Nothing checks that the prose and the mechanism still
agree. The gate gets renamed, the script gets removed from CI, the count
changes on one side and not the other, and the documentation keeps asserting
something that stopped being true. It reads exactly like a project that is
still enforcing what it claims, which is the same failure this whole suite
exists to catch, aimed at the documentation layer instead of the design
system.

This audit does not know or guess what any project's rules are. It reads a
mapping the project provides — CLAUDE.md rule -> the mechanism supposed to
enforce it — and mechanically verifies each mapped mechanism still exists,
still runs, and still says what CLAUDE.md claims it says. A rule with no
mechanical mechanism (most process rules: "ask before every push", "cut a
branch from main") is reported as unenforced, never silently passed — the
same convention `resolve.py` uses for an unmapped doc role: refuse to guess
rather than report clean by accident. See docs/DOC-ROLES.md's exit-code
contract, which this mirrors.

## What it audits — the project, never this plugin

The target is the project being audited, resolved by `project_root()` exactly
as every other audit here resolves it: the consumer's own `CLAUDE.md` and the
consumer's own enforcement mapping. It never falls back to this plugin's copies
of either. Pointed at this repo it audits this repo (that is the dogfooding
case, and this repo's `.backend-suite/claude_md_enforcement.json` is a real
mapping against its own CLAUDE.md); pointed anywhere else it audits there or it
refuses.

## Config

Reads the project's `.backend-suite/claude_md_enforcement.json`. A project may
point somewhere else with `audits.claudeMdEnforcement` in
`.backend-suite/profile.json`; `--config` overrides both.

**A missing `CLAUDE.md` or a missing mapping is exit 2, not exit 0.** Both are
CapabilityError territory per docs/DOC-ROLES.md's exit-code contract: there is
no honest way to distinguish "this project's rules all hold" from "this project
never told me what its rules are", so the second one refuses out loud rather
than borrowing another repo's answer.

No rule text from any project's CLAUDE.md is hardcoded here — a project that
drops this script in and writes its own config gets a real check against its
own rules, not this repo's.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT, project_root  # noqa: E402  (also puts the plugin on sys.path)

# The project being audited — NOT the directory this script lives in. Until the
# fix for issue #104 this read `parents[3]`, the plugin's own repository, so on
# every consumer project it verified THIS repo's CLAUDE.md against THIS repo's
# gates and handed the result to the consumer as if it were theirs. Run against
# two different consumer projects it produced byte-identical output, and that
# output was about neither of them. An audit reporting nothing about the
# codebase it was pointed at, indistinguishable from that codebase being clean,
# is the governing principle's own failure mode — shipped inside the tool built
# to catch it. `project_root()` is how every other audit here resolves its
# target; there is no reason this one was different beyond the bug.
REPO = project_root()
PLUGIN_REPO = PLUGIN_ROOT.parents[1]  # this plugin's own repo, for dogfooding only
from backend_suite.engine import findings as F  # noqa: E402
BIN = Path(__file__).resolve().parent

_EXAMPLE_SCHEMA = {
    "rules": [
        {
            "id": "example-count-claim",
            "statement": "CLAUDE.md claims a specific count that a command also reports",
            "check": {
                "kind": "value_match",
                "claudeMdPattern": r"runs (\d+) of the \d+ gates",
                "actualCommand": "python3 plugins/backend-suite/bin/gates.py --list",
                "actualPattern": r"^(\d+) gate\(s\)",
            },
        },
        {
            "id": "example-mechanism-wired",
            "statement": "a named script is claimed to enforce something and must be wired into the gate runner",
            "check": {"kind": "script_wired_in_gates", "path": "plugins/backend-suite/bin/some_audit.py"},
        },
        {
            "id": "example-process-rule",
            "statement": "a rule with no code to check",
            "check": {"kind": "unenforceable", "reason": "process rule; no mechanical signal exists for it"},
        },
    ]
}


class Unresolvable(Exception):
    """Raised when a rule's check cannot be evaluated at all — not the same as failing it."""


class Refuse(Exception):
    """This audit cannot run on this project at all. Exit 2, never 0, never 1.

    Exit 1 would say "I looked and found drift"; exit 0 would say "I looked and
    this project's CLAUDE.md is honest". Neither is true when there is nothing
    to look at.
    """


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)


def _claude_md_text(path: Path) -> str:
    if not path.is_file():
        raise Refuse(
            f"no CLAUDE.md in the project being audited ({REPO}) — looked for {path}.\n"
            "This audit checks a project's OWN CLAUDE.md against its OWN enforcement "
            "mechanisms. It will not fall back to the plugin's CLAUDE.md: doing that "
            "produced identical output on two unrelated projects and described "
            "neither of them (issue #104).\n"
            "If you meant to audit a different tree, run from it or export "
            "CLAUDE_PROJECT_DIR; --claude-md points at one explicitly.")
    return path.read_text()


def _load_config(path: Path) -> dict:
    if not path.is_file():
        raise Refuse(
            f"no rule-enforcement config at {_rel(path)} in the project being "
            f"audited ({REPO}).\n"
            "This audit needs a mapping from CLAUDE.md's stated rules to what actually "
            "enforces them before it can check anything — without one it would either "
            "guess (wrong, on someone else's project) or report clean (worse: a rule with "
            "no config looks identical to a rule that was checked and passed).\n"
            "Create it — see audit_claude_md_drift.py's _EXAMPLE_SCHEMA for the shape.")
    try:
        cfg = json.loads(path.read_text())
    except ValueError as exc:
        raise Refuse(f"{_rel(path)} is not valid JSON: {exc}")
    rules = cfg.get("rules")
    if not isinstance(rules, list) or not rules:
        raise Refuse(
            f"{_rel(path)} declares no rules — an empty mapping would report a clean audit "
            "for reasons that have nothing to do with CLAUDE.md actually being clean.")
    return cfg


def _run(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", cmd], cwd=REPO, capture_output=True, text=True)


def _check_value_match(check: dict, claude_md: str) -> tuple[bool, str]:
    doc_pat = check.get("claudeMdPattern")
    cmd = check.get("actualCommand")
    act_pat = check.get("actualPattern")
    if not (doc_pat and cmd and act_pat):
        raise Unresolvable("value_match needs claudeMdPattern, actualCommand and actualPattern")

    doc_m = re.search(doc_pat, claude_md, re.MULTILINE)
    if not doc_m:
        raise Unresolvable(
            f"claudeMdPattern {doc_pat!r} matched nothing in CLAUDE.md — the rule this "
            "config maps may itself have been reworded or removed")
    claimed = doc_m.group(1)

    proc = _run(cmd)
    combined = proc.stdout + proc.stderr
    act_m = re.search(act_pat, combined, re.MULTILINE)
    if not act_m:
        raise Unresolvable(
            f"actualPattern {act_pat!r} matched nothing in the output of {cmd!r} "
            f"(exit {proc.returncode}) — cannot tell what is actually true")
    actual = act_m.group(1)

    if claimed == actual:
        return True, f"CLAUDE.md claims {claimed!r}, actual is {actual!r} — match"
    return False, f"CLAUDE.md claims {claimed!r}, actual is {actual!r} — DRIFTED"


def _check_script_exists(check: dict) -> tuple[bool, str]:
    rel = check.get("path")
    if not rel:
        raise Unresolvable("script_exists needs path")
    ok = (REPO / rel).is_file()
    return ok, (f"{rel} exists" if ok else f"{rel} does not exist")


def _gate_commands() -> list[str]:
    """Every runnable command gates.py would execute, by importing it directly.

    Not re-parsing the workflow here — gates.py already does that, and a second
    parser is exactly the two-sources-of-truth problem this whole audit exists to
    find. If gates.py's parsing breaks, this breaks with it, loudly.
    """
    sys.path.insert(0, str(BIN))
    import gates  # noqa: E402
    return [cmd for _, cmd in gates.steps() if cmd]


def _check_script_wired_in_gates(check: dict) -> tuple[bool, str]:
    rel = check.get("path")
    if not rel:
        raise Unresolvable("script_wired_in_gates needs path")
    if REPO != PLUGIN_REPO:
        # gates.py parses THIS plugin's `.github/workflows/validate.yml`, so the
        # answer it gives is about this plugin's CI and not about the project
        # being audited. Reporting it to a consumer as their own result is the
        # exact defect this file was fixed for; unresolvable is the honest answer
        # until a project-scoped equivalent exists.
        raise Unresolvable(
            "script_wired_in_gates reads gates.py, which parses THIS plugin's "
            f"workflow, not {REPO}'s. It can only answer for the plugin's own repo. "
            "Use command_exits_zero against this project's own CI runner instead.")
    if not (REPO / rel).is_file():
        return False, f"{rel} does not exist — cannot be wired into anything"
    try:
        commands = _gate_commands()
    except Exception as exc:  # noqa: BLE001 - surfaced as unresolvable, not a silent pass
        raise Unresolvable(f"could not read gates.py's step list: {exc}")
    wired = any(rel in cmd for cmd in commands)
    return wired, (f"{rel} is invoked from a gate in .github/workflows/validate.yml"
                   if wired else
                   f"{rel} exists but no gate in .github/workflows/validate.yml runs it")


def _check_command_exits_zero(check: dict) -> tuple[bool, str]:
    cmd = check.get("command")
    if not cmd:
        raise Unresolvable("command_exits_zero needs command")
    proc = _run(cmd)
    ok = proc.returncode == 0
    return ok, (f"{cmd!r} exited 0" if ok else f"{cmd!r} exited {proc.returncode}")


_CHECKS = {
    "value_match": _check_value_match,
    "script_exists": _check_script_exists,
    "script_wired_in_gates": _check_script_wired_in_gates,
    "command_exits_zero": _check_command_exits_zero,
}


def _config_path(explicit: str | None) -> Path:
    """Where THIS project keeps its enforcement mapping.

    Order: --config, then the profile's `audits.claudeMdEnforcement`, then the
    conventional `.backend-suite/claude_md_enforcement.json`. All three resolve
    inside the project being audited. There is deliberately no fallback to the
    plugin's own copy.
    """
    if explicit:
        return Path(explicit).resolve()
    profile = REPO / ".backend-suite" / "profile.json"
    if profile.is_file():
        try:
            node = json.loads(profile.read_text())
        except (OSError, ValueError):
            node = {}
        rel = (node.get("audits") or {}).get("claudeMdEnforcement")
        if isinstance(rel, str) and rel:
            return (REPO / rel).resolve()
    return REPO / ".backend-suite" / "claude_md_enforcement.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="path to the rule-enforcement mapping (default: this "
                    "project's audits.claudeMdEnforcement, else "
                    ".backend-suite/claude_md_enforcement.json)")
    ap.add_argument("--claude-md", help="path to CLAUDE.md (default: <project root>/CLAUDE.md)")
    ap.add_argument("--findings", nargs="?", const=True, default=None,
                    help="also write the common findings envelope for /design-debt "
                         "(default .backend-suite/findings/claude-md-drift.json)")
    args = ap.parse_args()

    claude_md_path = Path(args.claude_md).resolve() if args.claude_md else REPO / "CLAUDE.md"
    config_path = _config_path(args.config)

    # Stated up front, every run: a reader must be able to see WHICH repo the
    # lines below are about. The bug this replaced was invisible precisely
    # because the output never said.
    print(f"auditing {REPO}")
    print(f"  CLAUDE.md           {_rel(claude_md_path)}")
    print(f"  enforcement mapping {_rel(config_path)}")
    print()

    try:
        claude_md = _claude_md_text(claude_md_path)
        cfg = _load_config(config_path)
    except Refuse as exc:
        print(f"audit_claude_md_drift: CANNOT RUN on {REPO}\n\n{exc}", file=sys.stderr)
        return 2

    matched: list[str] = []
    drifted: list[str] = []
    unresolvable: list[str] = []
    unenforceable: list[str] = []

    for rule in cfg["rules"]:
        rid = rule.get("id", "<unnamed rule>")
        statement = rule.get("statement", "")
        check = rule.get("check") or {}
        kind = check.get("kind")

        if kind == "unenforceable":
            reason = check.get("reason", "no mechanical check exists for this rule")
            unenforceable.append(f"{rid}: {statement} — UNENFORCED ({reason})")
            continue

        fn = _CHECKS.get(kind)
        if fn is None:
            unresolvable.append(f"{rid}: unknown check kind {kind!r}")
            continue

        try:
            ok, detail = fn(check, claude_md) if kind == "value_match" else fn(check)
        except Unresolvable as exc:
            unresolvable.append(f"{rid}: {statement} — CANNOT VERIFY ({exc})")
            continue

        line = f"{rid}: {statement} — {detail}" if statement else f"{rid}: {detail}"
        (matched if ok else drifted).append(line)

    total = len(cfg["rules"])

    if args.findings:
        # Three categories, three different claims. `drifted` is CLAUDE.md
        # stating something untrue and is critical. `cannot-verify` is the
        # governing principle's own case — a check that could not run must
        # appear as a finding, never as a silent pass. `unenforceable` is a
        # rule nothing mechanical can check at all: real, permanent, and FYI
        # rather than actionable, but still counted, because a process rule
        # that disappears from the report is one nobody rereads.
        where = _rel(claude_md_path)
        records = (
            [F.make("claude-md-drift", "drifted", line,
                    severity=F.CRITICAL, file=where) for line in drifted]
            + [F.make("claude-md-drift", "cannot-verify", line,
                      severity=F.SHOULD_FIX, file=where) for line in unresolvable]
            + [F.make("claude-md-drift", "unenforceable", line,
                      severity=F.FYI, file=where) for line in unenforceable])
        F.write(
            F.default_path(REPO, "claude-md-drift") if args.findings is True
            else REPO / args.findings,
            "claude-md-drift", records,
            # The sweep is over mapped rules, not files: an enforcement mapping
            # that lost its rules would otherwise report clean.
            scanned=total,
        )

    print(f"  rules mapped        {total}")
    print(f"  verified, matching  {len(matched)}")
    for line in matched:
        print(f"    ok    {line}")

    if unenforceable:
        print(f"  unenforceable       {len(unenforceable)} "
              "(process rules with no mechanical signal — reported, never passed)")
        for line in unenforceable:
            print(f"    ----  {line}")

    sys.stdout.flush()

    if unresolvable:
        print(f"\nCANNOT VERIFY — {len(unresolvable)} rule(s) whose check could not run "
              "at all:\n", file=sys.stderr)
        for line in unresolvable:
            print(f"  {line}", file=sys.stderr)
        print("\nAn unresolvable check is not a pass. Fix the config or the thing it "
              "points at, then re-run.", file=sys.stderr)

    if drifted:
        print(f"\nDRIFTED — {len(drifted)} rule(s) where CLAUDE.md's claim and reality "
              "disagree:\n", file=sys.stderr)
        for line in drifted:
            print(f"  {line}", file=sys.stderr)
        print("\nEither CLAUDE.md is wrong now, or the thing it describes stopped doing "
              "what it says. Fix whichever one drifted.", file=sys.stderr)

    if drifted or unresolvable:
        return 1

    print(f"\naudit_claude_md_drift: {len(matched)} enforced rule(s) verified, "
          f"{len(unenforceable)} flagged as unenforced. No drift found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
