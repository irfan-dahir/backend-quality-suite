#!/usr/bin/env python3
"""backend-suite doctor — validate this project's profile before any skill trusts it.

Checks three things the JSON Schema alone cannot:
  1. every declared path actually resolves (a schema-valid dead path is the
     failure mode that made a config file point at three paths that
     no longer exist);
  2. no absolute or home-relative path is committed (machine-specific, silently
     inert on every other checkout — .claude/settings.json has a live instance);
  3. every doc role in the manifest resolves, and roles owned by another repo
     are declared external rather than left dangling;
  4. per-field provenance (RFC-0002 §3b, §3h): a field a human ratified that the
     tree no longer agrees with is CONTRADICTED and fatal, and every field whose
     provenance is `inferred` or unrecorded is reported as untrusted. The
     ratified-of-total count prints on a healthy run too, so a profile nobody has
     reviewed cannot read like one that was.
  5. declined roles carry a reason, and registered-but-unwritten documents
     (`status: stub`) are named as outstanding work rather than counted as
     documentation this project has.
  6. the hooks map can actually fire: absent, empty, all-disabled, or still
     carrying only the scaffold's TODO entries all mean `audit_on_edit.py` runs
     nothing on save — and its silence then reads exactly like every audit
     passing, which is the one thing this suite refuses to let happen.

Usage:  python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py" [--profile .backend-suite/profile.json]
Exit 0 = healthy, 1 = problems found. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT, project_root  # noqa: E402

from backend_suite.engine import audit_discovery  # noqa: E402
from backend_suite.engine import doc_roles  # noqa: E402
from backend_suite.engine import harness_hooks  # noqa: E402
from backend_suite import scaffold  # noqa: E402
from backend_suite.engine import provenance  # noqa: E402

import audit_safe_repairers as safe_repairers  # noqa: E402

# The path vocabulary and the provenance vocabulary both live in the engine, so
# that this checker and `bin/ratify.py` — the reader and the writer of the same
# states — cannot drift apart. Two copies of a state machine is two copies to
# disagree, which is the trap `resolve_role.py` already documents.
# The interpreter floor this suite is supported on. See check_python_version().
MIN_PYTHON = (3, 9)

ABSOLUTE = provenance.ABSOLUTE
PATH_KEYS = provenance.PATH_KEYS


def walk(node, repo: Path, problems: list[str], trail: str = "",
         seen: set | None = None) -> None:
    """Check every path-valued field, recording which trails were flagged.

    `seen` collects the trails this walk already reported as dead, so the
    provenance check can add "…and a human ratified it" to a finding instead of
    emitting a second, near-identical one for the same dead path.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{trail}.{key}" if trail else key
            if key.startswith("_") or key == "$schema":
                continue
            if isinstance(value, str) and (key in PATH_KEYS or key == "otherSharedDirs"):
                check_path(value, repo, problems, here, seen)
            else:
                walk(value, repo, problems, here, seen)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            here = f"{trail}[{i}]"
            if isinstance(value, str) and trail.endswith("otherSharedDirs"):
                check_path(value, repo, problems, here, seen)
            else:
                walk(value, repo, problems, here, seen)


# Script paths mentioned ANYWHERE in a config file's strings, comments included.
#
# doctor.py used to walk the profile only, and only values under PATH_KEYS — so a
# path buried in a `$namesComment` or a `_readme` was never checked. Three had gone
# stale that way when the scripts moved into this plugin:
#
#   profile.json              $namesComment  lib/theme/app_theme.dart
#   design-audit-config.json  _readme        .backend-suite/doctor.py
#   exceptions.json                          token_pipeline/scripts/audit_tokens.py
#
# Comment keys are exactly where this hides, because they are the only place a config
# explains which tool consumes it — and an instruction to run a script that no longer
# exists is worse than no instruction. So comments ARE scanned here, unlike in walk().
SCRIPT_REF = re.compile(
    r"(?<![\w/.-])((?:\.backend-suite|[a-z_]+_pipeline/scripts|mock_api/scripts|scripts|tooling/scripts)"
    r"/[a-z_]+\.(?:py|sh))")

# Only .py/.sh are in scope. A dead .dart path is a different thing: config values
# that ARE paths get checked by walk()/PATH_KEYS, and a .dart file named in prose is
# usually there to explain a removal — this file's own _readme mentions
# `lib/app/theme/app_theme.dart` and a `components.dart` barrel precisely because both
# were deleted, and flagging that sentence would be wrong. If you ever widen this
# regex to .dart, that distinction is semantic and will need an exemption list with
# reasons; it does not need one today.
CANONICAL_SCHEMA = PLUGIN_ROOT / "templates" / "profile.schema.json"


def _schema_paths(node: dict, prefix: str = "") -> set:
    """Every property path a JSON Schema declares, flattened."""
    out = set()
    for key, value in (node.get("properties") or {}).items():
        out.add(prefix + key)
        if isinstance(value, dict):
            out |= _schema_paths(value, prefix + key + ".")
    return out


def check_schema_drift(repo: Path) -> tuple[list[str], list[str]]:
    """The consumer's schema copy vs the plugin's canonical one.

    The schema describes the SUITE's contract, not any one project's, so it lives in
    the plugin. Consumers keep a copy because editors resolve `$schema` from disk and
    an offline copy is what makes that work — but a copy nobody compares is a fork
    waiting to happen.

    Both consumers were found carrying their own: 341 and 300 lines. Structurally
    identical, as it turned out, but only by luck — nothing had ever compared them,
    and one had already grown a `debt` property in a working tree.

    Compares PROPERTY PATHS, not bytes. Descriptions and comments are allowed to
    differ — a project may usefully annotate its own copy — while a property present
    in one and not the other is a real fork, because it means the two disagree about
    what a valid profile IS.
    """
    problems: list[str] = []
    ahead: list[str] = []
    local = repo / ".backend-suite" / "profile.schema.json"
    if not CANONICAL_SCHEMA.is_file():
        return ([f"the plugin ships no canonical schema at "
                 f"{CANONICAL_SCHEMA.name} — nothing to compare against"], ahead)
    if not local.is_file():
        # Not a finding. A project may rely on the plugin's copy and keep none.
        return problems, ahead
    try:
        canon = _schema_paths(json.loads(CANONICAL_SCHEMA.read_text()))
        mine = _schema_paths(json.loads(local.read_text()))
    except ValueError as exc:
        return ([f".backend-suite/profile.schema.json: invalid JSON ({exc})"], ahead)

    # Two directions, two severities — they are not the same failure.
    #
    # AHEAD (extra properties) is usually a project piloting something that has not
    # landed upstream yet, which is how a suite feature is supposed to start. Failing
    # on it would block the very work that grows the schema. Reported loudly, not
    # fatally: this caught a `debt` property mid-flight, and the right response was
    # "land it upstream", not "stop".
    #
    # BEHIND (missing properties) is fatal. The copy no longer describes what a valid
    # profile is, so an editor validating against it accepts profiles the suite will
    # reject, or flags valid ones — worse than having no copy at all.
    for extra in sorted(mine - canon):
        ahead.append(
            f"{extra!r} — not in the canonical schema. If it is real, land it "
            f"upstream; if not, this copy has forked")
    for missing in sorted(canon - mine):
        problems.append(
            f".backend-suite/profile.schema.json is missing {missing!r}, which the "
            f"plugin's canonical schema declares. Re-sync the copy")
    return problems, ahead


def check_script_pointers(repo: Path, files: list[Path]) -> list[str]:
    """Script paths inside config strings that do not exist."""
    problems: list[str] = []
    for f in files:
        if not f.is_file():
            continue
        try:
            raw = f.read_text()
        except OSError:
            continue
        for hit in sorted(set(SCRIPT_REF.findall(raw))):
            rel = f.relative_to(repo) if repo in f.parents or f.parent == repo else f
            if not (repo / hit).exists():
                problems.append(
                    f"{rel}: references {hit!r}, which does not exist. A config that "
                    f"names the tool consuming it must name one that is actually there")
    return problems


_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": (int,),  # bool excluded explicitly below
    "number": (int, float),
    "null": type(None),
}


def _check_type(node, expected: str) -> bool:
    """isinstance, but bool is not an int and 'integer' rejects float."""
    if expected == "integer":
        return isinstance(node, int) and not isinstance(node, bool)
    if expected == "boolean":
        return isinstance(node, bool)
    if expected == "number":
        return isinstance(node, (int, float)) and not isinstance(node, bool)
    py_type = _TYPE_MAP.get(expected)
    if py_type is None:
        return True  # unknown/unsupported type keyword — don't fail closed on it
    return isinstance(node, py_type)


def _resolve_ref(ref: str, root: dict) -> dict:
    """Resolve a local `#/$defs/...` pointer. Anything else is left alone."""
    if not ref.startswith("#/"):
        return {}
    node = root
    for part in ref[2:].split("/"):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node


def _validate_node(node, schema: dict, root: dict, path: str, problems: list[str]) -> None:
    """Minimal recursive JSON-Schema check: type, required, additionalProperties, enum,
    $ref, oneOf, const, pattern, items, minItems, minLength.

    Not a general-purpose validator — no $id resolution, no remote refs, no
    format/if-then-else — but those are not the shapes this schema uses, and this
    covers every keyword `profile.schema.json` actually contains. It exists because
    doctor previously checked only top-level keys: a wrong type, a missing nested
    required field, or an unknown key three levels down (e.g. `docs.externalRoles.<name>.repo`
    misspelled, or `adapters.langauge` instead of `adapters.lang`) passed silently
    and was the most common failure a new project hit, per issue #14.
    """
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], root)
        if not schema:
            return

    if "oneOf" in schema:
        sub_problems = []
        matched = 0
        for sub in schema["oneOf"]:
            trial: list[str] = []
            _validate_node(node, sub, root, path, trial)
            if not trial:
                matched += 1
            else:
                sub_problems.append(trial)
        if matched == 0:
            problems.append(
                f"{path or '(root)'}: does not match any of the allowed shapes "
                f"({len(schema['oneOf'])} alternatives; e.g. {sub_problems[0][0]!r})"
                if sub_problems and sub_problems[0] else
                f"{path or '(root)'}: does not match any of the allowed shapes")
        return

    # Without this the enum keyword validates nothing, and a closed vocabulary
    # (projectKind) would accept any string while appearing to be enforced.
    if "enum" in schema and node not in schema["enum"]:
        problems.append(
            f"{path or '(root)'}: must be one of "
            f"{', '.join(repr(v) for v in schema['enum'])}, got {node!r}")
        return

    if "const" in schema and node != schema["const"]:
        problems.append(f"{path or '(root)'}: must be {schema['const']!r}, got {node!r}")
        return

    # `enum` was in the schema before it was in this validator, which meant
    # release.versionSources[].kind accepted any string at all while the schema
    # said it accepted three — a closed vocabulary enforced by nobody. The
    # provenance states are a closed vocabulary too, and the one value that must
    # NOT appear there (`contradicted`, which is computed) is only kept out by
    # this keyword actually running.
    if "enum" in schema and not any(node == allowed and type(node) is type(allowed)
                                    for allowed in schema["enum"]):
        problems.append(
            f"{path or '(root)'}: {node!r} is not one of {schema['enum']!r}")
        return

    expected = schema.get("type")
    if expected and not _check_type(node, expected):
        problems.append(
            f"{path or '(root)'}: expected {expected}, got "
            f"{type(node).__name__} ({node!r})")
        return  # further checks assume the right shape; don't cascade

    if isinstance(node, str):
        pattern = schema.get("pattern")
        if pattern and not re.match(pattern, node):
            problems.append(f"{path or '(root)'}: {node!r} does not match required pattern")
        min_len = schema.get("minLength")
        if min_len is not None and len(node) < min_len:
            problems.append(f"{path or '(root)'}: must not be empty")

    if isinstance(node, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in node:
                problems.append(f"{path + '.' if path else ''}{key}: missing required key")
        additional = schema.get("additionalProperties", True)
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if key.startswith("_") or key == "$schema":
                continue
            if key in props:
                _validate_node(value, props[key], root, here, problems)
            elif additional is False:
                problems.append(
                    f"{here}: not a key the schema knows about. Either add it to the "
                    f"schema or remove it — an unrecognised key is read by nothing "
                    f"while looking exactly like configuration")
            elif isinstance(additional, dict):
                _validate_node(value, additional, root, here, problems)

    if isinstance(node, list):
        item_schema = schema.get("items")
        min_items = schema.get("minItems")
        if min_items is not None and len(node) < min_items:
            problems.append(f"{path or '(root)'}: needs at least {min_items} item(s)")
        if isinstance(item_schema, dict):
            for i, item in enumerate(node):
                _validate_node(item, item_schema, root, f"{path}[{i}]", problems)


def check_against_schema(profile: dict, schema_path: Path) -> list[str]:
    """The structural half of the schema, enforced in stdlib.

    `profile.schema.json` was shipped alongside the profile and documented in
    ADOPTING.md as the thing that validates it — and nothing ran it. Not CI, not
    a skill, not this script. A gate nobody executes is the failure this suite
    exists to forbid, and it was sitting inside the suite's own scaffolding.

    Full JSON Schema needs a dependency these tools do not take, so this walks the
    schema recursively in stdlib and enforces the keywords `profile.schema.json`
    actually uses: type, required (at every level, not just the top), unknown keys
    under `additionalProperties: false` (at every level), `$ref`/`$defs`, `oneOf`,
    `const`, `pattern` (the repo-relative-path check), and array `items`/`minItems`.
    This is what turns a wrong type, a misspelled nested key, or a missing nested
    required field — the most common failure a new project hits per issue #14 — into
    a reported problem instead of a silently "healthy" profile. Still not full JSON
    Schema: no `format` enforcement, no remote `$ref`, no `if`/`then`/`else`. None
    of those are used here, so this says what it does rather than implying full
    coverage.
    """
    if not schema_path.is_file():
        # Returning [] silently was the same failure this function's own docstring
        # describes: a gate nobody executes. It was found in the wild — a project declared
        # `"$schema": "../.backend-suite/profile.schema.json"` pointing at a file that did
        # not exist, this returned no problems, and doctor printed "profile healthy". The
        # profile had a type error in it at the time.
        #
        # A missing schema is not a passing check, so say so. It is not fatal either —
        # a project may legitimately not have copied the schema in yet — so this reports
        # rather than exits, and the caller decides.
        return [
            f"SKIPPED: no schema at {schema_path} — the structural check did not run. "
            f"Copy templates/profile.schema.json into .backend-suite/ to enable it. "
            f"(This is a gap in coverage, not a healthy profile.)"
        ]
    try:
        schema = json.loads(schema_path.read_text())
    except ValueError as exc:
        return [f"{schema_path.name} is not valid JSON: {exc}"]

    if not isinstance(profile, dict):
        return [f"{schema_path.name}: profile must be a JSON object, "
                f"got {type(profile).__name__}"]

    problems: list[str] = []
    _validate_node(profile, schema, schema, "", problems)
    return problems


PRECOMMIT_SENTINEL = "backend-suite:precommit-hook"


def check_precommit_wiring(repo: Path) -> list[str]:
    """A project that marked an audit "preCommit": true but never ran the
    installer has an entry that reads as enforced and isn't — the same
    "reports nothing but looks clean" trap this project keeps designing
    against, one layer up: the map looks like a gate, but nothing calls it.
    """
    map_path = repo / ".backend-suite" / "hooks.map.json"
    if not map_path.is_file():
        return []
    try:
        entries = json.loads(map_path.read_text()).get("entries", [])
    except (OSError, ValueError):
        return []  # the malformed-JSON case is reported elsewhere (audit_on_edit).
    if not any(isinstance(e, dict) and e.get("preCommit") and not e.get("disabled")
               for e in entries):
        return []

    git_hook = repo / ".git" / "hooks" / "pre-commit"
    framework_config = repo / ".pre-commit-config.yaml"
    installed = (
        (git_hook.is_file() and PRECOMMIT_SENTINEL in git_hook.read_text())
        or (framework_config.is_file() and PRECOMMIT_SENTINEL in framework_config.read_text())
    )
    if installed:
        return []
    return [
        "hooks.map.json declares a \"preCommit\": true entry, but no pre-commit hook "
        "is installed (checked .git/hooks/pre-commit and .pre-commit-config.yaml) — "
        "run bin/install_precommit_hook.py, or those audits are not actually gating "
        "commits."
    ]


def check_hooks_map_disabled_audits(repo: Path) -> list[str]:
    """A map entry that registers an audit the suite has since switched off.

    doctor's job is to find config that looks live and isn't, and this is the
    purest example of it: the entry sits in the map, the project believes that
    check is watching its edits or gating its commits, and the audit refuses on
    every invocation. The runners now name it at run time, but a developer only
    sees that when they happen to trigger the hook — doctor is where someone
    goes to ask "is my setup honest?", so it has to answer this one too.

    Reported whether or not the entry is preCommit: an advisory on-save entry
    pointing at a dead audit is the same lie, just quieter.
    """
    map_path = repo / ".backend-suite" / "hooks.map.json"
    if not map_path.is_file():
        return []
    try:
        entries = json.loads(map_path.read_text()).get("entries", [])
    except (OSError, ValueError):
        return []  # the malformed-JSON case is reported elsewhere (audit_on_edit).

    problems = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("disabled"):
            continue
        hit = audit_discovery.disabled_in_command(entry.get("command"))
        if hit is None:
            continue
        audit, reason = hit
        problems.append(
            f"hooks.map.json entry {entry.get('name', '?')!r} runs {audit}, which is "
            f"DISABLED ({reason['reason']}). It refuses with exit 2 on every trigger — "
            f"it is not checking anything, and its quiet must not be read as a pass. "
            f"Remove the entry, or track the path back in "
            f"backend_suite/engine/audit_discovery.DISABLED."
        )
    return problems


# The placeholder test is shared with hooks/audit_on_edit.py — see
# backend_suite/scaffold.py for why it must be one definition.
_entry_is_placeholder = scaffold.entry_is_placeholder


def check_hooks_map_configured(repo: Path) -> list[str]:
    """A hooks map that will never fire — absent, empty, all-disabled, or scaffold.

    This is the governing principle aimed at the suite's own scaffold. The
    template shipped a single TODO-shaped entry whose glob ("TODO: e.g.
    'lib/**/*.dart'") matches no path a human ever saves. `audit_on_edit.py`
    then did exactly nothing on every edit, by design and without complaint —
    absence of a map is deliberately silent there, because most projects adopt
    entries one at a time and a nag on every save is how a hook gets uninstalled.

    The consequence is a project that installs the suite, sees a
    `hooks.map.json` in its tree, believes its saves are audited, and receives
    the same silence a clean codebase would produce. Nothing anywhere reported
    it. doctor is where someone goes to ask whether their setup is honest, so
    this is the one place it has to be said — and it is said once, on demand,
    rather than on every keystroke.

    An all-disabled map is included deliberately: `disabled: true` is documented
    as "keep the entry, stop running it", which is a legitimate choice, but a map
    where EVERY entry is switched off audits exactly as much as an empty one.
    """
    map_path = repo / ".backend-suite" / "hooks.map.json"
    fix = ("Copy a working entry from "
           "plugins/backend-suite/templates/dot-backend-suite/hooks.map.json.template "
           "(it ships one live, advisory, non-blocking token-drift entry) and narrow "
           "its glob to this project's source.fileGlob.")

    if not map_path.is_file():
        return [
            "no .backend-suite/hooks.map.json — nothing runs on save, and nothing "
            "says so. An absent map is a legitimate choice, but it is not the same "
            f"as a project whose on-save audits are clean. {fix}"
        ]
    try:
        entries = json.loads(map_path.read_text()).get("entries", [])
    except (OSError, ValueError):
        return []  # the malformed-JSON case is reported elsewhere (audit_on_edit).
    if not isinstance(entries, list):
        return []  # shape is the schema's problem, not this check's.

    live = [e for e in entries if isinstance(e, dict) and not e.get("disabled")]
    if not live:
        which = "empty" if not entries else "every entry disabled"
        return [
            f"hooks.map.json is registered but inert ({which}) — audit_on_edit.py "
            f"runs nothing on save and reports nothing, which is indistinguishable "
            f"from every audit passing. {fix}"
        ]

    placeholders = [e for e in live if _entry_is_placeholder(e)]
    if len(placeholders) < len(live):
        return []  # at least one real entry — the map does something.
    names = ", ".join(repr(e.get("name", "?")) for e in placeholders)
    return [
        f"every live hooks.map.json entry is still scaffold text ({names}) — a TODO "
        f"glob matches no file, so the hook fires on nothing and stays silent, which "
        f"reads exactly like a clean project. {fix}"
    ]


# A bare skill/script name pulled out of a fixHint or repair.command value.
# Unlike audit_safe_repairers.SCRIPT_RUN/SKILL_RUN, these fields are not prose
# sentences — a project writes the command itself ("/sync-mock-api <contract>",
# or ["some-script.py", "--files"]), with no "run"/"Fix with" wrapper to key
# off. So the extraction here is simpler: pull the first script-shaped or
# skill-shaped token out of the value directly.
_FIXHINT_SCRIPT = re.compile(r"([A-Za-z_][A-Za-z0-9_./-]*\.(?:py|sh))\b")
_FIXHINT_SKILL = re.compile(r"^(/[a-z][a-z0-9-]*)\b")


def _fix_hint_target(value) -> tuple[str, str] | None:
    """(kind, name) named by a fixHint string or a repair.command argv, or None.

    `repair.command` may be a list (argv) or a string; a fixHint is always a
    string. Only the first token matters for command lists — the schema
    requires `command` to be the repairer's own invocation, not a shell
    pipeline, so later argv entries are flags/paths, not another program to
    vet.
    """
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith("/"):
        m = _FIXHINT_SKILL.match(value)
        return ("skill", m.group(1)) if m else None
    m = _FIXHINT_SCRIPT.search(value)
    # Normalised to a basename: a fixHint/repair.command routinely spells the
    # plugin's own scripts as a CLAUDE_PLUGIN_ROOT-prefixed bin/ path, and
    # safe-repairers.json is keyed on the bare script name (see its own
    # `invocation` field description) — comparing the full path would report a
    # vetted script as unvetted just because of how it was pathed.
    return ("script", m.group(1).rsplit("/", 1)[-1]) if m else None


def check_fix_hints_are_safe(repo: Path) -> list[str]:
    """A consumer's own hooks.map.json can recommend a repair too, and nothing
    was checking THAT one.

    audit_safe_repairers.py closes this hole for the plugin's own bin/,
    backend_suite/engine/, hooks/, commands/, and agents/ text — every "run
    <script>" or "Fix with: <script>" sentence there has to name something on
    templates/safe-repairers.json or be exempted with a reason. But a
    consumer's `fixHint` ("Command to suggest when this entry reports
    something") and `repair.command` (actually EXECUTED at commit time by
    run_precommit_audits.py, per hooks.map.schema.json) are project-authored
    values that gate never sees, because they do not live in the plugin at
    all. A project could declare `"fixHint": "some-destructive-script.sh"` —
    or worse, `"repair": {"command": "some-destructive-script.sh", ...}`,
    which actually RUNS on every commit — and nothing would ever ask whether
    that script is any safer than sync_mock_api.py was before issue #116.

    This does not (cannot) vet an arbitrary project script's internals the way
    an allowlist entry attests to a plugin script's. What it CAN do is refuse
    to treat "nobody objected" as equivalent to "someone checked" — the same
    principle as check_hooks_map_disabled_audits just above. A script or skill
    named here that also happens to be a PLUGIN entry point is checked against
    the real allowlist; anything else is reported so a human has to look at it
    once, rather than never.
    """
    map_path = repo / ".backend-suite" / "hooks.map.json"
    if not map_path.is_file():
        return []
    try:
        entries = json.loads(map_path.read_text()).get("entries", [])
    except (OSError, ValueError):
        return []  # malformed JSON is reported elsewhere (audit_on_edit).

    try:
        allowlist = safe_repairers.load_allowlist()
    except SystemExit as exc:
        return [f"hooks.map.json: could not check fixHint/repair.command safety "
                f"— {exc}"]

    problems: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "?")

        hint_target = _fix_hint_target(entry.get("fixHint"))
        if hint_target:
            kind, target = hint_target
            covered = (target in allowlist if kind == "skill"
                      else safe_repairers._covered(target, "", allowlist))
            if not covered:
                problems.append(
                    f"hooks.map.json entry {name!r}: fixHint suggests "
                    f"{target!r}, which is not on the plugin's safe-repairers "
                    f"allowlist ({safe_repairers.ALLOWLIST}). "
                    f"A suggested fix is exactly the sentence shape that "
                    f"deleted correct data in issue #116 — confirm {target!r} "
                    f"emits a diff or refuses to write destructively before "
                    f"pointing developers at it, the same bar "
                    f"templates/safe-repairers.schema.json sets for the "
                    f"plugin's own scripts")

        repair = entry.get("repair")
        if isinstance(repair, dict):
            cmd_target = _fix_hint_target(repair.get("command"))
            if cmd_target:
                kind, target = cmd_target
                covered = (target in allowlist if kind == "skill"
                          else safe_repairers._covered(target, "", allowlist))
                if not covered:
                    problems.append(
                        f"hooks.map.json entry {name!r}: repair.command runs "
                        f"{target!r} at COMMIT TIME (run_precommit_audits.py "
                        f"executes this automatically), and it is not on the "
                        f"safe-repairers allowlist. This is the live-execution "
                        f"version of the fixHint problem above — an unvetted "
                        f"repair command here does not just get suggested to a "
                        f"human, it runs unattended on every commit that "
                        f"touches a matching file")
    return problems


REGENERABLE_DIRS = (".backend-suite/findings", ".backend-suite/evidence",
                    ".backend-suite/.golden_local_ab")


def _declared_output_globs(profile: dict) -> list[str]:
    """Findings globs under the output directory this project declares.

    Returned as globs rather than a bare directory: the output dir legitimately
    holds hand-authored config alongside generated findings, so naming the whole
    directory would report files that belong in git.
    """
    out = (profile.get("audits") or {}).get("outputDir")
    if not isinstance(out, str) or not out.strip() or out.startswith("TODO"):
        return []
    out = out.strip().strip("/")
    return [f"{out}/*findings*.json", f"{out}/*.findings.json"]


def check_regenerable_not_tracked(repo: Path, profile: dict) -> list[str]:
    """Regenerable audit output committed into the repository.

    An audit finding quotes the source line it matched — that is what makes a
    finding actionable, and also what makes it a disclosure. The literals a
    token audit greps for (a bare string in a widget constructor) are the same
    shape a hardcoded credential has, so a committed findings file publishes
    code excerpts, into a client repository, by default.

    A `.gitignore` alone cannot fix this: ignore rules do not apply to paths
    git already tracks, so a project that committed findings once keeps
    committing them silently forever. That is the case this check exists for —
    same shape as `/audit-assets`'s check H ("renders/ or outputs/ files
    tracked by git"), which already treats a bypassed ignore as a finding
    rather than assuming the ignore worked.

    Reports rather than exits: untracking a file is a decision with history
    implications (the content stays in past commits either way), so this names
    the problem and the fix and leaves the call to a human.
    """
    # Audits do not all write under .backend-suite/. A project declares its own
    # output directory in the profile, and that is where most findings land —
    # measured: a consumer had four findings files there, three enumerated in
    # .gitignore and a fourth (added with a later audit) tracked and exposed,
    # quoting source verbatim. Checking only the fixed dirs above is how a
    # check meant to prevent disclosure reported nothing while a disclosure sat
    # in the tree. Ignore-by-enumeration fails open every time an audit is
    # added, which is exactly when nobody is thinking about .gitignore.
    targets = list(REGENERABLE_DIRS) + _declared_output_globs(profile)
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--", *targets],
            cwd=repo, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []  # not a git repo, or git unavailable — not this check's business
    if tracked.returncode != 0:
        return []
    files = [f for f in tracked.stdout.splitlines() if f.strip()]
    if not files:
        return []
    shown = ", ".join(files[:5]) + (f", +{len(files) - 5} more" if len(files) > 5 else "")
    return [
        f"{len(files)} regenerable audit output file(s) are tracked by git ({shown}) — "
        f"these quote matched source lines, so committing them publishes code excerpts. "
        f"A .gitignore does not untrack what git already tracks: run "
        f"`git rm --cached` on them and commit that, then confirm the ignore rule is a "
        f"PATTERN and not a list of filenames — an enumerated list silently stops "
        f"covering the next audit's output. .backend-suite/.gitignore (scaffolded by "
        f"bin/init.py) covers this directory; a project-declared output dir needs its own."
    ]


# --------------------------------------------------------------------------- #
# Per-field provenance (RFC-0002 §3b, §3h)
# --------------------------------------------------------------------------- #

# `contradicted` is the fourth state and the only one that is never written down.
# It is what an `approved`/`declared` field BECOMES when the tree stops agreeing
# with it, computed here on every run. Storing it would let a stale fact be
# re-asserted by hand, and would make "nobody has re-checked this" and "this was
# checked and found false" the same edit.
PROVENANCE_STATES = provenance.STATES
TRUSTED_STATES = provenance.TRUSTED_STATES

profile_leaves = provenance.profile_leaves
lookup = provenance.lookup
_MISSING = provenance.MISSING


def commits_since(repo: Path, sha: str) -> int | None:
    """How many commits HEAD is ahead of `sha`, or None when git cannot say.

    Staleness measured in diffs, not days — §3h rejects a calendar TTL on
    approvals outright, because expiry by date invents re-ratification work on a
    quiet project and stays silent on a busy one.
    """
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-list", "--count", f"{sha}..HEAD"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


def check_provenance(profile: dict, repo: Path,
                     dead_paths: set) -> tuple[list[str], list[str]]:
    """Returns (problems, untrusted) — fatal contradictions, and what is not ratified.

    Two severities, because they are two different failures:

      * a CONTRADICTION is fatal. A human ratified a value and the tree no longer
        agrees; every audit downstream is scoped by a fact that is now false, and
        that is the `routesFile` shape of bug — a check that reports nothing
        because it is pointed somewhere that no longer exists.
      * being UNTRUSTED is not fatal, because a profile with no provenance block
        at all is valid (§6 keeps this additive) and failing those would break
        every consumer on the day this shipped. But it is never silent: the count
        prints on a healthy run too, so "0 of 137 fields are ratified" cannot be
        mistaken for "this profile was reviewed".
    """
    problems: list[str] = []
    untrusted: list[str] = []
    leaves = profile_leaves(profile)
    block = profile.get("provenance") or {}
    entries = block.get("fields") or {}

    for dotted in sorted(entries):
        if dotted.startswith("_"):
            continue  # comment key, same convention as everywhere else in the profile
        entry = entries[dotted]
        if not isinstance(entry, dict):
            problems.append(f"provenance.fields.{dotted}: must be an object, "
                            f"got {type(entry).__name__}")
            continue
        state = entry.get("state")
        if state == "contradicted":
            problems.append(
                f"provenance.fields.{dotted}: 'contradicted' is COMPUTED, never stored. "
                f"Write the state a human actually took ('declared' or 'approved') and "
                f"let doctor derive the contradiction — a hand-written 'contradicted' "
                f"survives the fix that resolves it")
            continue
        if state not in PROVENANCE_STATES:
            problems.append(
                f"provenance.fields.{dotted}: unknown state {state!r}; expected one of "
                f"{list(PROVENANCE_STATES)}")
            continue

        live = lookup(profile, dotted)
        if live is _MISSING:
            problems.append(
                f"provenance.fields.{dotted}: no such field in this profile. A "
                f"ratification of a field nobody has is a ratification of nothing — "
                f"delete the entry, or restore the field it describes")
            continue

        if state == "inferred":
            untrusted.append(
                f"{dotted}: inferred{_why(entry)} — a machine proposed this and no human "
                f"has ratified it. Nothing downstream may treat it as authoritative")
            continue

        # From here the field claims a human decision, so it can be contradicted.
        ratified = entry.get("value", _MISSING)
        if ratified is not _MISSING and ratified != live:
            problems.append(
                f"{dotted}: CONTRADICTED — ratified as {ratified!r}{_who(entry)}, but the "
                f"profile now says {live!r}. The value was edited after ratification, so "
                f"the ratification no longer covers it; re-approve it or restore the value")
        elif isinstance(live, str) and dotted not in dead_paths \
                and _looks_like_path(dotted, live) and not (repo / live).exists():
            problems.append(
                f"{dotted}: CONTRADICTED — ratified as {live!r}{_who(entry)}, and nothing "
                f"is there now. Treat this exactly as `inferred`: refuse to run on it "
                f"rather than audit a path that no longer exists")
        elif dotted in dead_paths:
            problems.append(
                f"{dotted}: CONTRADICTED — the dead path reported above was ratified"
                f"{_who(entry)}, so this is a false human assertion, not just a typo")

        stamp = entry.get("verifiedAgainst") or {}
        sha = stamp.get("commit")
        if not sha:
            untrusted.append(
                f"{dotted}: {state}, but carries no verifiedAgainst.commit — staleness "
                f"cannot be measured. A date would not substitute: §3h measures staleness "
                f"in diffs, not days")
        else:
            behind = commits_since(repo, sha)
            if behind is None:
                untrusted.append(
                    f"{dotted}: verifiedAgainst.commit {sha!r} cannot be read here (not in "
                    f"this repository, a shallow clone, or git is absent) — the stamp "
                    f"cannot be checked, which is not the same as it being current")
            elif behind:
                untrusted.append(
                    f"{dotted}: {state}, last verified against a tree {behind} commit(s) "
                    f"ago ({sha[:12]})"
                    + (" — and that confirmation was made against a dirty working tree"
                       if stamp.get("dirty") else ""))

    unattributed = sorted(set(leaves) - set(entries))
    for dotted in unattributed:
        untrusted.append(f"{dotted}: no provenance entry — how this value got here is "
                         f"unrecorded, so it is untrusted, not approved")
    return problems, untrusted


def _why(entry: dict) -> str:
    evidence = entry.get("evidence")
    return f" ({evidence})" if evidence else ""


def _who(entry: dict) -> str:
    by, on = entry.get("by"), entry.get("on")
    if by and on:
        return f" by {by} on {on}"
    if by:
        return f" by {by}"
    if on:
        return f" on {on}"
    return " (unattributed)"


# Whether a contradiction can honestly be tested against disk — deliberately
# narrow, and shared with the writer so that what doctor calls a false path and
# what ratify.py refuses to approve are the same predicate.
_looks_like_path = provenance.looks_like_path


def check_path(value: str, repo: Path, problems: list[str], where: str,
               seen: set | None = None) -> None:
    if ABSOLUTE.match(value):
        problems.append(f"{where}: absolute or escaping path {value!r} — must be repo-relative")
        if seen is not None:
            seen.add(where)
        return
    if not (repo / value).exists():
        problems.append(f"{where}: {value!r} does not exist")
        if seen is not None:
            seen.add(where)


def check_python_version() -> list[str]:
    """The interpreter floor. Doctor owns it because doctor is the environment check.

    MIN_PYTHON is measured, not aspirational: `str.removeprefix` (3.9) is the
    highest-versioned construct the engine actually uses, and every `X | Y`
    annotation sits behind `from __future__ import annotations`, so none is
    evaluated at runtime. Raise it only alongside a construct that needs it.

    This refuses rather than warning. On an older interpreter the engine fails
    at call time, deep inside whichever audit reaches `removeprefix` first,
    which reads as a defect in that audit rather than in the environment — and
    an audit that dies partway has reported nothing while looking like it ran.
    """
    if sys.version_info < MIN_PYTHON:
        running = ".".join(str(p) for p in sys.version_info[:3])
        want = ".".join(str(p) for p in MIN_PYTHON)
        return [f"Python {running} is below the supported minimum {want}. "
                f"Audits would fail partway through, on a missing stdlib method, "
                f"rather than reporting cleanly. Re-run with a newer python3."]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=".backend-suite/profile.json")
    args = ap.parse_args()

    # Before anything else: a wrong interpreter makes every other finding
    # unreliable, so this refuses instead of adding to the problem list.
    version_problems = check_python_version()
    if version_problems:
        for line in version_problems:
            print(f"UNSUPPORTED ENVIRONMENT: {line}", file=sys.stderr)
        return 1

    repo = project_root()
    profile_path = repo / args.profile
    if not profile_path.is_file():
        print(f"no profile at {args.profile}", file=sys.stderr)
        return 1

    profile = json.loads(profile_path.read_text())
    problems: list[str] = []
    schema_path = profile_path.parent / "profile.schema.json"
    problems += check_against_schema(profile, schema_path)
    dead_paths: set = set()
    walk(profile, repo, problems, "", dead_paths)
    provenance_problems, untrusted = check_provenance(profile, repo, dead_paths)
    problems += provenance_problems

    # Doc roles.
    stubs: list[str] = []
    manifest_rel = profile.get("docs", {}).get("manifest")
    if manifest_rel and (repo / manifest_rel).is_file():
        manifest = json.loads((repo / manifest_rel).read_text())
        stubs = doc_roles.stub_roles(repo, manifest)
        declined = doc_roles.declined_roles(manifest)
        for role, entry in sorted(declined.items()):
            if not doc_roles.decline_reason(entry):
                # A decline exists precisely to distinguish "we decided against it"
                # from "nobody looked". Without a reason it does neither — it just
                # removes the role from view, which is the silence it was meant to
                # replace.
                problems.append(
                    f"docs.declinedRoles.{role}: declared with no reason. A decline "
                    f"with no reason is indistinguishable from an oversight — give "
                    f"it a \"declined\" string, and ideally \"by\" and \"on\"")
            elif doc_roles.decline_reason(entry).startswith("TODO"):
                # An unfilled placeholder is the empty-reason failure wearing a
                # sentence. It passes the check above, resolve.py exits 4 on it,
                # and the skill dutifully reports "declined: TODO: why this
                # project has no…" as though it were the project's decision.
                problems.append(
                    f"docs.declinedRoles.{role}: the reason is still a TODO "
                    f"placeholder. Every skill that needs this role is skipping "
                    f"its check and reporting that placeholder as a decision — "
                    f"write the real reason, or remove the decline entirely if "
                    f"nobody actually decided this")
            if role in (manifest.get("roles") or {}) or role in (
                    manifest.get("externalRoles") or {}):
                problems.append(
                    f"docs.declinedRoles.{role}: also mapped elsewhere in the "
                    f"manifest — a role cannot be both declined and present")
        for role, rel in manifest.get("roles", {}).items():
            if ABSOLUTE.match(rel):
                problems.append(f"docs.roles.{role}: absolute path {rel!r}")
            elif not (repo / rel).exists():
                problems.append(f"docs.roles.{role}: {rel!r} does not exist "
                                f"(delete the role, or move it to externalRoles)")
        for group in ("directories",):
            for name, rel in manifest.get(group, {}).items():
                if not (repo / rel).exists():
                    problems.append(f"docs.{group}.{name}: {rel!r} does not exist")
        for name, ref in manifest.get("externalRoles", {}).items():
            if name.startswith("_"):
                continue
            if not ref.get("repo"):
                problems.append(f"docs.externalRoles.{name}: needs a repo URL")

    # Script pointers inside every config the profile names, comments included.
    audits = profile.get("audits", {}) or {}
    config_files = [repo / args.profile]
    for rel in (audits.get("exceptionsFile"),
                audits.get("archRulesFile"), (profile.get("docs", {}) or {}).get("manifest")):
        if rel:
            config_files.append(repo / rel)

    # Each pipeline's own config, which the profile names by DIRECTORY rather than
    # by file — so the loop above cannot reach them.
    #
    # mock_api/config.json was invisible for exactly that reason: it selects the
    # provider for each seam and its `_comment` names the directory those providers
    # live in, which is precisely the kind of "which tool consumes this" pointer that
    # goes stale when code moves. A config the profile points at indirectly is still
    # a config the profile points at.
    for key, rel in (profile.get("pipelines", {}) or {}).items():
        if key.startswith("_") or not isinstance(rel, str):
            continue
        for name in ("config.json", "manifest.json"):
            candidate = repo / rel / name
            if candidate.is_file():
                config_files.append(candidate)
    problems += check_script_pointers(repo, config_files)
    problems += check_precommit_wiring(repo)
    problems += check_hooks_map_disabled_audits(repo)
    problems += check_hooks_map_configured(repo)
    problems += check_fix_hints_are_safe(repo)
    problems += check_regenerable_not_tracked(repo, profile)
    schema_problems, schema_ahead = check_schema_drift(repo)
    problems += schema_problems
    if schema_ahead:
        print(f"doctor: this project's schema copy is AHEAD of canonical in "
              f"{len(schema_ahead)} place(s) — not a failure, but it should not stay "
              f"true:")
        for a in schema_ahead:
            print(f"  · {a}")
        print()

    # Harness wiring: informational, never a pass. A generated AGENTS.md that a
    # harness's own file hides is silently unread — say so by name.
    from backend_suite import harness_files  # noqa: E402
    wiring = harness_files.wiring(repo)
    if wiring:
        print("doctor: harness wiring — instructions some harnesses will NOT see:")
        for h, status, detail in wiring:
            print(f"  · {h}: {status} — {detail}")
    else:
        print("doctor: harness wiring — no NOT WIRED / SHADOWED harness detected.")
    # Hook wiring per harness — informational, never a problem (a project need
    # not use every harness), but always printed: an unwired harness gets no
    # onboarding offer and no after-edit audits, and saying nothing about it
    # would imply coverage that is not there.
    print(harness_hooks.render(harness_hooks.status(repo)))
    print()

    # Printed on a healthy run too, and before the verdict. An unratified profile
    # that prints nothing about provenance reads as a reviewed one — the governing
    # principle applied to the profile itself.
    leaves = profile_leaves(profile)
    entries = (profile.get("provenance") or {}).get("fields") or {}
    ratified = sum(1 for d, e in entries.items()
                   if isinstance(e, dict) and e.get("state") in TRUSTED_STATES
                   and lookup(profile, d) is not _MISSING)
    print(f"doctor: provenance — {ratified} of {len(leaves)} field(s) carry a human "
          f"decision ('declared' or 'approved').")
    if untrusted:
        print(f"  {len(untrusted)} field(s) are UNTRUSTED. Not a failure, and not a pass "
              f"either — an audit scoped by an unratified field is running on a guess:")
        for u in untrusted:
            print(f"  · {u}")
    print()
    # Stubs are printed on both paths, and named in the healthy line, because the
    # whole point of exit 5 is that a registered-but-unwritten document must never
    # be silently absorbed into a clean bill of health. They are not counted as
    # problems: the profile is not broken, the documentation is unfinished.
    if stubs:
        print(f"backend-suite doctor — {len(stubs)} role(s) are STUBS: registered and "
              f"mapped, but unwritten (status: stub). Outstanding work, not coverage:")
        for role in stubs:
            print(f"  ▫ {role}")
        print()

    if problems:
        print(f"backend-suite doctor — {len(problems)} problem(s):\n")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    stub_note = f"; {len(stubs)} doc role(s) still stubs" if stubs else ""
    print(f"backend-suite doctor: profile healthy; "
          f"{len(config_files)} config file(s) name no dead scripts{stub_note}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
