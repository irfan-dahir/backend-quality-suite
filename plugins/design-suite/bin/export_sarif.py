#!/usr/bin/env python3
"""Export the collected findings envelopes as one SARIF 2.1.0 log.

    python3 bin/export_sarif.py                          envelopes on disk -> stdout
    python3 bin/export_sarif.py --out design.sarif
    python3 bin/repo_health.py --json > health.json
    python3 bin/export_sarif.py --health health.json --out design.sarif

One run per audit. Reads `.design-suite/findings/*.json` (the common envelope,
`design_suite/engine/findings.py`); never runs an audit itself, for the same
reason `design_debt.py` does not — an export must not be why an audit's output
moved. Writes only the file named by `--out` (or stdout).

AN AUDIT THAT COULD NOT CHECK NEVER VANISHES. An empty SARIF run reads as "no
alerts" in GitHub code scanning, so every audit gets a run, and each one that
refused, was INERT, crashed, is DISABLED, or simply has no envelope is emitted
with `invocations[0].executionSuccessful: false` and a notification naming why.

  * With `--health` (a `repo_health.py --json` document) the status of each
    audit is known exactly — refused, crashed, disabled — and an audit that did
    not run successfully contributes no results, even if an older envelope from
    a previous run is still on disk.
  * Without it, every discovered audit is still listed: DISABLED ones from the
    registry, and live ones with no envelope as "not collected — never run or
    refused", which is the most this script can know without running anything.

`--validate` checks the output against the vendored official SARIF 2.1.0 schema
(templates/vendor/sarif-2.1.0/) and exits 1 if it does not conform.

Exit 0 written; 1 schema validation failed; 2 input unusable (no envelopes and
no health document — there is nothing to export, which is not a clean result).
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT, project_root  # noqa: E402

from design_suite.engine import audit_discovery  # noqa: E402
from design_suite.engine import findings as F  # noqa: E402
from design_suite.engine import json_schema_lite  # noqa: E402
from design_suite.engine import sarif  # noqa: E402

BIN = Path(__file__).resolve().parent
SCHEMA = PLUGIN_ROOT / "templates/vendor/sarif-2.1.0/sarif-schema-2.1.0.json"


def plugin_version() -> str | None:
    try:
        return json.loads((PLUGIN_ROOT / ".claude-plugin/plugin.json").read_text()).get("version")
    except (OSError, ValueError):
        return None


def _envelope_name(script: Path) -> str:
    return audit_discovery.envelope_name(script) or script.stem.removeprefix("audit_")


def build(repo: Path, health: dict | None, scripts: list[Path] | None = None) -> dict:
    version = plugin_version()
    envelopes = {e["audit"]: e for e in F.read_all(repo)}
    scripts = audit_discovery.discover(BIN) if scripts is None else scripts
    by_stem = {s.stem: s for s in scripts}
    runs: list[dict] = []
    seen: set[str] = set()

    if health is not None:
        for row in health.get("audits", []):
            stem = row.get("audit", "?")
            script = by_stem.get(stem)
            name = _envelope_name(script) if script else stem.removeprefix("audit_")
            seen.add(name)
            runs.append(sarif.build_run(
                name, envelope=envelopes.get(name), status=row.get("status"),
                reason=row.get("disabledDetail") or row.get("message"),
                exit_code=row.get("exitCode"), version=version, repo=repo))
    else:
        for script in scripts:
            name = _envelope_name(script)
            entry = audit_discovery.disabled_reason(script)
            if entry:
                seen.add(name)
                runs.append(sarif.build_run(
                    name, envelope=None, status="disabled",
                    reason=f"{entry['reason']} — {entry['detail']}", version=version, repo=repo))
            elif name not in envelopes:
                seen.add(name)
                runs.append(sarif.build_run(
                    name, envelope=None, status=None, version=version, repo=repo,
                    reason=(f"No findings envelope collected for {script.stem} — never run, "
                            f"refused, or it does not support --findings. Zero results here "
                            f"does NOT mean clean; a repo_health.py --json document passed as "
                            f"--health says which.")))

    for name in sorted(envelopes):
        if name in seen:
            continue
        runs.append(sarif.build_run(name, envelope=envelopes[name], status=None,
                                    version=version, repo=repo))
    runs.sort(key=lambda r: r["tool"]["driver"]["name"])
    return sarif.build_log(runs)


def validate(log: dict) -> list[str]:
    schema = json.loads(SCHEMA.read_text())
    return json_schema_lite.errors(log, schema)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", help="project root (default: the detected project)")
    ap.add_argument("--health", metavar="FILE",
                    help="a repo_health.py --json document giving each audit's run status")
    ap.add_argument("--out", metavar="FILE", help="write here instead of stdout")
    ap.add_argument("--validate", action="store_true",
                    help="validate against the vendored SARIF 2.1.0 schema")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve() if args.repo else project_root()
    health = None
    if args.health:
        try:
            health = json.loads(Path(args.health).read_text())
        except (OSError, ValueError) as exc:
            print(f"export_sarif: cannot read --health {args.health}: {exc}", file=sys.stderr)
            return 2
    if health is None and not F.read_all(repo):
        print(f"export_sarif: no findings envelopes under {repo / F.FINDINGS_DIR} and no "
              f"--health document — nothing to export. That is not a clean result; collect envelopes "
              f"(repo_health.py --json) first.", file=sys.stderr)
        return 2

    log = build(repo, health)
    text = json.dumps(log, indent=2) + "\n"
    if args.validate:
        problems = validate(log)
        if problems:
            for p in problems[:20]:
                print(f"export_sarif: schema: {p}", file=sys.stderr)
            return 1
    if args.out:
        Path(args.out).write_text(text)
        failed = [r["tool"]["driver"]["name"] for r in log["runs"]
                  if not r["invocations"][0]["executionSuccessful"]]
        print(f"export_sarif: {len(log['runs'])} run(s) -> {args.out}; "
              f"{sum(len(r['results']) for r in log['runs'])} result(s); "
              f"{len(failed)} audit(s) could not check: {', '.join(failed) or 'none'}",
              file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
