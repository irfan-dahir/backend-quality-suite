#!/usr/bin/env python3
"""Score this project's declared colour pairs against their WCAG thresholds.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_contrast.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_contrast.py" --json
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_contrast.py" --findings <path>

## Why this exists here at all

It did not, until now. `/audit-contrast` was `maturity: pointer` — a command in
the catalogue whose entire body said "this runs in the design-system repository,
next to the palette it scores". For this repo that was true and harmless. For a
suite being prepared to ship to other teams it was a capability claim that was
not one: the repository it pointed at is private, so for every consumer outside
that org the command resolved to nothing, and a listed command that does nothing
is the governing principle's failure mode wearing a link.

The stated reason for the split does not survive being looked at. Contrast has
two halves and only one of them is palette-shaped:

  * the **pair list** — which foreground goes on which background, at which
    threshold — is a fact about one product, and stays with that product; this
    reads it from the consumer's own `.design-suite/contrast-pairs.json`
  * the **scoring** — relative luminance, the ratio, the WCAG threshold — is
    fixed arithmetic that is identical for every palette in every language

So the scoring moved here (`design_suite/engine/contrast.py`) and the pair list
did not. The design system keeps its own `--matrix` run across every brand and
mode; that is a *fleet* question this plugin has no standing to answer. This
answers the per-project one, which nothing answered before.

## Exit codes

    0   every declared pair meets its threshold
    1   at least one pair is below its threshold — a real finding
    2   refused: no pair list, an unreadable one, a palette that could not be
        resolved, a pair naming a token the palette does not declare, or a
        colour value that could not be parsed

Exit 2 is the interesting one. Every path to it is somewhere this could have
produced a smaller, plausible-looking pass rate instead — a skipped pair, an
empty palette, a colour defaulted to black. It does not. A contrast report that
scores 24 of a declared 26 and still prints "all passing" is indistinguishable
from a clean palette, which is the exact failure this repo is built against.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from design_suite.adapters import for_project            # noqa: E402
from design_suite.engine import contrast as C            # noqa: E402
from design_suite.engine import findings as F            # noqa: E402

# The findings-envelope name is written as the LITERAL "contrast" at each call
# site below rather than hoisted into a constant. That is deliberate and not a
# style slip: repo_health.py greps the envelope name out of an audit's own source
# (audit_discovery.envelope_name) rather than importing it, precisely so the two
# can never drift — and a name reachable only through a variable reads to that
# grep as "this audit writes no envelope at all".

# The adapter layer's existing colour-token convention: `dart.token_names()` is
# documented as "a thin, colour-specific wrapper over token_names_matching" with
# exactly this prefix. Naming it once here rather than re-deciding it means this
# audit and `audit_unused_tokens` disagree about what a colour token is only if
# someone changes it deliberately.
DEFAULT_COLOR_PREFIX = "color"


def palette(adapter, ctx, prefix: str) -> dict:
    """`{token name: declared value text}`, or `ContrastError`.

    `token_declarations` returns `None` for "could not read the token source",
    which the adapter contract is explicit is *not* the same answer as an empty
    palette. Collapsing the two here would turn an unresolved package into a run
    that scores zero pairs and reports no failures.
    """
    if not hasattr(adapter, "token_declarations"):
        raise C.ContrastError(
            f"the {getattr(adapter, 'NAME', '?')!r} adapter cannot read declared "
            f"token values (no token_declarations capability), so this project's "
            f"palette cannot be scored. This is a refusal, not a finding of zero: "
            f"implement the capability or do not list this audit for this stack.")
    declared = adapter.token_declarations(ctx, prefix)
    if declared is None:
        raise C.ContrastError(
            f"could not resolve the token source for colour prefix {prefix!r}. If "
            f"it names a package, install dependencies first — every pair would "
            f"otherwise resolve to nothing and this audit would refuse or, worse, "
            f"pass by being blind.")
    if not declared:
        raise C.ContrastError(
            f"the token source resolved but declares no tokens starting with "
            f"{prefix!r}. Either the prefix is wrong for this project (pass "
            f"--color-prefix) or the palette is empty; both are refusals, because "
            f"an empty palette scores every pair as unresolvable and none as failing.")
    return declared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--color-prefix", default=DEFAULT_COLOR_PREFIX,
                        help=f"name prefix identifying colour tokens "
                             f"(default {DEFAULT_COLOR_PREFIX!r})")
    parser.add_argument("--json", action="store_true",
                        help="print the scored pairs as JSON")
    parser.add_argument("--findings", nargs="?", const="",
                        help="also write the common findings envelope here "
                             "(default .design-suite/findings/contrast.json)")
    args = parser.parse_args()

    try:
        pairs = C.load_pairs(REPO)
        adapter, ctx, _ = for_project(REPO)
        results = C.score(pairs, palette(adapter, ctx, args.color_prefix))
    except C.ContrastError as exc:
        print(f"audit_contrast refused: {exc}", file=sys.stderr)
        return 2

    failing = [r for r in results if not r["passed"]]

    if args.findings is not None:
        path = (Path(args.findings) if args.findings
                else F.default_path(REPO, "contrast"))
        records = [
            F.make("contrast", "wcag-contrast",
                   f"{r['name']}: {r['foreground']} on {r['background']} "
                   f"is {r['ratio']}:1 against a {r['min_ratio']}:1 minimum",
                   severity=F.CRITICAL if not r["passed"] else F.FYI,
                   passed=r["passed"],
                   detail=json.dumps({k: r[k] for k in
                                      ("ratio", "min_ratio", "foreground",
                                       "background", "surface")}))
            for r in results
        ]
        # REPORTS_CHECKS, not violations: every pair is recorded, passing ones
        # included, so "no records" reads as "this never ran" rather than as a
        # perfect score. findings.py reserved this polarity for exactly this audit.
        F.write(path, "contrast", records, reports=F.REPORTS_CHECKS,
                scanned=len(results))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            mark = "✅" if r["passed"] else "🔴"
            print(f"  {mark} {r['name']}: {r['foreground']} on {r['background']} "
                  f"— {r['ratio']}:1 (min {r['min_ratio']}:1)")
        print(f"\n{len(results) - len(failing)}/{len(results)} pairs pass.")

    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
