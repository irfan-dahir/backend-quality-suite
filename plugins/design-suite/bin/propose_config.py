#!/usr/bin/env python3
"""Propose real values for init.py's TODO config sections, inferred from code.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py"                 preview (default)
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py" --json          preview, machine-readable
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py" --apply layerBoundaries
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py" --apply all

Exit 0 at least one proposal (preview), or every --apply'd section written.
2 refused: no profile, nothing could be proposed, or an --apply'd section has no
proposal / is already filled in by a human. Nothing is written on 2.

## Why

After survey -> init --from-survey -> map-project, most audits refuse (exit 2)
because the sections init scaffolds are still `TODO` placeholders. That is honest,
and it reads to a new user as a wall of "could not check". Some of those TODOs are
facts a code scan can measure; this proposes those, and only those.

## What it proposes, and the bar each has to clear

  * `arch-rules.json` `layerBoundaries` — from the project's own import graph,
    resolved exactly the way audit_layer_boundaries.py resolves it. A top-level
    source directory (>= 2 files) that >= MIN_EDGES files in other directories
    import, and that imports none of them back, is proposed as a layer that must not
    import its consumers. Tied candidates: nothing proposed.
  * `arch-rules.json` `adapterPattern` — only where a screens scope is known
    (the adapter's default, or a filled-in `source.screensGlob`) and matches
    real files. A layer — a top-level source directory, or a per-feature sibling
    such as `<screensDir>/*/X` with the feature name wildcarded — that >= MIN_EDGES
    non-screen files import and no screen file imports is proposed as banned.
  * `design-audit-config.json` `token_categories.motion.animated_widgets` — the
    animated widget names this project's source actually uses, matched with the
    adapter's `ANIMATED_NODE_NAME_RE`. No adapter capability, or no use found:
    nothing proposed.
  * `design-audit-config.json` `token_categories.color.names` — the colour tokens
    the adapter enumerates from `tokens.source`, only when that source is filled
    in (not a TODO). An unresolved source is a map-project question, not this one.

Every one of those is an OBSERVED INVARIANT ("this is true of the code today"),
not a known architectural intent. That is why each lands carrying a
`_provenance: {"state": "inferred", "evidence": ...}` entry — the same whitelist
map_project.py builds, via its `build_entry` / `check_evidence` — and why the
preview is the default. Where evidence is weak, it proposes nothing and says why:
a guessed rule that makes an audit "pass" is worse than a refusal.

## What it never proposes

errorHandling, contractHeaders, apiConsistency.checks, reinventedComponents,
patternAdoption, unwiredRoles, unusedTokens, contrast pairs: those are this
project's names for its own machinery, or decisions about which checks matter.
They are listed in the preview under `notProposed` with the reason.

## Writes

Only with --apply SECTION (repeatable, or `all`). A section a human already
filled in (no TODO left in it, and no inferred `_provenance`) is never
overwritten. Stdlib only; no project literals — directory names come from the
code being scanned.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from _bootstrap import project_root  # noqa: E402

from design_suite.adapters import for_project  # noqa: E402
from design_suite.engine import imports as I  # noqa: E402
from design_suite.engine.refusal import Refused as SuiteRefused  # noqa: E402

import map_project  # noqa: E402  reuse its evidence rules and entry whitelist

PROFILE = ".design-suite/profile.json"

#: Fewest import edges that count as evidence of a layer relationship.
MIN_EDGES = 5

NOT_PROPOSED = {
    "errorHandling": "the guard, error widget and network-call spelling are this "
                     "project's own names; a wrong guess matches nothing and reports "
                     "a confident zero",
    "contractHeaders": "the header marker and receiver are a convention a human "
                       "chose; there is nothing to measure until one exists",
    "apiConsistency": "which checks are on is a decision about what matters here, "
                      "not a fact in the code",
    "reinventedComponents": "the design system's export prefix/package is a naming "
                            "decision; a prefix guessed from frequency would compare "
                            "private widgets against the wrong set",
    "patternAdoption": "which patterns the project means to adopt is intent, not a "
                       "measurement",
    "unwiredRoles / unusedTokens": "need a resolved token source and a human choice "
                                   "of required roles/categories",
}


class Refused(Exception):
    pass


# --------------------------------------------------------------------------- #
# Import graph — resolved the way audit_layer_boundaries.py resolves it
# --------------------------------------------------------------------------- #

def _source_root(profile: dict) -> str | None:
    root = (profile.get("source") or {}).get("root")
    if not isinstance(root, str) or I.placeholder(root):
        return None
    return root.strip("/") or "."


def _resolve(repo: Path, target: str, source: Path, prefix: str | None) -> str | None:
    if prefix and target.startswith(prefix):
        return "lib/" + target[len(prefix):]
    if target.startswith((".", "/")):
        resolved = ((source.parent / target).resolve() if target.startswith(".")
                    else (repo / target.lstrip("/")).resolve())
        try:
            return resolved.relative_to(repo.resolve()).as_posix()
        except ValueError:
            return None
    return None  # bare specifier: external, as the audit treats it


def _group(rel: str, root: str) -> str | None:
    """Top-level directory under the source root, or None for a root-level file."""
    base = "" if root == "." else root + "/"
    if not rel.startswith(base):
        return None
    parts = rel[len(base):].split("/")
    return parts[0] if len(parts) > 1 else None


def import_graph(repo: Path, adapter, ctx, root: str):
    """files_by_group, edges[(src_group, dst_group)] -> set(src files), raw imports."""
    rx = getattr(adapter, "IMPORT_RE", None)
    if rx is None or getattr(adapter, "IMPORT_TARGETS", "path") != "path":
        return None
    prefix = adapter.package_prefix(ctx) if hasattr(adapter, "package_prefix") else None
    files = I.adapter_files(repo / root if root != "." else repo, adapter)
    by_group: dict[str, list[str]] = defaultdict(list)
    edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    raw: dict[str, list[tuple[str, str | None]]] = {}
    for path in files:
        rel = path.relative_to(repo).as_posix()
        src = _group(rel, root)
        if src:
            by_group[src].append(rel)
        targets = []
        for _line, target in I.import_targets(rx, path.read_text(errors="replace")):
            resolved = _resolve(repo, target, path, prefix)
            targets.append((target, resolved))
            dst = _group(resolved, root) if resolved else None
            if src and dst and dst != src:
                edges[(src, dst)].add(rel)
        raw[rel] = targets
    return by_group, edges, raw, prefix


# --------------------------------------------------------------------------- #
# Proposers. Each returns (proposal | None, reason).
# --------------------------------------------------------------------------- #

def propose_layer_boundaries(graph, root):
    if graph is None:
        return None, ("the language adapter's imports are not file paths (or it has "
                      "no IMPORT_RE), so a directory layer rule cannot be measured")
    by_group, edges, _raw, _ = graph
    inbound: dict[str, Counter] = defaultdict(Counter)
    for (src, dst), files in edges.items():
        inbound[dst][src] += len(files)
    scored = []
    for layer, consumers in inbound.items():
        strong = {c: n for c, n in consumers.items()}
        total = sum(strong.values())
        back = sum(len(edges.get((layer, c), ())) for c in strong)
        if total >= MIN_EDGES and back == 0 and len(by_group.get(layer, ())) >= 2:
            scored.append((total, layer, strong))
    if not scored:
        return None, (f"no source directory (with >= 2 files) is imported by >= {MIN_EDGES} "
                      f"files from other directories while importing none of them back — no "
                      f"measured layer direction to propose. (Alias imports such as "
                      f"'@/x' are invisible to the audit's resolver, so they are not "
                      f"counted here either.)")
    scored.sort(key=lambda t: (-t[0], t[1]))
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None, (f"{scored[0][1]!r} and {scored[1][1]!r} tie at {scored[0][0]} "
                      f"inbound imports; the audit enforces one rule, and picking one "
                      f"would be a coin toss")
    total, layer, consumers = scored[0]
    base = "" if root == "." else root + "/"
    names = sorted(consumers)
    rule = {
        "label": f"{base}{layer} must not import the directories that consume it",
        "fromGlob": f"{base}{layer}/**",
        "mustNotImport": [f"{base}{c}/**" for c in names],
        "why": "inferred: an observed one-way dependency, not a stated design rule",
    }
    counts = ", ".join(f"{c} ({consumers[c]} file(s))" for c in names)
    evidence = (f"import graph over {sum(len(v) for v in by_group.values())} source "
                f"file(s): {base}{layer} is imported by {total} file(s) from {counts}, "
                f"and no file under {base}{layer} imports any of them. Proposed as an "
                f"observed invariant; a human should confirm it is intended.")
    if len(scored) > 1:
        evidence += (" Runner-up: " + ", ".join(f"{s[1]} ({s[0]})" for s in scored[1:4])
                     + " — only one rule is enforced (rules[0]).")
    return {"section": "layerBoundaries", "file": "arch", "path": ["layerBoundaries"],
            "value": {"rules": [rule],
                      "baseline": ".design-suite/baselines/layer-boundaries.json"},
            "evidence": evidence}, None


def _screens_glob(adapter, profile):
    declared = (profile.get("source") or {}).get("screensGlob")
    if isinstance(declared, str) and declared and not I.placeholder(declared):
        return declared, "source.screensGlob in the profile"
    default = getattr(adapter, "ADAPTER_PATTERN_SCREENS_GLOB", None)
    if default:
        return default, f"the {adapter.NAME} adapter's default screens layout"
    return None, None


def _screens_dir(repo, adapter, profile, root, glob):
    """(screensDir repo-rel, screen files) — the declared dir, else source.root,
    else the one immediate child of source.root the glob actually matches."""
    declared = (profile.get("source") or {}).get("screensDir")
    candidates = [declared] if isinstance(declared, str) and declared \
        and not I.placeholder(declared) else []
    base = repo / (root if root != "." else "")
    candidates.append(root)
    if base.is_dir():
        candidates += sorted(p.relative_to(repo).as_posix()
                             for p in base.iterdir() if p.is_dir())
    for cand in candidates:
        found = {p.relative_to(repo).as_posix()
                 for p in I.adapter_files(repo / cand, adapter, glob)}
        if found:
            return cand, found
    return None, set()


def propose_adapter_pattern(repo, adapter, profile, graph, root):
    glob, origin = _screens_glob(adapter, profile)
    if not glob:
        return None, (f"no screens scope: the {adapter.NAME!r} adapter has no default "
                      f"layout and source.screensGlob is unset — which files are "
                      f"screens is a human decision")
    if graph is None:
        return None, "the adapter's imports are not file paths; nothing to measure"
    _by_group, _edges, raw, prefix = graph
    sdir, screens = _screens_dir(repo, adapter, profile, root, glob)
    if not screens:
        return None, (f"the screens scope {glob!r} ({origin}) matches no file under "
                      f"{root}/ or any directory directly inside it — the layout does "
                      f"not look like that, so there is no screen import set to measure")

    def key(rel):
        """Feature-relative layer ('*/data') inside the screens dir, else the
        top-level source directory. Feature names are wildcarded, never named."""
        if rel.startswith(sdir + "/"):
            parts = rel[len(sdir) + 1:].split("/")
            return f"*/{parts[1]}" if len(parts) >= 3 else None
        return _group(rel, root)

    screen_keys = {key(s) for s in screens}
    from_screens: Counter = Counter()
    from_others: dict[str, set] = defaultdict(set)
    for rel, targets in raw.items():
        for _t, resolved in targets:
            dst = key(resolved) if resolved else None
            if not dst or dst in screen_keys:
                continue
            if rel in screens:
                from_screens[dst] += 1
            elif key(rel) != dst:
                from_others[dst].add(rel)
    banned = sorted(k for k, files in from_others.items()
                    if len(files) >= MIN_EDGES and from_screens[k] == 0)
    if not banned:
        seen = ", ".join(f"{k} ({len(v)} importer(s), {from_screens[k]} from screens)"
                         for k, v in sorted(from_others.items())) or "none"
        return None, (f"{len(screens)} screen file(s) under {sdir}/, but no layer is "
                      f"imported by >= {MIN_EDGES} non-screen files and never by a "
                      f"screen (measured: {seen}) — no seam to propose")
    base = "" if root == "." else root + "/"
    pkg_rel = sdir[len("lib/"):] if prefix and sdir.startswith("lib/") else None
    entries = []
    for k in banned:
        if k.startswith("*/"):
            layer = re.escape(k[2:])
            alts = [r"(?:^|/)" + re.escape(sdir) + r"/[^/]+/" + layer + "/"]
            if pkg_rel:
                alts.insert(0, "^" + re.escape(prefix + pkg_rel) + r"/[^/]+/" + layer + "/")
            alts.append(r"^(?:\.\./)+" + layer + "/")
            label = f"screens reach {sdir}/<feature>/{k[2:]} only through an adapter"
        else:
            alts = [r"(?:^|/)" + re.escape(base + k) + "/"]
            if prefix:
                alts.insert(0, "^" + re.escape(prefix + k) + "/")
            label = f"screens reach {base}{k} only through an adapter"
        entries.append({"label": label, "pattern": "|".join(alts)})
    evidence = (f"{len(screens)} screen file(s) matched {glob!r} ({origin}) under "
                f"{sdir}/; none of them imports " + ", ".join(
                    f"{k} (imported by {len(from_others[k])} non-screen file(s))"
                    for k in banned)
                + ". Proposed as an observed invariant, not a known seam.")
    value = {"screensDir": sdir, "bannedImports": entries}
    if origin.startswith("source.screensGlob"):
        value["screensGlob"] = glob
    return {"section": "adapterPattern", "file": "arch", "path": ["adapterPattern"],
            "value": value, "evidence": evidence}, None


def propose_animated_widgets(repo, adapter, root):
    rx = getattr(adapter, "ANIMATED_NODE_NAME_RE", None)
    if rx is None:
        return None, (f"the {adapter.NAME!r} adapter does not say how this stack names "
                      f"animated nodes (no ANIMATED_NODE_NAME_RE)")
    found: Counter = Counter()
    where: dict[str, set] = defaultdict(set)
    for path in I.adapter_files(repo / (root if root != "." else ""), adapter):
        for m in rx.finditer(path.read_text(errors="replace")):
            name = next(g for g in m.groups() if g)
            found[name] += 1
            where[name].add(path.relative_to(repo).as_posix())
    if not found:
        return None, ("no animated widget is used anywhere under the source root — an "
                      "empty list would read as 'nothing to check'; leave it refused")
    names = sorted(found)
    evidence = ("animated widget names used in source: " + ", ".join(
        f"{n} x{found[n]} in {len(where[n])} file(s)" for n in names)
        + ". Add any project-defined animated wrapper a human knows of.")
    return {"section": "animated_widgets", "file": "config",
            "path": ["token_categories", "motion", "animated_widgets"],
            "value": names, "evidence": evidence}, None


def propose_color_names(adapter, ctx, profile):
    src = (profile.get("tokens") or {}).get("source") or {}
    if I.placeholder(src) or not src:
        return None, ("tokens.source is still a TODO — which file is the token source "
                      "is map-project's question, and names read from no source would "
                      "be invented")
    if not hasattr(adapter, "token_names"):
        return None, f"the {adapter.NAME!r} adapter cannot enumerate tokens"
    real = adapter.token_names(ctx)
    if not real:
        return None, ("the adapter could not enumerate any colour token from "
                      "tokens.source (unresolved, or empty)")
    return {"section": "color.names", "file": "config",
            "path": ["token_categories", "color", "names"],
            "value": {"tokens": sorted(real)},
            "evidence": f"{len(real)} colour token(s) enumerated by the "
                        f"{adapter.NAME} adapter from tokens.source "
                        f"({src.get('path') or src.get('package')}); grouping them is "
                        f"left to a human"}, None


# --------------------------------------------------------------------------- #
# Read / write
# --------------------------------------------------------------------------- #

def _get(doc, path):
    for key in path:
        if not isinstance(doc, dict) or key not in doc:
            return None
        doc = doc[key]
    return doc


def _human_filled(current) -> bool:
    """True when a human has already replaced the TODO — never overwrite that."""
    if current is None:
        return False
    if isinstance(current, dict):
        prov = current.get("_provenance")
        if isinstance(prov, dict) and prov.get("state") == map_project.PROPOSED_STATE:
            return False
    return not I.placeholder(current)


def collect(repo: Path):
    try:
        adapter, ctx, _ = for_project(repo)
    except (SuiteRefused, SystemExit) as exc:
        raise Refused(f"no usable language adapter: {exc}")
    profile = ctx.profile
    audits = profile.get("audits") or {}
    files = {"arch": audits.get("archRulesFile"), "config": audits.get("configFile")}
    root = _source_root(profile)
    if not root:
        raise Refused("source.root is unset or a TODO — onboard first (/onboard-new-client) "
                      "there is no tree to measure")
    graph = import_graph(repo, adapter, ctx, root)
    results = [
        propose_layer_boundaries(graph, root),
        propose_adapter_pattern(repo, adapter, profile, graph, root),
        propose_animated_widgets(repo, adapter, root),
        propose_color_names(adapter, ctx, profile),
    ]
    names = ["layerBoundaries", "adapterPattern", "animated_widgets", "color.names"]
    proposals, skipped = [], {}
    for name, (prop, why) in zip(names, results):
        if prop is None:
            skipped[name] = why
            continue
        rel = files.get(prop["file"])
        if not rel or not (repo / rel).is_file():
            skipped[name] = f"the profile names no existing {prop['file']} file ({rel})"
            continue
        current = _get(json.loads((repo / rel).read_text()), prop["path"])
        if _human_filled(current):
            skipped[name] = f"{rel} already has a non-TODO value here; never overwritten"
            continue
        prop["target"] = rel
        prop["evidence"] = map_project.check_evidence(name, prop["evidence"])
        proposals.append(prop)
    return proposals, skipped


def write(repo: Path, proposals: list[dict]) -> list[str]:
    docs: dict[str, dict] = {}
    for prop in proposals:
        doc = docs.setdefault(prop["target"],
                              json.loads((repo / prop["target"]).read_text()))
        node = doc
        for key in prop["path"][:-1]:
            node = node.setdefault(key, {})
        entry = map_project.build_entry(prop["evidence"])
        if isinstance(prop["value"], dict):
            value = {"_provenance": entry, **prop["value"]}
            old = node.get(prop["path"][-1])
            if isinstance(old, dict) and "_comment" in old:
                value = {"_comment": old["_comment"], **value}
            node[prop["path"][-1]] = value
        else:
            # A list leaf cannot carry its own provenance; record it beside it.
            node[prop["path"][-1]] = prop["value"]
            node[f"_{prop['path'][-1]}_provenance"] = entry
    for rel, doc in docs.items():
        (repo / rel).write_text(json.dumps(doc, indent=2) + "\n")
    return sorted(docs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="append", default=[], metavar="SECTION",
                    help="write this proposed section (repeatable, or 'all'). "
                         "Without it, nothing is written.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dir", default=None, help="project root (default: detected)")
    args = ap.parse_args(argv)
    repo = Path(args.dir).resolve() if args.dir else project_root()
    if not (repo / PROFILE).is_file():
        print(f"refusing: no {PROFILE} — this project is not onboarded (/onboard-new-client)", file=sys.stderr)
        return 2
    try:
        proposals, skipped = collect(repo)
    except (Refused, map_project.Refused) as exc:
        print(f"refusing: {exc}\nnothing was written.", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"proposals": proposals, "notInferred": skipped,
                          "notProposed": NOT_PROPOSED}, indent=2))
    else:
        for p in proposals:
            print(f"PROPOSE {p['section']} -> {p['target']} [{map_project.PROPOSED_STATE}]")
            print(f"  value:    {json.dumps(p['value'])}")
            print(f"  evidence: {p['evidence']}")
        for name, why in skipped.items():
            print(f"NO PROPOSAL {name}: {why}")
        for name, why in NOT_PROPOSED.items():
            print(f"NEVER PROPOSED {name}: {why}")

    if not args.apply:
        if not proposals:
            print("nothing could be proposed — exit 2, never 0: 'nothing inferred' "
                  "must not read like 'all configured'.", file=sys.stderr)
            return 2
        print("preview only — nothing was written. Re-run with --apply SECTION "
              "after a human confirms that section.", file=sys.stderr)
        return 0

    wanted = {p["section"] for p in proposals} if "all" in args.apply else set(args.apply)
    if not wanted:
        print("refusing: --apply all, but nothing could be proposed — exit 2, never 0."
              "\nnothing was written.", file=sys.stderr)
        return 2
    unknown = wanted - {p["section"] for p in proposals}
    if unknown:
        print(f"refusing: no proposal for {sorted(unknown)} "
              f"({'; '.join(skipped.get(u, 'unknown section') for u in sorted(unknown))})"
              f"\nnothing was written.", file=sys.stderr)
        return 2
    chosen = [p for p in proposals if p["section"] in wanted]
    touched = write(repo, chosen)
    print(f"wrote {len(chosen)} section(s) to {', '.join(touched)}, each with "
          f"_provenance state {map_project.PROPOSED_STATE!r}. They are guesses until a "
          f"human reviews them; edit or delete the section to overrule.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
