"""Constructor-shape extraction and the `component-capabilities.json` manifest.

`audit_promotion_candidates.py` and `audit_reinvented_components.py` each parse
a Dart widget's constructor to get its parameter names (`constructor_params` /
`_constructor_params`), duplicated on purpose per their own module docstrings —
"two independent CLI scripts by design", the regex is the contract, not the
module. That reasoning holds for the two audits staying independent scripts.
It does not hold for a third near-identical copy: issue #61 needs the same
shape extraction to populate `component-capabilities.json`'s machine-written
`derived` layer, and typing the parameter regex a third time is exactly the
drift CLAUDE.md already called out three separate times for hand-written
coverage claims. So this module is the one place the extraction logic lives;
the two audits keep their own copies (nothing here changes their behaviour),
and this is what a manifest-regenerating tool calls instead of adding a fourth
copy later.

Also holds the reader for the `capabilities` (hand-authored) side of the
manifest and the overlap score the two duplicate-detection audits use as an
optional second signal alongside their existing parameter-shape Jaccard/
containment checks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .arch import load as arch_load

PROFILE = ".design-suite/profile.json"

# Same regex pair `audit_promotion_candidates.py` and `audit_reinvented_components.py`
# each already carry — see this module's docstring for why a third copy lives
# here instead of a fourth one in a future script.
CLASS_RE = re.compile(
    r"^class\s+(\w+)\s+extends\s+(?:StatelessWidget|StatefulWidget)\b",
    re.M,
)
PARAM_RE = re.compile(r"(?:required\s+)?(?:this\.(\w+)|([\w<>,\s?]+?)\s+(\w+))\s*[,)=}]")


def constructor_params(body: str, cls: str, plumbing: frozenset[str] = frozenset()) -> frozenset[str]:
    """Parameter names of `cls`'s primary constructor.

    Identical extraction to `audit_promotion_candidates.constructor_params()` /
    `audit_reinvented_components._constructor_params()`. `plumbing` lets a
    caller drop names that carry no design information (a project's `theme`,
    `key`) the way both audits' own `PLUMBING`/`BESPOKE_PLUMBING` sets do.
    """
    m = re.search(rf"\b{re.escape(cls)}\s*\(([^)]*)\)\s*(?::[^{{;]*)?[;{{]", body)
    if not m:
        return frozenset()
    names = set()
    for groups in PARAM_RE.findall(m.group(1) + ","):
        a, _typ, b = groups
        name = a or b
        if name and name not in plumbing:
            names.add(name)
    return frozenset(names)


def constructor_props(body: str, cls: str, plumbing: frozenset[str] = frozenset()) -> list[dict]:
    """Like `constructor_params`, but keeps the declared type and required-ness
    for each parameter — what `component-capabilities.json`'s `derived.props`
    needs and a bare `frozenset[str]` of names throws away.

    Best-effort: a `this.foo` shorthand parameter has no type in the
    constructor signature, so `type` is omitted for it rather than guessed.
    """
    m = re.search(rf"\b{re.escape(cls)}\s*\(([^)]*)\)\s*(?::[^{{;]*)?[;{{]", body)
    if not m:
        return []
    props: list[dict] = []
    seen: set[str] = set()
    # Named-parameter braces (`Foo({required this.x})`) sit INSIDE the
    # captured parens, not around them, so they land on the first/last
    # chunk after a naive split and break both the `this.foo` and typed
    # regexes below. Strip them; they carry no parameter information.
    raw = m.group(1).replace("{", " ").replace("}", " ")
    for chunk in (raw + ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        required = chunk.startswith("required ")
        rest = chunk[len("required "):] if required else chunk
        this_m = re.match(r"^this\.(\w+)\s*(?:=.*)?$", rest)
        if this_m:
            name = this_m.group(1)
            if not name or name in plumbing or name in seen:
                continue
            seen.add(name)
            props.append({"name": name, "required": required})
            continue
        typed_m = re.match(r"^([\w<>,\s?]+?)\s+(\w+)\s*(?:=.*)?$", rest)
        if typed_m:
            typ, name = typed_m.group(1).strip(), typed_m.group(2)
            if not name or name in plumbing or name in seen:
                continue
            seen.add(name)
            entry = {"name": name, "required": required}
            if typ:
                entry["type"] = typ
            props.append(entry)
    return props


def derive_component(
    src: str,
    cls: str,
    *,
    source_path: str,
    framework: str = "flutter",
    platform: str | None = None,
    plumbing: frozenset[str] = frozenset(),
) -> dict:
    """Build the `derived` block for one component, for a manifest-regenerating
    tool to write into `component-capabilities.json`. Never call this to
    populate `capabilities` — that layer is hand-authored, see the schema.
    """
    m = re.search(rf"^class\s+{re.escape(cls)}\b", src, re.M)
    body = src[m.start():] if m else src
    derived: dict = {
        "props": constructor_props(body, cls, plumbing),
        "framework": framework,
        "sourcePath": source_path,
    }
    if platform:
        derived["platform"] = platform
    return derived


def _token_source(repo: Path) -> dict:
    profile_path = repo / PROFILE
    if not profile_path.is_file():
        return {}
    try:
        profile = json.loads(profile_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return (profile.get("tokens", {}) or {}).get("source", {}) or {}


def design_system_package(repo: Path) -> str | None:
    """The package a project's design system ships as — from the project's own
    config, never from a constant here.

    Both duplicate-detection audits used to compile one consumer's package name
    into a regex literal (`package:<name>/`). On any other project that regex
    matched nothing, so every file read as "never imports the design system" and
    the audits compared widgets against a design system they had already decided
    was absent. Nothing errored and nothing was reported — the failure this
    suite's governing principle names.

    Two sources, in order, both the project's own:

      1. `reinventedComponents.package` in the project's arch-rules, beside
         `exportPrefix` — the same fact spelled for symbols rather than for the
         package. For a project whose design system is not the package that
         owns its tokens. This function loads that section ITSELF and takes no
         `rules` argument, because it used to: `audit_promotion_candidates.py`
         handed it the `promotionCandidates` section, which has no `package`
         key, so on every project that declared one the documented way the
         lookup fell through to source 2 and the `near_ds` suggestions were
         off — while the error named the very key that WAS set. One right
         section and a parameter that accepts any dict is a footgun, not a
         seam.
      2. `tokens.source.package` in the profile — the shape `export_palette.py`
         and `adapters/dart.py` already resolve a design-system package through,
         and the field `audit_skill_paths.py` names as the correct home for a
         package literal. Only meaningful when `tokens.source.kind` is
         `"package"`.

    `None` means "this project has not declared one". Every caller must REFUSE
    on it, never fall back to a guess: a wrong package name here produces a
    confident zero.
    """
    declared = arch_load(repo, "reinventedComponents").get("package")
    if declared:
        return declared
    source = _token_source(repo)
    if source.get("kind") == "package":
        return source.get("package") or None
    return None


def package_resolver(repo: Path, default: str = ".dart_tool/package_config.json") -> str:
    """Repo-relative path of the package manager's own resolution map.

    `tokens.source.resolveVia` is the project's declaration of it — the same
    field `export_palette.py` requires, for the same reason: guessing a
    dependency's path on disk is what silently broke that script and both copies
    of the contrast audit. The default is the Dart toolchain's conventional
    location, which is a TOOLCHAIN fact rather than a project one; a project
    that declares the field wins.
    """
    return _token_source(repo).get("resolveVia") or default


def load_capabilities(repo: Path) -> dict[str, dict]:
    """Component name -> its full manifest entry (`derived` + `capabilities`),
    from the project's own `component-capabilities.json`.

    Optional, mirroring `load_component_maturity()` in
    `audit_promotion_candidates.py`: a project with no manifest configured
    gets an empty map, and every caller must treat that as "no capability
    signal available", never as "components have none". See
    `templates/component-capabilities.schema.json`'s file-level description.
    """
    profile_path = repo / PROFILE
    if not profile_path.is_file():
        return {}
    try:
        profile = json.loads(profile_path.read_text())
    except json.JSONDecodeError:
        return {}
    rel = profile.get("componentCapabilities", {}).get("file")
    if not rel:
        return {}
    manifest_path = repo / rel
    if not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return {}
    return {
        name: entry
        for name, entry in data.get("components", {}).items()
        if isinstance(entry, dict)
    }


def capability_overlap(a: dict | None, b: dict | None) -> float | None:
    """Jaccard overlap of two components' hand-authored `capabilities`
    (a11y flags treated as tagged booleans, plus `states` and `variants`),
    or `None` when there is nothing to compare.

    `None`, not `0.0`, when either side's `capabilities` block is missing or
    empty — a missing block means unknown, and scoring it as zero overlap
    would read as "confirmed to diverge" when the truth is "never verified".
    A caller (an audit narrowing a duplicate-shape match) must treat `None`
    as "no additional signal, fall back to shape alone", never as evidence
    the two are, or are not, the same component.
    """
    a = (a or {}).get("capabilities") or {}
    b = (b or {}).get("capabilities") or {}
    if not a and not b:
        return None

    def _tags(entry: dict) -> set[str]:
        tags: set[str] = set()
        a11y = entry.get("a11y") or {}
        for k, v in a11y.items():
            if isinstance(v, bool):
                tags.add(f"a11y:{k}={v}")
        for s in entry.get("states") or []:
            tags.add(f"state:{s}")
        for v in entry.get("variants") or []:
            tags.add(f"variant:{v}")
        return tags

    ta, tb = _tags(a), _tags(b)
    if not ta and not tb:
        return None
    if not ta or not tb:
        return None
    return len(ta & tb) / len(ta | tb)


class ShapeSourceError(RuntimeError):
    """This project's widget sources cannot be enumerated for shape extraction.

    Raised, never answered with an empty list: both duplicate-detection audits
    used to sweep a hardcoded `lib/**/*.dart`, so on any project whose source was
    not exactly that — every non-Dart stack, and a Dart project rooted elsewhere —
    they scanned zero files and printed "no NEW widget built twice" with exit 0.
    """


def widget_sources(repo: Path) -> list[Path]:
    """Every file the constructor-shape parser above can read, under the
    profile's declared source root(s).

    Which files those are is the language adapter's to say
    (`WIDGET_SHAPE_GLOB`), because `CLASS_RE` / `PARAM_RE` are Dart-shaped: an
    adapter that does not declare one has no widget-shape extraction, and the
    audit must refuse rather than parse another language with Dart's regexes.
    """
    from ..adapters import load, load_project
    from . import source_roots

    profile, _ = load_project(repo)
    lang = (profile.get("adapters", {}) or {}).get("lang")
    adapter = load(lang) if lang else None
    if adapter is None:
        raise ShapeSourceError(f"{PROFILE} does not set adapters.lang, so there is no "
                               "way to tell which files hold widget constructors")
    glob = getattr(adapter, "WIDGET_SHAPE_GLOB", None)
    if not glob:
        raise ShapeSourceError(
            f"the {adapter.NAME!r} adapter has no widget constructor-shape extraction "
            f"(no WIDGET_SHAPE_GLOB) — the parser this audit uses is implemented for "
            f"Dart widgets only. INERT for this stack, not clean.")
    try:
        files = source_roots.source_files(repo, profile, glob)
    except source_roots.SourceRootError as exc:
        raise ShapeSourceError(str(exc)) from exc
    if not files:
        raise ShapeSourceError(
            f"no files matching {glob!r} under the declared source root(s) "
            f"{source_roots.declared(profile)} — an empty sweep is INERT, not clean")
    return files
