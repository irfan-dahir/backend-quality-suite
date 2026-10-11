"""Doc-role states that are neither "here" nor "unmapped": declined, and stub.

Both exist because the manifest could previously express only two answers about a
role — a path, or nothing — and three distinct situations were collapsing into
them:

  * a role the team **deliberately declined**, with a reason, was indistinguishable
    from a role nobody has looked at yet;
  * a registered-but-**unwritten** document resolved to a path and exit 0, so a
    scaffolded stub read as coverage the project does not have.

Both are the suite's governing failure wearing different hats: silence that reads
as a pass. They live here rather than in `bin/resolve.py` because `doctor.py` and
`quality_debt.py` must agree with the resolver about what counts as coverage — a
second copy of this rule would be a second copy to drift.

Stdlib only.
"""
from __future__ import annotations

from pathlib import Path

DECLINED_KEY = "declinedRoles"
STUB_STATUS = "stub"

# How many lines of a document to look at before giving up on finding frontmatter.
# A `status:` key 200 lines down is prose about status, not the document's own.
_FRONTMATTER_MAX_LINES = 200


def declined_roles(manifest: dict) -> dict[str, dict]:
    """Declined entries, with `_comment`-style keys dropped.

    Same underscore convention as `externalRoles`, which this is modelled on
    rather than invented alongside.
    """
    raw = manifest.get(DECLINED_KEY) or {}
    return {k: v for k, v in raw.items()
            if not k.startswith("_") and isinstance(v, dict)}


def decline_reason(entry: dict) -> str:
    """The recorded reason, or "" when the entry has none.

    Returning "" rather than a stand-in sentence is deliberate: a decline with no
    reason is exactly the silence the state exists to prevent, and callers must be
    able to tell that case apart and report it.
    """
    reason = entry.get("declined")
    return reason.strip() if isinstance(reason, str) else ""


def decline_summary(role: str, entry: dict) -> str:
    """One line naming the decline, its reason, and its provenance.

    Skills print this into their reports: a check that vanishes silently because a
    role was declined is the failure mode; a check that says which role it skipped,
    why, and who decided is a record.
    """
    reason = decline_reason(entry) or "NO REASON RECORDED"
    who, when = entry.get("by"), entry.get("on")
    stamp = " ".join(p for p in (f"— {who}" if who else "", f"({when})" if when else "") if p)
    return f"role {role!r} declined: {reason}{(' ' + stamp) if stamp else ''}"


def frontmatter_status(path: Path) -> str | None:
    """The `status:` value from a document's leading `---` frontmatter block.

    Hand-parsed rather than via a YAML library because these tools take no
    dependencies, and because the only shape that matters is a top-level scalar at
    the head of the file.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            first = handle.readline()
            if first.strip() != "---":
                return None
            for _ in range(_FRONTMATTER_MAX_LINES):
                line = handle.readline()
                if not line or line.strip() in ("---", "..."):
                    return None
                key, sep, value = line.partition(":")
                if sep and key.strip() == "status":
                    return value.strip().strip("\"'").lower() or None
    except OSError:
        return None
    return None


def is_stub(path: Path) -> bool:
    """A document that exists and is registered, but is declared unwritten."""
    return path.is_file() and frontmatter_status(path) == STUB_STATUS


def stub_frontmatter() -> str:
    """The block a scaffolder prepends, ending in a newline.

    It is emitted at scaffold time rather than shipped inside the templates: a
    template is not a document, and a template carrying `status: stub` would make
    every reader of the plugin tree — and any check that walks it — see stubs
    that nobody scaffolded.

    The comment lines are load-bearing rather than decorative. The only way this
    status is cleared is a human deleting the block, so the block has to say that
    where that human is already looking; a bare `status: stub` would leave the
    person filling the document guessing whether it is theirs to remove.
    """
    return (
        "---\n"
        f"status: {STUB_STATUS}\n"
        "# Scaffolded from a template, not yet written. Delete this whole\n"
        "# frontmatter block once you have authored the document. Until then it\n"
        "# resolves with exit 5 and counts as design debt, never as coverage.\n"
        "---\n"
    )


def stub_roles(repo: Path, manifest: dict) -> list[str]:
    """Every mapped role whose document is still a stub, sorted.

    Directory-valued roles are skipped by the `isinstance(rel, str)` guard rather
    than by accident: "is this one document unwritten" is not the question to ask
    of a directory, and `directory_state` answers the directory version of it.
    """
    return sorted(role for role, rel in (manifest.get("roles") or {}).items()
                  if isinstance(rel, str) and is_stub(repo / rel))


# ---------------------------------------------------------------------------
# Directory-valued roles
# ---------------------------------------------------------------------------
#
# WHY A ROLE MAY POINT AT A DIRECTORY.
# ------------------------------------
# `components` maps to one file, which is right for a project whose components
# are described in a single document and wrong for a design system with one
# markdown file per component — roughly 130 of them in the repository this was
# measured against. PR #111 already gave `components` a `pageTemplate`, an index
# plus one page per component: that is the WRITE side. Nothing on the READ side
# could express the result, so a project that took the scaffolding had no way to
# map the role to what the scaffolding produced.
#
# A directory role is declared as an object instead of a string:
#
#     "roles": {"components": {"directory": "docs/components"}}
#
# Object rather than a trailing slash on the string, because a caller has to be
# able to tell the two apart BEFORE touching the disk. A string ending in `/`
# would make the manifest's meaning depend on a typo.
#
# THE FOUR STATES, AND WHY THEY GET FOUR CODES.
# ---------------------------------------------
# "The directory resolved" is not one answer. Collapsing these would be the
# suite's governing failure with a new hat on: an empty directory reported as
# coverage is a check that looked at nothing and said nothing.
#
#   populated  -> 0  at least one authored member. Real coverage.
#   stubs only -> 5  members exist, every one is `status: stub`. Exactly what 5
#                    already means for a single document — registered, unwritten,
#                    outstanding work, never coverage.
#   empty      -> 2  the directory is there and holds no members. "I could not
#                    look": there is nothing to read, and a caller that globbed
#                    it would get an empty list and grade the category clean.
#                    This is the state the whole design is here to refuse.
#   absent     -> 1  mapped, and does not exist. Exactly what 1 already means.
#
# Absent is reported WITHOUT `--check`, unlike a file role. For a file, printing
# the path unchecked is useful: the caller often intends to create it. For a
# directory the caller's next move is to enumerate members, and enumerating a
# directory that is not there returns an empty list with no error — indistinguish-
# able from a documented-and-empty one. So the directory branch always checks.

DIR_KEY = "directory"

# What counts as a member. Markdown only: a directory role names a set of
# DOCUMENTS, and counting a stray image or a generated index JSON as coverage
# would be the empty-directory bug wearing a file extension.
MEMBER_GLOB = "*.md"

POPULATED, STUBS_ONLY, EMPTY, ABSENT = "populated", "stubs-only", "empty", "absent"

# state -> exit code. A table rather than an if-chain so that the contract in
# docs/DOC-ROLES.md and the code can be read against each other in one glance.
DIR_EXIT = {POPULATED: 0, STUBS_ONLY: 5, EMPTY: 2, ABSENT: 1}


def is_directory_role(value) -> bool:
    """Whether a manifest role value declares a directory rather than a file."""
    return isinstance(value, dict) and isinstance(value.get(DIR_KEY), str)


def directory_of(value) -> str:
    """The declared relative directory. Caller must have checked the shape."""
    return value[DIR_KEY]


def directory_members(path: Path) -> list[Path]:
    """Every markdown document under a directory role, sorted, recursively.

    Recursive because a design system that groups its component pages into
    subdirectories has not stopped documenting them; a non-recursive glob would
    report such a project as empty, which is the one answer this must never give
    wrongly.
    """
    if not path.is_dir():
        return []
    return sorted(p for p in path.rglob(MEMBER_GLOB) if p.is_file())


def directory_state(path: Path) -> tuple[str, list[Path], list[Path]]:
    """(state, all members, authored members) for a directory role's path."""
    if not path.is_dir():
        return ABSENT, [], []
    members = directory_members(path)
    if not members:
        return EMPTY, [], []
    authored = [m for m in members if not is_stub(m)]
    return (POPULATED if authored else STUBS_ONLY), members, authored


def directory_summary(role: str, rel: str, state: str,
                      members: list[Path], authored: list[Path]) -> str:
    """One line a skill can paste into a report, naming the state by name.

    Every branch names the role, the path and the state. A report that says only
    "components: 0 findings" is the output this module exists to make impossible.
    """
    if state == ABSENT:
        return (f"role {role!r} maps to the directory {rel}, which does not exist. "
                f"Outstanding work — never report the category as covered")
    if state == EMPTY:
        return (f"role {role!r} maps to the directory {rel}, which exists and "
                f"contains no {MEMBER_GLOB} document. I could not look: there is "
                f"nothing here to read. Do not grade this category")
    if state == STUBS_ONLY:
        return (f"role {role!r} maps to the directory {rel}: {len(members)} "
                f"document(s), every one of them a stub. Registered but unwritten "
                f"— outstanding work, never coverage")
    return (f"role {role!r} maps to the directory {rel}: {len(authored)} authored "
            f"of {len(members)} document(s)")
