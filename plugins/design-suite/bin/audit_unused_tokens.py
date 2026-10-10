#!/usr/bin/env python3
"""A design token nothing reads is dead weight in the palette.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_unused_tokens.py"

## Why this exists

`audit_unwired_roles.py` asks "of the semantic colour roles this design system
defines, which does no component ever read?" — the theming contract's actual
surface. This is the same question asked one layer down and across more
categories: of the raw tokens the token file declares — spacing, radii,
durations, curves, sizing, colour, whatever naming convention this project
actually uses — which does nothing in the scanned source ever reference?

A token nobody reads is not a theming risk the way an unwired role is (nothing
re-skins on it), but it is still the thing a pruning pass exists to find: dead
weight in the palette, one `spaceXX` or `radiusYY` a designer keeps seeing in
the file and has to re-verify is safe to delete every time, because "declared"
and "used" have quietly drifted apart.

## Sharing with `audit_unwired_roles.py` rather than duplicating it

Both scripts ask the identical shape of question — of a declared name and a way
to detect a read, which names are never read? — against different graphs. That
comparison (`design_suite/engine/tokens.py`: `unwired()`, `split_required()`) is
shared; only the *language-specific* halves differ and stay in the adapter:

  - what counts as "declared" (`dart.token_names_matching(ctx, prefix)`, a
    generalisation of the colour-only `dart.token_names`/`color_role_names`)
  - what counts as "read" (the project's `tokens.accessor`, the same one
    `audit_tokens.py` already uses to recognise `AppTokens.space16`)

## Categories are config, not a Dart convention baked into this script

Which name prefixes mean "spacing" vs "radius" vs "duration" is a project's own
naming convention, not a fact this script or the adapter is allowed to guess.
It is read from `unusedTokens.categories` in the project's architecture rules
(`.design-suite/arch-rules.json`), same `engine/arch.load()` mechanism every
other structural audit here uses — an empty or absent section is a refusal to
run, not a pass with nothing checked.

## What "used" means, and the None-vs-empty-set contract

Identical to `audit_unwired_roles.py`: a token counts as read when something
matches it through the token accessor (`AppTokens.space16`). Being declared in
the token file does not count as being used. And when the adapter cannot
resolve the token source at all (the package containing it is not installed,
say), that is `None`, never an empty set — reporting `None` as "no tokens
exist" would make every token look wired and this audit would pass by being
blind, exactly the failure `token_names`/`color_role_names` already guard
against for the colour case.

## Exemptions are debts, not verdicts

Same as `audit_unwired_roles.py`: a token can be legitimately unread and still
belong in the graph (consumed by an asset pipeline, say, not by the swept
source). Those carry a reason in `exceptions.json`'s `unusedTokens.exempt` so
"we decided" and "nobody noticed" stay distinguishable.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
from design_suite.adapters import for_project        # noqa: E402
from design_suite.engine.arch import load            # noqa: E402
from design_suite.engine.tokens import split_required, unwired as find_unwired  # noqa: E402
from design_suite.engine import source_roots as source_roots_engine  # noqa: E402
from design_suite.engine import findings as F  # noqa: E402
from design_suite.project import need, profile       # noqa: E402
from design_suite.engine.refusal import Refused  # noqa: E402

_RULES = load(REPO, "unusedTokens")


def _exemptions() -> dict:
    rel = need(profile(REPO), "audits.exceptionsFile",
               "is where audit_unused_tokens reads its documented exemptions from")
    path = REPO / rel
    if not path.is_file():
        raise Refused(f"exceptions file not found at {rel}")
    try:
        exceptions = json.loads(path.read_text())
    except ValueError as exc:
        raise Refused(f"{rel} is not valid JSON: {exc}")
    return (exceptions.get("unusedTokens", {}) or {}).get("exempt", {}) or {}


def _declared_tokens(adapter, ctx, categories: dict) -> dict:
    """{category: set(names)}, or a SystemExit if any category is undeterminable.

    Every category is resolved even if an earlier one is empty — an empty
    category (a project with no curve tokens, say) is a legitimate answer and
    must not stop the sweep of the rest. `None` from the adapter is not that; it
    means the token source itself could not be read, and must abort the whole
    audit rather than being silently treated as "this category has zero tokens".
    """
    if not hasattr(adapter, "token_names_matching"):
        raise Refused(
            f"the {getattr(adapter, 'NAME', '?')!r} adapter cannot enumerate "
            "design tokens by category (no token_names_matching capability). "
            "This is a refusal, not a finding of zero — pick a different "
            "adapter or implement the capability before trusting this audit.")

    by_category = {}
    for category, prefix in categories.items():
        if not prefix:
            raise Refused(
                f"unusedTokens.categories.{category} has no name prefix — "
                "cannot tell which declared tokens belong to it")
        names = adapter.token_names_matching(ctx, prefix)
        if names is None:
            raise Refused(
                f"could not resolve tokens.source for category {category!r} "
                f"(prefix {prefix!r}). If it names a package, install "
                "dependencies first; every token would otherwise read as wired "
                "and this audit would pass by being blind.")
        by_category[category] = names
    return by_category


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /design-debt "
                             "(default .design-suite/findings/unused-tokens.json)")
    args = parser.parse_args()

    categories = _RULES.get("categories")
    if not categories:
        raise Refused(
            "arch-rules.json's unusedTokens.categories is empty or missing — "
            "nothing would ever be checked. Name at least one "
            '{"category": "namePrefix"} pair matching this project\'s token '
            "naming convention (e.g. {\"spacing\": \"space\", \"radius\": \"radius\"}).")

    adapter, ctx, _ = for_project(REPO)
    by_category = _declared_tokens(adapter, ctx, categories)

    all_names = {name for names in by_category.values() for name in names}
    if not all_names:
        raise Refused(
            "unusedTokens.categories resolved but matched no declared tokens — "
            "refusing to report clean on an empty set.")

    accessor = ctx.token_accessor
    if not accessor:
        raise Refused(
            "tokens.accessor is not set in the profile — nothing would ever "
            "count as a token read")

    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    file_glob = need(profile(REPO), "source.fileGlob",
                     "is how this audit finds the sources that read tokens")
    # "Is this token read anywhere?" is a reachability question, so the roots are
    # unioned: a token read in one workspace member is read. See
    # engine/source_roots.py for why the other kind of question attributes instead.
    try:
        scan_roots = source_roots_engine.resolve(REPO, profile(REPO))
        sources = source_roots_engine.source_files(REPO, profile(REPO), file_glob,
                                                   generated)
    except source_roots_engine.SourceRootError as exc:
        raise Refused(str(exc))
    if not sources:
        rels = ", ".join(p.relative_to(REPO).as_posix() for p in scan_roots)
        raise Refused(f"source.fileGlob {file_glob!r} matched nothing under any "
                         f"declared source root ({rels}) — an empty sweep would report "
                         f"every token wired")
    src = "\n".join(p.read_text() for p in sources)

    exempt = _exemptions()
    declared_required = _RULES.get("requiredTokens")
    required = all_names if declared_required is None else set(declared_required)

    candidates = {n for n in all_names if n not in exempt}
    accessor_pattern = re.escape(accessor)
    unwired = find_unwired(candidates, accessor_pattern, src)
    failing, unused = split_required(unwired, required)

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"failing": failing, "unusedButAllowed": unused}, indent=2) + "\n")

    if args.findings:
        # Category is the project's own token category (spacing, radius, ...),
        # so /design-debt grades a dead radius separately from a dead duration
        # rather than rolling every unread token into one row.
        of_category = {n: c for c, names in by_category.items() for n in names}
        records = (
            [F.make("unused-tokens", of_category.get(n, "token"),
                    f"{n} is declared and read nowhere",
                    severity=F.SHOULD_FIX,
                    detail="claimed by unusedTokens.requiredTokens")
             for n in failing]
            + [F.make("unused-tokens", of_category.get(n, "token"),
                      f"{n} is declared and read nowhere here",
                      severity=F.FYI,
                      detail="offered by the token source, not claimed by this "
                             "project — see unusedTokens.requiredTokens")
               for n in unused])
        F.write(
            F.default_path(REPO, "unused-tokens") if args.findings is True
            else REPO / args.findings,
            "unused-tokens", records,
            # The sweep is over declared tokens, not over files: zero findings
            # means nothing unless the size of the set checked comes with it.
            scanned=len(all_names),
            suppressed={"exempt": sorted(exempt)} if exempt else None,
        )

    print(f"  tokens declared   {len(all_names)}  ({len(categories)} categor"
          f"{'y' if len(categories) == 1 else 'ies'}: {', '.join(sorted(categories))})")
    print(f"  wired             {len(all_names) - len(unwired) - len(exempt)}"
          f"  ({len(exempt)} documented exemption(s))")

    if unused:
        # Reported every run, never failed — see split_required.
        print(f"  unread here       {len(unused)}: {', '.join(unused)}")
        print("                    (declared, not claimed by this project — see "
              "unusedTokens.requiredTokens)")

    sys.stdout.flush()  # so the summary above lands before the stderr block

    if failing:
        print(f"\nUNUSED — {len(failing)} token(s) this project claims and reads "
              f"nowhere:\n", file=sys.stderr)
        for name in failing:
            print(f"  {name}", file=sys.stderr)
        print(
            "\nA token nothing reads is dead weight in the palette. Either read "
            "it somewhere, move it out of unusedTokens.requiredTokens, exempt it "
            "WITH A REASON in the exceptions file, or — if no call site ever "
            "wanted it — delete it; that is the honest answer to a token nothing "
            "asks for.",
            file=sys.stderr)
        return 1

    print("\naudit_unused_tokens: every claimed design token is read by something")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
