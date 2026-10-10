"""Filename stem -> doc role, DERIVED from the role vocabulary rather than listed.

## Why this module exists

`bin/survey.py` carries a hand-maintained `ROLE_BY_STEM` table: a literal dict of
filename stems mapped to roles, written when the vocabulary was 20-odd roles and
never revisited. `templates/docs/roles.json` is the vocabulary of record, and it
kept growing. Measured read-only against a real design-system repository
(2026-09-15): 231 documents proposed no role at all, and **eight of those
top-level stems are literally role names** — `ADAPTIVE-PATTERNS`,
`COMMON-MISTAKES`, `DEPRECATIONS`, `FIGMA`, `GALLERY`, `PATTERNS`, `RELEASE`,
`THEMING`. Reproduced here as a set difference: the hand table reaches 18 roles,
`roles.json` declares 35, so **18 roles are unreachable from any stem**, and the
eight above are the subset a real repository happened to have files for.

The drift runs the other way too, and that half is worse: the hand table still
maps `instructions`, which stopped being a role when issue #95 renamed it to
`entry-point`. A hand copy does not just lag additions — it keeps proposing names
the vocabulary has retired.

This is the same shape as the audit registry that broke `capture-baselines.sh`
and the maturity registry that needed a parity gate: **a second copy of a list
that already exists.** So this module does not maintain a list. It derives one,
and the only hand-written entries left are the ones that are *not* derivable —
stems that are conventions rather than role names (`README`, `CLAUDE`, `ADR`).

A role added to `roles.json` is reachable by stem the same day, with no edit
here. That is the point: the drift cannot recur, rather than being caught later
by a gate.

## What it deliberately does not do

It does not guess. A stem that is neither a role name, an alias of one, nor a
listed convention returns `None`, exactly as the hand table did — a filename
regex scored 4 confident of 20 on a real zero-state repository, and proposing a
role for `NOTES.md` because it is a markdown file in `docs/` is the kind of
confident wrong answer the governing principle forbids.

Stdlib only.
"""
from __future__ import annotations

from . import archetypes

# Confidence for a stem that simply *is* a role name. Deliberately middling: the
# filename agreeing with the vocabulary is real evidence, and it is still only a
# filename.
DEFAULT_CONFIDENCE = 0.7

# Confidence for a stem that is a RETIRED role name reached through an alias.
# Below the canonical case on purpose — a project still using the old filename is
# more likely to be un-migrated than to be deliberate.
ALIAS_CONFIDENCE = 0.6

# Per-role confidence, where measurement disagreed with the default. These are
# the hand-tuned values from the table this module replaces, kept because they
# were measured rather than assumed; everything not listed takes the default.
#
# Only CONFIDENCE is overridden here, never the mapping itself. That distinction
# is what keeps this from quietly becoming the second copy again: if you find
# yourself wanting to add a role->stem pair to this dict, it belongs in
# roles.json (if it is a role) or in CONVENTIONAL_STEMS (if it is a convention).
CONFIDENCE = {
    "decisions": 0.8,
    "backlog": 0.8,
    "contributing": 0.9,   # CONTRIBUTING.md is a near-universal convention
    "components": 0.6,     # this role is external more often than not
    "tokens": 0.5,         # external more often than not
    "copy": 0.6,
    "api": 0.6,
    "responsive": 0.6,
    "documentation-rules": 0.6,
}

# Stems that are NOT role names and cannot be derived from anything. This is the
# irreducible hand-written part, and it is small by construction: every entry
# here is a filename convention that exists in the world independently of this
# vocabulary. An entry whose stem equals its role is a bug — it would shadow the
# derivation and reintroduce exactly the drift this module removes.
#
# stem -> (role, confidence, why)
CONVENTIONAL_STEMS = {
    "readme": ("entry-point", 0.5,
               "README.md is the conventional entry point, but many projects keep "
               "their agent instructions elsewhere"),
    "claude": ("entry-point", 0.8,
               "CLAUDE.md is the agent instruction file by convention"),
    "agents": ("entry-point", 0.6,
               "AGENTS.md is an emerging agent-instruction convention"),
    "adr": ("decisions", 0.5,
            "ADR is the conventional name for a decision record"),
    "documentation": ("documentation-rules", 0.6,
                      "DOCUMENTATION.md is the conventional filename for the "
                      "documentation-rules role"),
}


def _variants(role: str) -> list[str]:
    """Filename stems that spell one role name.

    A role is kebab-case (`brand-voice`); a real repository writes the file as
    `BRAND-VOICE.md`, `BRAND_VOICE.md` or `BRANDVOICE.md`. All three are the same
    claim about the same document, so all three are derived rather than being
    three hand-written rows that can each be forgotten separately — the previous
    table listed `brand-voice` and `brand_voice` and no others, for no stated
    reason.
    """
    return list(dict.fromkeys([role, role.replace("-", "_"), role.replace("-", "")]))


def stem_map() -> dict[str, tuple[str, float, str]]:
    """Every recognised stem -> (role, confidence, why). Lower-case keys."""
    out: dict[str, tuple[str, float, str]] = {}

    for role in sorted(archetypes.roles()):
        if role.startswith("_"):
            continue
        confidence = CONFIDENCE.get(role, DEFAULT_CONFIDENCE)
        why = f"filename matches the role name {role!r}"
        for stem in _variants(role):
            out[stem] = (role, confidence, why)

        # Retired names still resolve, at lower confidence. Derived from the
        # vocabulary's own alias table so a rename cannot orphan the old filename
        # — `resolve.py` already follows aliases in both directions, and a survey
        # that did not would propose "unmapped" for a document the resolver can
        # find.
        for old in archetypes.aliases_of(role):
            for stem in _variants(old):
                if stem in out:
                    continue
                out[stem] = (role, ALIAS_CONFIDENCE,
                             f"{old!r} is the former name of the role {role!r}")

    for stem, entry in CONVENTIONAL_STEMS.items():
        # Conventions win over derivation only where they do not collide: a stem
        # that is already a role name keeps its role. Asserting that here rather
        # than trusting the table means a future collision is a loud test failure
        # instead of a silently shadowed role.
        if stem in out:
            continue
        out[stem] = entry

    return out


def role_for_stem(stem: str) -> tuple[str, float, str] | None:
    """The proposal for one filename stem, or None.

    None is the honest answer and must stay one: a caller that got a guess back
    could not tell "this repository documents its decisions in DECISIONS.md" from
    "this is a markdown file and decisions is a role", and a survey that proposed
    roles for everything would be indistinguishable from a survey that proposed
    them correctly.
    """
    return stem_map().get(stem.strip().lower())


def unreachable_roles(hand_map: dict[str, tuple]) -> list[str]:
    """Roles in the vocabulary that a hand-written stem map cannot propose.

    Takes the map as an argument rather than importing one, so that this is a
    measurement any caller can run against any candidate table — including the
    derived one, where the answer is by construction empty.
    """
    reachable = {entry[0] for entry in hand_map.values()}
    return sorted(r for r in archetypes.roles() if not r.startswith("_")
                  and r not in reachable)


def retired_roles(hand_map: dict[str, tuple]) -> list[tuple[str, str]]:
    """(stem, role) pairs proposing a name the vocabulary no longer declares.

    The other direction of drift, and the one a coverage count hides: a stem map
    that proposes `instructions` makes a survey register a role `resolve.py`
    will refuse, which reads as a mapped document right up to the moment anything
    tries to use it.
    """
    known = {r for r in archetypes.roles() if not r.startswith("_")}
    return sorted((stem, entry[0]) for stem, entry in hand_map.items()
                  if entry[0] not in known)
