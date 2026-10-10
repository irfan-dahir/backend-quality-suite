#!/usr/bin/env python3
"""design-suite survey — read an unknown project and say what it found, what it
is guessing, and what it could not determine at all.

RFC-0002 phase 1 (`docs/proposals/RFC-0002-agnostic-drop-in.md` §3a, §3b-ii, §3h).

Two halves, one command:

  survey.py            the DISCOVERY half — writes .design-suite/survey.json
  survey.py --check    the COMPLETENESS half — disk → declared, writes nothing

`survey.json` is a **derived collateral** (`docs/CONCEPTS.md`): regenerable,
disposable, source-stamped, and never written back into `profile.json`,
`docs.manifest.json`, or any context document. This script writes exactly one
file and only when `--write` is in effect; `--check` writes nothing at all, so
it is safe to point at a repository you do not own.

## Why the discovery half is so hedged

Every number in RFC-0002 is measured, and three of the measurements are warnings
rather than encouragements:

  * a file-extension census reads a Flutter repo as JavaScript when four MkDocs
    builds are committed to it, so **root manifests decide the stack and the
    census is corroboration only** — never a conclusion on its own;
  * token-source detection matched `.design-suite/findings/tokens.json`, the
    audit's *own output*, on both real consumers; and on both of them the true
    token source is not in the repository at all, it arrives as a package
    dependency. So tokens are emitted as a **ranked candidate list with reasons**
    and never as a single answer;
  * a root manifest can be a workspace stub, so `sourceRoots` is a list and is
    allowed to be empty — with a reason.

Everything the survey cannot settle lands in `couldNotDetermine`, which is
load-bearing output and not a nicety: a survey with an empty findings list and an
empty `couldNotDetermine` list would be indistinguishable from a survey that did
not run.

## Why the check half exists

All five `doctor.py` checks run declared → disk: they start from a config entry
and ask whether it still resolves. That catches a moved or deleted target and is
blind *by construction* to anything added that no config mentions — an addition
is not a broken path, it is the absence of a path, and absences are invisible to
a checker iterating over what is present (RFC-0002 §3h).

`--check` runs the other direction. Four rules produce its findings — the first
two find **divergence**, the last two find **absence**, which is the reflexion
verdict (`docs/CONCEPTS.md`) no check in the catalogue used to produce:

  1. **Undeclared top-level entries.** A directory at the repository root that no
     config file under `.design-suite/` declares as a path.
  2. **Undeclared siblings.** A config that names one member of a directory
     (`source.sharedComponentDir: lib/shared/components/`) makes an implicit
     completeness claim about that directory. Its siblings on disk that nothing
     declares are reported.
  3. **Undeclared capabilities.** The code routes, and the profile field a check
     reads to find the routes is null. Nothing is missing from disk, so rules 1
     and 2 are blind to it by construction — while the check downstream runs
     against nothing and prints clean. The *adapter* answers whether the project
     has the capability, because the answer is language-shaped, and an adapter
     that cannot answer raises rather than saying no
     (`design_suite/engine/capabilities.py`).
  4. **Schemas that accept keys they never describe.** An object with no
     `additionalProperties: false` validates undescribed keys silently; reported
     where a document actually carries such keys
     (`design_suite/engine/schema_permissiveness.py`).

A path counts as **declared** only when some config string is *entirely* a path
or glob. A path mentioned inside a prose sentence is not a declaration — and
that distinction is the whole reason this check works on the acceptance case: the
portal's profile contains the sentence "The portal has no assets/ directory and
ships no imagery", so a substring sweep over config text would find `assets/`
"mentioned" and stay silent about the six JPEGs that landed 34 days after the
profile was written. Prose mentions are reported separately, as the weaker
signal they are — and a prose mention that *asserts absence* about a path that
exists is exactly the contradiction §3h's `contradicted` state is for.

Exit codes follow `docs/DOC-ROLES.md`: 0 clean, 1 findings, 2 refuse. Stdlib
only, like every other script in `bin/`.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import PLUGIN_ROOT  # noqa: F401  (puts design_suite on sys.path)

MARKER = ".design-suite"
SURVEY_REL = f"{MARKER}/survey.json"
SURVEY_VERSION = 1

# Never walked, never surveyed, never reported as undeclared. Two different
# reasons live in this one set and both matter: VCS/tooling noise, and — more
# importantly — the suite's own output. `.design-suite/` holds findings the
# audits wrote; surveying it is how token detection previously matched
# `.design-suite/findings/tokens.json` and proposed the audit's own output as the
# project's token source.
ALWAYS_SKIP = {
    ".git", ".hg", ".svn", MARKER, "node_modules", "build", "dist", "out",
    ".dart_tool", ".gradle", ".idea", ".vscode", "__pycache__", ".venv", "venv",
    ".next", ".nuxt", ".parcel-cache", "target", "vendor", "coverage",
    ".mypy_cache", ".pytest_cache", ".tox", ".DS_Store", ".claude",
}

# Root manifest → (stack, adapter candidate, conventional source roots, why).
# Manifests are the reliable signal; the census below is not.
MANIFESTS = {
    "pubspec.yaml": ("dart/flutter", "dart", ["lib"], "a root pubspec.yaml is the Dart/Flutter package manifest"),
    # The adapter column was `None` here long after `adapters/tsx.py` shipped —
    # a stale table entry, not a missing adapter. survey then told every
    # JS/TS project "stack 'javascript/typescript' has no adapter in this
    # plugin" while printing `tsx` in the availableAdapters list two lines
    # below, and init_from_survey left `adapters.lang` unset on a stack the
    # plugin could in fact audit. `adapter_reachability()` is the control that
    # stops this silently happening to the next adapter.
    "package.json": ("javascript/typescript", "tsx", ["src", "app", "lib"], "a root package.json is the Node package manifest"),
    "pyproject.toml": ("python", None, ["src"], "a root pyproject.toml is the Python project manifest"),
    "setup.py": ("python", None, ["src"], "a root setup.py is a Python distutils manifest"),
    "go.mod": ("go", None, ["."], "a root go.mod is the Go module manifest"),
    "Cargo.toml": ("rust", None, ["src"], "a root Cargo.toml is the Cargo manifest"),
    "Gemfile": ("ruby", None, ["app", "lib"], "a root Gemfile is the Bundler manifest"),
    "composer.json": ("php", None, ["src"], "a root composer.json is the Composer manifest"),
    "pom.xml": ("java", None, ["src/main/java"], "a root pom.xml is the Maven manifest"),
    "build.gradle": ("java/kotlin", None, ["src/main"], "a root build.gradle is the Gradle manifest"),
    "build.gradle.kts": ("java/kotlin", None, ["src/main"], "a root build.gradle.kts is the Gradle manifest"),
    "Package.swift": ("swift", "swift", ["Sources"], "a root Package.swift is the Swift Package Manager manifest"),
}

# Manifests named by pattern rather than a fixed filename. An Xcode project is a
# *directory* (`MyApp.xcodeproj`), so `(root / name).is_file()` can never see it;
# an app with no Package.swift used to be reported as "no recognisable manifest".
MANIFEST_DIR_GLOBS = {
    "*.xcodeproj": ("swift", "swift", [], "a root *.xcodeproj is an Xcode project"),
}

# Gradle says "JVM", not "UI". The kotlin adapter reads Jetpack Compose, so it is
# proposed only when a Gradle build file (root or one level down — Android puts
# Compose in app/build.gradle.kts) or the version catalog actually enables
# Compose. A plain JVM backend keeps `None`: proposing a UI adapter there would
# sweep service code and print a clean result that means nothing.
GRADLE_STACK = "java/kotlin"
GRADLE_COMPOSE = ("kotlin", re.compile(
    r"compose\s*=?\s*true|androidx\.compose|org\.jetbrains\.compose|plugin\.compose"
    r"|kotlin\.plugin\.compose|compose-bom"),
    "a Gradle build file enables Jetpack Compose, which the kotlin adapter reads")

# Within one manifest's stack, a file census that DOES vote — but only between
# adapters, never on the stack. `package.json` says "JavaScript"; it does not say
# whether the styling lives in .tsx (tsx) or in .vue/.svelte/.css/.scss (web),
# and proposing `tsx` for a Vue project made `audit_tokens` sweep `main.js` and
# report 0 findings over a tree full of hardcoded values. Any file with one of
# these suffixes outside ALWAYS_SKIP switches the proposal.
#   base adapter -> (refined adapter, suffixes that trigger it, why)
ADAPTER_REFINEMENTS = {
    "tsx": ("web", (".vue", ".svelte", ".css", ".scss", ".sass", ".less"),
            "styling lives in single-file components or stylesheets, which only "
            "the web adapter reads"),
}

CENSUS_LANG = {
    ".dart": "dart/flutter", ".ts": "javascript/typescript", ".tsx": "javascript/typescript",
    ".js": "javascript/typescript", ".jsx": "javascript/typescript", ".py": "python",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php", ".java": "java",
    ".kt": "java/kotlin", ".swift": "swift", ".cs": "c#",
    ".vue": "javascript/typescript", ".svelte": "javascript/typescript",
}

# Filename stem → (role, confidence, why). Deliberately conservative: a regex
# over filenames scored 4 confident of 20 on a real zero-state repository, so
# anything not in this table is proposed at low confidence or not at all.
ROLE_BY_STEM = {
    "readme": ("entry-point", 0.5, "README.md is the conventional entry point, but many projects keep their agent instructions elsewhere"),
    "claude": ("instructions", 0.8, "CLAUDE.md is the agent instruction file by convention"),
    "agents": ("instructions", 0.6, "AGENTS.md is an emerging agent-instruction convention"),
    "design": ("design", 0.7, "filename matches the role name"),
    "flows": ("flows", 0.7, "filename matches the role name"),
    "decisions": ("decisions", 0.8, "filename matches the role name"),
    "adr": ("decisions", 0.5, "ADR is the conventional name for a decision record"),
    "backlog": ("backlog", 0.8, "filename matches the role name"),
    "contributing": ("contributing", 0.9, "CONTRIBUTING.md is a near-universal convention"),
    "documentation": ("documentation-rules", 0.6, "filename matches the role name"),
    "brand-voice": ("brand-voice", 0.8, "filename matches the role name"),
    "brand_voice": ("brand-voice", 0.8, "filename matches the role name"),
    "copy": ("copy", 0.6, "filename matches the role name"),
    "brief": ("brief", 0.7, "filename matches the role name"),
    "motion": ("motion", 0.7, "filename matches the role name"),
    "components": ("components", 0.6, "filename matches the role name — but this role is external more often than not"),
    "tokens": ("tokens", 0.5, "filename matches the role name — external more often than not"),
    "accessibility": ("accessibility", 0.7, "filename matches the role name"),
    "api": ("api", 0.6, "filename matches the role name"),
    "changelog": ("changelog", 0.7, "CHANGELOG.md is a near-universal convention"),
    "instructions": ("instructions", 0.7, "filename matches the role name"),
    "responsive": ("responsive", 0.6, "filename matches the role name"),
}

PATHISH = re.compile(r"^[A-Za-z0-9._\-/*{}\[\]]+$")

# Keys whose VALUE is a path by role, even when that value is a bare single
# segment with no `/` and no `.` in it. See `declared_paths` for the measurement
# that made this necessary and for why the set is deliberately narrow.
#
# Same idea as doctor.py's PATH_KEYS, and for the same reason — a field's key
# name, not its value's shape, is what says "this is a path". Kept as a separate
# set rather than imported because the two answer different questions: doctor
# asks "does this declared path still exist" (declared → disk), survey asks
# "does this string declare anything" (disk → declared), and a key can matter to
# one and not the other. If you find yourself syncing them by hand more than
# once, that is the signal to lift one shared set into the engine — not to have
# survey import bin/doctor.py, which would couple two CLIs at import time.
#
# These are SUITE schema key names (profile.schema.json), not project literals:
# no consumer directory name appears here, and none may.
PATH_VALUED_KEYS = {
    "root", "path", "dir", "testRoot", "sharedComponentDir", "baselineDir",
    "goldensDir", "manifest", "configFile", "exceptionsFile", "archRulesFile",
    "resolveVia", "pathInPackage",
}

# Containers every one of whose string members is a path by role, whatever the
# member key is called. `pipelines` is the measured case: its keys name the
# PIPELINE (`assets`, `copy`, `mockApi`), and the value is the directory that
# pipeline's data lives in — so the key name carries no path signal at all and
# the container has to.
PATH_VALUED_CONTAINERS = {"pipelines", "otherSharedDirs"}

# A bare name also qualifies under a key whose name ENDS in a path-ish word —
# `foo Dir`, `fooRoot`, `fooPath`, `fooFile`. Suffix rather than exact match
# because these compound key names are how the schema already spells "this
# is a path" (sharedComponentDir, testRoot, routesFile, goldensDir).
PATH_KEY_SUFFIXES = ("Dir", "Dirs", "Root", "Path", "File")


def _argv_member(trail: str) -> bool:
    """Whether `trail` names a member of a COMMAND, i.e. an argv token.

    The second half of the same 22% measurement. A command is argv, not a path
    list: `["flutter", "test", "--no-pub", "test/sweep"]`. Three of those four
    tokens are not paths at all, and the one that is happens to be — nobody
    DECLARED `test/sweep` by putting it after `flutter test`.

    Reading argv as declarations is not merely untidy, it manufactures findings.
    `verification.goldensUpdateCommand` ends in `test/sweep`, which put `test`
    into the sibling rule's parent set — and the sibling rule then read that as
    "a config names one member of test/, so the rest of test/ is an unmet
    completeness claim" and reported test/fixtures/, test/goldens/ and test/web/
    as undeclared. Three findings, from an implicit claim the profile never
    made. The genuine declaration inside that tree, `verification.goldensDir:
    test/sweep/goldens`, is unaffected and still carries its own claim about
    test/sweep/.

    Bounded the same way the bare-name rule is: by key ROLE, not value shape,
    and by a suite schema key name (`*Command`), never a project literal.
    """
    parts = [p.split("[", 1)[0] for p in trail.split(".") if p]
    return any(p.endswith(("Command", "Commands")) for p in parts)


def _path_valued_key(trail: str) -> bool:
    """Whether `trail`'s leaf names a value that is a path BY ROLE.

    `trail` is the dotted config trail, e.g. `profile.json.source.testRoot` or
    `profile.json.pipelines.assets` or `profile.json.source.otherSharedDirs[1]`.
    """
    parts = [p.split("[", 1)[0] for p in trail.split(".") if p]
    if not parts:
        return False
    leaf = parts[-1]
    if leaf in PATH_VALUED_KEYS or leaf.endswith(PATH_KEY_SUFFIXES):
        return True
    # A member of a path-valued container: either the leaf's parent is one
    # (pipelines.assets) or the leaf itself is (otherSharedDirs[1], whose leaf
    # after stripping the index IS the container name).
    return bool(set(parts[-2:]) & PATH_VALUED_CONTAINERS)


# --------------------------------------------------------------------------- #
# Roots, git, and the source stamp
# --------------------------------------------------------------------------- #

def resolve_root(explicit: str | None) -> Path:
    """The project to survey.

    Unlike `design_suite.project.project_root`, a survey must work on a project
    that has no `.design-suite/` at all — that is the case it exists for. So it
    never looks for the marker, and in particular never walks up to the nearest
    directory that has one: on an unconfigured project nested anywhere inside a
    configured repo, that walk-up silently surveys the *outer* repo and reports
    on the wrong codebase. Every other tool is right to refuse without a
    profile, and `project_root` now applies the same boundary rule as step 3
    below: its walk stops at the nearest git root, so an unconfigured repo
    nested in a configured one refuses there too rather than borrowing the
    outer profile.

    Order, most authoritative first:

      1. `--project-root` — the caller said so.
      2. `CLAUDE_PROJECT_DIR` — Claude Code's own statement of which project the
         session is in (doctor.py honours it too). Refused if the working
         directory lies outside it: the two disagree, and picking one is a guess.
      3. The git root of the working directory — the nearest repository boundary,
         which is what "this project" means for a checkout. Nearest, so a git
         repo nested inside another resolves to the inner one.
      4. The working directory itself, only when it is not in a git repo AND no
         ancestor carries a `.design-suite/`. If one does, the working directory
         may be a subdirectory of that project or a separate project inside it;
         nothing on disk says which, so that is exit 2, named — never a guess.
    """
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"survey: --project-root {explicit!r} is not a directory")
        return root

    here = Path.cwd().resolve()
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        root = Path(env).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"survey: CLAUDE_PROJECT_DIR={env!r} is not a directory. "
                             f"Pass --project-root to say which project to survey.")
        if here != root and root not in here.parents:
            raise SystemExit(f"survey: the working directory {here} is outside "
                             f"CLAUDE_PROJECT_DIR={root} — they disagree about which project "
                             f"this is. Pass --project-root; refusing to guess.")
        return root

    top = git(here, "rev-parse", "--show-toplevel")
    if top:
        return Path(top).resolve()

    for ancestor in here.parents:
        if (ancestor / MARKER).is_dir():
            raise SystemExit(f"survey: {here} is not in a git repository, but {ancestor} "
                             f"has a {MARKER}/ — this may be part of that project or a "
                             f"separate one, and nothing on disk says which. Pass "
                             f"--project-root; refusing to guess.")
    return here


def git(root: Path, *args: str) -> str | None:
    """A read-only git query, or None when git cannot answer.

    None is a real answer here and is recorded as such in the stamp: an
    unstamped survey that claims a commit it never read would be worse than one
    that says it could not look.
    """
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def source_stamp(root: Path) -> dict:
    """What produced this survey, when, and against which tree.

    §3h: a timestamp makes staleness a calendar guess; a commit SHA makes it a
    diff. §7's resolution on a dirty tree: run anyway, and stamp the dirt —
    blocking a survey exactly when it is most useful helps nobody, but a survey
    of an uncommitted tree that reads as a survey of `HEAD` is a lie.
    """
    commit = git(root, "rev-parse", "HEAD")
    status = git(root, "status", "--porcelain")
    stamp = {
        "generatedBy": f"design-suite bin/survey.py v{SURVEY_VERSION}",
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "projectRoot": str(root),
        "commit": commit,
        "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "workingTreeDirty": None,
        "dirtyFiles": [],
        "regenerate": "python3 ${CLAUDE_PLUGIN_ROOT}/bin/survey.py",
        "_note": ("Derived collateral. Regenerable and disposable; never written back "
                  "into profile.json, docs.manifest.json, or any context document."),
    }
    if commit is None:
        stamp["commitUnavailable"] = "git could not be read here (not a repository, or git is absent)"
    if status is not None:
        files = [ln[3:].strip() for ln in status.splitlines() if ln.strip()]
        stamp["workingTreeDirty"] = bool(files)
        stamp["dirtyFiles"] = sorted(files)[:200]
        if len(files) > 200:
            stamp["dirtyFilesTruncated"] = len(files)
    return stamp


# --------------------------------------------------------------------------- #
# Ignore handling
# --------------------------------------------------------------------------- #

class Ignores:
    """A deliberately partial `.gitignore` reader.

    Partial, and says so: it reads the root `.gitignore` only, and supports plain
    globs, directory rules and a leading `/` anchor — not negation, not nested
    ignore files, not `**` in the middle of a pattern. That is enough to keep
    build output out of a survey, and a survey must never claim it was exhaustive
    about what git would ignore. Unsupported rules are collected and surfaced in
    `couldNotDetermine` rather than dropped.
    """

    def __init__(self, root: Path):
        self.patterns: list[str] = []
        self.unsupported: list[str] = []
        gitignore = root / ".gitignore"
        if not gitignore.is_file():
            return
        for raw in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                self.unsupported.append(line)
                continue
            self.patterns.append(line.rstrip("/").lstrip("/"))

    def ignored(self, rel: str) -> bool:
        parts = rel.split("/")
        for pattern in self.patterns:
            if "/" in pattern:
                if fnmatch.fnmatch(rel, pattern) or rel.startswith(pattern + "/"):
                    return True
            elif any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
        return False


def walk(root: Path, ignores: Ignores, max_depth: int = 6):
    """Every non-ignored file under `root`, as repo-relative POSIX paths."""
    out: list[str] = []

    def rec(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.name in ALWAYS_SKIP:
                continue
            rel = entry.relative_to(root).as_posix()
            if ignores.ignored(rel):
                continue
            if entry.is_symlink():
                continue
            if entry.is_dir():
                rec(entry, depth + 1)
            elif entry.is_file():
                out.append(rel)

    rec(root, 0)
    return sorted(out)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

def language_adapters() -> list[str]:
    """Adapter module stems that are actually LANGUAGE adapters.

    Structural rather than a name denylist: a language adapter is a module in
    `design_suite/adapters/` that declares `NAME`, `FILE_GLOBS` and a `checks()`
    — the contract `adapters/__init__.for_project()` consumes. The previous
    version excluded `base`, `__init__` and `verify_*` by name and so reported
    `tailwind_theme` — a helper the loader cannot use as `adapters.lang` — as an
    available adapter. Reading the property instead of maintaining a list is the
    same choice `audit_skill_paths.py`'s rule 5 makes, and for the same reason.

    Text-matched rather than imported: survey runs against a project that may not
    have the suite's dependencies resolved, and importing every adapter to ask it
    a question is a lot of machinery for three greps.
    """
    adapters_dir = PLUGIN_ROOT / "design_suite" / "adapters"
    out = []
    for path in sorted(adapters_dir.glob("*.py")):
        if path.stem in {"base", "__init__"}:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        if all(m in src for m in ("\nNAME = ", "\nFILE_GLOBS = ", "\ndef checks(")):
            out.append(path.stem)
    return out


def adapter_reachability() -> list[str]:
    """Language adapters no root manifest in MANIFESTS names — i.e. adapters the
    survey can never propose.

    This is the control for the defect that made `tsx` unreachable: the adapter
    shipped, `availableAdapters` listed it, and MANIFESTS still said the
    JavaScript/TypeScript stack had no adapter. Nothing errored. An adapter
    present but unreachable is a capability the suite has and denies having,
    which is the governing principle's failure mode pointed inwards.
    """
    named = {a for _s, a, _r, _w in [*MANIFESTS.values(), *MANIFEST_DIR_GLOBS.values()] if a}
    named.add(GRADLE_COMPOSE[0])
    named |= {ADAPTER_REFINEMENTS[a][0] for a in list(named) if a in ADAPTER_REFINEMENTS}
    return [a for a in language_adapters() if a not in named]


def _gradle_compose_evidence(root: Path) -> list[str]:
    """Gradle files (root, one level down, version catalog) that enable Compose."""
    paths = [*root.glob("build.gradle*"), *root.glob("*/build.gradle*"),
             *root.glob("gradle/*.versions.toml")]
    hits = []
    for path in sorted(paths):
        if path.is_file() and not ALWAYS_SKIP.intersection(path.relative_to(root).parts):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if GRADLE_COMPOSE[1].search(text):
                hits.append(path.relative_to(root).as_posix())
    return hits


def detect_stack(root: Path, files: list[str], unknown: list[dict],
                 ui: dict | None = None) -> dict:
    """Stack and candidate adapter, decided by root manifests.

    The census is computed and reported because "how many files of each kind" is
    genuinely useful, and it is labelled `corroborationOnly` because on
    `<design-system-repo>` it reads a Dart repository as JavaScript — 4,722
    `.html` and 910 `.js` ahead of 317 `.dart`, entirely from four committed
    MkDocs builds. It never votes.
    """
    found = [(name, *MANIFESTS[name]) for name in MANIFESTS if (root / name).is_file()]
    for pattern, row in MANIFEST_DIR_GLOBS.items():
        hit = next((p.name for p in sorted(root.glob(pattern)) if p.is_dir()), None)
        if hit:
            found.append((hit, *row))

    census: dict[str, int] = {}
    for rel in files:
        lang = CENSUS_LANG.get(Path(rel).suffix)
        if lang:
            census[lang] = census.get(lang, 0) + 1

    available = language_adapters()

    result = {
        "manifestsFound": [{"file": name, "stack": stack, "why": why}
                           for name, stack, _adapter, _roots, why in found],
        "fileCensus": dict(sorted(census.items(), key=lambda kv: -kv[1])),
        "_censusNote": ("CORROBORATION ONLY — never a conclusion. A committed docs build "
                        "makes a census read the wrong language; measured on a real repo."),
        "availableAdapters": available,
    }

    stacks = {stack for _n, stack, _a, _r, _w in found}
    # The UI decides, when the UI can be found. A design suite audits the code
    # that renders; on a Rails + React or Django + Vue repository the root
    # manifest that names the SERVER language is the wrong vote. Only applied
    # when the root manifests cannot answer on their own (none, several that
    # disagree, or one whose stack has no adapter) — a single-stack repository
    # the manifests already settle is left exactly as it was.
    from_ui = ui_adapter(ui or {}, files, available)
    single_adapter = (len(stacks) == 1
                      and next((a for _n, _s, a, _r, _w in found if a), None))
    if from_ui and not single_adapter and not (
            len(stacks) == 1 and next(iter(stacks)) == GRADLE_STACK
            and _gradle_compose_evidence(root)):
        adapter, ui_stack, because = from_ui
        result["stack"] = ui_stack
        if len(stacks) > 1:
            result["candidateStacks"] = sorted(stacks)
        result["candidateAdapter"] = adapter
        result["uiStackDecision"] = {
            "provenance": "inferred",
            "manifestStacks": sorted(stacks),
            "chosenRoots": ui["chosen"],
            "because": because,
            "why": ("the root manifest(s) name a server or packaging stack; the UI the "
                    "suite audits lives under the chosen UI root(s), whose files need "
                    f"the {adapter!r} adapter"),
        }
        return result

    if not found:
        result["stack"] = None
        result["candidateAdapter"] = None
        unknown.append({
            "field": "stack",
            "why": "no root manifest matched any known packaging convention",
            "looked_for": sorted(MANIFESTS),
            "note": "The file census is present but does not vote; see _censusNote.",
        })
        return result

    if len(stacks) > 1:
        result["stack"] = None
        result["candidateStacks"] = sorted(stacks)
        result["candidateAdapter"] = None
        unknown.append({
            "field": "stack",
            "why": f"{len(stacks)} root manifests disagree: {sorted(stacks)}",
            "note": "Likely a polyglot repository or a workspace. Declare it rather than "
                    "letting the survey pick one.",
        })
        return result

    stack = stacks.pop()
    result["stack"] = stack
    adapter = next((a for _n, _s, a, _r, _w in found if a), None)
    if adapter in ADAPTER_REFINEMENTS:
        refined, suffixes, why = ADAPTER_REFINEMENTS[adapter]
        hits = sorted({Path(rel).suffix for rel in files if rel.endswith(suffixes)})
        if hits and refined in available:
            result["adapterRefinement"] = {"from": adapter, "to": refined,
                                           "because": hits, "why": why}
            adapter = refined
    if stack == GRADLE_STACK and adapter is None:
        evidence = _gradle_compose_evidence(root)
        if evidence and GRADLE_COMPOSE[0] in available:
            result["adapterRefinement"] = {"from": None, "to": GRADLE_COMPOSE[0],
                                           "because": evidence, "why": GRADLE_COMPOSE[2]}
            adapter = GRADLE_COMPOSE[0]
    if adapter and adapter in available:
        result["candidateAdapter"] = adapter
    else:
        result["candidateAdapter"] = None
        # Two different answers, kept apart. "No adapter is mapped to this
        # stack" and "the adapter mapped to this stack is not installed" have
        # different fixes, and collapsing them into one sentence is how a stale
        # mapping reads as a missing capability — which is exactly what
        # happened to `tsx`.
        why = (f"the {stack!r} stack maps to adapter {adapter!r}, which is not "
               f"present in this plugin" if adapter else
               f"no adapter in this plugin is mapped to the {stack!r} stack")
        unknown.append({
            "field": "adapters.lang",
            "why": why,
            "note": f"adapters present: {available}. An unknown adapter is a hard error "
                    f"downstream, not a default.",
        })

    # An adapter that ships but that no manifest can reach is the same defect
    # in the other direction, and it is silent unless it is said out loud.
    unreachable = adapter_reachability()
    if unreachable:
        result["unreachableAdapters"] = unreachable
        unknown.append({
            "field": "adapters.lang",
            "why": f"adapter(s) {unreachable} ship in this plugin but no root "
                   f"manifest is mapped to them, so the survey can never propose "
                   f"them",
            "note": "Map them in survey.py's MANIFESTS table, or set adapters.lang "
                    "by hand. This is a plugin defect, not a project one.",
        })
    return result


def detect_source_roots(root: Path, files: list[str], unknown: list[dict]) -> list[dict]:
    """Candidate source roots — plural, ranked, and allowed to be empty.

    A root manifest can be a workspace stub: `pubspec.yaml` with a `workspace:`
    key, or a `package.json` whose only real content is `workspaces`. In that
    case the conventional root does not exist and the real sources are one level
    down, which is why this returns a list and records a reason when it is short.
    """
    candidates: list[dict] = []
    for name, (_stack, _adapter, roots, _why) in MANIFESTS.items():
        if not (root / name).is_file():
            continue
        for rel in roots:
            if rel == ".":
                continue
            if (root / rel).is_dir():
                count = sum(1 for f in files if f.startswith(rel + "/"))
                candidates.append({
                    "path": rel,
                    "files": count,
                    "why": f"conventional source root for {name}",
                    "confidence": 0.8 if count else 0.2,
                })

    workspace = []
    members: list[tuple[str, str]] = []  # (member dir, which manifest declared it)
    pubspec = root / "pubspec.yaml"
    if pubspec.is_file():
        text = pubspec.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"^workspace:", text, re.M):
            workspace.append("pubspec.yaml declares a `workspace:` — this manifest is a stub")
            members += [(m, "pubspec.yaml `workspace:`") for m in _yaml_list(text, "workspace")]
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
            spaces = data.get("workspaces")
            if spaces:
                workspace.append("package.json declares `workspaces` — this manifest is a stub")
                # npm/yarn accept either a bare list or `{"packages": [...]}`.
                listed = spaces.get("packages", []) if isinstance(spaces, dict) else spaces
                members += [(m, "package.json `workspaces`")
                            for m in listed if isinstance(m, str)]
        except ValueError:
            unknown.append({"field": "sourceRoots", "why": "package.json is not valid JSON"})

    # Enumerating the members is READING, not guessing: the manifest names them,
    # so they are as declared as `source.root` is. What stays un-guessed is which
    # of them the suite should audit, and that is why every candidate below scores
    # BELOW `init.py`'s auto-seed bar — a workspace's roots reach profile.json only
    # when a human writes `source.roots`, never by inference.
    for rel, where in members:
        if any(c in rel for c in "*?["):
            # A glob member (`packages/*`) names a set, not a directory. Expanding
            # it would freeze today's membership into a config that stops tracking
            # the glob, so it is reported and not expanded.
            unknown.append({
                "field": "sourceRoots",
                "why": f"{where} lists {rel!r}, a glob rather than a directory",
                "note": "Not expanded: a glob names a set that changes, and freezing "
                        "today's members into a config is how the config goes stale.",
            })
            continue
        member_dir = root / rel
        if not member_dir.is_dir():
            continue
        # A member is a package; its SOURCE root is the conventional directory
        # inside it, when that directory exists. Falling back to the member itself
        # is deliberate — a package with no conventional layout still has sources.
        inner = next((sub for name in MANIFESTS
                      if (member_dir / name).is_file()
                      for sub in MANIFESTS[name][2]
                      if sub != "." and (member_dir / sub).is_dir()), None)
        path = f"{rel}/{inner}" if inner else rel
        candidates.append({
            "path": path,
            "files": sum(1 for f in files if f.startswith(path + "/")),
            "why": f"declared as a workspace member by {where}"
                   + (f"; {inner}/ is the conventional source root inside it" if inner else ""),
            "confidence": 0.7,
            "workspaceMember": True,
        })

    for note in workspace:
        unknown.append({
            "field": "sourceRoots",
            "why": note,
            "note": "Members hold the real sources, and the ones listed above are the "
                    "manifest's own — but WHICH of them this project wants audited is a "
                    "decision no manifest states. Declare `source.roots` (a list) in "
                    "profile.json; `source.root` alone cannot describe this project "
                    "(RFC-0002 §3g #3). Nothing is seeded from this automatically.",
        })

    if not candidates:
        unknown.append({
            "field": "sourceRoots",
            "why": "no conventional source directory exists for the detected manifest(s)",
            "note": "Refusing to nominate one. An empty list is an answer; a guess is not.",
        })
    return sorted(candidates, key=lambda c: (-c["confidence"], c["path"]))



# --------------------------------------------------------------------------- #
# UI roots: where the DESIGN surface lives, ranked by evidence
# --------------------------------------------------------------------------- #
#
# The root manifest answers "how is this repository packaged", which is the
# wrong question for a design suite on any polyglot repository. A held-out run
# (docs/MEASUREMENT-2026-10-08-web-adapter-held-out.md §2) put six public
# projects through survey → init --from-survey → audit_tokens and got ZERO
# findings on all six: a Gemfile made a React+SCSS app read as Ruby, a
# workspace's backend package outranked its frontend, and five of six roots
# were left as TODO. Every run refused honestly — but a suite that can never
# get past onboarding audits nothing.
#
# So this ranks candidate directories by UI evidence instead: component files
# (JSX/TSX/SFC/Flutter widgets), stylesheets, and UI-framework dependencies in
# the manifest that owns the candidate. It PROPOSES — every candidate carries
# its evidence and the choice carries a confidence and the runners-up. Nothing
# here is a declaration; init.py writes whatever it seeds from this as
# `inferred`, and a low-confidence ranking picks nothing at all.

COMPONENT_SUFFIXES = (".tsx", ".jsx", ".vue", ".svelte", ".astro")
STYLE_SUFFIXES = (".css", ".scss", ".sass", ".less", ".styl", ".pcss")
CODE_SUFFIXES = (".ts", ".js", ".mjs", ".cjs", ".py", ".rb", ".go", ".rs", ".php",
                 ".java", ".kt", ".swift", ".cs", ".dart", ".ex", ".erb")

# Dependencies that mean "this package renders UI".
UI_DEPS = {
    "react", "react-dom", "vue", "svelte", "@angular/core", "solid-js", "preact",
    "lit", "react-native", "@mui/material", "@chakra-ui/react", "tailwindcss",
    "styled-components", "@emotion/react", "flutter",
}
# Dependencies that mean "this package is a runnable UI application" rather than
# a library — an app is what a design audit is usually pointed at.
APP_DEPS = {
    "next", "nuxt", "vite", "@sveltejs/kit", "react-scripts", "@angular/cli",
    "expo", "astro", "gatsby", "webpack", "@vitejs/plugin-react",
    "@vitejs/plugin-vue", "@rails/webpacker", "shakapacker", "esbuild",
}
# Dependencies that mean "this package is a server". Only counted against a
# candidate that has no UI dependency of its own.
SERVER_DEPS = {
    "express", "fastify", "koa", "@nestjs/core", "hapi", "@hapi/hapi", "typeorm",
    "mikro-orm", "@mikro-orm/core", "sequelize", "ioredis", "bull", "bullmq",
}
# Path segments that name something other than the product UI. A penalty, not a
# filter: a project whose only UI lives under `docs/` should still be found.
NON_UI_SEGMENTS = {
    "backend", "server", "api", "worker", "workers", "cli", "test", "tests",
    "e2e", "__tests__", "fixtures", "examples", "example", "scripts", "tools",
    "migrations", "db", "spec", "playground", "benchmarks", "docs",
}
# Directory names conventionally holding a web front end inside a server repo
# (Rails `app/javascript`, Django/Phoenix `assets` or `frontend`, …).
UI_DIR_NAMES = {"javascript", "frontend", "client", "web", "webapp", "ui", "www", "assets"}
NESTED_MANIFESTS = ("package.json", "pubspec.yaml")
UI_SEED_CONFIDENCE = 0.6
MIN_UI_FILES = 5


def _manifest_deps(path: Path) -> set[str]:
    """Dependency names declared by one package.json or pubspec.yaml."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    if path.name == "package.json":
        try:
            data = json.loads(text)
        except ValueError:
            return set()
        deps: set[str] = set()
        for group in ("dependencies", "devDependencies", "peerDependencies"):
            if isinstance(data.get(group), dict):
                deps |= set(data[group])
        return deps
    return {m.group(1) for m in re.finditer(r"^  ([A-Za-z0-9_]+):", text, re.M)}


def _ui_candidate_dirs(root: Path, files: list[str]) -> dict[str, str]:
    """Candidate directory → the manifest (repo-relative) that owns it."""
    packages = sorted({str(Path(rel).parent.as_posix()) for rel in files
                       if Path(rel).name in NESTED_MANIFESTS and rel.count("/") <= 4})
    packages = ["." if p == "" else p for p in packages]

    def owner(rel_dir: str) -> str | None:
        best = None
        for pkg in packages:
            if pkg == "." or rel_dir == pkg or rel_dir.startswith(pkg + "/"):
                if best is None or len(pkg) > len(best):
                    best = pkg
        return best

    out: dict[str, str] = {}
    for pkg in packages:
        base = "" if pkg == "." else pkg + "/"
        # `src/` only: a package's `lib/` or `app/` is as often a slice of it
        # (Next's `app/` router, a `lib/` of helpers) as its whole source.
        inner = [sub for sub in ("src",) if (root / base / sub).is_dir()]
        out[f"{base}{inner[0]}" if inner else (pkg)] = pkg
        if pkg == ".":
            # The root package's own conventional roots, each its own candidate:
            # a Node server + client repo keeps its UI in `app/` beside `server/`.
            for sub in ("src", "app", "lib", "client"):
                if (root / sub).is_dir():
                    out.setdefault(sub, ".")
    dirs = {"/".join(rel.split("/")[:i]) for rel in files
            for i in range(1, min(rel.count("/"), 3) + 1)}
    for rel_dir in sorted(dirs):
        parts = rel_dir.split("/")
        if (parts[-1] in UI_DIR_NAMES and rel_dir not in out
                and rel_dir not in packages):
            own = owner(rel_dir)
            out[rel_dir] = own if own is not None else ""
    return out


def detect_ui_roots(root: Path, files: list[str], unknown: list[dict]) -> dict:
    """Rank directories by how much of the UI they hold. Proposes; never decides."""
    candidates = []
    for rel_dir, pkg in _ui_candidate_dirs(root, files).items():
        prefix = "" if rel_dir in (".", "") else rel_dir + "/"
        under = [f for f in files if f.startswith(prefix)]
        comp = [f for f in under if f.endswith(COMPONENT_SUFFIXES)]
        style = [f for f in under if f.endswith(STYLE_SUFFIXES)]
        code = [f for f in under if f.endswith(COMPONENT_SUFFIXES + STYLE_SUFFIXES + CODE_SUFFIXES)]
        manifest = None
        if pkg:
            for name in NESTED_MANIFESTS:
                p = root / ("" if pkg == "." else pkg) / name
                if p.is_file():
                    manifest = p
                    break
        deps = _manifest_deps(manifest) if manifest else set()
        dart = [f for f in under if f.endswith(".dart")]
        if "flutter" in deps:
            comp = comp + dart
        ui_files = len(comp) + len(style)
        if ui_files == 0:
            continue
        ui_deps = sorted(deps & UI_DEPS)
        app_deps = sorted(deps & APP_DEPS)
        server_deps = sorted(deps & SERVER_DEPS)
        segments = set(rel_dir.lower().split("/"))
        bad_segments = sorted(segments & NON_UI_SEGMENTS)
        ratio = ui_files / max(len(code), 1)
        # Size dominates, density modulates: a 9-file helper directory that is
        # all components must not outrank a 500-file application.
        score = math.log2(1 + ui_files) * (0.75 + 0.5 * ratio)
        evidence = [f"{len(comp)} component file(s), {len(style)} stylesheet(s) "
                    f"of {len(code)} source file(s)"]
        if ui_deps:
            score += 3
            evidence.append(f"UI dependencies in {manifest.relative_to(root).as_posix()}: "
                            f"{', '.join(ui_deps[:5])}")
        if app_deps:
            score += 2
            evidence.append(f"application tooling: {', '.join(app_deps[:4])}")
        if "apps" in segments:
            score += 1
            evidence.append("lives under apps/")
        if server_deps and not ui_deps:
            score -= 3
            evidence.append(f"server dependencies and no UI dependency: {', '.join(server_deps[:4])}")
        if bad_segments:
            score -= 2
            evidence.append(f"path names a non-UI concern: {', '.join(bad_segments)}")
        candidates.append({
            "path": "." if rel_dir in ("", ".") else rel_dir,
            "score": round(score, 2),
            "componentFiles": len(comp),
            "styleFiles": len(style),
            "isApp": bool(app_deps) or "apps" in segments,
            # Whether this candidate IS a package (its root or its src/), rather
            # than a directory inside one. Only packages count as sibling apps.
            "ownPackage": pkg not in ("", ".") and rel_dir in (pkg, f"{pkg}/src"),
            "suffixes": sorted({Path(f).suffix for f in comp + style}),
            "evidence": evidence,
        })

    # A directory nested inside a better-or-equal candidate of the same package is
    # noise in the ranking, not a runner-up — but a nested directory that BEATS its
    # parent (Rails `app/javascript` inside `app`) is the answer.
    # The repository root is a candidate only when nothing narrower is: in a
    # workspace it is the sum of every package, and it always "wins" by size.
    if any(c["path"] != "." for c in candidates):
        candidates = [c for c in candidates if c["path"] != "."]
    candidates.sort(key=lambda c: (-c["score"], -c["path"].count("/"), c["path"]))
    result: dict = {"candidates": candidates[:8], "chosen": [], "confidence": 0.0,
                    "provenance": "inferred",
                    "_note": ("A ranking by UI evidence, not a declaration. init.py seeds "
                              "only a choice at or above "
                              f"{UI_SEED_CONFIDENCE} confidence, and always as `inferred`.")}
    strong = [c for c in candidates
              if c["score"] > 0 and c["componentFiles"] + c["styleFiles"] >= MIN_UI_FILES]
    if not strong:
        unknown.append({
            "field": "uiRoots",
            "why": "no directory holds enough component or style files to call it the UI",
            "note": f"looked for {', '.join(COMPONENT_SUFFIXES + STYLE_SUFFIXES)} and UI "
                    "framework dependencies. Nothing proposed — declare source.root.",
        })
        return result

    best = strong[0]
    rivals = [c for c in strong[1:] if not c["path"].startswith(best["path"] + "/")
              and not best["path"].startswith(c["path"] + "/")]
    second = rivals[0]["score"] if rivals else 0.0
    margin = (best["score"] - second) / best["score"] if best["score"] > 0 else 0.0
    confidence = round(min(0.9, 0.45 + 0.45 * margin + (0.1 if best["isApp"] else 0)), 2)

    # Several sibling applications, each about as strong as the best: a monorepo
    # with more than one UI, which `source.roots` exists to describe.
    apps = [c for c in [best, *rivals]
            if c["isApp"] and c["ownPackage"] and c["score"] >= 0.75 * best["score"]]
    if best["isApp"] and best["ownPackage"] and len(apps) >= 2:
        result["chosen"] = [c["path"] for c in apps]
        confidence = round(min(0.85, 0.5 + 0.1 * len(apps)), 2)
        result["why"] = (f"{len(apps)} sibling UI applications score within 25% of each "
                         "other; proposing all of them as source.roots")
    else:
        result["chosen"] = [best["path"]]
        result["why"] = (f"{best['path']} scores {best['score']}"
                         + (f"; runner-up {rivals[0]['path']} scores {rivals[0]['score']}"
                            if rivals else "; no rival candidate"))
    result["confidence"] = confidence
    result["runnersUp"] = [c["path"] for c in rivals if c["path"] not in result["chosen"]][:3]
    if confidence < UI_SEED_CONFIDENCE:
        unknown.append({
            "field": "uiRoots",
            "why": f"the UI-root ranking is not decisive (confidence {confidence}): "
                   f"{result['why']}",
            "note": "Candidates are listed under uiRoots with their evidence; none is "
                    "seeded. Pick one and declare source.root.",
        })
    return result


def ui_adapter(ui: dict, files: list[str], available: list[str]) -> tuple[str, str, list[str]] | None:
    """The adapter the CHOSEN UI roots need, from the files under them."""
    chosen = ui.get("chosen") or []
    if not chosen or ui.get("confidence", 0) < UI_SEED_CONFIDENCE:
        return None
    suffixes = set()
    for path in chosen:
        prefix = "" if path == "." else path + "/"
        suffixes |= {Path(f).suffix for f in files if f.startswith(prefix)}
    web_suffixes = set(ADAPTER_REFINEMENTS["tsx"][1])
    if suffixes & web_suffixes and "web" in available:
        return "web", "javascript/typescript", sorted(suffixes & web_suffixes)
    if suffixes & {".tsx", ".jsx", ".ts", ".js"} and "tsx" in available:
        return "tsx", "javascript/typescript", sorted(suffixes & {".tsx", ".jsx"})
    if ".dart" in suffixes and "dart" in available:
        return "dart", "dart/flutter", [".dart"]
    return None


def _yaml_list(text: str, key: str) -> list[str]:
    """The `- item` entries directly under a top-level `key:` in a YAML document.

    Deliberately not a YAML parser: this reads one shape (a top-level key whose
    value is a flat sequence of scalars) because that is the shape a workspace
    member list has, and stdlib-only is a standing constraint here. Anything
    else — a nested mapping, a flow sequence, an anchor — simply does not match
    and yields nothing, which leaves the caller's refusal in place rather than
    handing it a half-parsed answer.
    """
    out: list[str] = []
    collecting = False
    for line in text.splitlines():
        if re.match(rf"^{re.escape(key)}:\s*$", line):
            collecting = True
            continue
        if collecting:
            item = re.match(r"^\s+-\s+(.+?)\s*(?:#.*)?$", line)
            if item:
                out.append(item.group(1).strip().strip("\"'").rstrip("/"))
                continue
            if line.strip() and not line.strip().startswith("#"):
                break  # the sequence ended
    return out


def detect_token_sources(root: Path, files: list[str], unknown: list[dict]) -> list[dict]:
    """Ranked token-source CANDIDATES with reasons. Never a single conclusion.

    Measured failure modes this is shaped around (RFC-0002 §3e):
      * the previous detector matched `.design-suite/findings/tokens.json` — the
        token audit's own output — on both real consumers. `.design-suite/` is in
        ALWAYS_SKIP and build output is excluded here too;
      * on both real consumers the true source is not in the repository at all:
        it arrives as `package:ds_flutter`. So dependency names that look like a
        token package are emitted as candidates in their own right, and the
        caller is told in `couldNotDetermine` that the winner may be none of the
        files listed;
      * **the name gate was the bug.** Only a file *called* `tokens.json` or
        `*.tokens.json` was ever opened, so a design system whose sources are a
        directory of W3C-shaped files named after what they hold — geometry,
        motion, typography, one per brand — scored zero real candidates and the
        list was topped by a docs stylesheet that merely had the right filename.
        Content is now what earns the high scores and a filename only ever earns
        a low one, which is the correct way round: a name is a hint about a file
        and its contents are the file.

    Two shapes are recognised by content, because two are in wide use — the W3C
    Design Tokens format (`$value`/`$type`) and the older Style-Dictionary input
    shape (nested groups whose leaves are `{"value": …}`). Neither is scored above
    0.9: even a perfectly-shaped file may be one of several, or may be an example
    in somebody's documentation.
    """
    candidates: list[dict] = []
    excluded = ("dist/", "build/", "out/", f"{MARKER}/", "coverage/")

    for rel in files:
        if rel.startswith(excluded) or f"/{MARKER}/" in rel:
            continue
        name = Path(rel).name.lower()
        shape = _token_file_shape(root / rel) if name.endswith(".json") else None
        if shape:
            kind, score, why = shape
            candidate = {"path": rel, "confidence": score, "why": why, "format": kind}
            if _looks_generated(rel):
                # A compiled artefact is a token SINK, not a source. Editing it is
                # how a design system's real source and its build output diverge,
                # so it is reported (it is genuinely evidence tokens exist here)
                # and deliberately ranked below anything hand-authored.
                candidate["confidence"] = 0.2
                candidate["generated"] = True
                candidate["why"] = (f"{why} — but this path is marked generated, so it is "
                                    f"the compiled OUTPUT of a token source, not the source")
            candidates.append(candidate)
        elif name.endswith(".tokens.json") or name == "tokens.json":
            # Right name, unrecognised contents. Still worth surfacing, at the
            # confidence a filename alone deserves.
            candidates.append({"path": rel, "confidence": 0.5,
                               "why": "filename suggests design tokens, but the contents "
                                      "match no token format this detector recognises"})
        elif re.fullmatch(r"(design[-_.])?tokens?\.(dart|ts|js|json|scss|css|yaml)", name):
            candidates.append({"path": rel, "confidence": 0.5,
                               "why": "filename matches a conventional token module"})
        elif name in {"tailwind.config.js", "tailwind.config.ts", "tailwind.config.mjs"}:
            candidates.append({"path": rel, "confidence": 0.6,
                               "why": "Tailwind config carries the theme scale for this stack"})
        elif name in {"theme.dart", "theme.ts", "theme.js"}:
            candidates.append({"path": rel, "confidence": 0.3,
                               "why": "a theme module often re-exports tokens rather than defining them"})

    for dep, where in _dependency_names(root):
        if re.search(r"(token|theme|design[-_]?system|\bds[-_])", dep, re.I):
            candidates.append({
                "dependency": dep,
                "confidence": 0.6,
                "why": f"declared in {where}; on both real consumer projects the true token "
                       f"source is a package dependency and no file in the repository",
            })

    unknown.append({
        "field": "tokens.source",
        "why": "token-source detection is the worst-measured signal in the suite",
        "note": "The list above is CANDIDATES with reasons. `tokens.source` stays "
                "human-approved; the true source may be none of these, and on both real "
                "consumer projects it is a package dependency resolved through the "
                "package manager's own map.",
    })

    ranked = sorted(candidates,
                    key=lambda c: (-c["confidence"], c.get("path") or c.get("dependency")))
    # Several equally good answers is an ANSWER, and suppressing it to look
    # decisive is the specific dishonesty RFC-0002 §3e forbids. A design system
    # legitimately splits its tokens across core/semantic/per-brand files; sorting
    # picks one of them for the top of the list and that ordering means nothing.
    top = [c for c in ranked if c["confidence"] == ranked[0]["confidence"]] if ranked else []
    if len(top) > 1:
        unknown.append({
            "field": "tokens.source",
            "why": f"{len(top)} candidates tie at the highest confidence "
                   f"({ranked[0]['confidence']}) — nothing here separates them",
            "note": "The order of the list is alphabetical within a confidence band and "
                    "carries NO ranking. A token set split across several files (core, "
                    "semantic, per-brand) is normal; `tokens.source` may need to name a "
                    "directory, several files, or something outside the repository.",
            "candidates": [c.get("path") or c.get("dependency") for c in top],
        })
    return ranked


# A path the project's own build wrote. Two general conventions, no project
# literals: a `.g.`/`.generated.` infix (Dart, TS codegen, protobuf) and a
# `generated/` path segment.
_GENERATED = re.compile(r"(^|/)generated/|\.(g|generated|freezed|pb)\.[A-Za-z0-9]+$")


def _looks_generated(rel: str) -> bool:
    return bool(_GENERATED.search(rel.lower()))


# Beyond this a JSON file is data, not a token definition, and parsing every one
# of them turns a survey into a build step. A cap that is hit is not silently
# dropped — the file simply never becomes a candidate, and the filename rules
# below still see it.
_MAX_TOKEN_JSON_BYTES = 1_048_576


def _token_file_shape(path: Path):
    """`(format, confidence, why)` when this JSON file IS a token definition, else None.

    None is the common case and must stay cheap: the overwhelming majority of JSON
    in a repository is package metadata, fixtures, lockfiles and editor config,
    and none of it may become a token candidate. So both tests below require a
    *structural signature*, not the mere presence of a key.
    """
    try:
        if path.stat().st_size > _MAX_TOKEN_JSON_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (ValueError, OSError):
        return None
    if not isinstance(data, dict):
        return None

    if _has_w3c_shape(data):
        return ("w3c-design-tokens", 0.9,
                "W3C Design Tokens format — `$value`/`$type` present in the file's own "
                "contents. The format reached its first stable version in Oct 2025; this "
                "is the strongest signal available, and it is a content signal, not a name")

    # Style Dictionary's input shape: nested groups whose leaves are objects with
    # a `value`. Two leaves are required rather than one because a single
    # `{"value": …}` anywhere is a coincidence — config files, fixtures and API
    # samples are full of them — while a tree of them is a token file.
    leaves = _style_dictionary_leaves(data)
    if leaves >= 2:
        return ("style-dictionary", 0.8,
                f"Style-Dictionary input shape — {leaves} nested group leaves of the form "
                f"`{{\"value\": …}}`. A content signal; scored below the W3C format because "
                f"the shape is less distinctive and a non-token file can imitate it")
    return None


def _has_w3c_shape(node, depth: int = 0) -> bool:
    if depth > 6 or not isinstance(node, dict):
        return False
    if "$value" in node or "$type" in node:
        return True
    return any(_has_w3c_shape(v, depth + 1) for v in node.values())


# What Style Dictionary allows beside `value` on a leaf. A leaf carrying anything
# else is some other kind of object that happens to have a `value` key, and is not
# counted — that narrowness is what keeps ordinary config out of the candidate list.
_SD_LEAF_KEYS = {"value", "type", "comment", "attributes", "name", "description",
                 "themeable", "filePath", "isSource", "original", "deprecated"}


def _style_dictionary_leaves(node, depth: int = 0) -> int:
    if depth > 8 or not isinstance(node, dict):
        return 0
    if "value" in node and set(node) <= _SD_LEAF_KEYS:
        return 1
    return sum(_style_dictionary_leaves(v, depth + 1) for v in node.values())


def _dependency_names(root: Path):
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
            for group in ("dependencies", "devDependencies"):
                for dep in (data.get(group) or {}):
                    yield dep, f"package.json {group}"
        except ValueError:
            pass
    pubspec = root / "pubspec.yaml"
    if pubspec.is_file():
        text = pubspec.read_text(encoding="utf-8", errors="ignore")
        in_deps = False
        for line in text.splitlines():
            if re.match(r"^(dev_)?dependencies:", line):
                in_deps = True
                continue
            if line and not line[0].isspace():
                in_deps = False
            if in_deps:
                match = re.match(r"^  ([A-Za-z0-9_]+):", line)
                if match:
                    yield match.group(1), "pubspec.yaml dependencies"


def document_inventory(root: Path, files: list[str], unknown: list[dict]) -> dict:
    """Markdown documents, with a proposed role and a confidence per proposal.

    Confidence is reported per document rather than as an aggregate because the
    aggregate lies: doc-role inference scored 20/20 on one real consumer and
    4-confident-of-20 on a zero-state repository, and the difference is that the
    first project's documents were named by this suite's own convention. Anything
    this table cannot name lands in `unmapped`, which is reported and never
    silently ignored — silence there is how a suite claims doc coverage it does
    not have.
    """
    docs, unmapped = [], []
    for rel in files:
        if not rel.lower().endswith((".md", ".mdx")):
            continue
        if rel.count("/") > 2:
            continue
        stem = Path(rel).stem.lower()
        proposal = ROLE_BY_STEM.get(stem)
        if proposal:
            role, confidence, why = proposal
            docs.append({"path": rel, "proposedRole": role,
                         "confidence": confidence, "why": why,
                         "provenance": "inferred"})
        else:
            unmapped.append(rel)

    if unmapped:
        unknown.append({
            "field": "docs.roles",
            "why": f"{len(unmapped)} document(s) map to no role in the vocabulary",
            "note": "Not necessarily a detection failure: on a real zero-state repository "
                    "17 of 20 top-level documents had no role in the vocabulary AT ALL, and "
                    "you cannot infer a mapping to a role that does not exist. A document "
                    "mapped to no role is reported, never silently ignored.",
            "documents": unmapped[:100],
        })

    return {
        "documents": docs,
        "unmapped": unmapped,
        "_note": ("Every proposal here is `inferred` and nothing downstream may treat it as "
                  "authoritative. Choosing between four candidate `design` documents is the "
                  "judgement half (/map-project), not this script's job."),
    }


def survey(root: Path) -> dict:
    ignores = Ignores(root)
    files = walk(root, ignores)
    unknown: list[dict] = []

    if ignores.unsupported:
        unknown.append({
            "field": "ignoreRules",
            "why": f"{len(ignores.unsupported)} .gitignore rule(s) use negation, which this "
                   f"reader does not implement",
            "note": "Files those rules re-include may be missing from this survey.",
            "rules": ignores.unsupported,
        })
    if not (root / MARKER).is_dir():
        unknown.append({
            "field": "existingConfig",
            "why": f"no {MARKER}/ directory — this project has no context layer yet",
            "note": "Nothing to compare against, so `survey.py --check` has no declared side.",
        })

    ui = detect_ui_roots(root, files, unknown)
    stack = detect_stack(root, files, unknown, ui)
    return {
        "surveyVersion": SURVEY_VERSION,
        "sourceStamp": source_stamp(root),
        "stack": stack,
        "sourceRoots": detect_source_roots(root, files, unknown),
        "uiRoots": ui,
        "candidateTokenSources": detect_token_sources(root, files, unknown),
        "documents": document_inventory(root, files, unknown),
        "filesSeen": len(files),
        "couldNotDetermine": unknown,
        "_couldNotDetermineNote": (
            "Load-bearing output, not a nicety. A survey that determined everything and a "
            "survey that never ran produce the same short file unless this list is here."),
    }


# --------------------------------------------------------------------------- #
# The completeness diff: disk → declared
# --------------------------------------------------------------------------- #

def config_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / MARKER).glob("*.json")
                  if p.is_file() and not p.name.endswith(".schema.json"))


def declared_paths(configs: list[Path],
                   root: Path | None = None) -> tuple[set[str], list[tuple[str, str]], list[str]]:
    """Every path a config DECLARES, plus every path a config only mentions in prose.

    The split is the load-bearing part. A value that is entirely a path or glob is
    a declaration. A path inside a sentence is a mention — and treating the two
    alike is how the acceptance case stays silent: the portal profile's
    `pipelines._assets` is a paragraph containing the words "no assets/ directory",
    so a substring sweep finds `assets/` and reports nothing about the six JPEGs
    that landed there a month later.

    THE BARE-NAME RULE — do not "simplify" this back.
    ------------------------------------------------
    The shape test alone used to require a `/` or a `.` in the value, on the
    theory that a string with neither is not a path. That theory was measured
    against both consumer projects and was wrong 7 times out of 32 findings —
    a 22% false-positive rate against issue #104's ≤5% bar, and every one of
    the 7 had this single cause. A single-segment declaration is still a
    declaration:

        source.testRoot: "test"              → test/ reported undeclared
        pipelines.assets: "asset_pipeline"   → reported undeclared
        pipelines.mockApi: "mock_api"        → reported undeclared
        pipelines.copy: "copy_pipeline"      → reported undeclared

    and the last of those cascaded: with the parent declaration unrecognised,
    three `test/*` subdirectories were then flagged as undeclared siblings too.

    The obvious fix — accept any bare string that happens to name a real
    directory — trades one false-positive class for a worse false-NEGATIVE
    class, which is the failure this whole tool exists to prevent. A profile is
    full of short strings that are not paths: a project name, an adapter name, a
    palette brand, a category label. Any one of them colliding with a real
    directory name would silently discharge a genuine finding, and a suppressed
    finding leaves no trace at all. (`adapters.assets` and `assets.palette.brand`
    are both live examples of keys whose values must NOT be read as paths.)

    So a bare name is a declaration only when BOTH hold:

      1. its key is path-valued BY ROLE — `_path_valued_key`, the same
         key-name-not-value-shape test doctor.py's PATH_KEYS makes; and
      2. it names a directory that actually exists at the project root.

    (2) is not redundant with (1): it stops a path-valued key whose value is a
    placeholder, a package name, or a stale leftover from covering a tree that
    is not there. It is also why `root` is a parameter — without it rule 2
    cannot be evaluated, and the signature says so. When `root` is None the
    bare-name rule is simply off, i.e. the old behaviour: wrong, but not newly
    wrong.

    Values containing `/` or `.` are unaffected and still need no key check —
    their own shape is the evidence.
    """
    declared: set[str] = set()
    prose: list[tuple[str, str]] = []
    unreadable: list[str] = []

    def visit(node, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                visit(value, f"{trail}.{key}" if trail else key)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                visit(value, f"{trail}[{i}]")
        elif isinstance(node, str):
            text = node.strip()
            if _argv_member(trail):
                return  # argv token, not a declaration — see _argv_member.
            shaped = bool(text) and " " not in text and bool(PATHISH.match(text))
            bare = shaped and "/" not in text and "." not in text
            if shaped and (not bare or (
                    # See THE BARE-NAME RULE above: key role AND existence, both.
                    root is not None and _path_valued_key(trail)
                    and (root / text).is_dir())):
                declared.add(text.rstrip("/"))
            else:
                for match in re.finditer(r"\b([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-/]*)", text):
                    prose.append((match.group(1).rstrip("/"), trail))

    for config in configs:
        try:
            visit(json.loads(config.read_text(encoding="utf-8", errors="ignore")), config.name)
        except (ValueError, OSError) as exc:
            unreadable.append(f"{config.name}: {exc}")
    return declared, prose, unreadable


def literal_prefix(declared: str) -> str:
    """The part of a declared path before its first wildcard."""
    cut = min((declared.index(c) for c in "*?[{" if c in declared), default=len(declared))
    return declared[:cut].rstrip("/")


def covered(rel: str, declared: set[str]) -> bool:
    """Whether a declared path names `rel`, an ancestor of it, or a glob over it."""
    for d in declared:
        prefix = literal_prefix(d)
        if not prefix:
            continue
        if rel == prefix or rel.startswith(prefix + "/") or prefix.startswith(rel + "/"):
            return True
        if any(c in d for c in "*?[") and fnmatch.fnmatch(rel, d):
            return True
    return False


def named(rel: str, declared: set[str]) -> bool:
    """Whether a config names THIS directory, rather than merely an ancestor of it.

    The sibling rule needs the stricter test, and the difference is the entire
    acceptance case. `source.root: lib` is an ancestor of `lib/shared/format`, so
    the ancestor test would call every directory under `lib/` declared — and the
    four undeclared shared directories the audits skip would stay invisible,
    which is the bug this check exists to find. An ancestor declaration is the
    implicit claim; it cannot also be the thing that discharges it.
    """
    for d in declared:
        prefix = literal_prefix(d)
        if not prefix:
            continue
        if rel == prefix or prefix.startswith(rel + "/"):
            return True
        if any(c in d for c in "*?[") and fnmatch.fnmatch(rel, d):
            return True
    return False


def check(root: Path) -> tuple[list[dict], list[str]]:
    """The direction nothing else runs. Returns (findings, notes)."""
    if not (root / MARKER).is_dir():
        raise Refusal(f"no {MARKER}/ in {root} — --check compares disk against an existing "
                      f"config, and there is no declared side to diff against. Run the "
                      f"survey (without --check) and bin/init.py --from-survey first; refusing to report a clean completeness check "
                      f"on a project that declares nothing.")
    configs = config_files(root)
    if not configs:
        raise Refusal(f"{MARKER}/ holds no config JSON — nothing declares anything, so a "
                      f"completeness diff would report the whole repository. Refusing.")

    declared, prose, unreadable = declared_paths(configs, root)
    notes = [f"declared side: {len(configs)} config file(s) — "
             f"{', '.join(c.name for c in configs)}",
             f"{len(declared)} path-valued declaration(s)"]
    notes += [f"UNREADABLE CONFIG (its declarations are missing from this diff): {u}"
              for u in unreadable]

    ignores = Ignores(root)
    files = walk(root, ignores)
    findings: list[dict] = []

    # 1. Top-level entries nothing declares.
    top: dict[str, int] = {}
    for rel in files:
        head = rel.split("/")[0] if "/" in rel else None
        if head:
            top[head] = top.get(head, 0) + 1
    for name in sorted(top):
        if covered(name, declared):
            continue
        finding = {
            "kind": "undeclared-top-level-directory",
            "path": name + "/",
            "files": top[name],
            "why": "on disk, and no config file under .design-suite/ declares it as a path",
        }
        mentions = sorted({trail for path, trail in prose
                           if path.rstrip("/").split("/")[0] == name})
        if mentions:
            finding["proseMentions"] = mentions
            finding["note"] = ("Mentioned in PROSE at the config keys above, but never "
                               "declared as a path. A sentence about a directory is not a "
                               "declaration — and if that sentence asserts the directory "
                               "does not exist, this is a contradicted assertion, not a gap.")
        findings.append(finding)

    # 2. Siblings of a declared directory that nothing declares.
    #
    # Naming one member of a directory is an implicit completeness claim about
    # that directory — `sharedComponentDir: lib/shared/components/` says where the
    # shared components are, and says nothing about the four sibling directories
    # of shared code the audits therefore never look at.
    parents: set[str] = set()
    for d in declared:
        prefix = literal_prefix(d)
        if "/" in prefix and (root / prefix).exists():
            parents.add(prefix.rsplit("/", 1)[0])
    for parent in sorted(parents):
        if not (root / parent).is_dir():
            continue
        for entry in sorted((root / parent).iterdir()):
            if not entry.is_dir() or entry.name in ALWAYS_SKIP:
                continue
            rel = entry.relative_to(root).as_posix()
            if ignores.ignored(rel) or named(rel, declared):
                continue
            if not any(f.startswith(rel + "/") for f in files):
                continue
            findings.append({
                "kind": "undeclared-sibling-directory",
                "path": rel + "/",
                "why": f"a config declares a path inside {parent}/ but never names this "
                       f"sibling — naming one member of a directory is an implicit "
                       f"completeness claim about the rest of it",
            })

    # 3. Capabilities the code has and no field points at.
    #
    # Rules 1 and 2 are both divergence: something on disk that the config
    # contradicts by omission. This one is absence — nothing is missing from the
    # filesystem, so a directory walk is blind to it by construction. The answer
    # comes from the language adapter; see engine/capabilities.py for why a
    # refusal from it is reported more loudly than a finding, not less.
    from design_suite.adapters import load_project
    from design_suite.engine import capabilities as capability_engine

    profile, _exceptions = load_project(root)
    capability_findings = capability_engine.cross_check(root, profile)
    findings += capability_findings
    notes.append(f"capability cross-check: {len(capability_findings)} finding(s) — the "
                 f"absence direction, answered by the language adapter")

    # 4. Schemas that accept keys they never describe.
    findings += schema_findings(root, notes)

    return findings, notes


def schema_findings(root: Path, notes: list[str]) -> list[dict]:
    """Every `<name>.schema.json` under the marker, against the `<name>.json` it validates.

    Pairing by filename rather than by `$schema` on purpose: the document that
    most needs checking is the one whose `$schema` link is missing, and a
    schema with nothing to validate would otherwise go unexamined in silence.
    """
    out: list[dict] = []
    from design_suite.engine import schema_permissiveness

    schemas = sorted((root / MARKER).glob("*.schema.json"))
    if not schemas:
        notes.append(f"no *.schema.json under {MARKER}/ — nothing validates this project's "
                     f"config here, which is itself worth knowing")
        return out
    for schema_path in schemas:
        instance_path = schema_path.with_name(schema_path.name[: -len(".schema.json")] + ".json")
        if not instance_path.is_file():
            notes.append(f"{schema_path.name}: no {instance_path.name} beside it — "
                         f"not examined for permissiveness")
            continue
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8", errors="ignore"))
            instance = json.loads(instance_path.read_text(encoding="utf-8", errors="ignore"))
        except (ValueError, OSError) as exc:
            notes.append(f"UNREADABLE ({schema_path.name} / {instance_path.name}): {exc} — "
                         f"not examined for permissiveness")
            continue
        out += schema_permissiveness.findings(schema, instance,
                                              schema_path.name, instance_path.name)
    return out


class Refusal(RuntimeError):
    """Exit 2: the question could not be answered. Never a finding of zero."""


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Survey an unknown project (writes .design-suite/survey.json), or "
                    "diff disk against what the config declares (--check, writes nothing).")
    parser.add_argument("--project-root", help="project to survey; default: CLAUDE_PROJECT_DIR, else the git "
                                               "root of the working directory, else the "
                                               "working directory. Never requires an "
                                               "existing .design-suite/ (--check does).")
    parser.add_argument("--check", action="store_true",
                        help="completeness diff, disk → declared. Writes nothing.")
    parser.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    parser.add_argument("--stdout", action="store_true",
                        help="print the survey instead of writing survey.json")
    args = parser.parse_args()

    try:
        root = resolve_root(args.project_root)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.check:
        try:
            findings, notes = check(root)
        except Refusal as exc:
            print(f"survey --check: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({"projectRoot": str(root), "notes": notes,
                              "findings": findings}, indent=2))
        else:
            print(f"survey --check — completeness diff (disk → declared) for {root}\n")
            for note in notes:
                print(f"  · {note}")
            print()
            if not findings:
                print("  nothing on disk that no config mentions.")
            for finding in findings:
                print(f"  ✗ {finding['path']}  [{finding['kind']}]")
                print(f"      {finding['why']}")
                if finding.get("files"):
                    print(f"      {finding['files']} file(s) underneath")
                if finding.get("evidence"):
                    print(f"      evidence: {', '.join(finding['evidence'][:5])}"
                          + (" …" if len(finding["evidence"]) > 5 else ""))
                if finding.get("keys"):
                    print(f"      undescribed keys: {', '.join(finding['keys'])}")
                if finding.get("proseMentions"):
                    print(f"      prose mentions: {', '.join(finding['proseMentions'])}")
                    print(f"      {finding['note']}")
            print()
            print(f"{len(findings)} finding(s). This is the disk → declared direction; every "
                  f"doctor.py check runs declared → disk and is blind to additions by "
                  f"construction.")
        return 1 if findings else 0

    report = survey(root)
    if args.stdout or args.json:
        print(json.dumps(report, indent=2))
        return 0

    out = root / SURVEY_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"survey: wrote {SURVEY_REL} — {report['filesSeen']} file(s) seen, "
          f"stack={report['stack']['stack']!r}, "
          f"{len(report['candidateTokenSources'])} token candidate(s), "
          f"{len(report['couldNotDetermine'])} thing(s) it could NOT determine.")
    for item in report["couldNotDetermine"]:
        print(f"  ? {item['field']}: {item['why']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
