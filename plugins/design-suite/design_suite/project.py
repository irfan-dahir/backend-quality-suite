"""Find the repository under audit.

Lives in the package, not in bin/, because the mock-API engine needs it too and
cannot import a sibling of the CLI scripts. One implementation: two copies of
root-finding logic is how the plugin ends up auditing itself in one code path and
the project in another.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MARKER = ".design-suite"


def project_root(explicit: str | None = None) -> Path:
    """The repository being audited, identified by its .design-suite/ profile.

    Prefers CLAUDE_PROJECT_DIR (exported by Claude Code), then walks up from the
    working directory. Exits rather than falling back to a guess: an unconfigured
    project reports zero findings for the wrong reason, which reads exactly like a
    clean result.

    The walk stops at the nearest git root (a `.git` directory or file). An
    unconfigured repository nested inside a configured one — a vendored package,
    a submodule, a sibling checkout — must not silently borrow the outer
    repository's profile: every audit would then grade the wrong project. If the
    nearest git root has no `.design-suite/`, this refuses (exit 2) naming both
    paths. A plain subdirectory of a configured repository still resolves to it.
    """
    if explicit:
        return Path(explicit).resolve()

    from_env = _from_env()
    if from_env is not None:
        return from_env
    here = Path.cwd().resolve()

    found, git_root, outer = walk(here)
    if found is not None:
        return found
    if git_root is not None and outer is not None:
        print(f"{git_root} is its own git repository with no {MARKER}/, nested inside "
              f"the configured project {outer}. Refusing to audit it with the outer "
              f"project's profile. Run bin/init.py in {git_root} to configure it, or "
              f"run from {outer} (or set CLAUDE_PROJECT_DIR) to audit the outer one.",
              file=sys.stderr)
        raise SystemExit(2)
    print(f"no {MARKER}/ found in {here} or any parent directory — these tools need a "
          f"project profile. Run bin/init.py to create one. Refusing to guess.",
          file=sys.stderr)
    raise SystemExit(2)


def locate(start: Path | None = None) -> Path | None:
    """The same answer as project_root(), or None where it would refuse.

    For the hooks: a hook must never take the user's edit down over a project
    that has not adopted the suite, so "not found" is a value there, not an
    exit. It is the SAME resolution, not a lookalike — the hooks used to carry
    inlined copies of this walk, kept in agreement only by a parity test, and a
    single fix had to land four times.

    `start` is where the walk begins (default: the cwd). A non-Claude harness
    hook passes the directory its payload names, since its cwd may differ.
    """
    from_env = _from_env()
    if from_env is not None:
        return from_env
    found, _git_root, _outer = walk((start or Path.cwd()).resolve())
    return found


def _from_env() -> Path | None:
    """CLAUDE_PROJECT_DIR, but only when it names a configured project."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and (Path(env) / MARKER).is_dir():
        return Path(env)
    return None


# Single source. house-style/bin/resolve_role.py carries a GENERATED copy
# of walk() (it cannot import across plugin caches); after editing it, run
# bin/sync_house_style_walk.py. bin/project_root_test.py fails while it is stale.
def walk(here: Path) -> tuple[Path | None, Path | None, Path | None]:
    """(configured root, blocking git root, outer configured root) from `here` up.

    The first is the answer when found. Otherwise the second is the nearest git
    root that has no marker (None if the walk hit the filesystem root), and the
    third is the configured directory above it that the walk refused to cross —
    reported so the refusal can name both, never returned as the answer.
    """
    chain = [here, *here.parents]
    for i, candidate in enumerate(chain):
        if (candidate / MARKER).is_dir():
            return candidate, None, None
        if (candidate / ".git").exists():
            outer = next((c for c in chain[i + 1:] if (c / MARKER).is_dir()), None)
            return None, candidate, outer
    return None, None, None


PROFILE_REL = f"{MARKER}/profile.json"


def profile(repo: Path) -> dict:
    """The project profile, parsed.

    Five call sites were each reading and parsing this file themselves before the
    ported engines arrived. That is survivable while they all agree; it stops
    being survivable the moment one of them handles a missing key differently
    from the others, because then "this project does not configure X" produces a
    different outcome depending on which audit asked.
    """
    path = repo / PROFILE_REL
    if not path.is_file():
        raise SystemExit(f"no profile at {PROFILE_REL} — run bin/init.py")
    try:
        return json.loads(path.read_text())
    except ValueError as exc:
        raise SystemExit(f"{PROFILE_REL} is not valid JSON: {exc}")


_MISSING = object()


def need(node: dict, dotted: str, why: str, default=_MISSING):
    """A profile value by dotted key, or a hard error naming what is missing.

    `why` is not decoration — it is the whole reason this raises instead of
    returning None. An audit that quietly skips its own input reports zero
    findings, and zero findings is indistinguishable from a clean run. The
    message has to say what the caller wanted the key for so the reader can
    decide whether to add it or drop the audit.

    A `default` is allowed only where absence is a real configuration — not
    where it is an oversight.
    """
    cur = node
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            if default is not _MISSING:
                return default
            raise SystemExit(
                f"{PROFILE_REL} is missing {dotted!r}, which {why}.\n"
                f"Add it, or drop the audit that needs it — do not leave a check "
                f"that silently inspects nothing.")
        cur = cur[part]
    return cur
