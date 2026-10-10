"""Scaffold adapters — how a new screen is generated, and the loader.

`/scaffold-screen` already separates a portable three-state core — loading, error,
content — from its stack-specific instantiation. This is the seam that finishes
that split in code rather than only in prose.

Named by `adapters.scaffold` in the project profile.

Two rules carried over from the protocol spec, both about damage limitation:

- **`register()` returns a description of the edits, it does not apply them.**
  Routing is where a scaffolder does the most harm if it guesses, and a router is
  a file humans own.
- **`companion_files()` is not optional cosmetics.** In the originating project a
  screen without its adapter class fails the architecture audit, so a scaffolder
  that emits only the screen produces a repo that does not pass its own checks.
"""
from __future__ import annotations

import importlib
from pathlib import Path

PROFILE = ".design-suite/profile.json"

# The portable part: every screen has these three states, whatever the stack.
STATES = ("loading", "error", "content")


def load(name: str):
    """Import the scaffold adapter called `name`. Unknown is a hard error."""
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ImportError as exc:
        available = sorted(p.stem for p in Path(__file__).parent.glob("*.py")
                           if p.stem != "__init__")
        raise SystemExit(
            f"unknown scaffold adapter {name!r} (from {PROFILE} adapters.scaffold).\n"
            f"available: {', '.join(available)}\n{exc}")


def for_project(repo: Path):
    """(adapter, ctx) for whatever `adapters.scaffold` the profile names."""
    from .. import load_project
    from ..base import AdapterContext

    profile, exceptions = load_project(repo)
    name = (profile.get("adapters", {}) or {}).get("scaffold")
    if not name:
        raise SystemExit(
            f"{PROFILE} does not set adapters.scaffold — cannot pick a scaffold adapter")
    ctx = AdapterContext(repo=repo, profile=profile, exceptions=exceptions)
    return load(name), ctx
