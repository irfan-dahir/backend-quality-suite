#!/usr/bin/env python3
"""A colour role nothing reads is a promise the brand cannot cash.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_unwired_roles.py"

## Why this exists

The semantic colour roles are the contract: change these and the whole system
re-skins. That is the claim every theming document makes, and the reason a token
graph exists at all.

In the design system this found four roles that were defined, emitted to all five
targets, and read by **no component** — a scrim every modal ignored in favour of
Flutter's `black54`, a `disabledFill` every component hand-rolled its own alpha
for, and two nobody used at all. A brand changing any of them saw nothing move.

That is the same failure as a component hardcoding a brand colour, from the other
direction. There the component ignores the palette; here the palette offers
something no component asks for. Both end with a brand changing a value and
nothing happening.

## In a consumer, "this project reads it" is the WRONG question

Asked of a package, "does anything here read this role?" is exactly right. Asked
of a consuming app it is close to backwards: a consumer that reaches for
`colors.surface` directly is usually doing it wrong. The point of a design system
is that its **theme factory** and its **components** read the roles, and the app
gets them by using the components.

Scanning only the project's own source therefore produced a confident, wrong
report. On the staff portal it named eight of nineteen roles unread — including
`surface` and `background` — and every one of them turned out to be wired: four
through the design system's theme factory, three inside components, one by an
asset pipeline. Zero were dead. That is the same shape of failure this file
warns about in its next paragraph, committed by this file.

So when `tokens.roleSource` resolves to a package, that package's own source is
scanned too, and the report says *where* each role is read rather than only
whether. A role read by the theme is wired; a brand changing it moves the app.

And when that package is configured but its source cannot be found, this audit
**refuses** rather than scanning less: a narrower sweep than the one the config
asked for reports roles unread that are not, which is the measured failure above
happening again with nothing on screen to say so.

## Why a consuming app needs this too, and reads differently

`audit_tokens` catches the opposite direction — a literal where a role belongs.
This one catches roles going unasked-for, and in a *consumer* that is a different
and more interesting signal than in the package: it says which parts of the
design system this product has never once needed.

That is not automatically a defect in an app, which is why the failing set is
scoped. A role the app never reads may simply be one the package offers and this
product does not want. So a consumer declares which roles it considers itself on
the hook for; the rest are reported and not failed.

## What "used" means

A role counts as wired when something reads it through the theme accessor —
`colors.scrim`, `c.scrim`, `DsColors.of(context).scrim`. Being emitted to CSS
does not count: a role the code never reads is not part of that project's design
system, whatever the JSON says.

## Exemptions are debts, not verdicts

A role can be legitimately unread and still belong in the graph — one consumed by
an asset pipeline rather than a widget, say. Those carry a reason so that "we
decided" and "nobody noticed" stay distinguishable.

Re-read those reasons when the thing they describe changes. In the design system
`programAccents` was exempted because "this package ships no chart"; one release
later the chart landed and the justification had quietly expired, which is
indistinguishable from a role nobody noticed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()
from design_suite.adapters import for_project  # noqa: E402
from design_suite.engine.arch import load      # noqa: E402
from design_suite.engine import component_shape  # noqa: E402
from design_suite.engine.tokens import split_required, unwired as find_unwired  # noqa: E402
from design_suite.project import need, profile  # noqa: E402
from design_suite.engine import source_roots as source_roots_engine  # noqa: E402
from design_suite.engine import findings as F  # noqa: E402
from design_suite.engine.refusal import Refused  # noqa: E402

_RULES = load(REPO, "unwiredRoles")


def _exemptions() -> dict:
    rel = need(profile(REPO), "audits.exceptionsFile",
               "is where audit_unwired_roles reads its documented exemptions from")
    path = REPO / rel
    if not path.is_file():
        raise Refused(f"exceptions file not found at {rel}")
    try:
        exceptions = json.loads(path.read_text())
    except ValueError as exc:
        raise Refused(f"{rel} is not valid JSON: {exc}")
    return (exceptions.get("unwiredRoles", {}) or {}).get("exempt", {}) or {}


def refuse(message: str):
    """Stop with exit 2, never 1.

    Same split every other audit in this suite makes: `1` means "I looked and
    this is wrong", `2` means "I could not look". Collapsing them is how "the
    audit is red again" stops being read. See audit_contract_headers.refuse.
    """
    print(f"audit_unwired_roles: REFUSING TO RUN\n\n{message}", file=sys.stderr)
    raise SystemExit(2)


# The capabilities this audit cannot run without. `color_role_names` is
# currently implemented by exactly one adapter; every other adapter reaching
# line `adapter.color_role_names(ctx)` used to die with a raw AttributeError
# traceback (measured: `adapters.lang: "tsx"` → `AttributeError: module
# 'design_suite.adapters.tsx' has no attribute 'color_role_names'`, exit 1).
#
# Two things were wrong with that, and both come back the moment someone
# "simplifies" this guard away:
#   1. exit 1 is the code for findings, so a crash was indistinguishable from
#      "this project has unwired roles" to anything reading exit codes.
#   2. the carefully argued `roles is None` refusal immediately below was
#      unreachable on those adapters — the code that explains why blindness
#      must not read as a pass could never run on the adapters that are blind.
_REQUIRED_CAPABILITIES = ("color_role_names", "color_role_readers")


def _package_lib(repo: Path, source: dict) -> Path | None:
    """The resolved source root of the package the roles come from, or None.

    `None` means "there is no second place to look" — the roles are a plain file
    in this repo, and this repo's own source was already swept. It never means
    "the package was configured and I could not find it": that case refuses,
    because scanning less than the config asked for reports roles unread that the
    design system reads on the app's behalf. Eight of nineteen, measured.

    The resolution itself is the package manager's own map, not a guess at a path
    on disk — `component_shape.package_resolver()` is where that fact lives, so a
    project that declares `resolveVia` once is resolved the same way by every
    audit. The subdirectory scanned is derived from the project's own
    `pathInPackage` (its first segment, e.g. the `lib/` a Dart package's roles
    file sits under), never a literal here: which directory holds a package's
    source is a per-ecosystem fact, and this file holds none.
    """
    if source.get("kind") != "package":
        return None

    name = source.get("package")
    if not name:
        refuse("tokens.roleSource declares kind 'package' with no 'package' "
               "name, so the design system's own source cannot be found. Its "
               "theme factory and components are where a consumer's roles are "
               "actually read; sweeping without them reports wired roles as "
               "dead.")

    rel = source.get("resolveVia") or component_shape.package_resolver(repo)
    resolver = repo / rel
    if not resolver.is_file():
        refuse(f"the package manager's resolution map ({rel}) does not exist, so "
               f"the source of package {name!r} — which defines these roles and "
               f"reads most of them — cannot be located. Install dependencies "
               f"and re-run; a sweep of this project alone would report roles "
               f"unread that the design system reads for it.")
    try:
        packages = json.loads(resolver.read_text()).get("packages", [])
    except (OSError, ValueError) as exc:
        refuse(f"{rel} could not be read as the package manager's resolution "
               f"map ({exc}), so package {name!r} cannot be located.")

    for pkg in packages:
        if pkg.get("name") != name:
            continue
        root = pkg.get("rootUri", "")
        root = root[len("file://"):] if root.startswith("file://") else root
        pkg_root = (resolver.parent / root).resolve()
        parts = PurePosixPath(source.get("pathInPackage", "")).parts
        scan = pkg_root / parts[0] if len(parts) > 1 else pkg_root
        if not scan.is_dir():
            refuse(f"package {name!r} resolves to {pkg_root}, but its source "
                   f"directory {scan} is not there. Refusing to sweep without "
                   f"it rather than reporting the roles it reads as unread.")
        return scan

    refuse(f"package {name!r} is named by tokens.roleSource but is not in "
           f"{rel}. Its roles resolved, so the package exists — refusing to "
           f"sweep this project alone rather than calling the roles it reads "
           f"unread.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="also write findings as JSON here")
    parser.add_argument("--findings", nargs="?", const=True, default=None,
                        help="also write the common findings envelope for /design-debt "
                             "(default .design-suite/findings/unwired-roles.json)")
    args = parser.parse_args()

    adapter, ctx, _ = for_project(REPO)

    missing = [n for n in _REQUIRED_CAPABILITIES if not hasattr(adapter, n)]
    if missing:
        refuse(
            f"language adapter {getattr(adapter, 'NAME', '?')!r} cannot enumerate "
            f"semantic colour roles or their readers ({', '.join(missing)}), so "
            f"the theming contract cannot be checked for this stack. INERT, not "
            f"clean — implement the capability in design_suite/adapters/ or drop "
            f"this audit for this project rather than letting it pass by being "
            f"blind.")

    roles = adapter.color_role_names(ctx)
    if roles is None:
        # None, not empty. "Could not read the roles" must not be reported as
        # "no roles are unwired" — the second reads like a pass.
        raise Refused(
            "could not resolve tokens.roleSource. If it names a package, install "
            "dependencies first; every role would otherwise read as wired and this "
            "audit would pass by being blind.")
    if not roles:
        raise Refused(
            "tokens.roleSource resolved but defines no roles — refusing to report "
            "clean on an empty set.")

    readers = adapter.color_role_readers(ctx)
    if not readers:
        raise Refused("no role accessors configured (tokens.roleAccessor / "
                         "roleLocalNames) — nothing would ever count as a read")
    accessor = "(?:" + "|".join(readers) + ")"

    # The adapter owns which files are generated; a generated file reading a
    # role is the emitter's own output, not a component asking for it.
    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    file_glob = need(profile(REPO), "source.fileGlob",
                     "is how this audit finds the sources that read roles")
    # Reachability, so the declared roots are unioned — a role read in one
    # workspace member is read. engine/source_roots.py has the reasoning.
    try:
        scan_roots = source_roots_engine.resolve(REPO, profile(REPO))
        sources = source_roots_engine.source_files(REPO, profile(REPO), file_glob,
                                                   generated)
    except source_roots_engine.SourceRootError as exc:
        raise Refused(str(exc))
    if not sources:
        rels = ", ".join(p.relative_to(REPO).as_posix() for p in scan_roots)
        raise Refused(f"source.fileGlob {file_glob!r} matched nothing under any "
                         f"declared source root ({rels}) — an empty sweep would report "
                         f"every role wired")
    project_src = "\n".join(p.read_text() for p in sources)

    # The design system's own source, when the roles come from a package. A role
    # the theme factory or a component reads is wired — the app gets it by using
    # the component, which is the arrangement working rather than failing.
    ds_src = ""
    role_source = (profile(REPO).get("tokens", {}) or {}).get("roleSource", {}) or {}
    ds_root = _package_lib(REPO, role_source)
    if ds_root is not None:
        suffix = PurePosixPath(file_glob).suffix
        ds_files = sorted(f for f in ds_root.rglob(f"*{suffix}")
                          if f.is_file() and not f.name.endswith(generated))
        if not ds_files:
            refuse(f"package {role_source.get('package')!r} resolved to "
                   f"{ds_root}, but source.fileGlob {file_glob!r} matched "
                   f"nothing in it. An empty upstream sweep is worse than none: "
                   f"it reads as 'the design system reads no roles'.")
        ds_src = "\n".join(f.read_text(errors="ignore") for f in ds_files)

    src = project_src + "\n" + ds_src

    exempt = _exemptions()
    # Roles this project holds itself to.
    #
    # Absent means all of them — the right default for a package, which owns
    # every role it defines. An empty LIST means none, which is a consumer
    # saying "report, do not fail" and is a different statement entirely.
    # `.get(k) or roles` conflated the two and made an explicit [] fail on all
    # 19; the exceptions file's own readme says empty sets are deliberate and
    # not the same as absent, and this is why.
    declared = _RULES.get("requiredRoles")
    required = set(roles) if declared is None else set(declared)

    candidates = {r for r in roles if r not in exempt}
    unwired = find_unwired(candidates, accessor, src)
    failing, unused = split_required(unwired, required)

    # Split the wired ones by who reads them, because "the app reads it" and
    # "the design system reads it for the app" are different facts and only the
    # first is the app's to change. Both go through the same engine comparison
    # the sweep above uses — a second regex here would be a second answer.
    unread_here = set(find_unwired(candidates, accessor, project_src))
    by_project = sorted(candidates - unread_here)
    by_ds = sorted(unread_here - set(unwired))

    if args.out:
        (REPO / args.out).parent.mkdir(parents=True, exist_ok=True)
        (REPO / args.out).write_text(json.dumps(
            {"failing": failing, "unusedButAllowed": unused}, indent=2) + "\n")

    if args.findings:
        # Two categories, not one, because the two carry different claims: a
        # role this project holds itself to and never reads is a broken theming
        # promise; one the design system merely offers is not.
        #
        # Both details name WHERE the audit looked, because after the upstream
        # scan that is what the reader needs in order to size the claim: "read
        # nowhere" spanning the design system's own source is a much stronger
        # statement than "this app does not read it", and the envelope is where
        # /design-debt reads it from rather than from the stdout summary.
        reach = (f"searched this project and the {role_source.get('package')} "
                 f"package's own source" if ds_src
                 else "searched this project's own source")
        records = (
            [F.make("unwired-roles", "claimed-role",
                    f"{r} is claimed by this project and read nowhere",
                    severity=F.SHOULD_FIX,
                    detail=f"a brand changing this role sees nothing move; {reach}")
             for r in failing]
            + [F.make("unwired-roles", "offered-role",
                      f"{r} is defined by the design system and read nowhere here",
                      severity=F.FYI,
                      detail=f"offered, not claimed — see unwiredRoles.requiredRoles; "
                             f"{reach}")
               for r in unused])
        F.write(
            F.default_path(REPO, "unwired-roles") if args.findings is True
            else REPO / args.findings,
            "unwired-roles", records,
            # The sweep is over declared colour roles, not over files.
            scanned=len(roles),
            suppressed={"exempt": sorted(exempt)} if exempt else None,
        )

    print(f"  colour roles   {len(roles)}")
    if ds_src:
        print(f"  read here      {len(by_project)}")
        print(f"  read upstream  {len(by_ds)}  (the theme factory or a component "
              f"reads these — the app gets them by using the component)")
    print(f"  wired        {len(roles) - len(unwired) - len(exempt)}"
          f"  ({len(exempt)} documented exemption(s))")

    if unused:
        # Reported every run, never failed. A count alone would let the list grow
        # without anyone reading it, which is how an unwanted role becomes a
        # forgotten one.
        print(f"  unread here    {len(unused)}: {', '.join(unused)}")
        print("                 (offered by the design system, not claimed by this "
              "project — see unwiredRoles.requiredRoles)")

    sys.stdout.flush()  # so the summary above lands before the stderr block

    if failing:
        print(f"\nUNWIRED — {len(failing)} role(s) this project claims and reads "
              f"nowhere:\n", file=sys.stderr)
        for role in failing:
            print(f"  {role}", file=sys.stderr)
        print(
            "\nA brand changing one of these sees nothing move, which makes the "
            "re-skinning claim partly false. Either read it somewhere, or move it "
            "out of unwiredRoles.requiredRoles, or exempt it WITH A REASON in the "
            "exceptions file — and if no component ever wanted it, deleting the "
            "role is the honest answer.",
            file=sys.stderr)
        return 1

    print("\naudit_unwired_roles: every claimed colour role is read by something")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
