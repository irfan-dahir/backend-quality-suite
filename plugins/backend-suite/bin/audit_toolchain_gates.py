#!/usr/bin/env python3
"""The project's own gates: declared, wired to something real, runnable.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_toolchain_gates.py" [--out …] [--findings]

## Why this exists

Every project's test command lives somewhere — a composer script, an npm
script, a Make target — and it points at a runner configured elsewhere. The
join drifts: a script referencing a renamed testsuite, a testsuite whose
directory moved, a library that ships tests and declares no command to run
them. None of these fail at install time; they surface as the CI that
never ran anything, or the contributor who never learns how to.

Measured on the first validation targets (probed 2026-10-11):

- **jikan-rest** is coherent: composer declares `phpunit`, `test`
  (`--testsuite unit`) and `integration-test` (`--testsuite integration`),
  and `phpunit.xml` declares both suites with real directories — the
  clean direction, measured honestly.
- **jikan (the parser library) declares no test script at all**: its
  composer `scripts` block carries only `link-fixtures` (which clones the
  recorded responses). Tests exist (`test/JikanTest`, 56 files) and
  `phpunit.xml` plus `grumphp.yml` exist, but nothing in the manifest says
  how to run them — a contributor's `composer test` fails with "Script
  not found", and the knowledge lives in prose instead of the toolchain.

## What it checks

- `missing_required_script` — a script the config says this kind of
  project must declare is absent from the manifest.
- `script_testsuite_undefined` — a script passes `--testsuite X` and the
  runner declares no suite named X. The script is broken as written.
- `testsuite_directory_missing` — a declared suite points its
  `<directory>` at a path that no longer exists. This is the quiet one:
  a suite over a missing directory runs zero tests and exits green, which
  is this suite's governing failure wearing the project's own clothes.
- `check_script_missing` / `check_script_failed` — gates the project opted
  into via `toolchainGates.checkScripts`: each named composer script must
  exist in the manifest AND exit 0 when executed in the repo (capped at
  120s). Nothing is executed unless the project lists it.

Parsed as JSON and XML, not grepped: these are structured documents and a
regex reading of them is a second parser that can silently disagree with
the first.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
from backend_suite.engine import findings as F  # noqa: E402
from backend_suite.engine.arch import load  # noqa: E402
from backend_suite.engine.refusal import Refused  # noqa: E402

RULES = load(REPO, "toolchainGates")

ENVELOPE = "toolchain-gates"


def _script_lines(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _run_check_script(repo, name: str, spec) -> tuple[bool, str]:
    """(ok, why) for one composer script the project opted into running.

    Composer script values may be a string or a list of lines. Lines are
    joined with `&&` and executed via `bash -c` in the repo; composer's
    `@php`/`@composer` shorthands are normalized to platform binaries. Capped
    at 120s so a runaway gate cannot hang the audit. Only scripts listed in
    toolchainGates.checkScripts are ever executed — nothing runs by default.
    """
    lines = [spec] if isinstance(spec, str) else list(spec)
    cmd = " && ".join(
        line.replace("@php ", "php ", 1).replace("@composer ", "composer ", 1)
        for line in lines)
    try:
        proc = subprocess.run(["bash", "-c", cmd], cwd=repo,
                              capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, f"{name!r} did not finish within 120s"
    except (OSError, ValueError) as exc:
        return False, f"could not run ({exc})"
    if proc.returncode == 0:
        return True, ""
    tail = (proc.stdout or "").strip().splitlines()[-4:]
    if not tail:
        last_err = (proc.stderr or "").strip().splitlines()
        tail = last_err[-1:] if last_err else ["(no output)"]
    return False, f"exit {proc.returncode}: {' | '.join(tail)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for "
                             "/quality-debt (bare flag uses the default path)")
    args = parser.parse_args()

    manifest_glob = RULES.get("manifestGlob")
    if not manifest_glob:
        raise Refused("toolchainGates.manifestGlob is not set — the manifest "
                      "declaring the project's commands",
                      audit="audit_toolchain_gates")
    manifests = sorted(REPO.glob(manifest_glob))
    if not manifests:
        raise Refused(
            f"toolchainGates.manifestGlob ({manifest_glob!r}) matched no "
            f"files — the toolchain's declaration cannot be found.",
            audit="audit_toolchain_gates")

    runner_glob = RULES.get("runnerGlob")
    if not runner_glob:
        raise Refused("toolchainGates.runnerGlob is not set — the runner "
                      "config declaring suites (e.g. phpunit.xml)",
                      audit="audit_toolchain_gates")
    runners = [p for p in sorted(REPO.glob(runner_glob)) if p.is_file()]
    if not runners:
        raise Refused(
            f"toolchainGates.runnerGlob ({runner_glob!r}) matched no files — "
            f"there is nothing for a test command to point at, which is "
            f"exactly the drift this audit exists to name.",
            audit="audit_toolchain_gates")

    required = RULES.get("requiredScripts") or []
    testsuite_flag = RULES.get("testsuiteFlag") or "--testsuite"
    check_scripts = RULES.get("checkScripts") or []

    # Runner suites: name -> declared directories (paths relative to the
    # runner file's directory, per phpunit's own resolution).
    suites: dict[str, list[tuple[Path, str]]] = {}
    for runner in runners:
        try:
            root = ET.fromstring(runner.read_text())
        except ET.ParseError as exc:
            raise Refused(f"{runner.relative_to(REPO)} is not parseable XML: "
                          f"{exc} — refusing to compare against a file that "
                          f"cannot be read.", audit="audit_toolchain_gates")
        for suite_node in root.iter("testsuite"):
            name = suite_node.get("name")
            if not name:
                continue
            for directory in suite_node.iter("directory"):
                if directory.text:
                    suites.setdefault(name, []).append(
                        (runner.parent, directory.text.strip()))

    records = []
    scripts_seen = 0
    for manifest in manifests:
        rel = manifest.relative_to(REPO).as_posix()
        try:
            data = json.loads(manifest.read_text())
        except ValueError as exc:
            raise Refused(f"{rel} is not valid JSON: {exc}",
                          audit="audit_toolchain_gates")
        scripts = data.get("scripts") or {}
        scripts_seen += len(scripts)

        for name in required:
            if name not in scripts:
                records.append(F.make(
                    ENVELOPE, "missing_required_script",
                    f"{rel} declares no {name!r} script — tests exist but the "
                    f"manifest never says how to run them, so the knowledge "
                    f"lives in prose instead of the toolchain.",
                    severity=F.SHOULD_FIX, file=rel))

        for script, value in sorted(scripts.items()):
            for line in _script_lines(value):
                for match in re.finditer(
                        re.escape(testsuite_flag) + r"\s+(\S+)", line):
                    suite = match.group(1)
                    if suite not in suites:
                        records.append(F.make(
                            ENVELOPE, "script_testsuite_undefined",
                            f"{rel} script {script!r} runs "
                            f"{testsuite_flag} {suite}, which the runner "
                            f"does not declare — the command is broken as "
                            f"written.",
                            severity=F.SHOULD_FIX, file=rel))

    for name, entries in sorted(suites.items()):
        for base, directory in entries:
            if not (base / directory).exists():
                records.append(F.make(
                    ENVELOPE, "testsuite_directory_missing",
                    f"testsuite {name!r} points its <directory> at "
                    f"{directory!r}, which does not exist from the runner's "
                    f"location — the suite runs zero tests and exits green.",
                    severity=F.CRITICAL))

    # checkScripts — gates the project chose to have THIS audit actually run.
    # A script the gate list names must exist in the manifest AND exit 0 when
    # executed in the repo; a missing name is a config drift finding, a failing
    # name is a broken gate. Only scripts the project opts into via
    # toolchainGates.checkScripts are ever executed — nothing runs by default.
    for name in check_scripts:
        if name not in scripts:
            records.append(F.make(
                ENVELOPE, "check_script_missing",
                f"{rel} declares no {name!r} script, but toolchainGates."
                f"checkScripts requires it — the gate its name promises exists "
                f"nowhere to run.",
                severity=F.SHOULD_FIX, file=rel))
            continue
        ok, why = _run_check_script(REPO, name, scripts[name])
        if not ok:
            records.append(F.make(
                ENVELOPE, "check_script_failed",
                f"{rel} script {name!r} failed its toolchain gate: {why}",
                severity=F.CRITICAL, file=rel))

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"violations": [r["summary"] for r in records],
             "suites": sorted(suites)}, indent=2) + "\n")

    if args.findings:
        F.write(
            F.default_path(REPO, "toolchain-gates") if args.findings is True
            else REPO / args.findings,
            ENVELOPE, records,
            scanned=len(manifests) + len(runners) + len(check_scripts),
        )

    print(f"  manifests           {len(manifests)} ({scripts_seen} scripts)")
    print(f"  runner suites       {', '.join(sorted(suites)) or 'none'}")
    if not records:
        print(f"\naudit_toolchain_gates: the declared commands point at real "
              f"suites and every required script exists")
        return 0

    print(f"\nVIOLATIONS ({len(records)}):", file=sys.stderr)
    for record in records:
        print(f"  [{record['category']}] {record['summary']}", file=sys.stderr)
    if args.out:
        print(f"\nFindings written to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
