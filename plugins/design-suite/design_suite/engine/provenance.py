"""Per-field provenance: the vocabulary, and the one transition that writes it.

RFC-0002 §3b gives three stored states — `inferred` (a survey or a skill
proposed it), `declared` (a human wrote it), `approved` (a human reviewed an
inferred value and ratified it) — plus a fourth, `contradicted`, which is
COMPUTED by `doctor.py` and never stored.

`doctor.py` shipped the whole reading half: it refuses to trust `inferred`,
derives `contradicted`, and prints the ratified-of-total count even when it is
zero. Nothing shipped the *writing* half. The only way to move a field from
`inferred` to `approved` was to hand-edit `profile.json`, which is the same gap
`decline_doc.py` was written to close for declined roles: a state with consumers
and no producer is a contract that holds until someone is in a hurry.

This module is the transition, kept in the engine for two reasons. It is where
the refusals live — and ratification is mostly refusals, because a ratification
that silently no-ops is precisely the failure the governing principle forbids:
"nobody ratified anything" and "everything was already ratified" must never
print the same thing. And it lets `doctor.py` and `bin/ratify.py` share one
copy of the vocabulary rather than two that drift.

Nothing here is project-specific or language-specific. It reads a profile dict
and returns a profile dict; the caller owns argv, the filesystem and git.
"""
from __future__ import annotations

import datetime as _dt
import re
import subprocess
from pathlib import Path

# The three states a human or a machine may WRITE.
STATES = ("inferred", "declared", "approved")
# The two that assert a human decided, and so can be contradicted by the tree.
TRUSTED_STATES = ("declared", "approved")
# Never stored. `contradicted` is what a trusted field BECOMES when the tree
# stops agreeing with it; storing it would let a stale fact be re-asserted by
# hand, and would make "nobody re-checked this" and "this was checked and found
# false" the same edit (RFC-0002 §3h).
COMPUTED_STATES = ("contradicted",)

ABSOLUTE = re.compile(r"^(/|~|[A-Za-z]:|\.\./)")
# Keys whose values are paths. Globs are validated by shape, not existence.
PATH_KEYS = {
    "root", "path", "sharedComponentDir", "testRoot", "configFile",
    "exceptionsFile", "archRulesFile", "baselineDir", "manifest", "resolveVia",
    "goldensDir",
}


class RatificationRefused(Exception):
    """A ratification that would record nothing true, with the reason why.

    `exit_code` follows the suite's contract: 1 for a refusal the caller can fix
    by passing different arguments, 2 for a CapabilityError — the tool cannot
    answer the question at all, and must say so rather than write a weaker record.
    """

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# --------------------------------------------------------------------------- #
# Reading a profile
# --------------------------------------------------------------------------- #

class _Missing:
    def __repr__(self) -> str:
        return "<absent>"


MISSING = _Missing()


def profile_leaves(profile: dict) -> list[str]:
    """Every dotted leaf path in a profile — the denominator provenance is scored against.

    A list is one leaf, not one per element: `source.otherSharedDirs` is a single
    decision about which directories are shared, and scoring it per element would
    inflate the ratified-of-total count with the same decision counted five times.
    """
    out: list[str] = []

    def rec(node, trail: str) -> None:
        if isinstance(node, dict) and node:
            for key, value in node.items():
                if key.startswith("_") or key == "$schema":
                    continue
                rec(value, f"{trail}.{key}" if trail else key)
        elif trail:
            out.append(trail)

    for key, value in profile.items():
        # The provenance block describes the other fields; it is not itself a
        # field with a provenance, and counting it would be circular.
        if key.startswith("_") or key in ("$schema", "provenance"):
            continue
        rec(value, key)
    return sorted(out)


def lookup(profile: dict, dotted: str):
    """The live value at a dotted path, or `MISSING`."""
    node = profile
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    return node


def looks_like_path(dotted: str, value) -> bool:
    """Whether a value can honestly be tested against disk.

    Deliberately narrow. `project.framework` is free text that may well contain a
    slash, and reporting it as a missing path would be a false contradiction —
    worse than a missed one, because it teaches a reader to ignore the check.
    Only keys the profile already treats as paths qualify, and globs are
    excluded: a glob's non-existence as a literal path says nothing.
    """
    if not isinstance(value, str):
        return False
    key = dotted.rsplit(".", 1)[-1]
    if key not in PATH_KEYS and key != "otherSharedDirs":
        return False
    return not any(c in value for c in "*?[") and not ABSOLUTE.match(value)


def entries(profile: dict) -> dict:
    """The provenance entries, or an empty dict. Never None, never invented."""
    block = profile.get("provenance") or {}
    return block.get("fields") or {}


def awaiting_ratification(profile: dict) -> tuple[list[str], list[str]]:
    """(inferred, unattributed) — the two kinds of field nothing may trust yet.

    Kept separate because they need different acts. An `inferred` field has a
    proposal to review, so it can be *approved*; an unattributed one has no
    proposal at all, so the honest record is *declared* — a human saying "I wrote
    this", not a human saying "I checked the machine's guess".
    """
    recorded = entries(profile)
    inferred = sorted(d for d, e in recorded.items()
                      if not d.startswith("_")
                      and isinstance(e, dict) and e.get("state") == "inferred")
    unattributed = sorted(set(profile_leaves(profile)) - set(recorded))
    return inferred, unattributed


# --------------------------------------------------------------------------- #
# The tree a ratification is stamped against
# --------------------------------------------------------------------------- #

def head_stamp(repo: Path) -> tuple[str | None, bool]:
    """(HEAD sha, working-tree-is-dirty), or (None, False) when git cannot say.

    Staleness is measured in diffs, not days (§3h rejects a calendar TTL on
    approvals outright), so a ratification with no commit to point at is not a
    weaker ratification — it is one whose staleness can never be computed.
    Callers refuse rather than write it.
    """
    try:
        rev = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None, False
    if rev.returncode != 0 or not rev.stdout.strip():
        return None, False
    sha = rev.stdout.strip()
    try:
        status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                capture_output=True, text=True, timeout=30)
        dirty = bool(status.returncode == 0 and status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        dirty = False
    return sha, dirty


# --------------------------------------------------------------------------- #
# The transition
# --------------------------------------------------------------------------- #

def ratify(profile: dict, dotted: str, *, state: str, by: str, repo: Path,
           commit: str | None, dirty: bool = False, evidence: str | None = None,
           on: str | None = None, force: bool = False) -> tuple[dict, str]:
    """Record that a human decided `dotted`. Returns (entry, one-line summary).

    Mutates `profile` in place. Raises `RatificationRefused` rather than writing
    a record that would be untrue, unverifiable, or a no-op. Every refusal here
    is a case where writing the entry would leave the profile looking more
    reviewed than it is, which is the only thing this whole mechanism exists to
    prevent.
    """
    if state not in TRUSTED_STATES:
        raise RatificationRefused(
            f"{state!r} is not something a human can ratify TO. Ratification ends at "
            f"{list(TRUSTED_STATES)}; 'inferred' is what a machine writes, and "
            f"'contradicted' is COMPUTED by doctor, never stored")

    by = (by or "").strip()
    if not by:
        raise RatificationRefused(
            "refusing to record an unattributed ratification — an approval nobody "
            "signed cannot be re-examined, and reads downstream exactly like one "
            "that was reviewed by a person who could be asked")

    if commit is None:
        raise RatificationRefused(
            "cannot read HEAD here, so this ratification could not be stamped with the "
            "tree it was made against. §3h measures staleness in diffs, not days: an "
            "unstamped approval is one whose staleness can never be computed, and doctor "
            "would report it as untrusted the moment it was written. Refusing rather "
            "than writing a record that looks like an approval and is not.", exit_code=2)

    live = lookup(profile, dotted)
    if live is MISSING:
        known = profile_leaves(profile)
        near = [leaf for leaf in known if leaf.endswith(dotted.rsplit(".", 1)[-1])]
        raise RatificationRefused(
            f"{dotted}: no such field in this profile. Ratifying a field nobody has is a "
            f"ratification of nothing"
            + (f" — did you mean {near[0]!r}?" if near else
               f" ({len(known)} field(s) exist; run --list to see what is outstanding)"))

    recorded = entries(profile)
    existing = recorded.get(dotted)
    existing = existing if isinstance(existing, dict) else None
    prior = existing.get("state") if existing else None

    if state == "approved" and existing is None:
        raise RatificationRefused(
            f"{dotted}: nothing has proposed a value for this field, so there is no "
            f"proposal to approve. 'approved' means a human reviewed an INFERRED value; "
            f"a value a human simply wrote is 'declared'. Re-run with --declare if you "
            f"are asserting this yourself.")

    # Checked before the re-approval refusal below, so an exact repeat is named as
    # the no-op it is rather than as a generic "already approved". The two are
    # different facts: one says the tree and the ratifier are unchanged, the other
    # says a DIFFERENT person or tree is being recorded over an existing decision.
    if _unchanged(existing, state, by, live, commit):
        raise RatificationRefused(
            f"{dotted}: this changes nothing — already {state} by {by} against this exact "
            f"tree. Refusing rather than reporting a successful ratification that ratified "
            f"nothing.")

    if state == "approved" and prior in TRUSTED_STATES and not force:
        raise RatificationRefused(
            f"{dotted}: already {prior}{_by(existing)} — approving it again would record "
            f"a review of a proposal that no longer exists, and this command would print "
            f"success for a change it did not make. Pass --force to re-stamp it against "
            f"the current tree (which is the honest act after the value or the tree moved).")

    if state == "declared" and prior == "inferred" and not force:
        raise RatificationRefused(
            f"{dotted}: a machine proposed this value{_why(existing)}. Recording it as "
            f"'declared' would erase that it was ever inferred and claim a human authored "
            f"it. Approve it instead, or pass --force if you are genuinely replacing the "
            f"machine's proposal with your own authorship.")

    if looks_like_path(dotted, live) and not (repo / live).exists():
        raise RatificationRefused(
            f"{dotted}: {live!r} does not exist. Ratifying it would write a human "
            f"assertion that doctor reports as CONTRADICTED on its very next run — a "
            f"false assertion is worse than an unreviewed one, because it stops being "
            f"reported as outstanding work. Fix the path first.")

    entry: dict = {"state": state, "by": by,
                   "on": on or _dt.date.today().isoformat(), "value": live}
    # Carry the machine's argument forward unless the caller replaces it: what a
    # proposal argued is the record of what was actually reviewed, and dropping it
    # on approval would discard the only evidence the approval was informed.
    kept = evidence or (existing or {}).get("evidence")
    if kept:
        entry["evidence"] = kept
    stamp: dict = {"commit": commit}
    if dirty:
        stamp["dirty"] = True
    entry["verifiedAgainst"] = stamp

    block = profile.setdefault("provenance", {})
    fields = block.setdefault("fields", {})
    fields[dotted] = entry

    became = f"{prior} → {state}" if prior else state
    return entry, (f"{dotted}: {became}, by {by}, against {commit[:12]}"
                   + (" (dirty working tree)" if dirty else ""))


def _unchanged(existing: dict | None, state: str, by: str, live,
               commit: str) -> bool:
    if not existing:
        return False
    stamp = existing.get("verifiedAgainst") or {}
    return (existing.get("state") == state and existing.get("by") == by
            and existing.get("value", MISSING) == live
            and stamp.get("commit") == commit)


def _by(entry: dict | None) -> str:
    who = (entry or {}).get("by")
    return f" by {who}" if who else ""


def _why(entry: dict | None) -> str:
    evidence = (entry or {}).get("evidence")
    return f" ({evidence})" if evidence else ""
