#!/usr/bin/env python3
"""Scaffold ONE document for ONE role from its template, marked `status: stub`.

This is the missing producer for a mechanism that already had a consumer. Exit
code 5, `is_stub()`, and stub-aware debt counting all shipped, but nothing wrote
a stub — so the state they describe had no natural source and the whole contract
was theoretical.

**One role per invocation, on purpose** (RFC-0002 §3d-ii, decision 4). There is
deliberately no `--all`, no "scaffold my archetype", and no mode that walks
`roles_for(kind)` writing a file per role. Bulk scaffolding is the cheap change
to make here and it is the one the design forbids: a stub nobody asked for
reports as coverage the project does not have, which is this suite's governing
failure wearing a friendly face. Archetype-specific documents are proposed and
accepted one at a time; a caller that wants five of them asks five times, having
decided five times.

`init.py` stays the universal-core scaffolder (`.backend-suite/` config) and does
not call this.

Usage:
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/scaffold_doc.py" <role> [--path docs/MOTION.md]
                                                        [--dir .] [--force] [--no-register]

Exit 0 on success. Exit 1 on a refusal the caller can fix (unknown role, no
template, destination exists, role declined).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT, project_root  # noqa: E402
from backend_suite.engine import archetypes  # noqa: E402
from backend_suite.engine import doc_roles  # noqa: E402

TEMPLATE_DIR = PLUGIN_ROOT / "templates" / "docs"
DEFAULT_MANIFEST = ".backend-suite/docs.manifest.json"


def project_name(repo: Path) -> str | None:
    """The declared name, or None. Never guessed from the directory name.

    A directory is named after wherever someone happened to clone it; substituting
    that into a doc-of-record puts a wrong name in writing.
    """
    profile = repo / ".backend-suite" / "profile.json"
    try:
        return (json.loads(profile.read_text()).get("project") or {}).get("name")
    except (OSError, ValueError):
        return None


def template_for(role: str) -> tuple[str, dict]:
    """(template basename, role entry), or a refusal explaining which of the
    several distinct "no template" situations applies."""
    name = archetypes.canonical_role(role)
    entry = archetypes.roles().get(name)
    if entry is None:
        known = ", ".join(sorted(r for r in archetypes.roles() if not r.startswith("_")))
        raise SystemExit(f"unknown role {role!r}. Known roles: {known}")
    if entry.get("plugin"):
        raise SystemExit(
            f"role {name!r} is scaffolded by the {entry['plugin']!r} plugin, not this one. "
            "Use that plugin's template rather than re-implementing it here.")
    template = entry.get("template")
    if not template:
        raise SystemExit(
            f"role {name!r} has no template: it is a declared role with no scaffolding. "
            "Write the document by hand and map it in the manifest — scaffolding a "
            "blank file here would invent a shape nobody designed.")
    return template, entry


def register(manifest_path: Path, role: str, rel: str) -> str:
    """Map role -> path in the manifest, and say what happened.

    Registration is part of scaffolding rather than a follow-up step because an
    unregistered stub is invisible to every consumer of the state — it resolves
    to nothing, counts as nothing, and reads as a role nobody has looked at.
    """
    if not manifest_path.is_file():
        return f"no manifest at {manifest_path.name} — map {role!r} to {rel} yourself"
    data = json.loads(manifest_path.read_text())
    roles = data.setdefault("roles", {})
    existing = roles.get(role)
    if existing == rel:
        return f"already mapped: {role} -> {rel}"
    if isinstance(existing, str):
        return (f"manifest already maps {role!r} to {existing!r}, not {rel!r} — left alone. "
                "Two paths for one role is a decision, not a merge.")
    roles[role] = rel
    manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return f"registered: {role} -> {rel}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("role", help="the single doc role to scaffold")
    ap.add_argument("--dir", default=None, help="project root (default: the detected one)")
    ap.add_argument("--path", default=None,
                    help="destination relative to the project root "
                         "(default: docs/<TEMPLATE NAME>, or the manifest's existing mapping)")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--no-register", action="store_true",
                    help="write the file but do not map it in the manifest")
    ap.add_argument("--force", action="store_true", help="overwrite an existing destination")
    args = ap.parse_args()

    repo = Path(args.dir).resolve() if args.dir else project_root()
    role = archetypes.canonical_role(args.role)
    template, _entry = template_for(role)

    manifest_path = repo / args.manifest
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}

    declined = doc_roles.declined_roles(manifest)
    if role in declined:
        # Scaffolding over a decline would silently reverse a recorded decision.
        print(doc_roles.decline_summary(role, declined[role]), file=sys.stderr)
        print(f"refusing to scaffold {role!r}: remove the decline first if it no longer holds.",
              file=sys.stderr)
        return 1

    # A role marked `na` for this archetype has no business being scaffolded into
    # it — `flows` in a design-system package, say. Until now only the calling
    # skill's prose stopped that, which makes the constraint hold exactly as long
    # as whoever is driving read the prose. A project that declares no kind is not
    # second-guessed: not knowing the archetype is not evidence the role is wrong.
    try:
        kind = archetypes.kind_of(json.loads((repo / ".backend-suite" / "profile.json").read_text()))
    except (OSError, ValueError, archetypes.ArchetypeNotDeclared, archetypes.UnknownArchetype):
        kind = None
    if kind and archetypes.applicability(role, kind) == "na" and not args.force:
        print(f"refusing to scaffold {role!r}: it is marked 'na' for a "
              f"{kind!r} project. Pass --force if this project genuinely needs it, "
              f"or check whether the declared projectKind is wrong.", file=sys.stderr)
        return 1

    mapped = (manifest.get("roles") or {}).get(role)
    rel = args.path or (mapped if isinstance(mapped, str) else f"docs/{template.split('.md')[0]}.md")

    src = TEMPLATE_DIR / template
    if not src.is_file():
        print(f"missing template {src} — plugin install looks broken", file=sys.stderr)
        return 1

    dest = repo / rel
    if dest.exists() and not args.force:
        print(f"{rel} already exists — refusing to overwrite (use --force). "
              "Overwriting an authored document with a stub would delete work and "
              "then report the result as debt.", file=sys.stderr)
        return 1

    name = project_name(repo)
    text = src.read_text()
    if name:
        text = text.replace("{{PROJECT_NAME}}", name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(doc_roles.stub_frontmatter() + text)
    print(f"wrote {rel} (status: {doc_roles.STUB_STATUS})")

    if not args.no_register:
        print(register(manifest_path, role, rel))

    print()
    print("This document is a stub until someone writes it:")
    print(f"  - delete the frontmatter block at the top of {rel} once it is authored;")
    print(f"  - until then resolve.py exits 5 for {role!r} and quality_debt.py counts it as debt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
