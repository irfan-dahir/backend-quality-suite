#!/usr/bin/env python3
"""Resolve a documentation ROLE to this project's path for it.

The suite's skills used to name `docs/DESIGN.md` directly — 184 hardcoded
references across 24 distinct paths, measured 2026-08-03, which was the single
most pervasive form of project coupling it had. A skill that names a path only
works in a project that happens to use that path. A skill that names a *role*
works anywhere the role is mapped.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design         → docs/DESIGN.md
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design --check  exit 1 if it does not exist
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --all           every role, one per line
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --reverse docs/DESIGN.md → design

An unmapped role exits 2 with the list of known roles, and an unwritten role is
never silently treated as an empty path — a skill that reads "" would scan the
whole repo or nothing at all, and both look like success.

Roles a project does not own (component specs living in a design-system repo,
say) resolve to a printed URL and exit 3, so a caller can tell "elsewhere" from
"absent". A role the project has deliberately declined prints its recorded reason
and exits 4, and a registered but unwritten document prints its path and exits 5 —
so "we decided not to" and "started, never written" stay distinguishable from both
"absent" and "done".

A role whose manifest value is `{"directory": "..."}` resolves to a DIRECTORY of
documents rather than one file — a design system with one page per component
needs that, and PR #111's `pageTemplate` gave it a write side with no read side.
It reuses the same codes: 0 when at least one member is authored, 5 when every
member is a stub, 2 when the directory exists and is empty, 1 when it is absent.
Those four are never collapsed; see `design_suite/engine/doc_roles.py` for why an
empty directory answering 0 is this repo's governing failure exactly. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)
from design_suite.engine import archetypes  # noqa: E402

REPO = project_root()

from design_suite.engine import doc_roles  # noqa: E402
DEFAULT_MANIFEST = ".design-suite/docs.manifest.json"


def load(manifest_rel: str) -> dict:
    path = REPO / manifest_rel
    if not path.is_file():
        print(f"no manifest at {manifest_rel}", file=sys.stderr)
        raise SystemExit(2)
    return json.loads(path.read_text())


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("role", nargs="?")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--all", action="store_true", help="print every role and path")
    ap.add_argument("--dirs", action="store_true", help="print directory roles")
    ap.add_argument("--dir", metavar="NAME", help="print one directory role's path")
    ap.add_argument("--profile", metavar="KEY",
                    help="print a dotted key from profile.json, e.g. audits.configFile")
    ap.add_argument("--reverse", metavar="PATH", help="print the role for a path")
    ap.add_argument("--source-roots", action="store_true",
                    help="print every declared source root, one per line, or refuse")
    ap.add_argument("--project-kind", action="store_true",
                    help="print this project's declared archetype, or refuse")
    ap.add_argument("--roles-for-kind", metavar="KIND",
                    help="print the roles that apply to an archetype, with applicability")
    ap.add_argument("--check", action="store_true", help="fail if the file is missing")
    ap.add_argument("--members", action="store_true",
                    help="for a directory-valued role, also list its documents")
    args = ap.parse_args()

    if args.roles_for_kind:
        try:
            kind = archetypes.require_kind(args.roles_for_kind)
        except archetypes.ArchetypeError as exc:
            print(exc, file=sys.stderr)
            return 2
        for role in archetypes.roles_for(kind):
            print(f"{role}\t{archetypes.applicability(role, kind)}")
        return 0

    if args.project_kind:
        profile_path = REPO / ".design-suite/profile.json"
        if not profile_path.is_file():
            print("no profile at .design-suite/profile.json", file=sys.stderr)
            return 2
        try:
            print(archetypes.kind_of(json.loads(profile_path.read_text())))
        except archetypes.ArchetypeError as exc:
            # Exit 2 for both the undeclared and the unknown case: each is a
            # question only a human can answer, which is what 2 already means.
            print(exc, file=sys.stderr)
            return 2
        return 0

    if args.source_roots:
        # `--profile source.root` is what every shell caller uses today, and on a
        # workspace it either prints nothing or prints one of three trees. Neither
        # is survivable in a `grep -r "$(...)"` one-liner: the first greps the
        # whole repository, the second greps a third of it and looks complete.
        # This flag is the seam that answers plurally, or refuses out loud.
        from design_suite.engine import source_roots as source_roots_engine
        profile_path = REPO / ".design-suite/profile.json"
        if not profile_path.is_file():
            print("no profile at .design-suite/profile.json", file=sys.stderr)
            return 2
        try:
            for root in source_roots_engine.declared(json.loads(profile_path.read_text())):
                if not (REPO / root).is_dir():
                    raise source_roots_engine.SourceRootError(
                        f"declared source root {root!r} is not a directory here")
                print(root)
        except source_roots_engine.SourceRootError as exc:
            print(exc, file=sys.stderr)
            return 2
        return 0

    if args.profile:
        profile_path = REPO / ".design-suite/profile.json"
        if not profile_path.is_file():
            print("no profile at .design-suite/profile.json", file=sys.stderr)
            return 2
        node = json.loads(profile_path.read_text())
        for part in args.profile.split("."):
            if not isinstance(node, dict) or part not in node:
                print(f"profile has no key {args.profile!r}", file=sys.stderr)
                return 2
            node = node[part]
        if args.profile.split(".")[-1] == "projectKind":
            # The generic key reader would happily hand back a typo'd kind, and a
            # caller cannot tell a validated kind from an echoed string.
            try:
                archetypes.require_kind(node if isinstance(node, str) else None)
            except archetypes.ArchetypeError as exc:
                print(exc, file=sys.stderr)
                return 2
        print(node if isinstance(node, str) else json.dumps(node))
        return 0

    manifest = load(args.manifest)
    roles: dict[str, str] = manifest.get("roles", {})
    external: dict[str, dict] = {
        k: v for k, v in manifest.get("externalRoles", {}).items() if not k.startswith("_")
    }
    declined = doc_roles.declined_roles(manifest)

    if args.all:
        missing = 0
        for role, rel in sorted(roles.items()):
            if doc_roles.is_directory_role(rel):
                # Marked in every state, including the healthy one. --all is the
                # surface a reader uses to ask "what does this project document?",
                # and a directory listed like a file answers a different question.
                where = doc_roles.directory_of(rel)
                state, _, _ = doc_roles.directory_state(REPO / where)
                print(f"{role}\t{where}\t(directory: {state})")
                continue
            # A stub is marked here too: --all is the surface a reader uses to ask
            # "what does this project document?", and an unwritten file listed
            # beside written ones answers that question wrongly.
            # A mapped file that does not exist is marked too. init.py registers
            # universal roles whose files a fresh project does not have yet, and
            # listing those unmarked beside written documents told
            # /bootstrap-design-docs the project was already documented.
            if not (REPO / rel).exists():
                mark = "\t(missing)"
                missing += 1
            else:
                mark = "\t(stub)" if doc_roles.is_stub(REPO / rel) else ""
            print(f"{role}\t{rel}{mark}")
        for role, ref in sorted(external.items()):
            print(f"{role}\t{ref.get('repo', '')}/{ref.get('path', '')}\t(external)")
        for role, entry in sorted(declined.items()):
            print(f"{role}\t{doc_roles.decline_reason(entry) or 'NO REASON RECORDED'}"
                  f"\t(declined)")
        # --check keeps its single-role meaning: a mapped file that is missing is
        # exit 1. Without --check, --all stays a listing and exits 0 as before.
        return 1 if (args.check and missing) else 0

    if args.dirs:
        for name, rel in sorted(manifest.get("directories", {}).items()):
            print(f"{name}\t{rel}")
        return 0

    if args.dir:
        dirs = manifest.get("directories", {})
        if args.dir not in dirs:
            print(f"unknown directory role {args.dir!r}. Known:", file=sys.stderr)
            for known in sorted(dirs):
                print(f"  {known}", file=sys.stderr)
            return 2
        print(dirs[args.dir])
        return 0

    if args.reverse:
        needle = args.reverse.lstrip("./")
        for role, rel in roles.items():
            if doc_roles.is_directory_role(rel):
                # A path INSIDE a directory role plays that role too. Matching only
                # the directory itself would answer "no role maps to this" for the
                # ~130 documents the role exists to cover, which is the same wrong
                # answer as having no directory role at all.
                where = doc_roles.directory_of(rel).rstrip("/")
                if needle == where or needle.startswith(where + "/"):
                    print(archetypes.canonical_role(role))
                    return 0
                continue
            if rel == needle:
                print(archetypes.canonical_role(role))
                return 0
        print(f"no role maps to {args.reverse}", file=sys.stderr)
        return 2

    if not args.role:
        ap.print_usage(sys.stderr)
        return 2

    # A manifest written before a role was renamed, or a skill written after it,
    # must both keep resolving. Try what was asked for first so a project that
    # deliberately maps both names gets its own answer, then follow the rename in
    # either direction. A rename with no bridge is a silently unmapped role.
    role = args.role
    # Alias resolution runs FIRST so every later check sees one canonical name.
    # Order matters: a project that declines `entry-point` must still be seen to
    # have declined it when a skill asks for the old name `instructions`, or the
    # decline silently stops applying the moment someone uses an alias.
    if role not in roles and role not in external and role not in declined:
        for candidate in [archetypes.canonical_role(role), *archetypes.aliases_of(role)]:
            if candidate in roles or candidate in external or candidate in declined:
                role = candidate
                break

    if role in declined:
        # Before the unknown-role check, because a declined role IS known — the
        # question has been answered, and answering it again as "unmapped, stop and
        # ask" would re-open a decision that is on record.
        entry = declined[role]
        print(doc_roles.decline_reason(entry) or "NO REASON RECORDED")
        print(doc_roles.decline_summary(role, entry), file=sys.stderr)
        print("skip the check that needed it AND say so, with this reason, in your "
              "report — declined is not passed", file=sys.stderr)
        return 4

    if role in external:
        ref = external[role]
        print(f"{ref.get('repo','')}/blob/main/{ref.get('path','')}")
        print(f"role {role!r} is owned by another repository — do not edit it here",
              file=sys.stderr)
        return 3

    if role not in roles:
        print(f"unknown role {role!r}. Known roles:", file=sys.stderr)
        for known in sorted(roles):
            print(f"  {known}", file=sys.stderr)
        for known in sorted(external):
            print(f"  {known} (external)", file=sys.stderr)
        for known in sorted(declined):
            print(f"  {known} (declined)", file=sys.stderr)
        return 2

    rel = roles[role]

    if doc_roles.is_directory_role(rel):
        # Four states, four codes — see doc_roles' "Directory-valued roles" block
        # for why none of them may collapse into another. The path is printed on
        # stdout in EVERY state, including the refusals: a caller that has been
        # told to treat the category as outstanding work still needs to know where
        # the work goes, and the exit code (not the silence) is what stops it
        # reading an empty glob as a clean result.
        where = doc_roles.directory_of(rel)
        state, members, authored = doc_roles.directory_state(REPO / where)
        print(where)
        if args.members:
            for m in authored if state == doc_roles.POPULATED else members:
                print(m.relative_to(REPO))
        code = doc_roles.DIR_EXIT[state]
        if code != 0:
            print(doc_roles.directory_summary(role, where, state, members, authored),
                  file=sys.stderr)
        return code

    if args.check and not (REPO / rel).exists():
        print(f"role {role!r} maps to {rel}, which does not exist", file=sys.stderr)
        return 1
    print(rel)
    if doc_roles.is_stub(REPO / rel):
        # The path is still printed: a caller that wants to FILL the document needs
        # it. The exit code is what stops a caller reading an empty file and
        # reporting the category as covered.
        print(f"role {role!r} maps to {rel}, which is a stub — registered but "
              f"unwritten. Treat it as outstanding work, never as coverage",
              file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
