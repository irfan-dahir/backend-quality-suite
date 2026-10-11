"""Turn the compat report into a merge gate, with a way to say "yes, on purpose".

`upgrade.compare()` answers *what would change for a consumer*. This module
answers the next question, the one a pull request actually needs: **may this
merge?** Those are different questions, and conflating them is how a gate gets
deleted.

## Why an acknowledgement ratchet, and not a plain "fail on any change"

A gate that fails on every consumer-visible change makes a breaking change
unshippable. But this repo's own pinning contract (docs/ADOPTING.md,
docs/USER-GUIDE.md) says a minor version bump IS how a breaking change ships —
consumers pin to a tag precisely so that breaks arrive when they choose to
repin. So an un-escapable gate would contradict the contract it is meant to
protect, and the first time it was inconvenient somebody would delete it. A
deleted gate is worse than no gate, because its absence still reads as a pass.

So this is a ratchet, in the same shape `engine/ratchet.py` already uses for the
audit baselines, and for the same reason it gives there:

  * A known, written-down break passes and is **listed** — never silently
    absorbed. The listing is the whole point; a ratchet that stops printing what
    it is carrying is a baseline nobody reads.
  * A new critical break fails, and the failure prints the exact entry someone
    would have to write to accept it.
  * Accepting is a sentence a human wrote in a committed file, never a side
    effect of running the tool. `ratchet.py` learned this the expensive way:
    there, `--update-baseline` absorbed regressions it recommended absorbing. So
    there is deliberately **no `--acknowledge` flag here**. The only way to
    acknowledge is to edit the file, in the commit that causes the break, where
    a reviewer sees it in the diff next to the change it excuses.

## The acknowledgement must carry a migration path

An entry that says only "accepted" is a rubber stamp with extra steps, and a
rubber stamp is exactly the "audit that reports nothing" this repo is organised
against — it would make an acknowledged break and an examined break look
identical. So `migration` is mandatory and enforced **at load**, not at report
time: a file containing an entry without one is refused in its entirety (exit 2),
rather than that entry quietly failing to acknowledge anything. Refusing the
whole file is the fail-closed choice — a partially-loaded acknowledgement set
would grade a real break against an incomplete picture.

`consumerInvocation` is mandatory for the same reason at one remove: it is what
makes the blast radius nameable, so a reviewer can judge whether the
acknowledgement is proportionate instead of taking "intended" on faith.

## Identity of a finding

`(category, subject)`. Not the detail prose — that is rewritten whenever the
message improves, and matching on it would silently un-acknowledge every entry
the next time somebody fixed a typo. Not the severity either: a finding whose
severity is re-graded is the same break, and an acknowledgement should survive
the re-grading rather than evaporating exactly when the break got more serious.

## What fails, and what only gets listed

Unacknowledged **critical** findings fail. Unacknowledged should-fix findings are
reported and do not fail: they are the "check whether this still does what it
did" class, they are numerous, and grading them as blockers would train a
reviewer to acknowledge in bulk — which is how the critical list stops being
read. They are printed under their own heading, every time, so they are visible
rather than dropped.

A **stale** acknowledgement — an entry matching no current finding — is reported
and does not fail. It usually means the break was fixed or the release shipped,
and failing the merge for tidying up would be a gate that punishes the good
outcome. It is named so the file gets cleaned rather than growing forever.

Stdlib only, like everything else here.
"""
from __future__ import annotations

import json
from pathlib import Path

from .upgrade import CRITICAL, SHOULD_FIX, CannotDetermine, _git, compare

# Every field an entry must carry to acknowledge anything. `migration` and
# `consumerInvocation` are in this list on purpose — see the module docstring.
REQUIRED_FIELDS = ("id", "category", "subject", "break", "consumerInvocation",
                   "migration")

# The default spelling of this repository's release tags. A parameter with a
# default rather than a constant used directly, so the tag scheme is one string
# in one place and a caller can ask about a different one.
DEFAULT_TAG_MATCH = "backend-suite--v*"


def ack_key(record: dict) -> tuple[str, str]:
    """The identity of a finding or an acknowledgement — see the docstring."""
    return (record.get("category", ""), record.get("subject", ""))


# ------------------------------------------------------------------ the ack file


def load_acks(path: Path) -> list[dict]:
    """The acknowledgement entries, or `CannotDetermine`.

    A missing file is an empty list and NOT a refusal: a repository that has
    acknowledged nothing yet is a real and common state, and refusing on it would
    make the gate unrunnable until somebody created an empty file. Every other
    failure to read it *is* a refusal, because a malformed acknowledgement set
    and an empty one must not produce the same verdict.
    """
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise CannotDetermine(
            f"cannot read the acknowledgement file {path}: {exc}. An unreadable "
            f"acknowledgement set is not an empty one — refusing rather than "
            f"grading this merge against acknowledgements nobody can see"
        ) from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise CannotDetermine(
            f"{path}: expected an object with an `entries` array "
            f"(see templates/consumer-compat-acks.schema.json)"
        )

    entries: list[dict] = []
    problems: list[str] = []
    seen: dict[tuple[str, str], str] = {}
    for index, entry in enumerate(raw["entries"]):
        where = f"entries[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where}: not an object")
            continue
        label = entry.get("id") or where
        missing = [f for f in REQUIRED_FIELDS
                   if not str(entry.get(f, "") or "").strip()]
        if missing:
            problems.append(
                f"{label}: missing or empty {', '.join(missing)}"
                + (". An acknowledgement with no migration path is a rubber "
                   "stamp — say what a consumer must actually do to cross this "
                   "break." if "migration" in missing else "")
            )
            continue
        key = ack_key(entry)
        if key in seen:
            problems.append(
                f"{label}: acknowledges {key[0]} {key[1]!r}, which {seen[key]} "
                f"already acknowledges. Two entries for one break means one of "
                f"the two migration notes is never read"
            )
            continue
        seen[key] = label
        entries.append(entry)

    if problems:
        raise CannotDetermine(
            f"{path} is not a usable acknowledgement set:\n  "
            + "\n  ".join(problems)
            + "\n\nRefusing the whole file rather than the bad entries: grading "
              "a merge against a partially-loaded acknowledgement set would "
              "measure a real break against an incomplete picture."
        )
    return entries


# ----------------------------------------------------------------- the baseline


def latest_release_tag(repo: Path, match: str = DEFAULT_TAG_MATCH) -> str:
    """The most recent release tag reachable from HEAD, or `CannotDetermine`.

    This is the comparison's `--from`, and the choice is deliberate: consumers
    pin to a release tag, so "does this PR break anyone" means "does it break
    anyone sitting on the newest tag". Comparing against the merge-base with
    `main` would answer a different and less useful question — whether this
    branch alone introduced the break — and would let a break merge unflagged
    simply because an earlier merge on main already carried it.

    **No tag is a refusal, never a pass.** A gate that could not find its
    baseline and therefore reported "compatible" is this repository's governing
    failure mode wearing a suit.
    """
    proc = _git(repo, "describe", "--tags", "--abbrev=0", "--match", match)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise CannotDetermine(
            f"no tag matching {match!r} is reachable from HEAD in {repo} "
            f"({proc.stderr.strip() or 'no output'}). The comparison baseline is "
            f"the release consumers are pinned to, so without a release tag "
            f"there is nothing to compare against and no consumer this gate can "
            f"speak for. This is exit 2 — cannot determine — and it is "
            f"deliberately not exit 0: a gate that passes because it could not "
            f"find its baseline is indistinguishable from a gate that passed."
        )
    return proc.stdout.strip()


# --------------------------------------------------------------------- the gate


def evaluate(repo: Path, acks: list[dict], *, old_rev: str | None = None,
             new_rev: str = "HEAD", tag_match: str = DEFAULT_TAG_MATCH) -> dict:
    """The full gate report. Raises `CannotDetermine` rather than passing blind."""
    baseline = old_rev or latest_release_tag(repo, tag_match)
    report = compare(repo, baseline, new_rev)

    by_key = {ack_key(a): a for a in acks}
    matched: set[tuple[str, str]] = set()

    acknowledged: list[dict] = []
    blocking: list[dict] = []
    advisory: list[dict] = []
    for finding in report["findings"]:
        key = ack_key(finding)
        ack = by_key.get(key)
        if ack is not None:
            matched.add(key)
            acknowledged.append({"finding": finding, "ack": ack})
        elif finding["severity"] == CRITICAL:
            blocking.append(finding)
        else:
            advisory.append(finding)

    stale = [a for a in acks if ack_key(a) not in matched]

    return {
        "baseline": {"rev": baseline, "sha": report["old"]["sha"],
                     "derivedFrom": "release tag" if old_rev is None else "caller"},
        "head": {"rev": new_rev, "sha": report["new"]["sha"]},
        "counts": {
            "blocking": len(blocking),
            "acknowledged": len(acknowledged),
            "advisory": len(advisory),
            "stale": len(stale),
            CRITICAL: report["counts"][CRITICAL],
            SHOULD_FIX: report["counts"][SHOULD_FIX],
        },
        "blocking": blocking,
        "acknowledged": acknowledged,
        "advisory": advisory,
        "stale": stale,
        "notes": report["old"]["notes"] + report["new"]["notes"],
    }


def suggested_entry(finding: dict) -> dict:
    """The skeleton an author would fill in to acknowledge one finding.

    Printed with every blocking finding so that acknowledging is a copy-paste of
    a form with holes in it, rather than a schema lookup. The holes are the
    point: the placeholders say what must be written, and an entry left with them
    in place still fails review, but it fails as a visible blank rather than as
    an absence nobody notices.
    """
    slug = "".join(c if c.isalnum() else "-"
                   for c in f"{Path(finding['subject']).name}-{finding['category']}"
                   .lower())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return {
        "id": slug.strip("-"),
        "category": finding["category"],
        "subject": finding["subject"],
        "break": "WHAT CHANGES, in a consumer's terms — not 'exit code changed'",
        "consumerInvocation": "WHICH CI step, hook-map entry or runbook line "
                              "this affects",
        "migration": "WHAT A CONSUMER MUST DO to cross it — the command, flag, "
                     "config key or re-baseline. Mandatory.",
    }
