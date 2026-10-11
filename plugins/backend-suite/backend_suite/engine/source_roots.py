"""How many source trees this project has, and which ones.

RFC-0002 §3g #3: the profile and every audit that reads it model exactly one
source tree (`source.root`). That is true of an application and false of a
workspace — a pub workspace or an npm workspace has a *stub* manifest at the top
and the real sources one level down, in several members at once. An audit given
a single root on such a project sweeps one member and reports clean about the
other two, which is this repository's governing failure with extra steps.

## The three design decisions, and why

**1. `source.roots` sits BESIDE `source.root`, it does not replace it.**
RFC-0002 §6 commits to additive change, and both live consumer projects declare a
single `source.root`. `roots` is optional; when it is absent `root` answers
exactly as it always did, so a profile written before this module keeps working
byte-for-byte. When `roots` IS present it wins — a project that took the trouble
to enumerate its trees means it.

**2. A sweep unions the roots; a finding names its root by its path.**
Both shapes of question show up, and they want different answers:

  * *reachability* — "is this token read anywhere?" — must union, because a token
    read in any member is read. `source_files` is the union seam;
  * *location* — "which file hardcoded this colour?" — must attribute, because a
    finding that cannot say which root it came from is a finding nobody can act
    on. Every finding in this suite already carries a **repository-relative**
    path, and a repo-relative path begins with its root. So attribution is free
    and needs no second vocabulary: `root_of` recovers it, and `walk` hands
    callers `(root, files)` pairs when they would rather not re-derive it.

That is also why `roots` is a list of paths and not a list of `{name, path}`
objects. A separate name is a second identifier that can drift from the path it
labels, and there is nothing it buys that the path does not already say.

**3. Declaring nothing is a refusal, never a guess.**
If neither key is set, this raises. It never falls back to `.`, never infers the
workspace members it could perfectly well read out of the manifest, and never
returns an empty list. `survey.py` is allowed to *propose* roots because its
whole output is labelled as candidates; an engine that resolves them is not.
A declared root that does not exist on disk is also a refusal, for the same
reason: globbing a missing directory returns nothing, and nothing is the shape
of a pass.
"""
from __future__ import annotations

from pathlib import Path

PROFILE_REL = ".backend-suite/profile.json"


class SourceRootError(RuntimeError):
    """The source tree could not be determined. Exit 2 — never a finding of zero."""


def declared(profile: dict) -> list[str]:
    """Every source root this profile declares, as repo-relative POSIX strings.

    Raises rather than returning `[]`: an empty list here would be read by every
    caller as "sweep nothing", which prints clean.
    """
    source = profile.get("source") or {}
    roots = source.get("roots")
    if roots is not None:
        if not isinstance(roots, list) or not all(isinstance(r, str) and r.strip()
                                                  for r in roots):
            raise SourceRootError(
                f"{PROFILE_REL}: source.roots must be a non-empty list of relative "
                f"paths. Remove the key rather than leaving it empty — an empty list "
                f"reads as 'sweep nothing', which reports clean.")
        if not roots:
            raise SourceRootError(
                f"{PROFILE_REL}: source.roots is empty. A project with no source tree "
                f"cannot be audited; declare the trees or drop the audits.")
        # Order is the project's own, but duplicates are dropped: two entries for
        # one tree would double every union and make counts meaningless.
        seen, out = set(), []
        for rel in roots:
            rel = rel.strip().rstrip("/")
            if rel not in seen:
                seen.add(rel)
                out.append(rel)
        return out

    root = source.get("root")
    if isinstance(root, str) and root.strip():
        return [root.strip().rstrip("/")]

    raise SourceRootError(
        f"{PROFILE_REL} declares neither source.root nor source.roots, so there is no "
        f"source tree to audit. Declare one (or several, for a workspace whose top-level "
        f"manifest is a stub). Refusing to guess: a guessed root sweeps the wrong tree "
        f"and reports clean about the right one.")


def resolve(repo: Path, profile: dict) -> list[Path]:
    """The declared roots as absolute directories, or a refusal naming the bad one."""
    out = []
    for rel in declared(profile):
        path = repo / rel
        if not path.is_dir():
            raise SourceRootError(
                f"{PROFILE_REL} declares source root {rel!r}, which is not a directory "
                f"here. Refusing to sweep the rest and report on a partial tree — a "
                f"missing root contributes no files and therefore no findings.")
        out.append(path)
    return out


def primary(repo: Path, profile: dict) -> Path:
    """The single root, for a caller that genuinely models only one.

    Refuses when there are several rather than silently taking the first. A
    single-root call site handed a three-root project must stop and say so; the
    alternative is a report that covers a third of the project and looks complete.
    """
    roots = resolve(repo, profile)
    if len(roots) > 1:
        rels = [p.relative_to(repo).as_posix() for p in roots]
        raise SourceRootError(
            f"this project declares {len(roots)} source roots ({', '.join(rels)}) and "
            f"this check models one. Refusing to audit {rels[0]!r} and report as though "
            f"the project were covered.")
    return roots[0]


def walk(repo: Path, profile: dict, glob: str,
         exclude_suffixes: tuple[str, ...] = ()) -> list[tuple[Path, list[Path]]]:
    """`(root, files)` per declared root — the attribution seam.

    Kept separate from `source_files` so a caller that reports *per root* does not
    have to re-derive which root a path came from, and a caller that reports over
    the union does not have to care.
    """
    out = []
    for root in resolve(repo, profile):
        files = [p for p in sorted(root.glob(glob))
                 if not (exclude_suffixes and p.name.endswith(exclude_suffixes))]
        out.append((root, files))
    return out


def source_files(repo: Path, profile: dict, glob: str,
                 exclude_suffixes: tuple[str, ...] = ()) -> list[Path]:
    """Every file matching `glob` under every declared root — the union seam."""
    seen, out = set(), []
    for _root, files in walk(repo, profile, glob, exclude_suffixes):
        for path in files:
            if path not in seen:
                seen.add(path)
                out.append(path)
    return out


def root_of(repo: Path, profile: dict, rel: str) -> str | None:
    """Which declared root a repo-relative path belongs to, or None.

    None is a real answer and callers must say so rather than attributing the
    finding to the first root: a path outside every declared root is itself worth
    reporting.
    """
    rel = rel.lstrip("./")
    best = None
    for declared_rel in declared(profile):
        if rel == declared_rel or rel.startswith(declared_rel + "/"):
            # Longest match wins, so nested roots (a/b inside a) attribute to the
            # more specific one rather than to whichever was declared first.
            if best is None or len(declared_rel) > len(best):
                best = declared_rel
    return best
