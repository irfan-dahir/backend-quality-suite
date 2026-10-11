#!/usr/bin/env python3
"""Propose real values for init.py's TODO config sections, inferred from code.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py"                 preview (default)
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py" --json          preview, machine-readable
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py" --apply layerBoundaries
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/propose_config.py" --apply all

Exit 0 with at least one proposal (preview), or every --apply'd section written.
2 refused: no profile, nothing could be proposed, or an --apply'd section has no
proposal / is already filled in by a human. Nothing is written on 2.

## Why

After survey -> init --from-survey -> map-project, most audits refuse (exit 2)
because the sections init scaffolds are still `TODO` placeholders. That is honest,
and it reads to a new user as a wall of "could not check". Some of those TODOs are
facts a code scan can measure; this proposes those, and only those.

## What it proposes, and the bar each has to clear

  * `arch-rules.json` `layerBoundaries` — from the project's own import graph.
    A top-level source directory (>= 2 files) that >= MIN_EDGES files in other
    directories import, and that imports none of them back, is proposed as a
    layer that must not import its consumers. The banned roots are the two
    forms the audit can actually enforce on this stack: path roots for
    `require`d files and psr-4 namespace roots (`App\Http\`) for `use`
    statements, derived from composer.json via engine/psr4.py so a proposed
    rule is one audit_layer_boundaries.py can fire on. Tied candidates:
    nothing proposed.
  * `arch-rules.json` `routeCoverage` — the routes layout the adapter knows
    (its `routes/*.php` entry in FILE_GLOBS), an actionPattern measured from
    the routes files themselves (every 'uses' entry must spell Class@method,
    or nothing is proposed), and controllerDirs located by finding every
    referenced controller class file. A controller that cannot be found, or
    one that resolves to several files, refuses the whole section.
  * `arch-rules.json` `cacheTtlCoverage` — the same routes measurement plus
    the TTL map: exactly one file under config/ whose keys are action strings
    gives ttlConfigGlob and ttlKeyPattern, both re-verified against the map's
    own keys. Zero or several candidates: nothing proposed. (TTLs kept
    outside config/ are not searched for — the refusal reason says so, rather
    than the search pretending to be exhaustive.)

Every one of those is an OBSERVED INVARIANT ("this is true of the code today"),
not a known architectural intent. That is why each lands carrying a
`_provenance: {"state": "inferred", "evidence": ...}` entry — the same whitelist
map_project.py builds, via its `build_entry` / `check_evidence` — and why the
preview is the default. Where evidence is weak, it proposes nothing and says why:
a guessed rule that makes an audit "pass" is worse than a refusal.

## What it never proposes

errorHandling, contractHeaders, apiConsistency, errorShape, endpointParity,
rateLimit, versioning, toolchainGates, testNetworkCoupling: those are this
project's own names, its stated conventions, or decisions about what CI owes
the release. They are listed in the preview under `notProposed` with the
reason. Also listed: the sections the scaffold still carries for audits that
no longer ship (adapterPattern, reinventedComponents, unwiredRoles,
unusedTokens, promotionCandidates) — nothing would consume a value written
there, and the template drops them with its own re-author.

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
from collections import defaultdict
from pathlib import Path

from _bootstrap import project_root  # noqa: E402

from backend_suite.adapters import for_project  # noqa: E402
from backend_suite.engine import imports as I  # noqa: E402
from backend_suite.engine import psr4 as psr4_mod  # noqa: E402
from backend_suite.engine import scan as scan_mod  # noqa: E402
from backend_suite.engine.refusal import Refused as SuiteRefused  # noqa: E402

import map_project  # noqa: E402  reuse its evidence rules and entry whitelist

PROFILE = ".backend-suite/profile.json"

#: Fewest import edges that count as evidence of a layer relationship.
MIN_EDGES = 5

#: The routing table of this stack (Lumen/Laravel, same convention class the
#: php adapter's `routes/*.php` glob encodes): a router call whose array
#: carries a 'uses' entry. The router-call spelling is the same one
#: audit_route_coverage counts, so both tools read the table identically.
ROUTER_CALL_RE = re.compile(r"\$router->(?:get|post|put|patch|delete|any)\s*\(")
USES_VALUE_RE = re.compile(r"""['"]uses['"]\s*=>\s*['"]([^'"\n]+)['"]""")
#: What gets PROPOSED as routeCoverage.actionPattern: the audit reads
#: group(1) as the controller and group(2) as the method.
ACTION_PATTERN = (r"""['"]uses['"]\s*=>\s*['"]"""
                  r"""([A-Za-z][A-Za-z0-9_]*)@([A-Za-z][A-Za-z0-9_]*)['"]""")
ACTION_RE = re.compile(ACTION_PATTERN)
#: The Class@method spelling itself, for the N-of-N checks below.
ACTION_SHAPE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*@[A-Za-z][A-Za-z0-9_]*")
#: What gets PROPOSED as cacheTtlCoverage.ttlKeyPattern: group(1) is the whole
#: action string, which is how the TTL map spells its keys.
TTL_KEY_PATTERN = (r"""['"]"""
                   r"""([A-Za-z][A-Za-z0-9_]*@[A-Za-z][A-Za-z0-9_]*)"""
                   r"""['"]\s*=>""")
TTL_KEY_LOOSE_RE = re.compile(r"""['"]([^'"\n]+)['"]\s*=>""")

#: A php project's runtime configuration lives under config/ — the same kind
#: of layout fact the adapter's routes glob encodes. A TTL map kept anywhere
#: else is not hunted for; the refusal says so.
CONFIG_GLOB = "config/**/*.php"

NOT_PROPOSED = {
    "errorHandling": "the guard and error vocabulary are this project's own "
                     "names; a wrong guess matches nothing and reports a "
                     "confident zero",
    "contractHeaders": "the header marker and field pattern are a convention a "
                       "human chose; there is nothing to measure until one exists",
    "apiConsistency": "which of its checks run, and the naming rules behind "
                      "vocabulary, are explicit human decisions — the audit "
                      "refuses on an unconfigured check precisely so a machine "
                      "cannot pick for you",
    "errorShape": "bypassPattern — how THIS stack spells a direct error-status "
                  "response — is the project's stated convention (its own audit "
                  "says so when it refuses); filling the other keys would still "
                  "leave the audit refusing",
    "endpointParity": "docMarkers — which docblock annotation counts as "
                      "documentation — can only be found once already known: "
                      "measuring it would need the marker to search for it",
    "rateLimit": "protection spellings and the global-throttle wiring are this "
                 "project's middleware names, not observations",
    "versioning": "how a version prefix and namespace are spelled is a naming "
                  "convention; nothing in the tree decides it",
    "toolchainGates": "what CI must require is an expectation; proposing it "
                      "from the scripts that exist today would ratify whatever "
                      "absence already exists",
    "testNetworkCoupling": "which hosts tests are ALLOWED to hit live is "
                           "policy; a pattern measured from today's tests "
                           "would only legalize what already happens",
    # Sections whose consuming audit left with the design->backend swap: a
    # value written here would be read by nothing. The template drops them
    # with its own re-author; until then they still deserve an answer in the
    # preview, because a user scaffolded by that template will see them.
    "adapterPattern": "no audit ships for this section — its script left with "
                      "the domain swap, and nothing would consume the value",
    "reinventedComponents": "no audit ships for this section — its script left "
                            "with the domain swap, and nothing would consume "
                            "the value",
    "unwiredRoles": "no audit ships for this section — its script left with "
                    "the domain swap, and nothing would consume the value",
    "unusedTokens": "no audit ships for this section — its script left with "
                    "the domain swap, and nothing would consume the value",
    "promotionCandidates": "no audit ships for this section — its script left "
                           "with the domain swap, and nothing would consume "
                           "the value",
}


class Refused(Exception):
    pass


# --------------------------------------------------------------------------- #
# Import graph — attributed to directories the way the audit matches them
# --------------------------------------------------------------------------- #

def _source_root(profile: dict) -> str | None:
    root = (profile.get("source") or {}).get("root")
    if not isinstance(root, str) or I.placeholder(root):
        return None
    return root.strip("/") or "."


def _resolve(repo: Path, target: str, source: Path, prefix: str | None,
             psr4: psr4_mod.Psr4Map) -> tuple[str | None, str | None]:
    """(repo-relative POSIX path or None, namespace root or None) for one import.

    A bare namespace that composer.json maps resolves to a path AND names the
    prefix that matched, because the layer-boundary audit matches that prefix
    against the raw import — a rule proposed without it would never fire.
    """
    if prefix and target.startswith(prefix):
        return "lib/" + target[len(prefix):], None
    if target.startswith((".", "/")):
        resolved = ((source.parent / target).resolve() if target.startswith(".")
                    else (repo / target.lstrip("/")).resolve())
        try:
            return resolved.relative_to(repo.resolve()).as_posix(), None
        except ValueError:
            return None, None
    if psr4:
        hit = psr4.match(target)
        if hit:
            return hit
    return None, None  # bare specifier: external, as the audit treats it


def _group(rel: str, root: str) -> str | None:
    """Top-level directory under the source root, or None for a root-level file."""
    base = "" if root == "." else root + "/"
    if not rel.startswith(base):
        return None
    parts = rel[len(base):].split("/")
    return parts[0] if len(parts) > 1 else None


def import_graph(repo: Path, adapter, ctx, root: str) -> dict | None:
    """edges[(src_group, dst_group)] -> set(src files), plus namespace handles.

    None when the adapter's imports cannot be attributed to directories at all
    (no IMPORT_RE, or module-name imports with no path mapping) — the caller
    turns that into a refusal reason, never into an empty graph.
    """
    rx = getattr(adapter, "IMPORT_RE", None)
    if rx is None or getattr(adapter, "IMPORT_TARGETS", "path") != "path":
        return None
    prefix = adapter.package_prefix(ctx) if hasattr(adapter, "package_prefix") else None
    psr4 = psr4_mod.load(repo)  # Psr4Error propagates: a composer.json that
    # cannot be read is a refusal, never "no prefixes".
    files = I.adapter_files(repo / root if root != "." else repo, adapter)
    by_group: dict[str, list[str]] = defaultdict(list)
    edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    for path in files:
        rel = path.relative_to(repo).as_posix()
        src = _group(rel, root)
        if src:
            by_group[src].append(rel)
        for _line, target in I.import_targets(rx, path.read_text(errors="replace")):
            resolved, _ns = _resolve(repo, target, path, prefix, psr4)
            dst = _group(resolved, root) if resolved else None
            if src and dst and dst != src:
                edges[(src, dst)].add(rel)
    base = "" if root == "." else root + "/"
    ns_roots = {g: psr4.handles(base + g) for g in by_group}
    return {"by_group": by_group, "edges": edges, "ns_roots": ns_roots}


# --------------------------------------------------------------------------- #
# Route measurement — shared by routeCoverage and cacheTtlCoverage
# --------------------------------------------------------------------------- #

def measure_routes(repo: Path, adapter) -> tuple[dict | None, str | None]:
    """(measurement | None, reason). One measurement, two consumers, so the
    two sections can never disagree about how this project's routes read."""
    globs = [g for g in getattr(adapter, "FILE_GLOBS", ()) if "routes" in g]
    if len(globs) != 1:
        return None, (f"the {adapter.NAME!r} adapter's FILE_GLOBS names "
                      f"{len(globs)} routes layout(s) ({globs}) — exactly one is "
                      f"a fact this script can measure, and zero is none at all")
    glob = globs[0]
    files = [p for p in sorted(repo.glob(glob)) if p.is_file()]
    if not files:
        return None, (f"no file matches the adapter's routes layout {glob!r} — "
                      f"there is no routing table here to read")
    router_calls = 0
    values: list[str] = []
    actions: list[tuple[str, str]] = []
    for path in files:
        for line in path.read_text(errors="replace").splitlines():
            router_calls += len(ROUTER_CALL_RE.findall(line))
            values += USES_VALUE_RE.findall(line)
            # Same per-line view audit_route_coverage has, so a pattern
            # proposed here extracts there — no cross-line optimism.
            actions += ACTION_RE.findall(line)
    if router_calls == 0:
        return None, (f"the files under {glob!r} carry no $router-> route calls "
                      f"— this does not look like this stack's routing table")
    if not values:
        return None, (f"no quoted 'uses' entries under {glob!r} — this project's "
                      f"routes spell handlers another way (closures, ::class "
                      f"arrays); actionPattern is measured, never guessed")
    if len(actions) != len(values):
        odd = [v for v in values if not ACTION_SHAPE_RE.fullmatch(v)]
        return None, (f"{len(values) - len(actions)} of {len(values)} 'uses' "
                      f"entr(ies) do not spell Class@method (e.g. {odd[:3]!r}) — "
                      f"one actionPattern cannot cover this routing table")
    return {
        "glob": glob,
        "adapter": adapter.NAME,
        "files": [p.relative_to(repo).as_posix() for p in files],
        "router_calls": router_calls,
        "actions": actions,
    }, None


# --------------------------------------------------------------------------- #
# Proposers. Each returns (proposal | None, reason).
# --------------------------------------------------------------------------- #

def propose_layer_boundaries(graph: dict | None, root: str):
    if graph is None:
        return None, ("the language adapter's imports are not file paths (or it has "
                      "no IMPORT_RE), so a directory layer rule cannot be measured")
    by_group, edges, ns_roots = graph["by_group"], graph["edges"], graph["ns_roots"]
    inbound: dict[str, dict[str, int]] = defaultdict(dict)
    for (src, dst), files in edges.items():
        inbound[dst][src] = inbound[dst].get(src, 0) + len(files)
    scored = []
    for layer, consumers in inbound.items():
        total = sum(consumers.values())
        back = sum(len(edges.get((layer, c), ())) for c in consumers)
        if total >= MIN_EDGES and back == 0 and len(by_group.get(layer, ())) >= 2:
            scored.append((total, layer, dict(consumers)))
    if not scored:
        return None, (f"no source directory (with >= 2 files) is imported by >= {MIN_EDGES} "
                      f"files from other directories while importing none of them back — no "
                      f"measured layer direction to propose.")
    scored.sort(key=lambda t: (-t[0], t[1]))
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None, (f"{scored[0][1]!r} and {scored[1][1]!r} tie at {scored[0][0]} "
                      f"inbound imports; the audit enforces one rule, and picking one "
                      f"would be a coin toss")
    total, layer, consumers = scored[0]
    base = "" if root == "." else root + "/"
    names = sorted(consumers)
    banned = []
    handles_used = []
    for c in names:
        banned.append(f"{base}{c}/**")
        for ns in ns_roots.get(c, ()):
            banned.append(ns)
            handles_used.append(f"{c} = {ns}")
    rule = {
        "label": f"{base}{layer} must not import the directories that consume it",
        "fromGlob": f"{base}{layer}/**",
        "mustNotImport": sorted(set(banned)),
        "why": "inferred: an observed one-way dependency, not a stated design rule",
    }
    counts = ", ".join(f"{c} ({consumers[c]} file(s))" for c in names)
    evidence = (f"import graph over {sum(len(v) for v in by_group.values())} source "
                f"file(s): {base}{layer} is imported by {total} file(s) from {counts}, "
                f"and no file under {base}{layer} imports any of them. Proposed as an "
                f"observed invariant; a human should confirm it is intended.")
    if handles_used:
        evidence += (" Namespace handles come from composer.json psr-4, matched "
                     "against raw use targets the same way the audit matches "
                     f"them: {', '.join(sorted(handles_used))}.")
    if len(scored) > 1:
        evidence += (" Runner-up: " + ", ".join(f"{s[1]} ({s[0]})" for s in scored[1:4])
                     + " — only one rule is enforced (rules[0]).")
    return {"section": "layerBoundaries", "file": "arch", "path": ["layerBoundaries"],
            "value": {"rules": [rule],
                      "baseline": ".backend-suite/baselines/layer-boundaries.json"},
            "evidence": evidence}, None


def propose_route_coverage(repo: Path, routes: dict):
    missing, ambiguous, dirs = [], [], set()
    # The same installed-code names scan skips: a controller class must be this
    # project's own file, not one Composer brought in.
    skip_parts = scan_mod.DEFAULT_SKIP_DIRS | scan_mod.UNAMBIGUOUS_SKIP_DIRS
    for controller in sorted({c for c, _m in routes["actions"]}):
        hits = [p for p in repo.glob(f"**/{controller}.php")
                if p.is_file() and not skip_parts.intersection(p.relative_to(repo).parts)]
        if not hits:
            missing.append(controller)
        elif len(hits) > 1:
            ambiguous.append(f"{controller} -> "
                             + ", ".join(sorted(h.relative_to(repo).as_posix()
                                                for h in hits)))
        else:
            dirs.add(hits[0].parent.relative_to(repo).as_posix())
    if missing:
        return None, (f"controller class file(s) not found for {missing} — a "
                      f"controllerDirs that misses one of them would leave the "
                      f"audit resolving actions against nothing")
    if ambiguous:
        return None, (f"controller class file(s) resolve to several locations "
                      f"({'; '.join(ambiguous)}) — controllerDirs would be a guess")
    evidence = (f"{len(routes['actions'])} route action(s), all spelled "
                f"Class@method, across {len(routes['files'])} file(s) under "
                f"{routes['glob']!r} — the {routes['adapter']} adapter's routes "
                f"layout, carrying {routes['router_calls']} router call(s). Every "
                f"referenced controller class resolves by name to exactly one "
                f"file: {', '.join(sorted(dirs))}.")
    return {"section": "routeCoverage", "file": "arch", "path": ["routeCoverage"],
            "value": {"routesGlob": routes["glob"],
                      "actionPattern": ACTION_PATTERN,
                      "controllerDirs": sorted(dirs)},
            "evidence": evidence}, None


def propose_cache_ttl_coverage(repo: Path, routes: dict):
    files = [p for p in sorted(repo.glob(CONFIG_GLOB)) if p.is_file()]
    with_keys: dict[str, set[str]] = {}
    for path in files:
        keys: set[str] = set()
        for line in path.read_text(errors="replace").splitlines():
            keys |= {v for v in TTL_KEY_LOOSE_RE.findall(line) if "@" in v}
        if keys:
            with_keys[path.relative_to(repo).as_posix()] = keys
    if not with_keys:
        return None, (f"no action-keyed map under {CONFIG_GLOB!r} — either this "
                      f"project keeps its TTLs outside config/ or it has none; "
                      f"ttlConfigGlob is measured from config/, not hunted for "
                      f"across the tree")
    if len(with_keys) > 1:
        return None, (f"an action-keyed map was found in {len(with_keys)} files "
                      f"({', '.join(sorted(with_keys))}) — ttlConfigGlob would be "
                      f"a choice between them, and this script does not get one")
    rel, keys = next(iter(with_keys.items()))
    loose = []
    for line in (repo / rel).read_text(errors="replace").splitlines():
        loose += [v for v in TTL_KEY_LOOSE_RE.findall(line) if "@" in v]
    odd = [k for k in loose if not ACTION_SHAPE_RE.fullmatch(k)]
    if odd:
        return None, (f"action-shaped key(s) in {rel} do not spell Class@method "
                      f"({odd[:3]!r}) — ttlKeyPattern would not cover this map")
    action_keys = {f"{c}@{m}" for c, m in routes["actions"]}
    covered = len(action_keys & set(loose))
    evidence = (f"{len(loose)} action-keyed entr(ies) in {rel} beside "
                f"{len(action_keys)} route action(s) from {routes['glob']!r}: "
                f"{covered} of them have a TTL entry today. The key shape is "
                f"measured from the map itself, re-verified line by line the way "
                f"the audit reads it.")
    return {"section": "cacheTtlCoverage", "file": "arch",
            "path": ["cacheTtlCoverage"],
            "value": {"routesGlob": routes["glob"],
                      "actionPattern": ACTION_PATTERN,
                      "ttlConfigGlob": rel,
                      "ttlKeyPattern": TTL_KEY_PATTERN},
            "evidence": evidence}, None


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
    files = {"arch": audits.get("archRulesFile")}
    root = _source_root(profile)
    if not root:
        raise Refused("source.root is unset or a TODO — onboard first (/onboard-new-client) "
                      "there is no tree to measure")
    try:
        graph = import_graph(repo, adapter, ctx, root)
    except psr4_mod.Psr4Error as exc:
        raise Refused(f"cannot read this project's psr-4 map: {exc}")
    routes, routes_why = measure_routes(repo, adapter)
    results = [
        propose_layer_boundaries(graph, root),
        ((None, routes_why) if routes is None else propose_route_coverage(repo, routes)),
        ((None, f"the routes measurement failed first: {routes_why}")
         if routes is None else propose_cache_ttl_coverage(repo, routes)),
    ]
    names = ["layerBoundaries", "routeCoverage", "cacheTtlCoverage"]
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
