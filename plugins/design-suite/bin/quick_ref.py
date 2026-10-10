#!/usr/bin/env python3
"""Generate a per-component-family quick-reference card from what a project has
already declared about its components.

    python3 plugins/design-suite/bin/quick_ref.py            # write the quick-ref doc
    python3 plugins/design-suite/bin/quick_ref.py --check     # exit 1 if stale
    python3 plugins/design-suite/bin/quick_ref.py --component DsButton

## Why generated rather than hand-filled (issue #78)

A quick-reference card is a condensed, agent-facing cheat-sheet per component
family — "DsButton: 4 variants, common props X/Y/Z, states it actually handles,
link to full docs" — read before an agent works with a component, not instead
of the full docs. The tempting shape for that is a fill-in-the-blanks template
under templates/docs/, the same way DESIGN.md.template or API.md.template work.

That shape is wrong here, for a reason specific to this file rather than a
general preference: everything a quick-reference card needs to say about props,
variants, and states is *already* hand-authored or mechanically derived in
component-capabilities.json (issue #61) and component-maturity.json (issue #48).
A template would ask a project to retype `props` and `variants` a second time,
by hand, next to the manifest that already has them — which is exactly the
"hand-written claims have been wrong three separate times" failure this repo's
CLAUDE.md names for docs/CATALOG.md, applied to a new file instead of a new
lesson. `catalog.py` exists because a list of file-existence facts drifts the
moment it is typed twice; a list of prop names drifts the same way and for the
same reason.

So this script is the quick-reference card: it reads the two manifests a
project may already have populated and regenerates
`docs/COMPONENT-QUICK-REF.md` from them, the same relationship catalog.py has
to plugin frontmatter. What is genuinely a per-component editorial judgement —
*when* to reach for this component, and what people get wrong when they do —
is not recoverable from either manifest and is not invented here. It is read,
optionally, from a small hand-authored overlay
(conventionally `.design-suite/quick-ref-notes.json`, pointed to by
profile.json's `quickRef.notesFile`) and merged in verbatim. That overlay is
deliberately NOT schema-gated the way the two manifests are: it is free-text
editorial colour, not a fact an audit will ever compare against source, so
forcing it through `additionalProperties: false` would just be ceremony.

## What a missing manifest means

No component-capabilities file configured or populated is not an error but is
not silently "nothing to generate" either — see CLAUDE.md's governing
principle applied to a generator instead of an audit: a quick-ref doc that
generates empty must not look identical to one that generated from real data.
`main()` prints which manifest is missing and exits **2** — the doc-role
exit-code contract's "unknown role, or no manifest: **stop**, do not guess"
(plugins/design-suite/docs/DOC-ROLES.md). This used to be exit 3, which in that
same contract means "external — owned by another repository, read it but never
edit it". Nothing here is owned elsewhere; the manifests are this project's own
and simply unpopulated, so 3 told a caller to back off a file it was entitled
to write. The prose above already made the right argument — it reached for the
distinction resolve.py draws for an *unmapped role*, and that case is exit 2,
not 3. Do not "restore" 3: the analogy names the code.

## Card contents, per component

- maturity status (component-maturity.json), if the project maintains one
- derived prop shape (component-capabilities.json's `derived.props`)
- hand-verified states/variants/a11y (component-capabilities.json's
  `capabilities` block) — each field individually absent reads as "not
  verified", never as "has none", per that schema's own rule
- the free-text overlay's `whenToUse` / `commonMistakes` / `seeAlso`, if present

A component present in the manifest, and a component present only in the
overlay, both get a card — a card is never dropped just because one of the two
sources is silent about it.

Stdlib only, like every other script here.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
OUT = REPO / "docs" / "COMPONENT-QUICK-REF.md"
BIN = Path(__file__).resolve().parent

DEFAULT_CAPABILITIES = ".design-suite/component-capabilities.json"
DEFAULT_MATURITY = ".design-suite/component-maturity.json"
DEFAULT_NOTES = ".design-suite/quick-ref-notes.json"

MATURITY_LABEL = {
    "stable": "stable",
    "experimental": "experimental",
    "deprecated": "deprecated",
    "unverified": "unverified",
}


def _profile_value(key: str) -> str | None:
    """A profile.json key, or None if unset/absent — never an exception.

    Mirrors resolve.py's own --profile lookup rather than reimplementing it,
    so a project only has one place (profile.json) to point this at.
    """
    proc = subprocess.run(
        [sys.executable, str(BIN / "resolve.py"), "--profile", key],
        cwd=REPO, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _load_json(rel: str) -> dict | None:
    path = REPO / rel
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def load_sources() -> tuple[dict | None, dict | None, dict, str, str]:
    """(capabilities, maturity, notes, capabilities_path, maturity_path)."""
    cap_path = _profile_value("componentCapabilities.file") or DEFAULT_CAPABILITIES
    mat_path = _profile_value("componentMaturity.file") or DEFAULT_MATURITY
    notes_path = _profile_value("quickRef.notesFile") or DEFAULT_NOTES
    capabilities = _load_json(cap_path)
    maturity = _load_json(mat_path)
    notes = _load_json(notes_path) or {}
    return capabilities, maturity, notes, cap_path, mat_path


def _prop_line(prop: dict) -> str:
    name = prop.get("name", "?")
    ptype = prop.get("type")
    required = prop.get("required")
    bits = []
    if ptype:
        bits.append(ptype)
    if required is True:
        bits.append("required")
    elif required is False:
        bits.append("optional")
    return f"`{name}`" + (f" ({', '.join(bits)})" if bits else "")


def render_card(name: str, cap_entry: dict, mat_entry: dict, note: dict) -> str:
    lines = [f"## {name}", ""]

    status = mat_entry.get("status")
    if status:
        lines.append(f"**Maturity:** {MATURITY_LABEL.get(status, status)}")
        if mat_entry.get("notes"):
            lines.append(f"  — {mat_entry['notes']}")
        lines.append("")
    else:
        lines.append("**Maturity:** untagged (treat as unverified — no entry in "
                      "component-maturity.json)")
        lines.append("")

    derived = cap_entry.get("derived") or {}
    props = derived.get("props") or []
    if props:
        lines.append("**Props (derived from source):** " +
                      ", ".join(_prop_line(p) for p in props))
        lines.append("")
    if derived.get("framework"):
        lines.append(f"**Framework:** {derived['framework']}")
        lines.append("")

    caps = cap_entry.get("capabilities") or {}
    if caps.get("variants"):
        lines.append("**Variants:** " + ", ".join(caps["variants"]))
        lines.append("")
    if caps.get("states"):
        lines.append("**Handles states:** " + ", ".join(caps["states"]))
        lines.append("")
    a11y = caps.get("a11y") or {}
    if a11y:
        verified = [k for k, v in a11y.items() if v is True]
        unmet = [k for k, v in a11y.items() if v is False]
        if verified:
            lines.append("**Accessibility (verified):** " + ", ".join(verified))
            lines.append("")
        if unmet:
            lines.append("**Accessibility (verified absent):** " + ", ".join(unmet))
            lines.append("")
    if caps.get("notes"):
        lines.append(f"**Capability notes:** {caps['notes']}")
        lines.append("")

    if not cap_entry and not caps:
        lines.append("_No capabilities manifest entry — props, variants and states "
                      "are unknown, not absent._")
        lines.append("")

    if note.get("whenToUse"):
        lines.append(f"**When to use:** {note['whenToUse']}")
        lines.append("")
    if note.get("commonMistakes"):
        lines.append("**Common mistakes:**")
        for m in note["commonMistakes"]:
            lines.append(f"- {m}")
        lines.append("")
    if note.get("seeAlso"):
        lines.append(f"**See also:** {note['seeAlso']}")
        lines.append("")

    if mat_entry.get("path"):
        lines.append(f"**Source:** `{mat_entry['path']}`")
        lines.append("")
    elif (derived.get("sourcePath")):
        lines.append(f"**Source:** `{derived['sourcePath']}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render(capabilities: dict | None, maturity: dict | None, notes: dict,
           cap_path: str, mat_path: str, only: str | None = None) -> str:
    cap_components = (capabilities or {}).get("components", {})
    mat_components = (maturity or {}).get("components", {})
    names = sorted(set(cap_components) | set(mat_components) | set(notes))
    if only:
        names = [n for n in names if n == only]

    header = [
        "<!-- GENERATED by plugins/design-suite/bin/quick_ref.py — do not hand-edit. -->",
        "<!-- Regenerate: python3 plugins/design-suite/bin/quick_ref.py -->",
        "",
        "# Component quick reference",
        "",
        "Agent-facing cheat-sheet per component family: what a signature can prove"
        " (props, framework), what a human has verified (states, variants, a11y,"
        " maturity), and a short hand-authored note on when to reach for it. Not a"
        " replacement for the component's own docs — read those before writing"
        " anything the card doesn't answer.",
        "",
        f"Sources: `{cap_path}`" +
        (" (absent)" if capabilities is None else "") +
        f", `{mat_path}`" + (" (absent)" if maturity is None else ""),
        "",
    ]

    if not names:
        header.append("_No components found in either manifest or the notes overlay._")
        return "\n".join(header) + "\n"

    body = [
        render_card(
            name,
            cap_components.get(name, {}),
            mat_components.get(name, {}),
            notes.get(name, {}),
        )
        for name in names
    ]
    return "\n".join(header) + "\n" + "\n".join(body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if docs/COMPONENT-QUICK-REF.md is stale")
    ap.add_argument("--component", help="render only this one component")
    args = ap.parse_args()

    capabilities, maturity, notes, cap_path, mat_path = load_sources()

    if capabilities is None and maturity is None and not notes:
        # Never write an empty file that would look, on a clean diff, like a
        # project with zero components rather than a project that hasn't
        # populated either manifest yet.
        print(
            f"no component-capabilities file at {cap_path}, no component-maturity "
            f"file at {mat_path}, and no quick-ref notes overlay — nothing to "
            f"generate. This is not the same as a project with no components; "
            f"populate one of them first (see issue #61 / #48).",
            file=sys.stderr,
        )
        # 2, not 3. Exit 3 is reserved by the doc-role contract for "owned by
        # another repository — never edit it"; these manifests are this
        # project's own and merely unpopulated. See the docstring.
        return 2

    content = render(capabilities, maturity, notes, cap_path, mat_path, args.component)

    if args.check:
        current = OUT.read_text() if OUT.is_file() else None
        if current != content:
            print(f"{OUT.relative_to(REPO)} is stale — run "
                  f"plugins/design-suite/bin/quick_ref.py to regenerate.", file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(REPO)} is current.")
        return 0

    OUT.write_text(content)
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
