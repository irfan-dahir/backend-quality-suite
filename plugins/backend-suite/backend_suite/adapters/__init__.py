"""Language adapters and the loader that picks one from the project profile."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from .base import AdapterContext, Check, CheckSet  # re-exported for adapter authors

PROFILE = ".backend-suite/profile.json"
EXCEPTIONS = ".backend-suite/exceptions.json"


def load_project(repo: Path) -> tuple[dict, dict]:
    """(profile, exceptions). Missing files yield {} rather than raising, so a
    project that has not adopted the suite yet still runs with defaults."""
    def read(rel):
        path = repo / rel
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}
    return read(PROFILE), read(EXCEPTIONS)


# Exit 2 is "could not look" in DOC-ROLES.md's exit-code contract. A bare
# `SystemExit("message")` exits 1, which every hook and `repo_health.py` reads as
# "looked, and found something" — so a project whose stack has no adapter used to
# report as *having findings* rather than as *not audited*. Loud, but miscoded.
REFUSED = 2


def _refuse(message: str):
    print(message, file=sys.stderr)
    raise SystemExit(REFUSED)


def available() -> list[str]:
    """Language adapter stems, by the same structural test survey.py uses."""
    here = Path(__file__).parent
    return sorted(
        p.stem for p in here.glob("*.py")
        if p.stem not in {"__init__", "base"}
        and all(m in p.read_text() for m in ("\nNAME = ", "\nFILE_GLOBS = ", "\ndef checks("))
    )


def load(name: str):
    """Import the adapter module called `name`.

    An unknown adapter is a hard error. Falling back to a default would mean a
    project silently audited against another language's rules and reported zero
    findings — indistinguishable from a clean codebase.
    """
    if not isinstance(name, str) or not name.isidentifier():
        # Catches the scaffolded "TODO: which language adapter ..." placeholder,
        # which otherwise reached importlib and surfaced as a ModuleNotFoundError
        # quoting the whole sentence back as a module name.
        _refuse(
            f"{PROFILE} adapters.lang is {name!r}, which is not an adapter name "
            f"(an unfilled TODO, or a typo).\navailable: {', '.join(available())}\n"
            f"INERT, not clean — no source audit can run for this project until it "
            f"names an adapter. A stack with no adapter gets the documentation audits only."
        )
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ImportError as exc:
        _refuse(
            f"unknown language adapter {name!r} (from {PROFILE} adapters.lang).\n"
            f"available: {', '.join(available())}\n{exc}\n"
            f"INERT, not clean — refusing rather than auditing against another "
            f"language's rules."
        )


def for_project(repo: Path):
    """Adapter, context and checks for whatever `adapters.lang` the profile names."""
    profile, exceptions = load_project(repo)
    name = (profile.get("adapters", {}) or {}).get("lang")
    if not name:
        _refuse(f"{PROFILE} does not set adapters.lang — cannot pick a language adapter. "
                f"INERT, not clean.")
    adapter = load(name)
    ctx = AdapterContext(
        repo=repo,
        profile=profile,
        exceptions=exceptions,
    )
    return adapter, ctx, adapter.checks(ctx)


# Source suffixes of stacks the suite knows exist but has no language adapter for
# yet, so a file of one under the scan root is counted as "present and unscanned"
# rather than simply not noticed. Empty for now: every suffix the shipped
# adapters (php, node) glob is already covered, and a suffix belongs here only
# when a stack audits it through a DIFFERENT adapter — adding an adapter widens
# the derived set below without editing this line.
KNOWN_UNADAPTED_SUFFIXES = ()


def _suffixes(globs) -> set[str]:
    out = set()
    for g in globs:
        tail = g.rsplit("/", 1)[-1]
        if tail.startswith("*.") and "*" not in tail[1:]:
            out.add(tail[1:])
    return out


def uncovered_files(scan_root: Path, adapter, exceptions: dict | None = None) -> dict[str, int]:
    """Suffix -> count of files under `scan_root` that some stack audits but
    `adapter` does not glob.

    The control for the measured failure that motivated it: a Vue project on the
    `tsx` adapter swept `main.js`, found nothing, and exited 0 while every planted
    value sat in `.vue` and `.css` files the adapter never opened. "Known
    suffixes" are derived from every shipped language adapter's own FILE_GLOBS,
    plus KNOWN_UNADAPTED_SUFFIXES, so adding an adapter widens this without
    editing it.

    A project that deliberately leaves a suffix unscanned (a Dart app with a few
    `.js` interop shims under `lib/`) lists it in exceptions.json
    `acknowledgedUnscanned`, which is a recorded decision rather than a silence.
    """
    known = set(KNOWN_UNADAPTED_SUFFIXES)
    for name in available():
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except ImportError:
            continue
        known |= _suffixes(getattr(mod, "FILE_GLOBS", ()))
    covered = _suffixes(getattr(adapter, "FILE_GLOBS", ()))
    acked = set((exceptions or {}).get("acknowledgedUnscanned", []) or [])
    wanted = known - covered - acked
    counts: dict[str, int] = {}
    if not wanted:
        return counts
    skip_dirs = {"node_modules", ".git", "build", "dist", ".dart_tool", ".next", ".nuxt"}
    for path in scan_root.rglob("*"):
        if path.suffix in wanted and path.is_file() \
                and not skip_dirs.intersection(path.relative_to(scan_root).parts):
            counts[path.suffix] = counts.get(path.suffix, 0) + 1
    return dict(sorted(counts.items()))
