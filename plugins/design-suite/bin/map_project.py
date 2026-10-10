#!/usr/bin/env python3
"""Write `/map-project`'s proposals into the profile as `inferred`, and nothing else.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/map_project.py" --field docs.roles.design \
        --value docs/DESIGN.md --evidence "Four candidates; this is the only file the
        other three cite for the token tables, and it carries the screen inventory."
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/map_project.py" --proposals proposals.json
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/map_project.py" --list
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/map_project.py" --field X --value Y \
        --evidence "..." --dry-run

Exit 0 every proposal landed. 1 findings. 2 refused — including every
cannot-determine, which must never collapse to 0. 3 the answer lives in another
repository. 4 the role is declined. 5 the role is a registered stub.

## Why this is a script and not a paragraph

`/map-project`'s frontmatter claims that every value it proposes "**is written**
with provenance `inferred` and nothing else, so no downstream check trusts it
until a human ratifies". `doctor.py` reports mapped values as UNTRUSTED on the
assumption those entries are on disk, and `/ratify` exists to promote them. The
first eval suite run against the skill measured the claim and found the whole
chain starts from nothing: all eight file-based graders failed with
`.design-suite/profile.json` *does not exist*, with Write, Edit and Bash all
granted. The skill fired, argued well in conversation, and wrote nothing,
because the write was instructed in markdown and markdown was the entire
mechanism.

Prose could not hold the rule, so the rule moves here. This module is the
counterpart to `design_suite.engine.provenance.ratify()` — that one performs the
`inferred` → `declared`/`approved` transition a human makes, this one performs
the only transition a machine may make, and they share the vocabulary and the
profile-leaf handling rather than keeping two copies that drift.

## What is mechanical here, rather than instructed

  * **The entry is built from a whitelist, not filtered.** It is literally
    `{"state": "inferred", "evidence": ...}` and the serialised profile is
    re-scanned for the forbidden keys before the file is written. A proposal that
    arrives carrying `state`, `by`, `on` or `verifiedAgainst` is refused rather
    than cleaned up, because silently dropping a key teaches a caller the key was
    accepted.
  * **`value` never reaches the provenance entry.** The proposal's value is
    written to the profile *leaf* — that is the mapping. `value` inside the entry
    is the human's alone: `doctor.py` uses it to compute CONTRADICTED when a
    ratified value is edited afterwards, and pre-filling it from a guess would let
    the guess masquerade as a ratification that has drifted.
  * **Evidence is required and must be an argument.** The skill's own body says
    an entry whose evidence reads "filename matches" proposed nothing a script
    could not have, and should usually have been a refusal instead — so that is a
    refusal here.
  * **An already-ratified field is never overwritten.** Exit 2, nothing written.
  * **Tied candidates are a refusal, not a coin toss.** Naming two candidates
    exits 2. "A plausible default is worse than a gap, because a gap is visible
    and a plausible default reads as a decision."
  * **The write is all-or-nothing.** One refused proposal writes none of them, so
    a partially-applied mapping can never be mistaken for a complete one.

Stdlib only. No project literals: every field is a dotted path the caller names,
and the profile is the only thing that says what fields exist.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _bootstrap import PLUGIN_ROOT, project_root  # noqa: E402

from design_suite.engine import provenance  # noqa: E402

DEFAULT_PROFILE = ".design-suite/profile.json"

#: The one state this tool may ever write. Not a default — a constant.
PROPOSED_STATE = "inferred"

#: Exactly the keys a proposal's provenance entry is allowed to carry.
ALLOWED_ENTRY_KEYS = frozenset({"state", "evidence"})

#: Keys that assert a human decided, and so are never a proposal's to write.
#: `value` is included: it is what lets doctor compute CONTRADICTED later.
FORBIDDEN_ENTRY_KEYS = ("state", "by", "on", "verifiedAgainst", "value")

#: Evidence that is bare filename matching — the skill's own named anti-pattern.
BARE_EVIDENCE = re.compile(
    r"^(the\s+)?(file)?name(\s+(of\s+the\s+file\s+)?match(es|ed|ing)?)?\.?$"
    r"|^filename\s*match\w*\.?$"
    r"|^match(es)?\s+(the\s+)?(file)?name\.?$"
    r"|^(the\s+)?(file)?name\s+(alone|only)\.?$",
    re.IGNORECASE,
)

#: Short enough that it cannot be an argument from a document's contents.
MIN_EVIDENCE_CHARS = 40


class Refused(Exception):
    """A proposal that would leave the profile looking more decided than it is."""

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# --------------------------------------------------------------------------- #
# Reading and shaping proposals
# --------------------------------------------------------------------------- #

def parse_proposal(raw: object, where: str) -> dict:
    """One proposal dict, validated for shape only. Raises `Refused`.

    Shape errors are refusals rather than argparse errors because a malformed
    proposal is indistinguishable, from the outside, from one that was simply not
    made — and the whole point of this file is that those two must never read the
    same.
    """
    if not isinstance(raw, dict):
        raise Refused(f"{where}: a proposal must be an object, got "
                      f"{type(raw).__name__}")

    present = [key for key in FORBIDDEN_ENTRY_KEYS if key in raw]
    # `value` names the profile leaf's value here, which is legitimate — it is
    # only forbidden on the provenance ENTRY, and this function never builds one.
    present = [key for key in present if key != "value"]
    if present:
        raise Refused(
            f"{where}: a proposal may not carry {present!r}. Those belong to "
            f"ratification: `by` attributes a decision this did not make, `on` dates "
            f"one that has not happened, `verifiedAgainst` is the stamp a "
            f"ratification leaves, and `state` is not the caller's to choose — every "
            f"value written here is {PROPOSED_STATE!r} and only {PROPOSED_STATE!r}. "
            f"Refusing rather than dropping them, because a key silently ignored "
            f"reads to the caller like a key accepted.")

    field = (raw.get("field") or "").strip()
    if not field:
        raise Refused(f"{where}: a proposal must name a field, as a dotted profile "
                      f"path such as 'source.root' or 'docs.roles.design'")
    if "value" not in raw:
        raise Refused(f"{field}: no value proposed. A provenance entry describing a "
                      f"field that has no value is a record of nothing")

    candidates = raw.get("candidates")
    if candidates is not None and not isinstance(candidates, list):
        raise Refused(f"{field}: 'candidates' must be a list of the values that were "
                      f"genuinely in contention")

    return {"field": field, "value": raw["value"],
            "evidence": raw.get("evidence"), "candidates": candidates or []}


def check_evidence(field: str, evidence: object) -> str:
    """The evidence string, or `Refused`. The argument IS the deliverable.

    Evidence is what a human actually reads when ratifying, so an entry without
    one is an entry nobody can review — it would arrive at `/ratify` as a bare
    assertion wearing a provenance record's clothes.
    """
    if not isinstance(evidence, str) or not evidence.strip():
        raise Refused(
            f"{field}: no evidence. The evidence string is the whole deliverable of a "
            f"proposal — it is what a human reads when deciding whether to ratify, and "
            f"a mapping with no argument behind it is a guess this tool will not record.")

    text = " ".join(evidence.split())
    if BARE_EVIDENCE.match(text):
        raise Refused(
            f"{field}: evidence {text!r} is bare filename matching. An entry whose "
            f"evidence reads 'filename matches' has proposed nothing a script could not "
            f"have proposed, and should usually have been a refusal instead. Argue from "
            f"what the document contains — what it is the source of truth for, what "
            f"cites it, its structure — or refuse the field.")
    if len(text) < MIN_EVIDENCE_CHARS:
        raise Refused(
            f"{field}: evidence is {len(text)} characters, under the {MIN_EVIDENCE_CHARS} "
            f"it takes to be an argument rather than a label. Say what in the document "
            f"settled it, and what the rejected candidates were.")
    # A guard against the vocabulary leaking into prose: these two words mean a
    # human decided, and a profile containing them anywhere reads as reviewed.
    for word in ("approved", "declared"):
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            raise Refused(
                f"{field}: evidence uses the word {word!r}. That word means a human "
                f"decided, and nothing this tool writes may claim or resemble one. "
                f"Describe the evidence without it.")
    return text


# --------------------------------------------------------------------------- #
# The refusals that depend on the profile
# --------------------------------------------------------------------------- #

def check_not_ratified(profile: dict, field: str) -> None:
    """Never overwrite a human's decision. Exit 2, not a clobber."""
    entry = provenance.entries(profile).get(field)
    if not isinstance(entry, dict):
        return
    state = entry.get("state")
    if state in provenance.TRUSTED_STATES:
        who = entry.get("by")
        raise Refused(
            f"{field}: a human already ratified this"
            + (f" ({who})" if who else "") +
            f", and a machine's inference may not replace it. Refusing rather than "
            f"downgrading a recorded human decision to a guess. Report the "
            f"disagreement and your evidence; the human re-ratifies if they agree.")


def check_not_tied(field: str, candidates: list) -> None:
    """Two candidates equal on evidence is a refusal, not a pick."""
    distinct = []
    for candidate in candidates:
        if candidate not in distinct:
            distinct.append(candidate)
    if len(distinct) > 1:
        raise Refused(
            f"{field}: {len(distinct)} candidates are still in contention "
            f"({', '.join(repr(c) for c in distinct)}) and nothing separates them but "
            f"the filename. Refusing to pick one. A plausible default is worse than a "
            f"gap, because a gap is visible and a plausible default reads as a "
            f"decision. Report both, and say what evidence would settle it — that is a "
            f"question a human answers in ten seconds and a model cannot answer at all.")


def set_leaf(profile: dict, field: str, value) -> None:
    """Write the value at a dotted path, refusing to invent a whole profile section.

    Intermediate objects are created — `docs.roles.design` is a legitimate
    proposal on a profile whose `docs` block has no `roles` yet — but an unknown
    TOP-LEVEL key is refused. A proposal that lands under a section the schema
    never had is a field `doctor.py` will read as real, and inventing one is how a
    typo becomes a fact.
    """
    parts = field.split(".")
    if parts[0] not in profile:
        known = sorted(k for k in profile
                       if not k.startswith("_") and k not in ("$schema", "provenance"))
        raise Refused(
            f"{field}: this profile has no {parts[0]!r} section. Refusing to create "
            f"one — a field invented here is one doctor.py reports as real. "
            f"Top-level sections present: {', '.join(known) or '(none)'}.")
    node = profile
    for key in parts[:-1]:
        step = node.get(key)
        if step is None:
            step = node[key] = {}
        elif not isinstance(step, dict):
            raise Refused(
                f"{field}: {'.'.join(parts[:parts.index(key) + 1])} is a "
                f"{type(step).__name__}, not an object, so there is nothing to write "
                f"{parts[-1]!r} into.")
        node = step
    node[parts[-1]] = value


# --------------------------------------------------------------------------- #
# Doc roles that are already answered elsewhere
# --------------------------------------------------------------------------- #

def doc_role_status(repo: Path, field: str) -> tuple[int, str] | None:
    """(exit, message) when `resolve.py` already has a verdict for this doc role.

    Exits 3, 4 and 5 are the suite's external / declined / stub contract, and they
    outrank a proposal: a role the project has recorded as living in another
    repository, as declined, or as a registered stub is not a role this tool gets
    to map. Any other outcome — including resolve.py being unavailable — returns
    None and the proposal proceeds; this is an escalation path, never a gate.
    """
    if not field.startswith("docs.roles."):
        return None
    role = field.split(".", 2)[2]
    if not role or "." in role:
        return None
    manifest = repo / ".design-suite" / "docs.manifest.json"
    resolver = PLUGIN_ROOT / "bin" / "resolve.py"
    if not manifest.exists() or not resolver.exists():
        return None
    import subprocess
    try:
        done = subprocess.run([sys.executable, str(resolver), role],
                              capture_output=True, text=True, timeout=60,
                              cwd=str(repo))
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode in (3, 4, 5):
        label = {3: "lives in another repository", 4: "is declined",
                 5: "is a registered stub"}[done.returncode]
        detail = (done.stdout or done.stderr or "").strip().splitlines()
        return done.returncode, (
            f"{field}: the {role!r} role {label} — {detail[0] if detail else 'per resolve.py'}. "
            f"That is already recorded, and it is not a mapping to propose over.")
    return None


# --------------------------------------------------------------------------- #
# The write
# --------------------------------------------------------------------------- #

def build_entry(evidence: str) -> dict:
    """The whole of what a proposal writes. A whitelist, built fresh every time."""
    entry = {"state": PROPOSED_STATE, "evidence": evidence}
    assert entry["state"] == PROPOSED_STATE, "a proposal may only ever be inferred"
    assert set(entry) == ALLOWED_ENTRY_KEYS, "a proposal entry is state + evidence"
    return entry


def apply(profile: dict, proposals: list[dict], repo: Path) -> list[str]:
    """Apply every proposal to `profile` in place, or raise and apply none.

    The caller hands us a copy, so a `Refused` part-way through leaves the real
    profile untouched: a partially-applied mapping would read from the outside
    exactly like a complete one.
    """
    summaries: list[str] = []
    for proposal in proposals:
        field = proposal["field"]
        check_not_ratified(profile, field)
        check_not_tied(field, proposal["candidates"])
        evidence = check_evidence(field, proposal["evidence"])
        verdict = doc_role_status(repo, field)
        if verdict is not None:
            raise Refused(verdict[1], exit_code=verdict[0])
        set_leaf(profile, field, proposal["value"])
        block = profile.setdefault("provenance", {})
        fields = block.setdefault("fields", {})
        fields.pop("_example", None)
        fields[field] = build_entry(evidence)
        summaries.append(f"{field} = {proposal['value']!r}  [{PROPOSED_STATE}]")
    return summaries


def audit_serialised(text: str, touched: set[str] | None = None) -> None:
    """Last line of defence: no forbidden key may appear in a provenance entry.

    Re-read from the bytes about to hit disk rather than from the dict we think we
    built, because the assertion this file exists to make is about the FILE. If
    this ever fires it is a bug here, not a caller error — so it refuses loudly
    instead of repairing anything.
    """
    entries = (json.loads(text).get("provenance") or {}).get("fields") or {}
    for dotted, entry in entries.items():
        if dotted.startswith("_") or not isinstance(entry, dict):
            continue
        if entry.get("state") != PROPOSED_STATE:
            continue  # a human's ratified entry, which legitimately carries them
        if touched is not None and dotted not in touched:
            # An inferred entry this run did not write — e.g. one seeded by an
            # older init.py --from-survey that stamped `value`/`verifiedAgainst`.
            # Not this tool's defect, and refusing on it stalled every mapping.
            continue
        stray = sorted(set(entry) - ALLOWED_ENTRY_KEYS)
        if stray:
            raise Refused(
                f"internal: the entry for {dotted} was about to be written carrying "
                f"{stray!r}. Nothing was written. This is a defect in map_project.py, "
                f"not in the proposal.")


def report_inferred(profile: dict) -> int:
    """What this tool has proposed so far — distinguishing 'none' from 'no block'."""
    inferred, unattributed = provenance.awaiting_ratification(profile)
    total = len(provenance.profile_leaves(profile))
    if "provenance" not in profile:
        print(f"this profile has NO provenance block: all {total} field(s) are "
              f"unattributed, and nothing records how any of them got a value.")
    elif not inferred:
        print("no field carries an inferred proposal. Either nothing has been mapped, "
              "or every proposal has since been ratified — run doctor.py to tell those "
              "apart.")
    for dotted in inferred:
        entry = provenance.entries(profile)[dotted]
        print(f"  {PROPOSED_STATE}  {dotted}  — {entry.get('evidence', '(no evidence)')}")
    print(f"{len(inferred)} proposed, {len(unattributed)} unattributed, of {total} "
          f"field(s). Every proposed field is UNTRUSTED until a human ratifies it: "
          f"ratify.py <field> --by NAME")
    return 0


def collect(args: argparse.Namespace) -> list[dict]:
    """Proposals from `--proposals` and/or the single `--field` form."""
    raw: list[object] = []
    if args.proposals:
        path = Path(args.proposals)
        try:
            loaded = json.loads(path.read_text())
        except OSError as exc:
            raise Refused(f"cannot read {path}: {exc}")
        except ValueError as exc:
            raise Refused(f"{path} is not valid JSON ({exc})")
        if isinstance(loaded, dict):
            loaded = loaded.get("proposals", loaded)
        if not isinstance(loaded, list):
            raise Refused(f"{path}: expected a list of proposals, or an object with a "
                          f"'proposals' list")
        raw.extend(loaded)
    if args.field:
        if args.value is None:
            raise Refused(f"{args.field}: --field needs --value")
        one: dict = {"field": args.field, "value": args.value,
                     "evidence": args.evidence}
        if args.candidate:
            one["candidates"] = list(args.candidate)
        raw.append(one)

    parsed = [parse_proposal(item, f"proposal {i + 1}")
              for i, item in enumerate(raw)]
    seen: dict[str, int] = {}
    for i, proposal in enumerate(parsed):
        if proposal["field"] in seen:
            raise Refused(
                f"{proposal['field']}: proposed twice in one run (proposals "
                f"{seen[proposal['field']] + 1} and {i + 1}). Two arguments for one "
                f"field is a tie the caller has not noticed.")
        seen[proposal["field"]] = i
    return parsed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--field", default=None,
                    help="Dotted profile path to propose, e.g. docs.roles.design")
    ap.add_argument("--value", default=None, help="The value proposed for --field.")
    ap.add_argument("--evidence", default=None,
                    help="The argument this mapping rests on. Required, and it must "
                         "be more than filename matching.")
    ap.add_argument("--candidate", action="append", default=[],
                    help="A value that was in contention. Naming more than one is a "
                         "refusal, not a tiebreak.")
    ap.add_argument("--proposals", default=None,
                    help="JSON file: a list of {field, value, evidence, candidates}.")
    ap.add_argument("--list", action="store_true",
                    help="Show every field carrying a proposal, and stop.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Run every refusal and print what would be written, "
                         "without writing it.")
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--dir", default=None, help="Project root (default: detected).")
    args = ap.parse_args(argv)

    repo = Path(args.dir).resolve() if args.dir else project_root()
    profile_path = repo / args.profile
    try:
        profile = json.loads(profile_path.read_text())
    except OSError:
        print(f"refusing: no profile at {profile_path}. This project has not been "
              f"scaffolded, and mapping is not onboarding — run init.py (or "
              f"/onboard-new-client) first. A profile invented here would convert a "
              f"visible gap into a file that reads like one.", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"refusing: {profile_path} is not valid JSON ({exc})", file=sys.stderr)
        return 2

    if args.list:
        return report_inferred(profile)

    try:
        proposals = collect(args)
        if not proposals:
            raise Refused(
                "no proposals. A run that determines nothing exits 2, never 0 — "
                "'nothing could be mapped' and 'everything mapped cleanly' must never "
                "print the same verdict. Pass --field/--value/--evidence, or "
                "--proposals FILE; pass --list to see what has already been proposed.")
        working = json.loads(json.dumps(profile))
        summaries = apply(working, proposals, repo)
        text = json.dumps(working, indent=2) + "\n"
        audit_serialised(text, {p["field"] for p in proposals})
    except Refused as refusal:
        print(f"refusing: {refusal}", file=sys.stderr)
        print("nothing was written.", file=sys.stderr)
        return refusal.exit_code

    if args.dry_run:
        print("dry run — nothing was written. Would have proposed:")
        for line in summaries:
            print(f"  {line}")
        return 0

    profile_path.write_text(text)
    print(f"proposed {len(summaries)} field(s) in "
          f"{profile_path.relative_to(repo) if profile_path.is_relative_to(repo) else profile_path}:")
    for line in summaries:
        print(f"  {line}")
    inferred, unattributed = provenance.awaiting_ratification(working)
    print(f"every one is provenance {PROPOSED_STATE!r} — a machine proposed it and no "
          f"human has ratified it. {len(inferred)} proposed and {len(unattributed)} "
          f"unattributed field(s) are UNTRUSTED; doctor.py reports them, and nothing "
          f"downstream may treat them as authoritative.")
    print("ratify one at a time, with its argument in front of you:  "
          "ratify.py <field> --by NAME")
    return 0


if __name__ == "__main__":
    sys.exit(main())
