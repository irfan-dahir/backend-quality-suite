#!/usr/bin/env python3
"""Run a component's MECHANICAL part against a project, and record what happened.

    python3 plugins/backend-suite/bin/verify.py audit-tokens
    python3 plugins/backend-suite/bin/verify.py audit-tokens --project-root ../some-project
    python3 plugins/backend-suite/bin/verify.py --all

Roadmap Workstream A1 — the keystone item. This suite currently has components
whose `maturity: proven` in frontmatter is an assertion someone typed, not a
record. This script turns "does it actually work" into evidence written to
`.backend-suite/evidence/<component-name>.json` in the project it was run against.

## What "mechanical part" means, and how it's found

A component (a skill in `commands/*.md`, or an agent in `agents/*.md`) either
names a backing script under `${CLAUDE_PLUGIN_ROOT}/...` — the same
`${CLAUDE_PLUGIN_ROOT}/...` reference the "every script a skill tells Claude to
run actually exists" CI gate already parses — or it doesn't. This reuses that
gate's own resolution logic (`audit_skill_paths.PLUGIN_PATH`) instead of
reimplementing it, per this project's established "factor, don't duplicate"
precedent (#60's `decisions.py`, #84's `dating.py`).

Shared plumbing every skill's prose commonly mentions in a usage example
(`resolve.py`, `doctor.py`, `chain.py`, `gates.py`, `catalog.py`) is excluded
from candidacy — running `resolve.py` proves nothing about the specific claim
a component makes, and counting it would fabricate a pass by coincidence.

  - **Zero** `.py` references found: the component is prose for an LLM to
    follow (`design-critic`, most of `review-docs`'s judgement checks) — there
    is no deterministic execution trace to run. **Refused.**
  - **Exactly one** distinct `.py` reference: that is the mechanical part.
    Run it against the target project and record what happened.
  - **More than one** distinct reference: which one (if any) is "the"
    mechanical part this component claims is not decidable here without
    guessing, and a wrong guess is worse than no answer. **Refused.**

## What this deliberately does NOT do

It does not claim to verify the judgement half of anything. A component that
mixes a mechanical check with prose interpretation (most `/review-docs`
checks) is refused in full rather than partially credited — "ran the easy 20%
of this and reported success" is exactly the confident-nonsense failure mode
this suite exists to prevent, in the tool built to prevent it. Output is
always one of three outcomes, never a boolean:

  - **verified** — the backing script ran and exited 0.
  - **refused**  — nothing could be mechanically verified: no backing script,
    an ambiguous one, or the script itself exited 2 (this repo's own
    CapabilityError-style convention — see `docs/DOC-ROLES.md`'s exit-code
    contract, and e.g. `audit_doc_staleness.py`'s `return 2` sites — meaning
    the *script* refused: nothing to scan, missing config, etc).
  - **failed**   — the backing script ran and exited nonzero-not-2, i.e. it
    found something wrong or errored.

## Evidence file schema

Written to `<project-root>/.backend-suite/evidence/<component-name>.json`:

    {
      "component": "audit-tokens",
      "plugin": "backend-suite",
      "backing_script": "plugins/backend-suite/bin/audit_tokens.py"  | null,
      "verified_against": {"project": "<profile project.name or null>",
                            "path": "<absolute project root>",
                            "commit": "<HEAD sha>" | null,
                            "commit_status": "recorded" | "cannot-determine",
                            "dirty": true | false | null,
                            "commit_note": "<why HEAD could not be read>"  // cannot-determine only
                           },
      "verified_at": "<ISO 8601 timestamp>",
      "command_run": ["python3", "<script>", "--findings"] | null,
      "exit_code": 0 | int | null,
      "outcome": "verified" | "refused" | "failed",
      "verification": {          // templates/verification-tier.schema.json vocabulary
        "tier": "self-tested" | "unverified",
        "ranWhat": "<free text>" | omitted,
        "verifiedBy": "plugins/backend-suite/bin/verify.py",
        "timestamp": "<ISO 8601 timestamp>"
      },
      "findings_summary": "<the script's own last stdout line>" | null,
      "notes": "<why refused/failed, or any caveat>" | null
    }

`verification.tier` reuses `templates/verification-tier.schema.json` (#55)
rather than inventing a fourth vocabulary: `self-tested` when this tool itself
ran something (verified or failed — the code that made the claim is also the
code that checked it, so it is not `cross-verified`), `unverified` when
nothing ran at all (refused with no backing script). `ranWhat` is present for
every tier except `unverified`, matching that schema's own required-field rule.

Deliberately forward-compatible with RFC-0001 (accepted, gated — see
`docs/proposals/RFC-0001-evidence-and-tool-promotion.md` §3a): nothing here
assumes `component` names a suite-shipped skill specifically. `component` is
just a name, `backing_script` is just a path under whatever root the caller
resolved — a project-local skill/agent could be plugged in by a future caller
without changing this schema. RFC-0001's scope itself is NOT implemented here;
this is only "don't paint the evidence format into a suite-only corner."

## Staleness is computed, never stored (#151)

`verified_against.commit` is HEAD at verification time, read through
`provenance.head_stamp` — the same helper ratification stamps with, so there is
one way to read HEAD in this suite, not two. A record is current while
`git diff <commit>..HEAD` is empty and stale the moment it is not; no verdict
is written into the record, because a stored verdict rots.

An unreadable HEAD (not a git repo, no commits, git absent) is written as
`commit: null, commit_status: "cannot-determine"` with a named reason — never
omitted, because a record that cannot be dated must not look like one that can.
A record written before #151 has no `commit_status` at all and reads as
`unknown` (see `record_commit`), never as current.

`--staleness` reports, per existing record, the commit it was verified at and
how many files have changed since. It is project-wide, not per-component:
nothing yet declares which files a component's claim is *about*, and guessing
that set would manufacture a "current" verdict. Report-only, exit 0 when it
read the evidence directory, 2 when there is none to read.

## Chain-step compatibility (roadmap ✅ 1)

Single positional argument, exit 0/1/2 like every other script here — a future
"verify all unverified components" chain can sequence this per-component and
read the exit code the same way it would any other step. `--all` exists for
convenience today (closing out the 8-unverified-components goal by hand) but
is not the chain integration itself; that stays `chain.py`'s job.

Usage:
    python3 verify.py <component> [--project-root PATH]
    python3 verify.py --all [--project-root PATH]
    python3 verify.py --staleness [--project-root PATH]

Exit codes:
    0 = verified (single) / all resolved cleanly, nothing failed (--all)
    1 = failed (single) / at least one component failed (--all)
    2 = refused, or usage error, or no project found
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)
from audit_skill_paths import PLUGIN_PATH, TRAILING  # noqa: E402
from catalog import frontmatter as parse_frontmatter  # noqa: E402
from backend_suite.engine import audit_discovery  # noqa: E402
from backend_suite.engine.provenance import head_stamp  # noqa: E402

SUITE_REPO = Path(__file__).resolve().parents[3]
PLUGINS = SUITE_REPO / "plugins"

# Shared plumbing almost every skill's prose references to resolve profile
# config or a doc role — never "the" mechanical part any *specific* component
# claims to have. Without this exclusion, any skill that mentions
# `resolve.py --profile ...` in a usage example "verifies" by running
# resolve.py, which is a false positive as sharp as fabricating a pass:
# resolve.py exiting cleanly proves nothing about that skill's own claim.
SHARED_UTILITIES = {"resolve.py", "doctor.py", "chain.py", "gates.py", "catalog.py"}

TIER_SELF_TESTED = "self-tested"
TIER_UNVERIFIED = "unverified"

OUTCOME_VERIFIED = "verified"
OUTCOME_REFUSED = "refused"
OUTCOME_FAILED = "failed"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def find_component(name: str) -> dict | None:
    """Locate a skill or agent by its frontmatter `name` (falling back to filename
    stem), the same lookup `catalog.py` performs per-plugin.
    """
    for plugin_dir in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        for kind, subdir in (("skill", "commands"), ("agent", "agents")):
            d = plugin_dir / subdir
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.md")):
                meta = parse_frontmatter(f) or {}
                if meta.get("name", f.stem) == name or f.stem == name:
                    return {"name": name, "path": f, "plugin": plugin_dir,
                             "kind": kind, "meta": meta}
    return None


def all_components() -> list[dict]:
    """Every skill and agent this suite ships, across every plugin."""
    out = []
    for plugin_dir in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        for kind, subdir in (("skill", "commands"), ("agent", "agents")):
            d = plugin_dir / subdir
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.md")):
                meta = parse_frontmatter(f) or {}
                name = meta.get("name", f.stem)
                out.append({"name": name, "path": f, "plugin": plugin_dir,
                            "kind": kind, "meta": meta})
    return out


def eponymous_owner(script: Path) -> str | None:
    """The name of the component this script is `script.stem == name` for, if any.

    A component's prose routinely points at a script it doesn't own — a
    "gather evidence" step in a prose-authoring skill running `audit_tokens.py`
    to see what it finds, the way `establish-interaction-spec` does, is not
    that skill's own mechanical part; it's borrowing `audit-tokens`'s. Without
    this check, verify.py silently attributed audit-tokens's own result to a
    completely different component — found by running against real, prose-
    heavy docs, not the clean fixture this script was first tested against.
    """
    for c in all_components():
        if script.stem == c["name"].replace("-", "_"):
            return c["name"]
    return None


def backing_scripts(component: dict) -> list[Path]:
    """Distinct plugin-relative `.py` files this component's markdown names,
    resolved and deduplicated. Reuses the CI gate's own regex rather than
    re-deriving what a plugin-relative script reference looks like.
    """
    text = component["path"].read_text()
    plugin_dir = component["plugin"]
    found: set[Path] = set()
    for m in PLUGIN_PATH.finditer(text):
        target = m.group(1).rstrip(TRAILING)
        if not target.endswith(".py") or Path(target).name in SHARED_UTILITIES:
            continue
        full = plugin_dir / target
        if full.is_file():
            found.add(full)
    return sorted(found)


def resolve_project(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).resolve()
        if not (p / ".backend-suite").is_dir():
            print(f"verify.py: {p} has no .backend-suite/ profile — refusing to "
                  f"guess a project.", file=sys.stderr)
            return None
        return p
    try:
        return project_root()
    except SystemExit:
        # project_root() already explained itself on stderr.
        return None


def project_name(target: Path) -> str | None:
    profile = target / ".backend-suite" / "profile.json"
    if not profile.is_file():
        return None
    try:
        return (json.loads(profile.read_text()).get("project", {}) or {}).get("name")
    except ValueError:
        return None


COMMIT_RECORDED = "recorded"
COMMIT_CANNOT_DETERMINE = "cannot-determine"
COMMIT_UNKNOWN = "unknown"  # read-side only: a record written before #151


def verified_against(target: Path) -> dict:
    """Which project, and which state of it. An unreadable HEAD is named, not omitted."""
    stamp: dict = {"project": project_name(target), "path": str(target)}
    sha, dirty = head_stamp(target)
    if sha is None:
        stamp.update(commit=None, commit_status=COMMIT_CANNOT_DETERMINE, dirty=None,
                     commit_note="git could not read HEAD here (not a git repo, no "
                                 "commits yet, or git unavailable) — this record's "
                                 "staleness can never be computed")
    else:
        stamp.update(commit=sha, commit_status=COMMIT_RECORDED, dirty=dirty)
    return stamp


def record_commit(record: dict) -> tuple[str, str | None]:
    """(status, sha) for any evidence record, old or new.

    A record with no `commit_status` predates #151: it reads as `unknown`, never
    as current — absence of a commit is not evidence of no change.
    """
    va = record.get("verified_against") or {}
    status = va.get("commit_status")
    sha = va.get("commit")
    if status == COMMIT_RECORDED and isinstance(sha, str) and sha:
        return COMMIT_RECORDED, sha
    if status == COMMIT_CANNOT_DETERMINE:
        return COMMIT_CANNOT_DETERMINE, None
    return COMMIT_UNKNOWN, None


def changed_since(target: Path, sha: str) -> list[str] | None:
    """Files differing between <sha> and the working tree, or None if git cannot say."""
    try:
        proc = subprocess.run(["git", "-C", str(target), "diff", "--name-only", sha],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [l for l in proc.stdout.splitlines() if l.strip()]


def staleness_report(target: Path) -> int:
    ev_dir = target / ".backend-suite" / "evidence"
    records = sorted(ev_dir.glob("*.json")) if ev_dir.is_dir() else []
    if not records:
        print(f"verify.py: no evidence records under {ev_dir} — nothing to date.",
              file=sys.stderr)
        return 2
    counts: dict[str, int] = {}
    for path in records:
        try:
            record = json.loads(path.read_text())
        except ValueError:
            state, line = "unreadable", "record is not valid JSON"
        else:
            status, sha = record_commit(record)
            if status == COMMIT_RECORDED:
                changed = changed_since(target, sha)
                if changed is None:
                    state, line = "cannot-determine", f"verified at {sha[:12]}, git cannot diff against it"
                elif changed:
                    state, line = "stale", f"verified at {sha[:12]}, {len(changed)} file(s) changed since"
                else:
                    state, line = "current", f"verified at {sha[:12]}, nothing changed since"
            elif status == COMMIT_CANNOT_DETERMINE:
                state, line = "cannot-determine", "HEAD was unreadable when verified"
            else:
                state, line = "unknown", "commit unknown (record predates commit stamping)"
        counts[state] = counts.get(state, 0) + 1
        print(f"{path.stem}: {state.upper()} — {line}")
    print(f"\n{len(records)} record(s): " +
          ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) +
          " (project-wide diff, not scoped to each component's subject files)")
    return 0


def write_evidence(target: Path, name: str, payload: dict) -> Path:
    out_dir = target / ".backend-suite" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return out_path


def refuse(name: str, plugin: str | None, target: Path, reason: str) -> dict:
    ts = now_iso()
    return {
        "component": name,
        "plugin": plugin,
        "backing_script": None,
        "verified_against": verified_against(target),
        "verified_at": ts,
        "command_run": None,
        "exit_code": None,
        "outcome": OUTCOME_REFUSED,
        "verification": {"tier": TIER_UNVERIFIED, "verifiedBy": "plugins/backend-suite/bin/verify.py",
                          "timestamp": ts},
        "findings_summary": None,
        "notes": reason,
    }


def run_and_record(name: str, component: dict, script: Path, target: Path) -> dict:
    supports_findings = audit_discovery.supports_findings_flag(script)
    cmd = [sys.executable, str(script)] + (["--findings"] if supports_findings else [])

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(target)

    try:
        proc = subprocess.run(cmd, cwd=str(target), env=env,
                               capture_output=True, text=True, timeout=180)
        exit_code = proc.returncode
        tail_lines = [l for l in (proc.stdout or "").splitlines() if l.strip()]
        summary = tail_lines[-1] if tail_lines else None
        err_tail = "\n".join((proc.stderr or "").strip().splitlines()[-6:]) or None
    except subprocess.TimeoutExpired:
        exit_code = None
        summary = None
        err_tail = "timed out after 180s"

    rel_script = str(script.relative_to(SUITE_REPO))
    ts = now_iso()

    if exit_code == 0:
        outcome = OUTCOME_VERIFIED
        notes = None
    elif exit_code == 2:
        outcome = OUTCOME_REFUSED
        notes = f"the backing script itself refused (exit 2): {err_tail or summary or 'no output'}"
    else:
        outcome = OUTCOME_FAILED
        notes = err_tail if exit_code is not None else "process timed out"

    return {
        "component": name,
        "plugin": component["plugin"].name,
        "backing_script": rel_script,
        "verified_against": verified_against(target),
        "verified_at": ts,
        "command_run": cmd,
        "exit_code": exit_code,
        "outcome": outcome,
        "verification": {
            "tier": TIER_SELF_TESTED,
            "ranWhat": f"ran {rel_script} against {target.name or str(target)} "
                       f"(exit {exit_code})",
            "verifiedBy": "plugins/backend-suite/bin/verify.py",
            "timestamp": ts,
        },
        "findings_summary": summary,
        "notes": notes,
    }


def verify_one(name: str, target: Path) -> int:
    component = find_component(name)
    if component is None:
        print(f"verify.py: no skill or agent named {name!r} in {PLUGINS.relative_to(SUITE_REPO)}/",
              file=sys.stderr)
        evidence = refuse(name, None, target, f"no component named {name!r} found")
        path = write_evidence(target, name, evidence)
        print(f"  refused -> {path.relative_to(target)}")
        return 2

    scripts = backing_scripts(component)
    if not scripts:
        evidence = refuse(name, component["plugin"].name, target,
                           "no ${CLAUDE_PLUGIN_ROOT}/*.py reference found in this "
                           "component's markdown — this looks like a prose skill "
                           "for an LLM to follow, with no deterministic execution "
                           "trace to run mechanically")
        path = write_evidence(target, name, evidence)
        print(f"{name}: refused (no backing script) -> {path.relative_to(target)}")
        return 2

    chosen = scripts[0]
    if len(scripts) > 1:
        # A component's prose often names an unrelated utility script in passing
        # (e.g. "configure this via resolve.py --profile ..."). Prefer the one
        # whose filename actually matches the component's own name — a real
        # naming convention this suite already follows for every audit_*.py —
        # before treating multiple references as genuine ambiguity.
        eponymous = [s for s in scripts if s.stem == name.replace("-", "_")]
        if len(eponymous) == 1:
            chosen = eponymous[0]
        else:
            rels = ", ".join(str(s.relative_to(SUITE_REPO)) for s in scripts)
            evidence = refuse(name, component["plugin"].name, target,
                               f"{len(scripts)} distinct backing scripts referenced "
                               f"({rels}) — which one (if any) is 'the' mechanical part "
                               f"this component claims is not decidable without guessing")
            path = write_evidence(target, name, evidence)
            print(f"{name}: refused (ambiguous backing script) -> {path.relative_to(target)}")
            return 2
    elif chosen.stem != name.replace("-", "_"):
        # Exactly one reference, but it isn't eponymous to THIS component either
        # — check it isn't secretly someone else's. A private implementation
        # script nobody else claims (pipeline.py, extract_copy.py) is fine to
        # run; a script that IS another component's own eponymous mechanical
        # part (audit_tokens.py belongs to audit-tokens) is borrowed, not owned
        # — running it here would attribute a different component's result to
        # this one.
        owner = eponymous_owner(chosen)
        if owner is not None and owner != name:
            evidence = refuse(name, component["plugin"].name, target,
                               f"the only script referenced, {chosen.name}, is "
                               f"{owner!r}'s own eponymous backing script, not this "
                               f"component's — this component's prose merely uses it "
                               f"(e.g. as an evidence-gathering step), so running it "
                               f"here would attribute {owner!r}'s result to {name!r}")
            path = write_evidence(target, name, evidence)
            print(f"{name}: refused (script belongs to {owner!r}) -> {path.relative_to(target)}")
            return 2

    evidence = run_and_record(name, component, chosen, target)
    path = write_evidence(target, name, evidence)
    print(f"{name}: {evidence['outcome']} (exit {evidence['exit_code']}) -> "
          f"{path.relative_to(target)}")
    return {OUTCOME_VERIFIED: 0, OUTCOME_REFUSED: 2, OUTCOME_FAILED: 1}[evidence["outcome"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("component", nargs="?",
                     help="skill or agent name, e.g. audit-tokens")
    ap.add_argument("--all", action="store_true",
                     help="verify every catalogued component, refusing what can't be mechanised")
    ap.add_argument("--project-root", help="project to verify against "
                     "(default: CLAUDE_PROJECT_DIR, or walk up from cwd for .backend-suite/)")
    ap.add_argument("--staleness", action="store_true",
                     help="report, per existing evidence record, whether the project "
                          "has changed since the commit it was verified at")
    args = ap.parse_args()

    if args.staleness:
        if args.component or args.all:
            ap.error("--staleness reads existing records; give it no component or --all")
        target = resolve_project(args.project_root)
        return 2 if target is None else staleness_report(target)

    if not args.component and not args.all:
        ap.error("give a component name, or pass --all")
    if args.component and args.all:
        ap.error("give a component name, or --all, not both")

    target = resolve_project(args.project_root)
    if target is None:
        return 2

    if args.all:
        codes = []
        for component in all_components():
            codes.append(verify_one(component["name"], target))
        failed = any(c == 1 for c in codes)
        print(f"\n{len(codes)} component(s) checked "
              f"({codes.count(0)} verified, {codes.count(2)} refused, {codes.count(1)} failed)")
        return 1 if failed else 0

    return verify_one(args.component, target)


if __name__ == "__main__":
    sys.exit(main())
