"""Cross-check what a project *does* against what its profile *declares*.

`survey --check` rule 1 and 2 walk the filesystem: they find paths on disk that
no config names. That is the reflexion model's **divergence** verdict and it can
only ever see things that exist. The verdict it cannot reach is **absence** — the
config declares a check's input, the code does the thing that check is about, and
the two never meet. Nothing is missing from disk, so nothing is reported, and the
check downstream runs against a field that is `null` and prints a clean report.

That is not hypothetical: it is RFC-0002 §2b's first row, and it is the governing
principle violated in production.

## Who answers the question

The engine asks "does this project route?"; the *adapter* answers, because the
answer is spelled in a language. Nothing here knows what a router looks like, and
nothing here knows which profile field is supposed to point at one — the adapter
carries the pairing as a `Capability`.

## Why an adapter that cannot answer is louder than one that says no

An adapter is required to raise `CapabilityError` rather than report absence it
did not measure, and this module makes the refusal *more* visible than a finding,
never less: an undetermined capability is emitted as its own finding kind and the
run is non-clean. An adapter with no capability support at all is reported as
such, so "this project has no capability findings" can never be confused with
"nobody asked".
"""
from __future__ import annotations

from pathlib import Path

from backend_suite.adapters import load
from backend_suite.adapters.base import AdapterContext, CapabilityError

UNDETERMINED = "capability-undetermined"
UNDECLARED = "undeclared-capability"
DECLARED_UNUSED = "declared-capability-unused"
NOT_EXAMINED = "capabilities-not-examined"


def _field(profile: dict, dotted: str):
    """The value at a dotted path, or None when any segment is missing.

    Missing and null collapse deliberately: a field that is absent and a field
    explicitly set to null leave every downstream check with the same nothing.
    """
    node = profile
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def cross_check(repo: Path, profile: dict) -> list[dict]:
    """Capability findings for one project. Never returns [] for "did not run"."""
    lang = (profile.get("adapters", {}) or {}).get("lang")
    if not lang:
        return [{
            "kind": NOT_EXAMINED,
            "path": "adapters.lang",
            "why": "the profile names no language adapter, so no capability could be "
                   "detected. This is unexamined, not clean.",
        }]
    try:
        adapter = load(lang)
    except SystemExit as exc:
        # `load` is a CLI-shaped hard error elsewhere; here it must become a
        # finding, or an unknown adapter would abort the whole completeness diff
        # and take the filesystem findings down with it.
        return [{
            "kind": NOT_EXAMINED,
            "path": f"adapters.lang: {lang}",
            "why": f"adapter could not be loaded, so no capability was examined: "
                   f"{str(exc).splitlines()[0]}",
        }]

    declared_caps = getattr(adapter, "capabilities", None)
    detect = getattr(adapter, "detect_capability", None)
    if declared_caps is None or detect is None:
        return [{
            "kind": NOT_EXAMINED,
            "path": f"adapters.lang: {lang}",
            "why": f"the {lang!r} adapter implements no capability detection, so the "
                   f"absence verdict is unavailable for this project. Reported rather "
                   f"than left as an empty result.",
        }]

    ctx = AdapterContext(repo=repo, profile=profile, exceptions={})
    findings: list[dict] = []
    for cap in declared_caps(ctx):
        try:
            evidence = detect(ctx, cap.name)
        except CapabilityError as exc:
            findings.append({
                "kind": UNDETERMINED,
                "path": cap.profile_field,
                "capability": cap.name,
                "why": f"the {lang!r} adapter refused to answer whether this project does "
                       f"{cap.name!r}: {exc.why}. A refusal is not a finding of zero — "
                       f"nothing downstream may read this as absent.",
            })
            continue
        value = _field(profile, cap.profile_field)
        if evidence.present and value in (None, "", [], {}):
            findings.append({
                "kind": UNDECLARED,
                "path": cap.profile_field,
                "capability": cap.name,
                "evidence": list(evidence.files),
                "why": f"the code does {cap.name!r} ({evidence.why}) and {cap.profile_field} "
                       f"declares nothing. {cap.why}",
            })
        elif not evidence.present and value not in (None, "", [], {}):
            findings.append({
                "kind": DECLARED_UNUSED,
                "path": cap.profile_field,
                "capability": cap.name,
                "why": f"{cap.profile_field} is declared as {value!r}, but the adapter found "
                       f"no {cap.name!r} in the source: {evidence.why}",
            })
    return findings
