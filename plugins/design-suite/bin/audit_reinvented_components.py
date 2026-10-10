#!/usr/bin/env python3
"""Private widgets that duplicate a component the design system already ships,
and bespoke widgets built without ever touching the design system at all.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_reinvented_components.py"

## Why this exists

`_SectionLabel` is defined twice in an app. `SectionLabel` has been exported
from the design-system package the whole time.

That is not a missing component — it is a component nobody found. And it is the
failure mode a design system is *most* prone to once it gets large enough that
reading the barrel stops being how people discover things: the cost of a
reinvented widget is not the hour spent writing it, it is that the original now
has a competitor which will drift from it silently.

## What it flags, and what it deliberately does not

**Flagged (FORKED — the name check):** a private widget whose name matches an
exported design-system type, ignoring the leading underscore. `_SectionLabel`
vs `SectionLabel`.

**Not flagged:** a private widget that merely *resembles* one. Judging that
needs a human, and a check that guesses is a check people learn to ignore.

**Not flagged:** a name collision where the shapes differ. `_StickyFooter`
exists twice here and `StickyFooter` is exported, but the app's two are
screen-specific compositions — a subscribe bar and a share bar — that happen to
share a noun. Recorded in ALLOWED with the reason rather than silently skipped,
because "we looked and it was fine" and "nobody looked" should not be the same
absence.

## The gap this audit used to have (issue #21)

Everything above catches *forking* — a private widget that competes with a
design-system component it knows about, however faintly (by name). It has
nothing to say about the opposite failure: a file that reaches *past* the
design system entirely, building its own button/card/modal from primitives,
with no import of the design-system package anywhere in the file, and therefore
no name to collide with. That widget is invisible to the check above by construction —
there is nothing to match. It is also invisible to `audit_promotion_candidates`
unless the same shape happens to be built twice; a one-off is enough to be a
design-system gap in practice, and duplication is not the bar for that.

**Flagged (REACHING PAST — the shape check):** a widget in a file with no
design-system import, whose constructor shape (parameter names, sorted, minus
plumbing) closely resembles an exported design-system component's shape — the
same near-miss, Jaccard-similarity technique `audit_promotion_candidates` uses
to suggest "possibly already covered by", but applied per-file instead of
requiring the shape to reappear elsewhere in the app first, and gated on "does
this file import the design system at all" rather than gated on "is this shape
built twice".

**Not flagged:** a file that already imports the design-system package. If it
is in scope for that file, missing it there is a code-review question, not a
"never even looked" one. **Not flagged:** a similarity below the threshold — see
`REACHING_PAST["threshold"]`; this is a hint, not an assertion, for the same
reason `audit_promotion_candidates`'s suggestions are never confident answers.

## Where the package name comes from

Nowhere in this file. The design system's package name is a fact about the
consuming project, read from `reinventedComponents.package` in its architecture
rules or `tokens.source.package` in its profile — see the comment above
`design_system_package()`. Undeclared is a refusal (exit 2), never a clean run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

sys.path.insert(0, str(REPO))
from design_suite.engine.arch import load  # noqa: E402
from design_suite.engine import ratchet  # noqa: E402
from design_suite.engine.component_shape import (  # noqa: E402
    ShapeSourceError,
    capability_overlap,
    design_system_package,
    load_capabilities,
    package_resolver,
    widget_sources,
)

# Name collisions that are NOT duplication, with why. Vetted per project.
_RULES = load(REPO, "reinventedComponents")
ALLOWED = _RULES["allowedCollisions"]

# The design system's export prefix, from config rather than hardcoded — a
# project whose package prefixes differently must not silently get zero
# matches. Defaults to "Ds" only because that is this ecosystem's convention.
PREFIX = _RULES.get("exportPrefix", "Ds")

# Config for the complementary "reaching past" check (issue #21). Optional —
# a project that has not adopted it yet gets the name check only, not a hard
# error, because unlike ALLOWED/PREFIX this is new surface, not a rewrite of
# the existing contract.
REACHING_PAST = _RULES.get("reachingPast", {})
BESPOKE_ALLOWED = set(REACHING_PAST.get("allowed", []))
BESPOKE_THRESHOLD = REACHING_PAST.get("threshold", 0.6)
BESPOKE_PLUMBING = set(REACHING_PAST.get("plumbingParams", ["key"]))
BESPOKE_NOISE = {frozenset(s) for s in REACHING_PAST.get("noiseParamSets", [])}

# The design system's PACKAGE name and the package manager's resolution map,
# both read from the consuming project's own `.design-suite/` config rather than
# written here. `design_system_package()` carries the full account of what this
# used to be and what it silently did on every project but one; it lives in the
# engine because `audit_promotion_candidates.py` needs the same fact, and one
# fact wants one source.
#
# `None` -> main() REFUSES with exit 2. No fallback: a wrong package name here
# produces a confident zero, the one outcome this suite forbids.
PACKAGE = design_system_package(REPO)
RESOLVE_VIA = package_resolver(REPO)

DS_IMPORT = (
    re.compile(r"""^import\s+['"]package:""" + re.escape(PACKAGE) + "/", re.M)
    if PACKAGE else None)

# Same constructor-parameter extraction `audit_promotion_candidates` uses —
# duplicated rather than imported because these are two independent CLI
# scripts by design (see the module docstring there); the regex is the
# contract, not the module.
_CLASS_RE = re.compile(
    r"^class\s+(\w+)\s+extends\s+(?:StatelessWidget|StatefulWidget)\b", re.M)
_PARAM_RE = re.compile(
    r"(?:required\s+)?(?:this\.(\w+)|[\w<>,\s?]+\s+(\w+))\s*[,)=}]")


def _constructor_params(body: str, cls: str) -> frozenset[str]:
    m = re.search(rf"\b{re.escape(cls)}\s*\(([^)]*)\)\s*(?::[^{{;]*)?[;{{]", body)
    if not m:
        return frozenset()
    names = set()
    for a, b in _PARAM_RE.findall(m.group(1) + ","):
        name = a or b
        if name and name not in BESPOKE_PLUMBING:
            names.add(name)
    return frozenset(names)


def ds_shapes() -> dict[frozenset[str], str]:
    """Parameter shapes of the RESOLVED design-system package's public components.

    Same resolution path as `exported_types()` — through the package manager's
    own map rather than a hardcoded list — so this tracks whatever version is
    actually installed.
    """
    if not PACKAGE:
        return {}
    config = REPO / RESOLVE_VIA
    if not config.is_file():
        return {}
    try:
        entry = next(p for p in json.loads(config.read_text())["packages"]
                     if p["name"] == PACKAGE)
        pkg = Path(entry["rootUri"].replace("file://", ""))
    except (StopIteration, KeyError, json.JSONDecodeError):
        return {}

    out: dict[frozenset[str], str] = {}
    for dart in (pkg / "lib/src/components").glob("*.dart"):
        src = dart.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"^class (\w+) extends\s+\w*Widget", src, re.M):
            cls = m.group(1)
            if cls.startswith("_"):
                continue
            params = _constructor_params(src[m.start():], cls)
            if len(params) >= 2 and params not in BESPOKE_NOISE:
                out.setdefault(params, cls)
    return out


def reaching_past_hits(ds: dict[frozenset[str], str]) -> list[str]:
    """Bespoke widgets in files that never import the design system at all.

    Deliberately per-file and per-occurrence — unlike
    `audit_promotion_candidates`, this does not wait for the shape to be built
    twice. A file that reaches past the design system once already made the
    mistake the design system exists to prevent; requiring a second instance
    would mean the first is free.
    """
    if not ds:
        return []
    capabilities = load_capabilities(REPO)
    # Optional second signal, issue #61: when a capabilities manifest is
    # configured, don't flag a shape match whose hand-authored capabilities
    # clearly diverge from the design-system candidate's — same threshold and
    # reasoning as audit_promotion_candidates.py's near_ds_matches. No
    # manifest configured -> load_capabilities() returns {} -> this never
    # fires -> behaviour is unchanged.
    DIVERGENCE_THRESHOLD = 0.2
    hits = []
    for p in widget_sources(REPO):
        src = p.read_text(encoding="utf-8", errors="replace")
        if DS_IMPORT.search(src):
            continue  # in scope for this file already — not a "never looked" gap
        rel = str(p.relative_to(REPO))
        for m in _CLASS_RE.finditer(src):
            cls = m.group(1)
            if f"{rel}:{cls}" in BESPOKE_ALLOWED:
                continue
            nxt = _CLASS_RE.search(src, m.end())
            body = src[m.start(): nxt.start() if nxt else len(src)]
            params = _constructor_params(body, cls)
            if len(params) < 2 or params in BESPOKE_NOISE:
                continue
            best_name, best_score = None, 0.0
            for cand, name in ds.items():
                overlap = len(params & cand)
                if overlap < 2:
                    continue
                j = overlap / len(params | cand)
                if j > best_score:
                    best_name, best_score = name, j
            if best_name and best_score >= BESPOKE_THRESHOLD:
                if capabilities:
                    overlap = capability_overlap(
                        capabilities.get(cls), capabilities.get(best_name)
                    )
                    if overlap is not None and overlap < DIVERGENCE_THRESHOLD:
                        continue
                hits.append(
                    f"{rel}: {cls} — resembles {best_name} "
                    f"({round(best_score * 100)}%), file never imports {PACKAGE}")
    return hits


# Known duplicates, as a ratchet — same mechanism audit_layer_boundaries uses.
#
# Needed because adding the prefixed-name rule turned 0 findings into 16 overnight:
# real debt that was invisible, not new debt. Failing hard on all of it would block
# every push until someone triaged 16 components, and the predictable outcome of
# that is the check being deleted.
#
# So: existing entries do not fail; anything NEW does. A baselined entry is untriaged
# debt, NOT an accepted collision — `allowedCollisions` is the place for "verified
# not a duplicate", and conflating the two would turn this into the silent
# suppression the audit exists to prevent.
BASELINE_PATH = REPO / _RULES["baseline"] if "baseline" in _RULES else None


def exported_types() -> set[str]:
    """Public component types from the RESOLVED design-system package.

    Read from the package manager's resolution map rather than `dart pub deps`,
    which does not report package paths. This resolves whatever version is
    actually installed — so the check tracks the pinned tag rather than a
    hardcoded list that would rot the first time the dependency moves.
    """
    if not PACKAGE:
        return set()
    config = REPO / RESOLVE_VIA
    if not config.is_file():
        return set()
    try:
        entry = next(p for p in json.loads(config.read_text())["packages"]
                     if p["name"] == PACKAGE)
        pkg = Path(entry["rootUri"].replace("file://", ""))
    except (StopIteration, KeyError, json.JSONDecodeError):
        return set()

    types: set[str] = set()
    for dart in (pkg / "lib/src/components").glob("*.dart"):
        types |= set(re.findall(r"^class (\w+) extends", dart.read_text(),
                                flags=re.M))
    return {t for t in types if not t.startswith("_")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline to match reality. Use after adopting a component, "
             "never to silence a new finding.",
    )
    ap.add_argument(
        "--accept-new", action="store_true",
        help="with --update-baseline, deliberately accept duplicates that are not "
             "yet baselined. Without it the write is refused rather than absorbing "
             "a regression nobody was shown.",
    )
    ap.add_argument("--findings", nargs="?", const=True, default=None,
                    help="also write the common findings envelope for /design-debt "
                         "(bare flag uses the default path)")
    args = ap.parse_args()

    if not PACKAGE:
        # Cannot answer, so say so. Without a declared design-system package
        # there is nothing to compare private widgets AGAINST, and every check
        # below would report zero for that reason alone — the exact silence
        # this suite treats as a defect. Exit 2 is "I could not look", the same
        # split the resolution refusal below uses.
        print(
            "audit_reinvented_components: REFUSING TO RUN\n\n"
            "this project does not declare the package its design system ships "
            "as, so there is nothing to compare private widgets against.\n"
            "Set `reinventedComponents.package` in the architecture rules, or "
            "`tokens.source.package` in .design-suite/profile.json (with "
            "tokens.source.kind = \"package\").",
            file=sys.stderr,
        )
        return 2

    exported = exported_types()
    if not exported:
        # Refuse, never skip clean. Per the suite's governing principle, an
        # audit that reports nothing must never be indistinguishable from a
        # clean codebase — and an unresolvable dependency means this check
        # never compared anything, which is "cannot answer", not "found
        # nothing". `1` means "I looked and this is wrong"; `2` means "I
        # could not look" (the same split `audit_contract_headers.refuse`
        # and `audit_layer_boundaries` use). Exiting 0 here — as this used
        # to do unless a since-removed `--require-resolution` flag was
        # passed — let a broken `flutter pub get` pass as a clean run on
        # every machine that forgot the flag, CI included.
        print(
            "audit_reinvented_components: REFUSING TO RUN\n\n"
            f"could not resolve {PACKAGE} — resolve dependencies (for "
            f"Flutter, `flutter pub get`) before this audit.",
            file=sys.stderr,
        )
        return 2

    try:
        sources = widget_sources(REPO)
    except ShapeSourceError as exc:
        # This sweep used to be a literal `lib/**/*.dart`: a project rooted
        # anywhere else compared nothing and reported zero reinventions.
        print(f"audit_reinvented_components: REFUSING TO RUN\n\n{exc}", file=sys.stderr)
        return 2

    hits: list[str] = []
    for p in sources:
        for m in re.finditer(r"^class (_\w+) extends (?:Stateless|Stateful)Widget",
                             p.read_text(), flags=re.M):
            name = m.group(1)
            if name in ALLOWED:
                continue
            bare = name.lstrip("_")
            # Two forms, because the design system prefixes its exports.
            #
            # Only the unprefixed form was checked before, which meant the common
            # case slipped through: a private `_BulletList` beside an exported
            # `DsBulletList` never matched, since `BulletList` is not what the
            # package exports. That is not a rare shape — it is what "built in the
            # design system while the app kept its private copy" looks like, and
            # /promote-component's Step 4 is entirely about it.
            #
            # A single-file private duplicate is also invisible to
            # audit_promotion_candidates, which only flags a shape built in more
            # than one file. Between the two checks the case had no owner.
            for candidate in (bare, f"{PREFIX}{bare}"):
                if candidate in exported:
                    hits.append(f"{p.relative_to(REPO)}: {name} — "
                                f"{PACKAGE} exports {candidate}")
                    break

    hits.extend(reaching_past_hits(ds_shapes()))

    current = set(hits)

    # Loaded before the write so --update-baseline can tell a genuine improvement
    # from a regression it would otherwise absorb unseen.
    baseline = set()
    if BASELINE_PATH is not None and BASELINE_PATH.is_file():
        baseline = set(json.loads(BASELINE_PATH.read_text()))

    if args.update_baseline:
        if BASELINE_PATH is None:
            print("no reinventedComponents.baseline configured", file=sys.stderr)
            return 2
        refusal = ratchet.refusal("audit_reinvented_components", current, baseline,
                                  unit="duplicate")
        if refusal and not args.accept_new:
            print(refusal, file=sys.stderr)
            return 2
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(sorted(current), indent=2) + "\n")
        print(f"audit_reinvented_components: baseline updated — "
              f"{len(current)} known duplicate(s)")
        return 0

    new_hits = sorted(current - baseline)

    if args.findings:
        from design_suite.engine import findings as F
        # Hits are formatted strings — "path: Name — <package> exports X" — so the
        # file is split back off the front rather than re-derived. Baselined hits
        # stay in as FYI: the roadmap tracks these 12 as D5, and a register that
        # drops what has been accepted stops being a register.
        def _split(hit: str):
            head, _, rest = hit.partition(": ")
            return (head if "/" in head else None), (rest or hit)
        F.write(
            F.default_path(REPO, "reinvented_components") if args.findings is True
            else REPO / args.findings,
            "reinvented_components",
            [F.make("reinvented_components", "reinvented",
                    _split(h)[1],
                    severity=F.SHOULD_FIX if h in new_hits else F.FYI,
                    file=_split(h)[0])
             for h in sorted(current)],
            scanned=len(current),
        )
    fixed = sorted(baseline - current)

    print(f"  design-system types  {len(exported)}")
    print(f"  reinvented here      {len(current)}"
          f"  ({len(ALLOWED)} documented collision(s),"
          f" {len(current & baseline)} baselined)")

    if fixed:
        print(f"\n{len(fixed)} baselined duplicate(s) no longer present — nice:")
        for f_ in fixed:
            print(f"  {f_}")
        print("  Run with --update-baseline to lock the improvement in.")

    hits = new_hits
    if hits:
        print("\nREINVENTED — a private widget with the name of a component "
              "that already exists, or built in a file that reaches past the "
              "design system entirely:\n", file=sys.stderr)
        for h in hits:
            print(f"  {h}", file=sys.stderr)
        print(
            "\nFor a name match: use the exported one, or — if it genuinely "
            "does something different — rename it so the next person does "
            "not have to work out which is which. If the names collide but "
            "the shapes do not, add it to ALLOWED with the reason.\n"
            f"For a 'resembles X, file never imports {PACKAGE}' match: check "
            f"whether {PACKAGE} already covers this before building further "
            f"on top of it. If it genuinely is a different thing, add "
            "'<file>: <Class>' to reachingPast.allowed with the reason.",
            file=sys.stderr,
        )
        return 1

    print("\naudit_reinvented_components: nothing reinvented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
