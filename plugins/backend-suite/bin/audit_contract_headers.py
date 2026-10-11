#!/usr/bin/env python3
"""A screen's CONTRACT header, checked against the adapter it is actually handed.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_contract_headers.py" [--out …] [--baseline-write]

## Why this exists

A screen in this architecture carries a banner comment naming every input it may
read and every output it may call, and one of its own rules is "do not modify the
adapter interface". That header is the contract. Nothing checked that it was true.

In the originating project it was not. Measured 2026-08-10: **seven of the eight
screens taking an adapter object misdescribed it**, and the single accurate header
had been corrected by hand hours earlier, found by eye during unrelated work. A
header that undercounts its adapter is worse than no header — it reads as
authoritative while licensing exactly the drift it exists to prevent.

## Four findings, because there are four different defects

    undocumented_field       the screen reads it; the header does not list it
    stale_header_entry       the header lists it; the class does not declare it
    dead_adapter_field       the class declares it; nothing anywhere reads it
    missing_contract_header  no header at all

`dead_adapter_field` is why this is not merely a documentation check, and it
changes what the fix is. Of the 16 findings on the originating project, **15 were
fields nothing read** — `isLoading` and `errorMessage` declared on seven adapters
each, plus one `onRefresh` that was declared, wired by composition, documented in
the header, and called by no widget. Reporting only "add these to the header"
would have driven fifteen dead fields into documented permanence. All fifteen
were deleted; one genuine undocumented output was added.

## Why `undocumented_field` is scoped to what the screen reads

One adapter can serve several screens. The originating project's care-plan adapter
is built once per feature and forwarded by composition to both a list screen and a
publish screen, so its `onPublish` is live — just not for the list. Comparing the
whole class against one screen's header would report that as drift on a header
that is right, so the check compares only the fields **that screen's own tree
reads**. A field a sibling uses is neither undocumented here nor dead anywhere.

## What it refuses to do

Report zero because it could not look. An adapter without the structural
capabilities, an unresolvable adapter class, or a scope glob matching nothing all
exit non-zero with a reason. Per the suite's governing principle, an audit that
reports nothing must never be indistinguishable from a clean codebase.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
from backend_suite.adapters import for_project              # noqa: E402
from backend_suite.adapters.base import CapabilityError     # noqa: E402
from backend_suite.engine import contracts                  # noqa: E402
from backend_suite.engine.arch import load                  # noqa: E402
from backend_suite.project import need_refused, profile             # noqa: E402

RULES = load(REPO, "contractHeaders")

# Every one of these is a fact about a project's conventions, not this engine's.
MARKER = RULES.get("headerMarker") or "CONTRACT"
LABELS = RULES.get("sectionLabels") or {}
INPUT_LABELS = LABELS.get("input") or ["INPUT", "INPUTS"]
OUTPUT_LABELS = LABELS.get("output") or ["OUTPUT", "OUTPUTS"]
PREFIX = RULES.get("namePrefix", "")
IGNORE = set(RULES.get("ignoreFields") or [])
CHECKS = RULES.get("checks") or {}
# How far above a screen file its own subtree starts. `presentation/pages/x.dart`
# → 2 reaches `presentation/`, which is where a screen's own widgets live and
# therefore where a call to its adapter still counts as that screen's use.
TREE_DEPTH = int(RULES.get("screenTreeDepth", 2))

# The placeholder a freshly written baseline entry carries until someone says why.
UNJUSTIFIED = "UNJUSTIFIED — replace with why this is accepted rather than fixed"


def enabled(name: str) -> bool:
    return bool(CHECKS.get(name, True))


def refuse(message: str):
    """Stop with exit 2, never 1.

    A refusal and a finding are different answers and must not share an exit
    code: `1` means "I looked and this is wrong", `2` means "I could not look".
    Collapsing them is how "the audit is red again" stops being read.
    """
    print(f"audit_contract_headers: REFUSING TO RUN\n\n{message}", file=sys.stderr)
    raise SystemExit(2)


def _sources(globs, why: str) -> list[Path]:
    """Files matching one glob or several.

    A list is not a nicety: a project may declare its contract classes in
    dedicated files *and* inline in the screen that uses them, and the only
    single glob covering both is one broad enough to sweep the whole tree.
    """
    if isinstance(globs, str):
        globs = [globs]
    found = sorted({p for glob in globs for p in REPO.glob(glob)})
    if not found:
        refuse(f"contractHeaders glob {globs!r} matched nothing — {why}.\n"
               f"An empty sweep would report every header correct.")
    return found


def _excluded_set(patterns) -> set:
    """Files a documented exception covers, resolved by globbing the repo.

    Config, never a built-in: which files in a screens glob are not screens is a
    project's fact (route wrappers, tab hosts), and a hardcoded suffix list is
    how an engine ends up silently skipping something it should report.

    Globbed rather than pattern-matched per path on purpose. `PurePath.match`
    does not honour `**` on the Python versions this has to run on, so an author
    writing `**` would get a pattern that silently matched nothing — and a
    silently ineffective exclusion is the kind of config that looks applied and
    is not. `REPO.glob` gives every glob in this engine one meaning.
    """
    if isinstance(patterns, str):
        patterns = [patterns]
    return {p for pattern in patterns for p in REPO.glob(pattern)}


class _ClassIndex:
    """`class name -> (path, {field: line})`, built once, lazily per file.

    Resolving each screen by re-scanning every candidate is O(screens x files)
    and took 13s on a 382-file project — slow enough to invite narrowing the
    glob, which is the wrong fix and loses coverage.
    """

    def __init__(self, paths, resolve):
        self._paths = list(paths)
        self._resolve = resolve
        self._cache: dict[str, tuple] = {}

    def get(self, cls: str):
        if cls not in self._cache:
            self._cache[cls] = (None, None)
            for path in self._paths:
                fields = self._resolve(path.read_text(), cls)
                if fields is not None:
                    self._cache[cls] = (path, fields)
                    break
        return self._cache[cls]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /quality-debt "
                             "(bare flag uses the default path)")
    parser.add_argument("--baseline-write", action="store_true",
                        help="rewrite the configured baseline from the current findings")
    args = parser.parse_args()

    lang, _ctx, _checks = for_project(REPO)
    required = ("block_comments", "class_fields", "member_reads",
                "typed_member_reads")
    if not getattr(lang, "CONTRACT_CAPABLE", False) or any(
            not hasattr(lang, name) for name in required):
        refuse(
            f"language adapter {lang.NAME!r} cannot read class structure "
            f"({', '.join(required)}), so contract headers cannot be checked for "
            f"this stack. INERT, not clean — implement the capability or drop the "
            f"audit from CI rather than letting it pass by being blind.")

    receiver_pattern = RULES.get("receiverPattern")
    receiver_name = RULES.get("receiverName")
    if not receiver_pattern or not receiver_name:
        refuse(
            "contractHeaders needs receiverPattern and receiverName — how a screen "
            "names the object its header describes. Without them every field would "
            "read as undocumented.")
    receiver_re = re.compile(receiver_pattern)
    screen_class_re = re.compile(RULES.get("screenClassPattern") or r"class\s+(\w+)\b")

    screens = _sources(
        RULES.get("scope") or need_refused(profile(REPO), "source.screensGlob",
                                            "is the set of screens whose headers are checked",
                                            audit="audit_contract_headers"),
        "no screens to check")
    adapter_files = _sources(
        RULES.get("adapterGlob"), "the adapter classes cannot be found") \
        if RULES.get("adapterGlob") else []
    # A contract class is a surface, so its public methods belong to it — a
    # header documenting `totalMinutesToday(id)` is documenting a real member.
    # A screen widget is not: `build` and `createState` are framework overrides.
    # Hence two resolvers, and a fallback for an adapter that predates the split.
    resolve_contract = getattr(lang, "class_members", lang.class_fields)
    index = _ClassIndex(adapter_files, resolve_contract)
    # Documented exceptions: files inside the screens glob that are not screens.
    exclude = RULES.get("excludeGlobs") or []
    excluded = _excluded_set(exclude)
    skipped = [s for s in screens if s in excluded]
    screens = [s for s in screens if s not in excluded]
    if not screens:
        refuse(f"excludeGlobs {exclude!r} excluded every screen — an audit with "
               f"nothing left to check passes vacuously.")

    # Reads anywhere in the project, so a field forwarded by composition to a
    # sibling screen does not read as dead.
    root = REPO / need_refused(profile(REPO), "source.root", "is the tree searched for reads",
                               audit="audit_contract_headers")
    file_glob = need_refused(profile(REPO), "source.fileGlob", "is how sources are found",
                             audit="audit_contract_headers")
    alias_of = getattr(lang, "receiver_aliases", None)

    # Which contract classes exist to look for, gathered before the read sweep:
    # a read is resolved by the *type* of the identifier it goes through, so the
    # sweep has to know the types before it can see the reads.
    contract_types = {m.group(1) for m in
                      (receiver_re.search(s.read_text()) for s in screens) if m}

    def reads_in(path: Path, source: str | None = None) -> set:
        """Names read off the receiver in one file, through any local alias.

        A screen may bind its adapter to a shorter name and read through that;
        those are still reads, and missing them reported every field of one
        adapter as dead.
        """
        if source is None:
            source = path.read_text()
        names = {receiver_name}
        if alias_of:
            names |= alias_of(source, receiver_name)
        found = set()
        for name in names:
            found |= lang.member_reads(source, name)
        return found

    def typed_reads_in(path: Path, source: str, types) -> dict:
        """Reads resolved by the receiver's declared type, not by its name.

        The name-only answer is the defect this exists to close: a helper taking
        `CarePlanAdapter a` reads `a.patientName`, which a sweep for `adapter.`
        cannot see, so the field was reported dead with deletion as the advice.
        A `CapabilityError` here is the adapter saying it cannot follow a
        receiver in this file — it must stop the run, because carrying on would
        turn "I could not tell" into "nothing reads it", which is the governing
        principle's own failure mode.
        """
        try:
            return lang.typed_member_reads(source, types)
        except CapabilityError as exc:
            refuse(f"{path.relative_to(REPO)}: {exc}")

    everywhere: set[str] = set()
    by_type: dict[str, set] = {}
    for path in sorted(root.glob(file_glob)):
        source = path.read_text()
        everywhere |= reads_in(path, source)
        for cls_name, members in typed_reads_in(path, source, contract_types).items():
            by_type.setdefault(cls_name, set()).update(members)

    findings: list[dict] = []
    dead_seen: set[tuple[str, str]] = set()
    checked = 0

    for screen in screens:
        source = screen.read_text()
        rel = str(screen.relative_to(REPO))
        header = contracts.find_header(lang.block_comments(source), MARKER)
        if header is None:
            if enabled("missingContractHeader"):
                findings.append({
                    "file": rel, "line": 1, "kind": "missing_contract_header",
                    "name": "", "adapter": "",
                    "detail": f"{rel}:1 has no {MARKER} header, so nothing here can "
                              f"be checked against it.",
                })
            continue
        header_start, text = header
        declared_in = contracts.section(text, INPUT_LABELS, PREFIX, header_start)
        declared_out = contracts.section(text, OUTPUT_LABELS, PREFIX, header_start)
        listed = {**declared_in, **declared_out}

        match = receiver_re.search(source)
        if match:
            cls = match.group(1)
            adapter_path, fields = index.get(cls)
            if fields is None:
                refuse(
                    f"{rel} names {cls} but no file under "
                    f"{RULES.get('adapterGlob')!r} declares it. Refusing to skip: a "
                    f"screen whose contract cannot be resolved would silently pass.")
            # A screen may take an adapter AND a direct parameter, and its header
            # documents both. `readOnly — hides the add FAB` is a widget field,
            # not an adapter member; comparing the header against the adapter
            # alone called three of those stale.
            widget_match = screen_class_re.search(source)
            widget_own: dict = {}
            if widget_match:
                widget_own = {k: v for k, v
                              in (lang.class_fields(source, widget_match.group(1)) or {}).items()
                              if k not in IGNORE and not k.startswith("_")
                              and k != receiver_name}
            own_tree = screen.parents[TREE_DEPTH - 1]
            reads: set[str] = set()
            for path in sorted(own_tree.rglob(file_glob.split("/")[-1])):
                text = path.read_text()
                reads |= reads_in(path, text)
                reads |= typed_reads_in(path, text, {cls}).get(cls, set())
            shared = True
        else:
            # Loose-parameter screen: the widget's own fields *are* its contract.
            cls_match = screen_class_re.search(source)
            if not cls_match:
                refuse(
                    f"{rel} has a {MARKER} header but neither receiverPattern nor "
                    f"screenClassPattern matches, so its contract cannot be located.")
            cls = cls_match.group(1)
            adapter_path = screen
            widget_own = {}
            fields = lang.class_fields(source, cls) or {}
            # A constructor parameter is supplied by whoever builds the widget, so
            # "does this screen read it" is not the question here, and the language
            # already fails a build that stops passing a required one.
            reads = set(fields)
            shared = False

        fields = {k: v for k, v in fields.items()
                  if k not in IGNORE and not k.startswith("_")}
        # Two surfaces, deliberately different. The header describes everything a
        # screen is handed, adapter members and direct parameters alike. The
        # dead-member check may only look at the adapter: a widget parameter is
        # read as a bare identifier, never off the receiver, so including it here
        # reported live parameters as dead.
        contract = {**widget_own, **fields}
        checked += 1

        if enabled("undocumentedField"):
            for name in sorted(((reads | set(widget_own)) & set(contract)) - set(listed)):
                anchor = contracts.label_line(
                    text,
                    OUTPUT_LABELS if name.startswith(tuple(RULES.get("outputPrefixes") or ["on"]))
                    else INPUT_LABELS,
                    header_start, header_start)
                findings.append({
                    "file": rel, "line": anchor, "kind": "undocumented_field",
                    "name": name, "adapter": cls,
                    "detail": f"{rel}:{anchor} — {cls}.{name} is read by this screen "
                              f"but the {MARKER} header does not list it.",
                })
        if enabled("staleHeaderEntry"):
            for name in sorted(set(listed) - set(contract)):
                findings.append({
                    "file": rel, "line": listed[name], "kind": "stale_header_entry",
                    "name": name, "adapter": cls,
                    "detail": f"{rel}:{listed[name]} — the {MARKER} header lists "
                              f"{name!r}, which {cls} does not declare.",
                })
        if enabled("deadAdapterField") and shared:
            arel = str(adapter_path.relative_to(REPO))
            # `everywhere` is reads through the conventional receiver name;
            # `by_type[cls]` is reads through anything else declared as this
            # contract. A field is dead only when neither saw it.
            for name in sorted(set(fields) - everywhere - by_type.get(cls, set())):
                if (arel, name) in dead_seen:
                    continue
                dead_seen.add((arel, name))
                findings.append({
                    "file": arel, "line": fields[name], "kind": "dead_adapter_field",
                    "name": name, "adapter": cls,
                    "detail": f"{arel}:{fields[name]} — {cls}.{name} is declared and "
                              f"read nowhere. Documenting it would make it permanent; "
                              f"deleting it is usually the honest fix.",
                })

    if not checked:
        refuse(
            f"{len(screens)} screen(s) matched but none carried a {MARKER} header — "
            f"refusing to report clean on a corpus this audit never read.")

    def key(f):
        return f"{f['kind']}:{f['file']}:{f['name']}"

    # `{key: reason}`, not a list, matching the other baselines in this suite's
    # consumers — their own readme says a bare list is one nobody can
    # re-evaluate. An entry whose reason is still the placeholder is reported
    # every run, so "we decided" and "nobody got round to it" stay different
    # states.
    baseline_rel = RULES.get("baseline")
    if args.baseline_write:
        if not baseline_rel:
            refuse("contractHeaders.baseline is not set — nowhere to write")
        path = REPO / baseline_rel
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if path.is_file():
            existing = (json.loads(path.read_text()).get("accepted") or {})
        path.write_text(json.dumps({
            "_readme": "Contract-header findings accepted rather than fixed. Each "
                       "entry needs the REASON it is acceptable; an entry left "
                       "UNJUSTIFIED is reported on every run.",
            "accepted": {key(f): existing.get(key(f), UNJUSTIFIED)
                         for f in sorted(findings, key=key)},
        }, indent=2) + "\n")
        print(f"baseline written: {len(findings)} finding(s) → {baseline_rel}")
        return 0

    baselined, stale_baseline, unjustified = {}, [], []
    if baseline_rel and (REPO / baseline_rel).is_file():
        try:
            baselined = json.loads((REPO / baseline_rel).read_text()).get("accepted") or {}
        except ValueError as exc:
            refuse(f"{baseline_rel} is not valid JSON: {exc}")
        live = {key(f) for f in findings}
        stale_baseline = sorted(set(baselined) - live)
        unjustified = sorted(k for k, why in baselined.items()
                             if k in live and str(why).startswith(UNJUSTIFIED[:11]))

    active = [f for f in findings if key(f) not in baselined]

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(active, indent=2) + "\n")

    if args.findings:
        from backend_suite.engine import findings as F
        # Both baselined and new, severity distinguishing them — the same choice
        # audit_copy makes. A debt dashboard that hid accepted debt would
        # contradict what a baseline is for, while grading known debt as new
        # breakage would contradict a gate that just reported clean.
        F.write(
            F.default_path(REPO, "contract_headers") if args.findings is True
            else REPO / args.findings,
            "contract_headers",
            [F.make("contract_headers", f.get("kind", "contract"),
                    str(f.get("detail") or f.get("name") or "").strip(),
                    severity=F.SHOULD_FIX if f in active else F.FYI,
                    file=f.get("file"), line=f.get("line"))
             for f in findings],
        )

    counts = {}
    for f in active:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    header_kinds = {"undocumented_field", "stale_header_entry", "missing_contract_header"}
    drifted = {f["file"] for f in active if f["kind"] in header_kinds}
    print(f"  screens checked   {checked}")
    if skipped:
        print(f"  excluded          {len(skipped)}: "
              f"{', '.join(sorted(p.name for p in skipped))}")
        print("                    (contractHeaders.excludeGlobs — documented "
              "non-screens)")
    print(f"  headers agree     {checked - len(drifted)}")
    if baselined:
        print(f"  baselined         {len(findings) - len(active)}")
    if unjustified:
        # Accepted, but with no reason recorded. Left silent, a baseline becomes a
        # place findings go to be forgotten.
        print(f"  unjustified       {len(unjustified)}: {', '.join(unjustified)}")
        print("                    (baselined with no reason — say why, or fix it)")
    if stale_baseline:
        # A baseline entry for a finding that no longer exists means someone fixed
        # it and the baseline now grants an exemption nobody asked for.
        print(f"  stale baseline    {len(stale_baseline)}: {', '.join(stale_baseline)}")
        print("                    (fixed — remove these with --baseline-write)")
    sys.stdout.flush()

    if not active:
        print("\naudit_contract_headers: every header matches its adapter")
        return 0

    print(f"\nVIOLATIONS ({len(active)}):", file=sys.stderr)
    for kind in sorted(counts):
        print(f"\n  {kind} ({counts[kind]}):", file=sys.stderr)
        for f in active:
            if f["kind"] == kind:
                print(f"    {f['detail']}", file=sys.stderr)
    if args.out:
        print(f"\nFindings written to {args.out}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
