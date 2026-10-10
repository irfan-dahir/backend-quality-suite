#!/usr/bin/env python3
"""Private widgets built more than once — the design system's intake queue.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_promotion_candidates.py"
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_promotion_candidates.py" --update-baseline

## Why this exists, given there is already a reinvention audit

`audit_reinvented_components.py` answers "does this private widget have the same
NAME as something the design-system package exports". That is a precise question
with a precise answer, and it deliberately refuses to guess at resemblance.

The consequence is that it cannot see the two failures that actually cost the
most:

1. **A renamed duplicate.** `_IconBtn` in `tour_notes_screen.dart` is a worse
   `DsInteractive` — no focus ring, no semantics, on the button that saves a
   note. Different noun, so the name check is blind to it.
2. **A widget invented twice inside the app**, where the design system has
   nothing yet and so there is no name to match against. `_LegendItem` and
   `_VisitsLegend._item` were the same swatch-and-label row in two features,
   months before `DsChartLegend` existed.

Both are mechanical if you stop matching names and start matching **shape**.

## What "shape" means here

A widget's constructor parameter names, sorted, with `key` dropped. Two classes
in different files with the same parameter set are doing the same job with high
reliability — `(color, label)` twice is a legend entry twice, whatever each
file decided to call it.

This is a heuristic and it is stated as one. It is tuned to under-report:
single-parameter widgets are ignored only when that one parameter is itself
generic (`child`, `item`, ... — `(child)` would match half the codebase); a
domain-specific single param (`block`, `ticket`, `conversation`) is a real
signature and is kept. A signature must still appear in **two or more
different files** before it counts, and near-identical signatures — the same
idiom with one param added, dropped, or renamed — are clustered together
instead of requiring exact equality. A candidate is a question worth asking,
not a defect.

## Why this repo needs it now

A second designer is working in this app. When they build a feature that needs a
component, nothing currently notices — the design system finds out when someone
happens to read the diff. This turns "did anyone reinvent something" from an act
of attention into a command, and `--update-baseline` makes today's duplication
the ceiling rather than the norm.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
sys.path.insert(0, str(REPO))
from design_suite.engine.arch import load  # noqa: E402
from design_suite.engine.component_shape import (  # noqa: E402
    ShapeSourceError,
    capability_overlap,
    design_system_package,
    load_capabilities,
    package_resolver,
    widget_sources,
)

_RULES = load(REPO, "promotionCandidates")
BASELINE = REPO / _RULES["baseline"]

# The design system's package name and the package manager's resolution map,
# from the consuming project's own config — see `design_system_package()` for
# what these used to be (one consumer's package name, in a regex literal in the
# universal plugin) and what that silently did everywhere else.
#
# Unlike audit_reinvented_components.py this audit does NOT refuse when the
# package is undeclared: its primary finding — the same widget shape built in
# more than one file — is answerable without a design system at all. What it
# loses is the `near_ds` suggestion, and losing it silently is the failure this
# suite forbids, so `ds_shapes()` says so on stderr rather than returning {}
# with no explanation.
PACKAGE = design_system_package(REPO)
RESOLVE_VIA = package_resolver(REPO)


def load_component_maturity() -> dict[str, str]:
    """Component name -> `status`, from the project's own maturity file.

    Optional (see profile.schema.json's `componentMaturity`, and
    templates/component-maturity.schema.json): a project that has not
    populated one gets an empty map here, and every candidate is treated
    the same as before this existed. This is deliberately NOT the suite's
    own proven/unverified/experimental/pointer tier — that one grades this
    suite's audits and skills, not a consumer project's UI components.
    """
    profile_path = REPO / ".design-suite/profile.json"
    if not profile_path.is_file():
        return {}
    try:
        profile = json.loads(profile_path.read_text())
    except json.JSONDecodeError:
        return {}
    rel = profile.get("componentMaturity", {}).get("file")
    if not rel:
        return {}
    maturity_path = REPO / rel
    if not maturity_path.is_file():
        return {}
    try:
        data = json.loads(maturity_path.read_text())
    except json.JSONDecodeError:
        return {}
    return {
        name: entry.get("status", "")
        for name, entry in data.get("components", {}).items()
        if isinstance(entry, dict)
    }

# A class declaration and everything up to the first `}` that starts a line at
# class indentation. Good enough to find the constructor; this is a heuristic
# audit and a real parser would be a lot of machinery for a hint.
CLASS_RE = re.compile(
    r"^class\s+(_\w+)\s+extends\s+(?:StatelessWidget|StatefulWidget)\b",
    re.M,
)

# `required this.foo` / `this.foo` / `required Foo foo` inside a ctor.
#
# `}` belongs in the terminator class, and leaving it out was a real bug: a
# Dart named-parameter list ends `..., required this.beta})`, so the LAST
# parameter of every widget was silently dropped. `(alpha, beta)` scanned as
# `(alpha)`, which then fell under the two-parameter floor and vanished
# entirely. The audit reported 17 duplicated shapes and every one of them was
# missing a name.
#
# Found by planting two identical widgets and watching the check not fire —
# which is the only reason to plant them.
PARAM_RE = re.compile(r"(?:required\s+)?(?:this\.(\w+)|[\w<>,\s?]+\s+(\w+))\s*[,)=}]")

# Parameters that carry no design information.
#
# `theme` is the interesting one: passing `ThemeData` down as a constructor
# argument is an app habit, not a component's interface — every design-system
# component reads it from context instead. Counting it made `_PriceItem(amount,
# label, theme)` look like a different component from `DsPriceRow(amount,
# label, emphasis)`, which is exactly the match this audit exists to make.
PLUMBING = set(_RULES["plumbingParams"])

# Widgets whose parameter set is too generic to mean anything.
NOISE = {frozenset(s) for s in _RULES["noiseParamSets"]}

# Parameter names generic enough that being the ONLY parameter tells you
# nothing — `(child)` is half the widget tree. A single domain-specific
# parameter (`block`, `ticket`, `conversation`) is not this: it is exactly the
# kind of one-arg wrapper that gets duplicated across screens and was
# previously invisible to this audit because of a blanket `len(params) < 2`
# floor. See issue #39.
GENERIC_SINGLE_PARAMS = {
    "child", "children", "item", "value", "data", "builder", "index", "key",
}

# A near-duplicate must share this much of its parameter set with another
# shape before the two are treated as "possibly the same widget" rather than
# two unrelated ones. `SIMILARITY_THRESHOLD` (Jaccard, same test
# `near_ds_matches` already uses against the design system) catches two shapes of
# similar size that differ by a param or two. It alone misses the confirmed
# case from issue #39 — a smaller shape's params are a near-complete SUBSET
# of a bigger one that bolted an extra feature (bulk selection) on top, which
# tanks the Jaccard score even though the shared idiom is obvious — so
# `CONTAINMENT_THRESHOLD` (overlap over the SMALLER shape) catches that case
# too. Either test passing is enough; `MIN_OVERLAP` keeps a 2-vs-40-param
# shape pair from matching on trivial overlap alone.
SIMILARITY_THRESHOLD = 0.5
CONTAINMENT_THRESHOLD = 0.6
MIN_OVERLAP = 2


def constructor_params(body: str, cls: str) -> frozenset[str]:
    """Parameter names of `cls`'s primary constructor."""
    m = re.search(rf"\b{re.escape(cls)}\s*\(([^)]*)\)\s*(?::[^{{;]*)?[;{{]", body)
    if not m:
        return frozenset()
    names = set()
    for a, b in PARAM_RE.findall(m.group(1) + ","):
        name = a or b
        # `super.key` and positional noise.
        if name and name not in PLUMBING:
            names.add(name)
    return frozenset(names)


def scan() -> dict[frozenset[str], list[tuple[str, str]]]:
    by_shape: dict[frozenset[str], list[tuple[str, str]]] = defaultdict(list)
    for path in widget_sources(REPO):
        src = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(REPO))
        for m in CLASS_RE.finditer(src):
            cls = m.group(1)
            # The class body: from the declaration to the next top-level class.
            nxt = CLASS_RE.search(src, m.end())
            body = src[m.start() : nxt.start() if nxt else len(src)]
            params = constructor_params(body, cls)
            if not params or params in NOISE:
                continue
            if len(params) == 1 and next(iter(params)) in GENERIC_SINGLE_PARAMS:
                continue
            by_shape[params].append((rel, cls))
    return by_shape


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_similar(
    by_shape: dict[frozenset[str], list[tuple[str, str]]]
) -> list[dict]:
    """Group shapes that are identical, or near-identical, across files.

    `by_shape` buckets by literal `frozenset` equality, which is exact and
    therefore blind to the common case: an extracted-in-place idiom that
    picked up or dropped one parameter along the way (`(conversation,
    isSelected, onTap)` vs `(ticket, isSelected, isTicked, onTap, onTicked)`).
    This unions any two shapes that share at least `MIN_OVERLAP` parameters
    and clear `SIMILARITY_THRESHOLD` Jaccard similarity — the same test
    `near_ds_matches` already applies against the design system — so near-matches
    surface as a cluster instead of never colliding at all.

    A cluster of more than one distinct shape is marked `near_match` and
    reported with its individual variants intact: this is a question
    ("possibly the same widget, verify") never an assertion.
    """
    shapes = list(by_shape.keys())
    parent = list(range(len(shapes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            a, b = shapes[i], shapes[j]
            overlap = len(a & b)
            if overlap < MIN_OVERLAP:
                continue
            containment = overlap / min(len(a), len(b))
            if (
                a == b
                or _jaccard(a, b) >= SIMILARITY_THRESHOLD
                or containment >= CONTAINMENT_THRESHOLD
            ):
                union(i, j)

    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(len(shapes)):
        clusters[find(i)].append(i)

    out = []
    for idxs in clusters.values():
        variants = [shapes[i] for i in idxs]
        sites = sorted(s for i in idxs for s in by_shape[shapes[i]])
        files = {f for f, _ in sites}
        if len(files) < 2:
            continue
        if len(variants) == 1:
            out.append({"shape": sorted(variants[0]), "sites": sites})
        else:
            out.append({
                "shape": sorted(set().union(*variants)),
                "near_match": True,
                "variants": [
                    {
                        "params": sorted(v),
                        "sites": sorted(by_shape[v]),
                    }
                    for v in sorted(variants, key=sorted)
                ],
                "sites": sites,
            })
    return out


def ds_shapes() -> dict[frozenset[str], str]:
    """Parameter shapes of the RESOLVED design-system package's public components.

    Resolved through the package manager's own map, like the reinvention audit,
    so this tracks the pinned tag rather than a hardcoded list that rots the
    first time the dependency moves.

    This is the bucket that matters most. Extraction and adoption are two
    jobs, and only the first one feels finished: `DsPriceRow`, `DsStatCell`,
    `DsInfoRow` and `DsSubSection` were all built in the design system while
    the app kept every one of its private copies. A component nobody adopted
    is a component that will drift from the thing it was extracted from.
    """
    if not PACKAGE:
        print("audit_promotion_candidates: no design-system package declared "
              "(reinventedComponents.package / tokens.source.package), so the "
              "'possibly already covered by' suggestions are OFF. The duplicate-"
              "shape findings below are unaffected.", file=sys.stderr)
        return {}
    config = REPO / RESOLVE_VIA
    if not config.is_file():
        print(f"audit_promotion_candidates: {RESOLVE_VIA} is missing, so "
              f"{PACKAGE} could not be resolved and the 'possibly already "
              f"covered by' suggestions are OFF. Resolve dependencies (for "
              f"Flutter, `flutter pub get`) to restore them.", file=sys.stderr)
        return {}
    try:
        entry = next(
            p
            for p in json.loads(config.read_text())["packages"]
            if p["name"] == PACKAGE
        )
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
            params = constructor_params(src[m.start():], cls)
            if len(params) >= 2 and params not in NOISE:
                out.setdefault(params, cls)
    return out


def candidates() -> list[dict]:
    ds = ds_shapes()
    capabilities = load_capabilities(REPO)

    # Capability overlap as an OPTIONAL second signal alongside the existing
    # param-shape Jaccard check, per issue #61: a manifest lets both
    # duplicate-detection audits require capability overlap too, so a
    # look-alike whose capabilities clearly diverge (a keyboard-navigable
    # variant vs. one that isn't) is not flagged on shape alone. Narrow and
    # backward-compatible by construction — `load_capabilities` returns {}
    # when no manifest is configured, `capability_overlap` then always
    # returns None for every pair, and `_diverges` is False for every pair,
    # so behaviour is byte-identical to before this existed.
    DIVERGENCE_THRESHOLD = 0.2

    def _diverges(class_name: str, ds_name: str) -> bool:
        if not capabilities:
            return False
        overlap = capability_overlap(
            capabilities.get(class_name), capabilities.get(ds_name)
        )
        return overlap is not None and overlap < DIVERGENCE_THRESHOLD

    def near_ds_matches(shape: frozenset[str], classes: list[str]) -> list[tuple[str, int]]:
        """Design-system components with a similar parameter shape.

        Not exact-set equality: an extracted component almost always gains or
        loses a parameter in the move — `DsPriceRow` swapped the app's `theme`
        for an `emphasis` flag. Requiring an exact match meant this could only
        find components extracted *without being improved*, which is close to
        none of them.

        **Returns suggestions, deliberately plural, and does not assert.**
        Parameter-name similarity is a proxy for meaning and it misleads: the
        app's `_InfoRow(icon, label)` scores higher against `DsStatCell(icon,
        value, label)` than against `DsInfoRow(icon, text, color)`, which is
        the component it actually is — because `DsInfoRow` calls its text
        `text` and the app called it `label`. A single confident answer there
        would send someone to adopt the wrong component, which is worse than
        saying nothing.

        When a component-capabilities manifest is configured, a candidate
        whose hand-authored `capabilities` clearly diverge from every site's
        (below `DIVERGENCE_THRESHOLD` overlap) is dropped even though its
        shape matched — see issue #61.
        """
        scored = []
        for cand, name in ds.items():
            overlap = len(shape & cand)
            if overlap < 2:
                continue
            j = overlap / len(shape | cand)
            if j >= 0.5:
                if classes and all(_diverges(c, name) for c in classes):
                    continue
                scored.append((name, round(j * 100)))
        scored.sort(key=lambda x: -x[1])
        return scored[:3]

    out = []
    for group in sorted(cluster_similar(scan()), key=lambda g: -len(g["sites"])):
        shape = frozenset(group["shape"])
        site_classes = [c for _, c in group["sites"]]
        entry = {
            "shape": group["shape"],
            "near_ds": near_ds_matches(shape, site_classes),
            "sites": [{"file": f, "class": c} for f, c in group["sites"]],
        }
        if group.get("near_match"):
            entry["near_match"] = True
            entry["variants"] = [
                {
                    "params": v["params"],
                    "sites": [{"file": f, "class": c} for f, c in v["sites"]],
                }
                for v in group["variants"]
            ]
        out.append(entry)
    # Unadopted first: those need no design decision at all, only an import.
    out.sort(key=lambda c: (not c["near_ds"], -len(c["sites"])))
    return out


def key(c: dict) -> str:
    if c.get("near_match"):
        return "~" + "|".join(",".join(v["params"]) for v in c["variants"])
    return ",".join(c["shape"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--findings", nargs="?", const=True, default=None,
                    help="also write the common findings envelope for /design-debt "
                         "(bare flag uses the default path)")
    args = ap.parse_args()

    try:
        found = candidates()
    except ShapeSourceError as exc:
        # Refused, not clean. This sweep used to be a literal `lib/**/*.dart`,
        # which on any other tree scanned nothing and printed "no NEW widget
        # built twice" with exit 0.
        print(f"audit_promotion_candidates: REFUSING TO RUN\n\n{exc}", file=sys.stderr)
        return 2
    keys = {key(c) for c in found}

    existing = {}
    if BASELINE.exists():
        existing = json.loads(BASELINE.read_text())["accepted"]
        if isinstance(existing, list):  # pre-3.14 format
            existing = {k: "" for k in existing}

    if args.update_baseline:
        # Reasons survive a re-run; new entries come in blank and are listed
        # so nobody has to diff the file to find them.
        merged = {k: existing.get(k, "") for k in sorted(keys)}
        BASELINE.write_text(
            json.dumps({"accepted": merged}, indent=2) + "\n")
        blank = [k for k, v in merged.items() if not v]
        print(f"baseline updated: {len(merged)} accepted candidate shape(s)")
        if blank:
            print(f"\n{len(blank)} with NO REASON recorded — fill these in, "
                  "or the file records only that somebody ran a command:")
            for k in blank:
                print(f"  ({k})")
        return 0

    accepted = set(existing)

    fresh = [c for c in found if key(c) not in accepted]

    maturity = load_component_maturity()

    def all_experimental(c: dict) -> bool:
        classes = [s["class"] for s in c["sites"]]
        return bool(classes) and all(
            maturity.get(cls) == "experimental" for cls in classes
        )

    exempt = [c for c in fresh if all_experimental(c)]
    if exempt:
        exempt_keys = {key(c) for c in exempt}
        fresh = [c for c in fresh if key(c) not in exempt_keys]

    if args.findings:
        from design_suite.engine import findings as F
        # One finding per duplicated shape, anchored at its first site so the row
        # is navigable. Accepted shapes are FYI, fresh ones should-fix: this audit
        # is a debt register by design (its own message says existing duplication
        # "is recorded in the baseline"), and the roadmap tracks the standing 12 as
        # D5. Hiding accepted debt here would empty the register the dashboard
        # exists to show. An exempt shape (all sites tagged experimental) is FYI
        # too — flagged nowhere near should-fix, since nudging an experimental
        # component to promote is exactly the noise the exemption exists to cut.
        F.write(
            F.default_path(REPO, "promotion_candidates") if args.findings is True
            else REPO / args.findings,
            "promotion_candidates",
            [F.make("promotion_candidates", "duplicated_shape",
                    f"({', '.join(c['shape'])}) built in {len(c['sites'])} places"
                    + (f"; near {c['near_ds'][0][0]}" if c.get("near_ds") else ""),
                    severity=(F.SHOULD_FIX if key(c) not in accepted
                              and key(c) not in {key(e) for e in exempt}
                              else F.FYI),
                    file=(c["sites"][0]["file"] if c.get("sites") else None))
             for c in found],
            scanned=len(found),
        )


    print(f"  duplicated widget shapes   {len(found)}")
    print(f"  already accepted           {len(found) - len(fresh) - len(exempt)}")
    if exempt:
        print(f"  exempt (all sites tagged experimental in "
              f"component-maturity.json)  {len(exempt)}")

    unexplained = [k for k, v in existing.items() if not v]
    if unexplained:
        print(f"  accepted WITHOUT a reason  {len(unexplained)}")

    if not fresh:
        print(
            "\naudit_promotion_candidates: no NEW widget built twice.\n"
            "Existing duplication is recorded in the baseline — run with "
            "--update-baseline only after promoting or deliberately keeping "
            "one."
        )
        return 0

    print(
        f"\nPROMOTION CANDIDATES — {len(fresh)} shape(s) built in more than one "
        "file:\n",
        file=sys.stderr,
    )
    for c in fresh:
        print(f"  ({', '.join(c['shape'])})", file=sys.stderr)
        if c.get("near_match"):
            print("      NEAR-MATCH — not an exact signature, VERIFY before treating "
                  "as one component:", file=sys.stderr)
            for v in c["variants"]:
                print(f"      variant ({', '.join(v['params'])}):", file=sys.stderr)
                for s in v["sites"]:
                    print(f"        {s['class']:<26} {s['file']}", file=sys.stderr)
        else:
            for s in c["sites"]:
                print(f"      {s['class']:<28} {s['file']}", file=sys.stderr)
        if c["near_ds"]:
            hits = ", ".join(f"{n} ({s}%)" for n, s in c["near_ds"])
            print(f"      possibly already covered by: {hits}", file=sys.stderr)
            print("      ^ parameter-name overlap only — VERIFY before adopting",
                  file=sys.stderr)
        print(file=sys.stderr)

    print(
        "Each of these is a question, not a defect: is this one component that\n"
        "belongs in the design system, or two things that happen to take the\n"
        "same arguments? See docs/PROMOTING-COMPONENTS.md for the path, or ask\n"
        "Claude to \"promote this component to the design system\".\n\n"
        "If it is genuinely two things, run --update-baseline to record that\n"
        "you looked — so that \"we checked and it was fine\" and \"nobody\n"
        "checked\" never look the same.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
