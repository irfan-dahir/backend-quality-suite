"""Asset adapters — how bundled imagery enters a project, and the loader.

The generation side of an asset pipeline (Blender, rendering, encoding) is already
project-agnostic. All the coupling sits at the **registration** boundary: where a
rendered file lands, how it is declared to the build system, and what "registered"
even means. That boundary is what these adapters abstract.

Named by `adapters.assets` in the project profile.

An adapter implements `AssetAdapterProtocol` (see ../base.py). The rule that
matters most: `is_registered()` must raise `CapabilityError` when the stack has no
registry to consult, never return False. Returning False would manufacture a
permanent false finding on every asset; returning True would hide every real one.
"""
from __future__ import annotations

import importlib
from pathlib import Path

PROFILE = ".design-suite/profile.json"


def load(name: str):
    """Import the asset adapter called `name`. Unknown is a hard error.

    Same reasoning as the language loader: a silent fallback would audit a project
    against another stack's registration rules and report zero problems, which is
    indistinguishable from a correctly-registered library.
    """
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ImportError as exc:
        available = sorted(p.stem for p in Path(__file__).parent.glob("*.py")
                           if p.stem != "__init__")
        raise SystemExit(
            f"unknown asset adapter {name!r} (from {PROFILE} adapters.assets).\n"
            f"available: {', '.join(available)}\n{exc}")


def for_project(repo: Path):
    """(adapter, ctx) for whatever `adapters.assets` the profile names."""
    from .. import load_project
    from ..base import AdapterContext

    profile, exceptions = load_project(repo)
    name = (profile.get("adapters", {}) or {}).get("assets")
    if not name:
        raise SystemExit(
            f"{PROFILE} does not set adapters.assets — cannot pick an asset adapter")
    ctx = AdapterContext(repo=repo, profile=profile, exceptions=exceptions)
    return load(name), ctx
