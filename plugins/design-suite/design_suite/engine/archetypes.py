"""Project archetypes: which kind of repository this is, and which roles it expects.

The vocabulary lives in `templates/docs/roles.json`, not here, so the kinds and
the per-role applicability cannot disagree — a second copy of the kind list is a
second copy to drift.

Every function here refuses rather than assumes. `UnknownArchetype` is raised for
a kind outside the vocabulary and `ArchetypeNotDeclared` for a profile that never
said: guessing `app` for a package is what makes a scaffolder emit an empty flows
document and a doc audit report a clean sweep of documents it never looked for.
A profile with no `projectKind` is still valid (RFC-0002 §6 keeps this additive)
— it simply cannot be asked archetype questions.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

VOCABULARY = Path(__file__).resolve().parents[2] / "templates" / "docs" / "roles.json"

APPLICABILITY = ("expected", "optional", "na")


class ArchetypeError(Exception):
    """Base for every archetype refusal, so a caller can catch the category."""


class UnknownArchetype(ArchetypeError):
    pass


class ArchetypeNotDeclared(ArchetypeError):
    pass


@lru_cache(maxsize=1)
def vocabulary() -> dict:
    return json.loads(VOCABULARY.read_text())


def kinds() -> list[str]:
    block = vocabulary()["archetypes"]
    return sorted(k for k in block if not k.startswith("_"))


def canonical_role(role: str) -> str:
    """Current name for a role, following a rename alias if there is one."""
    aliases = {k: v for k, v in vocabulary().get("aliases", {}).items()
               if not k.startswith("_")}
    return aliases.get(role, role)


def aliases_of(role: str) -> list[str]:
    """Former names for a role — the reverse direction of `canonical_role`."""
    aliases = {k: v for k, v in vocabulary().get("aliases", {}).items()
               if not k.startswith("_")}
    return sorted(old for old, new in aliases.items() if new == role)


def roles() -> dict[str, dict]:
    """Every role, `pr`'s external-plugin entry included.

    The external one is merged in because it is part of the vocabulary a project
    is measured against; only its *scaffolding* lives in another plugin.
    """
    merged = dict(vocabulary()["roles"])
    merged.update(vocabulary().get("externalPlugin", {}))
    return merged


def require_kind(kind: str | None) -> str:
    """Validate a declared kind, or refuse. Never returns a fallback."""
    if kind is None:
        raise ArchetypeNotDeclared(
            "this project declares no projectKind. Declare one of "
            f"{', '.join(kinds())} in .design-suite/profile.json under `project`, "
            "or handle the absence explicitly — do not assume one.")
    if kind not in kinds():
        raise UnknownArchetype(
            f"unknown projectKind {kind!r}. Known kinds: {', '.join(kinds())}. "
            "A kind outside the vocabulary is a refusal, not a default.")
    return kind


def kind_of(profile: dict) -> str:
    """The archetype a loaded profile declares. Refuses on absent or unknown."""
    return require_kind(profile.get("project", {}).get("projectKind"))


def is_workspace(profile: dict) -> bool:
    """Whether this repo is a container of archetypes.

    Orthogonal to the kind on purpose: a monorepo holding an app and a package
    would have to pick one kind and be wrong either way.
    """
    return bool(profile.get("project", {}).get("workspace", False))


def applicability(role: str, kind: str) -> str:
    """`expected` / `optional` / `na` for one role under one kind."""
    require_kind(kind)
    name = canonical_role(role)
    entry = roles().get(name)
    if entry is None:
        raise UnknownArchetype(f"unknown role {role!r}")
    return entry.get("archetypes", {}).get(kind, "na")


def roles_for(kind: str, include_optional: bool = True) -> list[str]:
    """Roles that apply to a kind. `na` roles are excluded, never silently kept."""
    require_kind(kind)
    wanted = {"expected", "optional"} if include_optional else {"expected"}
    return sorted(name for name, entry in roles().items()
                  if entry.get("archetypes", {}).get(kind) in wanted)
