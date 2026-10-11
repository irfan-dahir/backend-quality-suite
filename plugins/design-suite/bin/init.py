#!/usr/bin/env python3
"""design-suite init — scaffold a fresh project's `.design-suite/` from templates.

Onboarding a new project used to mean opening an already-onboarded one and
hand-copying/reconstructing the config files: `profile.json`,
`docs.manifest.json`, `exceptions.json`, `arch-rules.json`, and
`hooks.map.json`. That is slow, error-prone, and the reason issue #15 exists.

This script copies the templates in `templates/dot-design-suite/*.template`
into a fresh project's `.design-suite/` directory (plus a copy of the canonical
`profile.schema.json`, so doctor.py's drift check has something to compare
against from day one), substituting `{{PROJECT_NAME}}` where given. It does not decide anything on the project's behalf: every value
that matters is left as a `TODO` for a human to fill in, exactly as
ONBOARDING.md Step 2 describes. Run `doctor.py` afterwards — it is expected to
report unresolved TODO paths until they are filled in or their roles deleted.

## `--from-survey` (RFC-0002 phase 4)

`bin/survey.py` already reads an unknown project from disk. `--from-survey`
seeds the scaffolded profile from its output instead of leaving those particular
TODOs for a human to retype — the **generate** step of RFC-0002 §3b's Gazelle
contract (generate → review → commit → drift). The other three steps are not
this script's: **review** is `doctor.py`, which reports every seeded field as
untrusted and prints the ratified-of-total count; **commit** is the human's;
**drift** is `survey.py --check` and doctor's contradiction check.

Two rules hold this together and neither is negotiable:

  * **Every seeded field is written `inferred`. Never `declared`, never
    `approved`.** A survey found it; no human decided it. Provenance exists so
    that inference cannot wear a human decision's clothes (§3b), and a
    scaffolder that wrote `approved` would defeat the entire design.
  * **A field the survey could not determine stays an explicit TODO.** No
    plausible default, ever. A visible gap gets filled; a confidently-wrong
    value gets trusted. That is the governing principle applied to scaffolding,
    and it is why `tokens.source` — the worst-measured signal in the suite, and
    on both real consumer projects not a file in the repository at all — is
    deliberately absent from the seed table below.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" [--name "My Project"] [--dir .] [--force] [--only profile.json,exceptions.json]
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --from-survey [--survey path/to/survey.json]

Exit 0 on success (including "nothing to do, everything already exists").
Exit 1 if a target file exists and --force was not given.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT  # noqa: E402

TEMPLATE_DIR = PLUGIN_ROOT / "templates" / "dot-design-suite"

# The one state a seeded field may ever carry. Named once, asserted at the write
# site, so that adding a seeder cannot quietly introduce a second state: the
# whole value of provenance is that a machine's proposal cannot be mistaken for
# a human's decision, and there is no code path here that produces any other
# word.
SEEDED_STATE = "inferred"

# Every file this scaffolds, in the order ONBOARDING.md / ADOPTING.md discuss them.
#
# `.gitignore` is scaffolded from `gitignore.template` (leading dot dropped, so
# the template itself isn't hidden in the plugin tree). It is not optional in
# practice: audit findings quote the source they matched, `.design-suite/`'s
# regenerable subdirectories are not covered by a typical project's root
# `.gitignore`, and a scaffolder that stays silent here hands a client repo a
# default of committing code excerpts. Shipping the ignore is the fix; see the
# template's own header for the reasoning.
FILES = [
    "profile.json",
    "docs.manifest.json",
    "exceptions.json",
    "arch-rules.json",
    "hooks.map.json",
    "known-traps.json",
    ".gitignore",
]

# Scaffolded name -> template basename, where the two differ.
TEMPLATE_NAMES = {".gitignore": "gitignore"}


# --------------------------------------------------------------------------- #
# --from-survey: the "generate" step of the Gazelle contract
# --------------------------------------------------------------------------- #

# Stack → source file glob. Only stacks whose glob follows from the manifest
# ALONE are listed. `javascript/typescript` is deliberately absent: a Node
# manifest does not say whether the sources are `.ts`, `.tsx`, `.js` or a mix,
# and the only signal that would decide it is survey.py's file census — which is
# labelled corroboration-only because it read a Flutter repository as JavaScript
# off four committed MkDocs builds. An absent entry leaves the TODO standing,
# which is the correct outcome, not a shortfall.
FILE_GLOB_BY_STACK = {
    "dart/flutter": "**/*.dart",
    "python": "**/*.py",
    "go": "**/*.go",
    "rust": "**/*.rs",
}

# A source root is seeded only from a candidate this confident. survey.py scores
# a conventional directory that exists and holds files at 0.8 and one that exists
# but is empty at 0.2; an empty directory that happens to be conventionally named
# is exactly the plausible default this must not write.
SOURCE_ROOT_CONFIDENCE = 0.8


# The UI-root ranking (survey.py `uiRoots`) is seeded only at or above this
# confidence — survey.py's own UI_SEED_CONFIDENCE, restated because init reads a
# survey.json, which may come from another run, not survey.py's module state.
UI_ROOT_CONFIDENCE = 0.6


def _ui_choice(report: dict) -> dict | None:
    ui = report.get("uiRoots") or {}
    if ui.get("chosen") and ui.get("confidence", 0) >= UI_ROOT_CONFIDENCE:
        return ui
    return None


def _ui_evidence(ui: dict, path: str) -> str:
    cand = next((c for c in ui.get("candidates", []) if c["path"] == path), {})
    runners = ", ".join(ui.get("runnersUp") or []) or "none"
    return (f"ranked first of {len(ui.get('candidates', []))} UI-root candidate(s) by UI "
            f"evidence at confidence {ui['confidence']} ({'; '.join(cand.get('evidence', []))}); "
            f"runners-up: {runners}")


def _seed_adapter(report: dict) -> tuple[object, str] | None:
    adapter = (report.get("stack") or {}).get("candidateAdapter")
    if not adapter:
        return None
    decision = (report.get("stack") or {}).get("uiStackDecision")
    if decision:
        return adapter, (f"the root manifest(s) name {decision['manifestStacks'] or 'no stack'}, "
                         f"but the UI root(s) {decision['chosenRoots']} hold "
                         f"{', '.join(decision['because'])} files, which this adapter reads")
    manifests = ", ".join(m["file"] for m in (report.get("stack") or {}).get("manifestsFound", []))
    return adapter, f"survey.py read a root manifest ({manifests}) and this plugin ships that adapter"


def _seed_framework(report: dict) -> tuple[object, str] | None:
    stack = (report.get("stack") or {}).get("stack")
    if not stack:
        return None
    # The stack is a fact about packaging, not the free-text description this
    # field wants — so it is seeded as a starting point that names its own
    # incompleteness, rather than as an answer. A human ratifying it is expected
    # to rewrite it; a human reading it is not misled about where it came from.
    return (f"{stack} (inferred from the root manifest — replace with the real stack, "
            f"including deliberate non-features so audits do not report them as gaps)",
            "root manifest identified the packaging stack; the design framework itself "
            "is not something a manifest states")


def _seed_source_root(report: dict) -> tuple[object, str] | None:
    # A design suite audits the UI, so the UI ranking answers first. Its first
    # choice is also `root` when several roots are seeded: scripts that read
    # only `source.root` then audit the strongest UI instead of nothing.
    ui = _ui_choice(report)
    if ui:
        return ui["chosen"][0], _ui_evidence(ui, ui["chosen"][0])
    strong = [c for c in report.get("sourceRoots") or []
              if c.get("confidence", 0) >= SOURCE_ROOT_CONFIDENCE]
    if len(strong) != 1:
        return None
    candidate = strong[0]
    return candidate["path"], (f"{candidate['why']}; {candidate['files']} file(s) underneath "
                               f"and no other candidate scored as high")


def _seed_file_glob(report: dict) -> tuple[object, str] | None:
    stack = (report.get("stack") or {}).get("stack")
    glob = FILE_GLOB_BY_STACK.get(stack)
    if not glob:
        return None
    return glob, f"the only source extension a {stack} manifest implies on its own"


# Dotted profile path → seeder. A field absent from this table is a field the
# survey cannot settle, and its TODO survives untouched. `tokens.*` is the
# deliberate headline absence (see the module docstring); so are
# `project.audience` (intent, which no codebase states), `project.singleLocale`
# (a decision, and its absence is meaningful), and every optional `source.*`
# glob, which needs the judgement half — /map-project — not this script.
SEEDERS = {
    "adapters.lang": _seed_adapter,
    "project.framework": _seed_framework,
    "source.root": _seed_source_root,
    "source.fileGlob": _seed_file_glob,
}


def load_survey(path: Path) -> dict:
    """The survey, or a refusal. An unreadable survey is never a seed of nothing."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "surveyVersion" not in data:
        raise ValueError(f"{path} does not look like a survey.json (no surveyVersion)")
    return data


def run_survey(repo: Path) -> Path:
    """Generate `survey.json` for a project that has none."""
    script = PLUGIN_ROOT / "bin" / "survey.py"
    result = subprocess.run([sys.executable, str(script), "--project-root", str(repo)])
    if result.returncode != 0:
        raise RuntimeError(f"survey.py exited {result.returncode}; nothing was seeded")
    return repo / ".design-suite" / "survey.json"


def _set(profile: dict, dotted: str, value) -> None:
    node = profile
    *parents, leaf = dotted.split(".")
    for key in parents:
        node = node[key]
    node[leaf] = value


def _get(profile: dict, dotted: str):
    node = profile
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def seed_profile(profile: dict, report: dict) -> tuple[list[dict], list[str]]:
    """Apply every seeder that has an answer. Returns (seeded, left_as_todo).

    Only fields the survey actually settled are touched; the rest keep the
    template's TODO text verbatim, because the alternative — a plausible default
    — is the failure this whole design exists to prevent.
    """
    stamp = report.get("sourceStamp") or {}
    verified = {}
    if stamp.get("commit"):
        verified = {"commit": stamp["commit"]}
        if stamp.get("workingTreeDirty"):
            verified["dirty"] = True

    entries = profile.setdefault("provenance", {}).setdefault("fields", {})
    entries.pop("_example", None)

    seeded: list[dict] = []
    todo: list[str] = []

    def record(dotted: str, value, evidence: str) -> None:
        # Exactly {state, evidence} — the same whitelist map_project.py enforces
        # on every `inferred` entry. `value` and `verifiedAgainst` are what a
        # human's ratification stamps (doctor computes CONTRADICTED from them);
        # writing them here made map_project.py refuse every proposal on a
        # freshly seeded profile, stalling understand-existing-project at its
        # second step. The survey's commit still travels, inside the evidence.
        where = ""
        if verified:
            where = f" (survey of {verified['commit'][:12]}" + (
                ", dirty tree)" if verified.get("dirty") else ")")
        entry = {"state": SEEDED_STATE,
                 "evidence": f"inferred by survey.py{where}: {evidence}"}
        assert entry["state"] == SEEDED_STATE, "a seeded field may only ever be inferred"
        entries[dotted] = entry
        seeded.append({"field": dotted, "value": value, "evidence": evidence})

    for dotted, seeder in SEEDERS.items():
        if _get(profile, dotted) is None:
            continue  # the template does not carry this field; nothing to seed into
        answer = seeder(report)
        if answer is None:
            todo.append(dotted)
            continue
        value, evidence = answer
        _set(profile, dotted, value)
        record(dotted, value, evidence)

    # Several sibling UI applications: `source.roots` is the only key that can say
    # so (RFC-0002 §3g #3). The template does not carry it, so it is added here,
    # and only from a UI ranking that cleared the bar.
    ui = _ui_choice(report)
    source = profile.get("source")
    if ui and len(ui["chosen"]) > 1 and isinstance(source, dict):
        source["roots"] = list(ui["chosen"])
        record("source.roots", list(ui["chosen"]),
               f"{ui.get('why', '')}; confidence {ui['confidence']}")
    return seeded, todo


TOKEN_GROUP = "discovered"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="project root to scaffold into (default: current directory)")
    ap.add_argument("--name", default=None, help="substituted for {{PROJECT_NAME}} in profile.json")
    ap.add_argument("--force", action="store_true", help="overwrite files that already exist")
    ap.add_argument("--only", default=None,
                     help="comma-separated subset of filenames to write, e.g. 'profile.json,exceptions.json'")
    ap.add_argument("--precommit", action="store_true",
                     help="also wire bin/install_precommit_hook.py into this project's git hooks "
                          "(opt-in: it gates commits on whatever hooks.map.json later marks "
                          "\"preCommit\": true, which is nothing until you add it)")
    ap.add_argument("--from-survey", action="store_true",
                     help="seed profile.json from bin/survey.py's findings instead of leaving "
                          "those fields as TODOs. Every seeded field is written provenance "
                          "'inferred'; anything the survey could not determine stays a TODO")
    ap.add_argument("--survey", default=None,
                     help="path to an existing survey.json to seed from (implies --from-survey; "
                          "default: .design-suite/survey.json, generated if absent)")
    args = ap.parse_args()
    from_survey = args.from_survey or bool(args.survey)

    if not TEMPLATE_DIR.is_dir():
        print(f"no template directory at {TEMPLATE_DIR} — plugin install looks broken", file=sys.stderr)
        return 1

    repo = Path(args.dir).resolve()
    target_dir = repo / ".design-suite"
    target_dir.mkdir(parents=True, exist_ok=True)

    wanted = set(args.only.split(",")) if args.only else set(FILES)
    unknown = wanted - set(FILES)
    if unknown:
        print(f"unknown file(s) in --only: {sorted(unknown)}. Known: {FILES}", file=sys.stderr)
        return 1

    blocked = []
    written = []
    profile_written: Path | None = None
    for name in FILES:
        if name not in wanted:
            continue
        src = TEMPLATE_DIR / f"{TEMPLATE_NAMES.get(name, name)}.template"
        if not src.is_file():
            print(f"missing template for {name} at {src} — plugin install looks broken", file=sys.stderr)
            return 1
        dest = target_dir / name
        if dest.exists() and not args.force:
            blocked.append(dest)
            continue
        text = src.read_text()
        if args.name:
            text = text.replace("{{PROJECT_NAME}}", args.name)
            text = text.replace("TODO_PROJECT_NAME", args.name)
        dest.write_text(text)
        written.append(dest)
        if name == "profile.json":
            profile_written = dest

    # doctor.py checks profile.json against a local copy of the canonical schema
    # (offline $schema resolution) and reports drift if the two disagree — so a
    # fresh project needs its own copy from day one, not just a $schema pointer.
    if "profile.json" in wanted:
        schema_src = PLUGIN_ROOT / "templates" / "profile.schema.json"
        schema_dest = target_dir / "profile.schema.json"
        if schema_src.is_file() and (args.force or not schema_dest.exists()):
            schema_dest.write_text(schema_src.read_text())
            written.append(schema_dest)
        elif schema_dest.exists() and not args.force:
            blocked.append(schema_dest)

    seeded: list[dict] = []
    left_as_todo: list[str] = []
    if from_survey:
        # Only a profile THIS run wrote is seeded. An existing profile may hold
        # ratified values, and overwriting a human decision with a fresh
        # inference inverts the provenance model (RFC-0002 §3h) — so the refusal
        # is loud rather than a silent skip.
        if profile_written is None:
            print("--from-survey: profile.json was not written by this run "
                  "(it already exists, or --only excluded it), so there is nothing to seed. "
                  "Refusing to re-infer over a profile that may already carry human "
                  "decisions.", file=sys.stderr)
            return 1
        try:
            survey_path = Path(args.survey).resolve() if args.survey else \
                (target_dir / "survey.json" if (target_dir / "survey.json").is_file()
                 else run_survey(repo))
            report = load_survey(survey_path)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"--from-survey: {exc}", file=sys.stderr)
            return 1
        profile = json.loads(profile_written.read_text())
        seeded, left_as_todo = seed_profile(profile, report)
        profile_written.write_text(json.dumps(profile, indent=2) + "\n")

    for dest in blocked:
        print(f"skipped (already exists, use --force to overwrite): {dest.relative_to(repo)}")
    for dest in written:
        print(f"wrote {dest.relative_to(repo)}")

    precommit_failed = False
    if args.precommit:
        installer = PLUGIN_ROOT / "bin" / "install_precommit_hook.py"
        print()
        result = subprocess.run([sys.executable, str(installer), "--dir", str(repo)])
        precommit_failed = result.returncode != 0

    if blocked and not written:
        return 1

    if from_survey:
        print()
        print(f"--from-survey: seeded {len(seeded)} field(s) from {survey_path.name}. "
              f"EVERY one is provenance `inferred` — a machine proposed it and nobody has "
              f"reviewed it. Review each before you commit:")
        for item in seeded:
            print(f"  ~ {item['field']} = {item['value']!r}")
            print(f"      why: {item['evidence']}")
        if left_as_todo:
            print(f"  Left as TODO because the survey could not determine them "
                  f"(a visible gap, not a guess): {', '.join(left_as_todo)}")
        unknown = report.get("couldNotDetermine") or []
        if unknown:
            print(f"  The survey also reported {len(unknown)} thing(s) it could not determine "
                  f"at all — see {survey_path.name}.")

    print()
    print("Next steps (see ONBOARDING.md Step 2 and docs/ADOPTING.md):")
    if from_survey:
        print("  1. Fill in every remaining TODO, and ratify or correct the inferred fields above.")
        print("  2. python3 \"${CLAUDE_PLUGIN_ROOT}/bin/doctor.py\"       "
              "# proves every declared path resolves, and prints how many fields "
              "carry a human decision — the inferred ones will read as untrusted until you ratify them")
    else:
        print("  1. Fill in every TODO in the files just written — none of it was guessed for you.")
        print("  2. python3 \"${CLAUDE_PLUGIN_ROOT}/bin/doctor.py\"       # proves every declared path resolves")
    print("  3. python3 \"${CLAUDE_PLUGIN_ROOT}/bin/preflight.py\"    # shows which skills can run here")
    print("  4. If you have no design docs yet: /bootstrap-design-docs")
    if not args.precommit:
        print("  5. Optional: mark fast, invariant audits \"preCommit\": true in hooks.map.json, "
              "then python3 \"${CLAUDE_PLUGIN_ROOT}/bin/install_precommit_hook.py\" to gate commits on them")
    return 1 if (blocked or precommit_failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
