"""Asset adapter for bundler-driven projects — Vite, webpack, Next, Metro.

This adapter exists to be *correct about refusing*, which is a real job.

In these stacks there is no asset registry. A file becomes part of the build
because something imports it, or because it sits in a conventional public
directory that gets copied wholesale. Nothing declares assets, so
"is this asset registered?" has no answer.

The protocol spec is explicit about this case: an adapter that cannot tell must
raise rather than return False. Both wrong answers are worse than an error:

    return False  →  every asset reported unregistered, forever. A permanent
                     false finding trains people to ignore the audit.
    return True   →  every genuinely-missing asset hidden. The audit reports
                     clean and means nothing.

So `is_registered` and `register` raise `CapabilityError`, and the audit surfaces
that as a refusal naming the missing capability — the same contract the language
adapters follow when `tsx` is asked for accessibility checks.

What this adapter *can* answer is where assets live and where the manifest is,
which is enough for the parts of an asset audit that do not involve registration:
orphan detection, manifest drift, naming conventions.
"""
from __future__ import annotations

from ..base import CapabilityError

NAME = "bundler"
_WHY = ("bundler-driven projects have no asset registry — a file is included "
        "because something imports it or because it sits in a copied public "
        "directory. There is nothing to consult, so any boolean here would be "
        "invented")


def asset_root(ctx) -> str:
    declared = (ctx.profile.get("assets", {}) or {}).get("root")
    return declared or "public"


def manifest_path(ctx) -> str:
    pipelines = ctx.profile.get("pipelines", {}) or {}
    return f"{pipelines.get('assets', 'asset_pipeline')}/manifest.json"


def local_manifest_path(ctx) -> str:
    pipelines = ctx.profile.get("pipelines", {}) or {}
    return f"{pipelines.get('assets', 'asset_pipeline')}/manifest.local.json"


def registered_entries(ctx):
    raise CapabilityError("registered_entries", NAME, _WHY)


def is_registered(ctx, path: str) -> bool:
    raise CapabilityError("is_registered", NAME, _WHY)


def register(ctx, path: str) -> None:
    raise CapabilityError(
        "register", NAME,
        _WHY + ". Import the asset from code, or place it under "
        f"{asset_root(ctx)!r}, instead")
