"""Flutter scaffold adapter — screen file, contract header, adapter companion.

Implements `ScaffoldAdapterProtocol`. Everything here is read out of the profile
(`source.screensGlob`, `source.root`) rather than hardcoded, so a Flutter project
with a different layout is not overridden.

## The contract header is the load-bearing part

Screens in the originating project open with an all-caps `<NAME> SCREEN CONTRACT`
block declaring PURPOSE, RULES, INPUT and OUTPUT. It is not decoration: the
documentation audit checks for it, and it is what stops a screen quietly growing
data-fetching logic. So the scaffold emits it with the INPUT/OUTPUT sections
marked `DECIDE` rather than inventing plausible fields — a header full of
guessed-at inputs is worse than an obviously-unfinished one, because it looks
authoritative.

Note for anyone matching this header elsewhere: search case-insensitively for
`CONTRACT` alone. A case-sensitive match on the exact phrase "Screen Contract" is
a confirmed false positive — it flagged 69 correctly-formed headers.

## Honest status

`/scaffold-screen` has never been run to produce a real screen that shipped; its
only verification on record is a throwaway file that was compiled and deleted.
Building this seam does not change that, and does not upgrade the skill's
maturity. What it does mean is that the next person to run it is working against
a defined contract instead of prose.
"""
from __future__ import annotations

import re

from . import STATES

NAME = "flutter"


def _snake(name: str) -> str:
    s = re.sub(r"[\s-]+", "_", name.strip())
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    return re.sub(r"__+", "_", s).strip("_").lower()


def _pascal(name: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in _snake(name).split("_") if p)


def _feature_root(ctx, feature: str) -> str:
    root = (ctx.profile.get("source", {}) or {}).get("root", "lib")
    return f"{root}/features/{_snake(feature)}"


def screen_path(ctx, name: str, feature: str | None = None) -> str:
    """Where a screen file belongs.

    Derived from `source.screensGlob` so the convention comes from the project.
    The glob in the originating profile is `lib/features/*/presentation/pages/
    *_screen.dart`; this fills in the two wildcards.
    """
    feature = feature or name
    return f"{_feature_root(ctx, feature)}/presentation/pages/{_snake(name)}_screen.dart"


def companion_files(ctx, name: str, feature: str | None = None) -> list[dict]:
    """Files a screen cannot exist without in this stack.

    The adapter class is mandatory, not a nicety: every feature exposes exactly
    one, it is the only bridge between presentation and the outside world, and
    `audit_adapter_pattern.py` fails a feature that lacks one. A scaffolder that
    emitted just the screen would produce a repo failing its own architecture
    audit on the first run.
    """
    feature = feature or name
    cls = _pascal(feature)
    return [{
        "path": f"{_feature_root(ctx, feature)}/{_snake(feature)}_adapter.dart",
        "why": ("Mandatory. The single bridge between presentation and the outside "
                "world; audit_adapter_pattern.py fails a feature without one."),
        "body": f"""/// {cls}Adapter — the only bridge between {cls}Screen and the outside world.
///
/// INPUTS are what the UI reads. OUTPUTS are what it can emit. Business logic,
/// API calls and state management do NOT belong here — they belong in the domain
/// layer and the BLoC.
class {cls}Adapter {{
  const {cls}Adapter();

  // INPUTS
  // DECIDE: declare each value the screen renders, e.g.
  //   String get patientName;

  // OUTPUTS
  // DECIDE: declare each event the screen can emit, e.g.
  //   void onRetry();
}}
""",
    }]


def render(ctx, name: str, states=STATES, feature: str | None = None) -> str:
    """The screen file body.

    `states` is the portable part — loading, error, content. Everything else here
    is this stack's: widget names, the contract-header convention, and how the
    adapter arrives.
    """
    cls = _pascal(name)
    feature = feature or name
    acls = _pascal(feature)
    heading = _snake(name).replace("_", " ").upper()

    branches = "\n".join(
        f"        // {s}\n"
        f"        if (state.is{_pascal(s)}) return const _{cls}{_pascal(s)}();"
        for s in states if s != "content")

    placeholders = "\n\n".join(
        f"""class _{cls}{_pascal(s)} extends StatelessWidget {{
  const _{cls}{_pascal(s)}();

  @override
  Widget build(BuildContext context) {{
    // DECIDE: the {s} presentation for this screen.
    return const SizedBox.shrink();
  }}
}}""" for s in states if s != "content")

    return f"""/*
==============================================================================
{heading} SCREEN CONTRACT
==============================================================================

PURPOSE:
DECIDE: one paragraph — what this screen is for, how it is reached, and what it
does not do. Written for someone who has never seen the feature.

RULES:
1. Do not fetch data.
2. Do not call repositories.
3. Do not call APIs.
4. Do not access Bloc directly.
5. Do not modify the adapter interface.
6. UI changes are allowed.
7. Layout changes are allowed.
8. Styling changes are allowed.

INPUT:
DECIDE: list every `adapter.<field>` this screen reads. Do not guess — an
authoritative-looking list of invented fields is worse than an empty one.

OUTPUT:
DECIDE: list every `adapter.<callback>()` this screen can emit.

Any new functionality must be added through {acls}Adapter.
==============================================================================
*/

import 'package:flutter/material.dart';

class {cls}Screen extends StatelessWidget {{
  const {cls}Screen({{super.key, required this.adapter}});

  final {acls}Adapter adapter;

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      body: SafeArea(
        child: Builder(builder: (context) {{
{branches}
          // content
          // DECIDE: the real content for this screen.
          return const SizedBox.shrink();
        }}),
      ),
    );
  }}
}}

{placeholders}
"""


def register(ctx, name: str, feature: str | None = None) -> list[dict]:
    """Edits needed to route to the screen, described rather than applied.

    Returned as a description on purpose. The router is a file humans own and
    ordering inside it carries meaning; a scaffolder that rewrites it is the part
    most likely to do real damage.
    """
    root = (ctx.profile.get("source", {}) or {}).get("root", "lib")
    cls = _pascal(name)
    return [{
        "file": f"{root}/app/router/app_router.dart",
        "edit": (f"Add a GoRoute for /{_snake(name).replace('_', '-')} building "
                 f"{cls}Screen, with its adapter supplied by the feature's "
                 f"dependency wiring."),
        "why": "Routing order and guards are human decisions; this is not applied automatically.",
    }, {
        "file": "DOC:flows",
        "edit": f"Document the new route and how the user reaches {cls}Screen.",
        "why": ("review-docs flags any route in the router that no document "
                "mentions, so skipping this makes the next audit fail."),
    }]
