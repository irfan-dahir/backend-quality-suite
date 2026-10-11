#!/usr/bin/env python3
"""Tests for map_project.py — the write `/map-project` claimed to do and did not.

The first eval suite ever run in this project measured `/map-project` at Δ 0.00,
with all eight file-based graders failing because `.backend-suite/profile.json`
was never created. This file is the unit-level counterpart to those graders: one
case per grader, so the contract is checked without spending an eval run.

Paired assertions throughout, for the reason CLAUDE.md gives. A writer that
refuses everything and a writer that writes correctly both leave a suite full of
exit-2s looking healthy, so **every refusal is paired with the positive case it
must not swallow**:

  * tied candidates refuse   — one candidate still writes
  * a ratified field refuses — an inferred field is still overwritten
  * bare-filename evidence refuses — a real argument still writes
  * no evidence refuses      — evidence present still writes
  * no proposals is exit 2   — never 0

    python3 plugins/backend-suite/bin/map_project_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
MAP = BIN / "map_project.py"
FAILURES: list[str] = []

GOOD = ("Four candidates could be this role. Only this file carries the screen "
        "inventory the other three cite by section number, and it is what the "
        "roadmap links to for the token tables.")


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


BASE = {
    "profileVersion": 1,
    "project": {"name": "Fixture", "framework": "none"},
    "source": {"root": "lib", "fileGlob": "**/*.dart"},
    "docs": {"manifest": ".backend-suite/docs.manifest.json"},
}


def fixture(tmp: Path, provenance: dict | None = None) -> Path:
    root = tmp / "project"
    (root / ".backend-suite").mkdir(parents=True)
    (root / "lib").mkdir()
    (root / "lib" / "main.dart").touch()
    profile = json.loads(json.dumps(BASE))
    if provenance is not None:
        profile["provenance"] = provenance
    (root / ".backend-suite" / "profile.json").write_text(json.dumps(profile, indent=2))
    return root


def run(root: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(MAP), "--dir", str(root), *argv],
                          capture_output=True, text=True)


def profile_of(root: Path) -> dict:
    return json.loads((root / ".backend-suite" / "profile.json").read_text())


def raw_of(root: Path) -> str:
    return (root / ".backend-suite" / "profile.json").read_text()


def propose(root: Path, field="docs.roles.design", value="docs/DESIGN.md",
            evidence=GOOD, *extra: str) -> subprocess.CompletedProcess:
    return run(root, "--field", field, "--value", value, "--evidence", evidence,
               *extra)


# --------------------------------------------------------------------------- #
# The happy path, asserted on what landed rather than on the exit code
# --------------------------------------------------------------------------- #

def case_a_proposal_is_written_as_inferred() -> None:
    print("\na proposal actually lands on disk, as inferred")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        done = propose(root)
        expect(done.returncode == 0, f"exit 0 (got {done.returncode}: {done.stderr})")
        profile = profile_of(root)
        expect(profile["docs"]["roles"]["design"] == "docs/DESIGN.md",
               "the profile LEAF carries the proposed value")
        entry = profile["provenance"]["fields"]["docs.roles.design"]
        expect(entry["state"] == "inferred", "the entry's state is inferred")
        expect(entry["evidence"] == GOOD, "the evidence string is recorded verbatim")
        expect(set(entry) == {"state", "evidence"},
               f"the entry is state + evidence and nothing else (got {sorted(entry)})")
        expect("UNTRUSTED" in done.stdout,
               "the run says out loud that what it wrote is untrusted")


def case_graders_no_trusted_state_no_stamp_keys() -> None:
    """One case per file-based grader the eval names, read off the raw bytes."""
    print("\nthe eval's file graders, asserted against the written bytes")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        expect(propose(root).returncode == 0, "the write succeeded (precondition)")
        raw = raw_of(root)
        expect(re.search(r'"fields"\s*:\s*\{\s*"', raw) is not None,
               "grader provenance-was-written: fields has at least one key")
        expect(re.search(r'"state"\s*:\s*"inferred"', raw) is not None,
               "grader proposals-are-inferred: an anchored inferred state")
        expect(re.search(r"(approved|declared)", raw) is None,
               "grader no-approved-or-declared-state: neither word anywhere in the file")
        expect(re.search(r'"by"\s*:', raw) is None, "grader no-by-key")
        expect(re.search(r'"on"\s*:', raw) is None, "grader no-on-key")
        expect("verifiedAgainst" not in raw, "grader no-verified-against-commit")
        expect(re.search(r'"value"\s*:', raw) is None,
               "grader no-value-key-on-a-proposal")
        expect('"evidence"' in raw, "grader evidence-string-present")
        expect(re.search(r'"evidence"\s*:\s*"filename( match)?\w*\.?"', raw,
                         re.IGNORECASE) is None,
               "grader evidence-is-not-bare-filename-matching")


def case_forbidden_keys_are_refused_not_stripped() -> None:
    print("\na proposal carrying ratification keys is refused, not cleaned up")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        for key, value in (("by", "someone"), ("on", "2026-01-01"),
                           ("verifiedAgainst", {"commit": "abc"}),
                           ("state", "approved")):
            path = Path(tmp) / f"p-{key}.json"
            path.write_text(json.dumps([{"field": "source.root", "value": "lib",
                                         "evidence": GOOD, key: value}]))
            done = run(root, "--proposals", str(path))
            expect(done.returncode == 2, f"{key!r} on a proposal exits 2")
            expect(key in done.stderr, f"the refusal names {key!r}")
        expect("provenance" not in profile_of(root) or
               not profile_of(root)["provenance"].get("fields"),
               "and none of those refusals wrote anything")
        # The pair: the same proposal without the key writes.
        clean = Path(tmp) / "clean.json"
        clean.write_text(json.dumps([{"field": "source.root", "value": "lib",
                                      "evidence": GOOD}]))
        expect(run(root, "--proposals", str(clean)).returncode == 0,
               "PAIR: the same proposal without those keys is written")


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #

def case_missing_evidence_is_refused() -> None:
    print("\nevidence is required — and the pair proves it is not refusing everything")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        done = run(root, "--field", "source.root", "--value", "lib")
        expect(done.returncode == 2, f"no --evidence exits 2 (got {done.returncode})")
        expect("evidence" in done.stderr, "the refusal says why")
        expect("provenance" not in profile_of(root),
               "nothing was written on the refusal")
        expect(propose(root, "source.root", "lib").returncode == 0,
               "PAIR: the same field WITH evidence is written")


def case_bare_filename_evidence_is_refused() -> None:
    print("\nbare filename matching is a refusal, per the skill's own body")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        for bad in ("filename matches", "Filename match.", "name matches",
                    "the filename", "filename only"):
            done = propose(root, "docs.roles.design", "docs/DESIGN.md", bad)
            expect(done.returncode == 2, f"evidence {bad!r} exits 2")
        short = propose(root, "docs.roles.design", "docs/DESIGN.md", "it is the one")
        expect(short.returncode == 2, "evidence too short to be an argument exits 2")
        expect("provenance" not in profile_of(root), "none of those wrote anything")
        expect(propose(root).returncode == 0,
               "PAIR: an argument from the document's contents is written")


def case_evidence_may_not_launder_the_human_vocabulary() -> None:
    print("\nevidence may not contain 'approved' or 'declared'")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        sneaky = ("This mapping was approved in the kickoff call and the team has "
                  "been treating it as settled ever since, so record it now.")
        done = propose(root, "source.root", "lib", sneaky)
        expect(done.returncode == 2, "evidence containing 'approved' exits 2")
        expect(re.search(r"(approved|declared)", raw_of(root)) is None,
               "the word never reaches the file, which is what the grader reads")
        expect(propose(root, "source.root", "lib").returncode == 0,
               "PAIR: the same field with neutral evidence is written")


# --------------------------------------------------------------------------- #
# The two named eval cases
# --------------------------------------------------------------------------- #

def case_a_ratified_field_is_never_overwritten() -> None:
    print("\nmap-project-preserves-ratified-field: refuse, never clobber")
    with tempfile.TemporaryDirectory() as tmp:
        ratified = {"fields": {"source.root": {
            "state": "approved", "by": "a human", "on": "2026-01-02",
            "value": "lib", "verifiedAgainst": {"commit": "deadbeef"}}}}
        root = fixture(Path(tmp), provenance=ratified)
        done = propose(root, "source.root", "app/src")
        expect(done.returncode == 2, f"exit 2 (got {done.returncode})")
        profile = profile_of(root)
        expect(profile["source"]["root"] == "lib", "the ratified VALUE is untouched")
        entry = profile["provenance"]["fields"]["source.root"]
        expect(entry["state"] == "approved", "the human's state is untouched")
        expect(entry["by"] == "a human", "the human's attribution is untouched")
        # The pair: an INFERRED entry for the same field is replaceable.
        inferred = {"fields": {"source.root": {"state": "inferred",
                                               "evidence": "an earlier, weaker read " * 3}}}
        root2 = fixture(Path(tmp) / "second", provenance=inferred)
        expect(propose(root2, "source.root", "app/src").returncode == 0,
               "PAIR: an inferred entry for the same field IS replaced")
        expect(profile_of(root2)["source"]["root"] == "app/src",
               "PAIR: and the new value landed")


def case_tied_candidates_are_refused() -> None:
    print("\nmap-project-refuses-tied-candidates: refuse, never pick")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        done = propose(root, "docs.roles.design", "docs/DESIGN.md", GOOD,
                       "--candidate", "docs/DESIGN.md", "--candidate", "docs/UI.md")
        expect(done.returncode == 2, f"two candidates exits 2 (got {done.returncode})")
        expect("docs/UI.md" in done.stderr, "the refusal names both candidates")
        expect("provenance" not in profile_of(root), "and wrote nothing")
        one = propose(root, "docs.roles.design", "docs/DESIGN.md", GOOD,
                      "--candidate", "docs/DESIGN.md")
        expect(one.returncode == 0, "PAIR: a single surviving candidate is written")
        expect(profile_of(root)["docs"]["roles"]["design"] == "docs/DESIGN.md",
               "PAIR: and it landed")


# --------------------------------------------------------------------------- #
# Cannot-determine is 2, never 0
# --------------------------------------------------------------------------- #

def case_no_proposals_is_exit_two() -> None:
    print("\na run that determines nothing exits 2, never 0")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        done = run(root)
        expect(done.returncode == 2, f"exit 2 (got {done.returncode})")
        expect("never 0" in done.stderr or "exits 2" in done.stderr,
               "and says why a silent success would have been wrong")
        empty = Path(tmp) / "empty.json"
        empty.write_text("[]")
        expect(run(root, "--proposals", str(empty)).returncode == 2,
               "an empty proposals FILE is the same refusal, not a clean run")
        expect(propose(root).returncode == 0, "PAIR: one real proposal exits 0")


def case_no_profile_is_refused_not_created() -> None:
    print("\nan unscaffolded project is refused — the profile is never invented")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "bare"
        (root / ".backend-suite").mkdir(parents=True)
        done = propose(root)
        expect(done.returncode == 2, f"exit 2 (got {done.returncode})")
        expect(not (root / ".backend-suite" / "profile.json").exists(),
               "and no profile was conjured to have somewhere to write")
        expect("init.py" in done.stderr, "the refusal names the step that comes first")


def case_unknown_top_level_section_is_refused() -> None:
    print("\na field under a section the profile does not have is refused")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        done = propose(root, "frobnicate.kind", "app")
        expect(done.returncode == 2, f"exit 2 (got {done.returncode})")
        expect("provenance" not in profile_of(root), "and wrote nothing")
        deep = propose(root, "docs.roles.design", "docs/DESIGN.md")
        expect(deep.returncode == 0,
               "PAIR: a NEW leaf under an existing section is written")
        expect(profile_of(root)["docs"]["roles"]["design"] == "docs/DESIGN.md",
               "PAIR: intermediate objects were created for it")


def case_the_write_is_all_or_nothing() -> None:
    print("\none bad proposal in a batch writes none of them")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        batch = Path(tmp) / "batch.json"
        batch.write_text(json.dumps([
            {"field": "source.root", "value": "lib", "evidence": GOOD},
            {"field": "docs.roles.design", "value": "d.md", "evidence": "filename matches"},
        ]))
        done = run(root, "--proposals", str(batch))
        expect(done.returncode == 2, f"exit 2 (got {done.returncode})")
        expect("provenance" not in profile_of(root),
               "the GOOD proposal was not written either — no partial mapping")
        both = Path(tmp) / "both.json"
        both.write_text(json.dumps([
            {"field": "source.root", "value": "lib", "evidence": GOOD},
            {"field": "docs.roles.design", "value": "d.md", "evidence": GOOD},
        ]))
        expect(run(root, "--proposals", str(both)).returncode == 0,
               "PAIR: with both arguments sound, both are written")
        expect(len(profile_of(root)["provenance"]["fields"]) == 2,
               "PAIR: and both entries are there")


def case_dry_run_writes_nothing_but_still_refuses() -> None:
    print("\n--dry-run runs every refusal and writes nothing")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        ok = propose(root, "source.root", "lib", GOOD, "--dry-run")
        expect(ok.returncode == 0, "a sound proposal dry-runs clean")
        expect("provenance" not in profile_of(root), "and wrote nothing")
        bad = propose(root, "source.root", "lib", "filename matches", "--dry-run")
        expect(bad.returncode == 2, "a bad one still refuses under --dry-run")


def case_list_distinguishes_nothing_from_unproposed() -> None:
    print("\n--list tells 'nothing proposed' from 'no provenance block'")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp))
        none = run(root, "--list")
        expect(none.returncode == 0 and "NO provenance block" in none.stdout,
               "a profile with no block says so")
        expect(propose(root).returncode == 0, "propose one (precondition)")
        after = run(root, "--list")
        expect("docs.roles.design" in after.stdout, "the proposal is listed")
        expect(after.stdout != none.stdout,
               "and the two states do not print the same thing")


def case_a_legacy_seeded_entry_does_not_block_a_proposal() -> None:
    """Found running understand-existing-project end to end: init.py
    --from-survey used to stamp `value`/`verifiedAgainst` on its inferred
    entries, and the serialised-bytes audit refused EVERY later proposal on
    that profile as "a defect in map_project.py". The audit is about what this
    run writes; an entry it did not touch is not its to refuse on."""
    print("\na pre-existing seeded entry with stamp keys does not block a proposal")
    legacy = {"fields": {"source.root": {
        "state": "inferred", "value": "lib", "evidence": "inferred by survey.py: x",
        "verifiedAgainst": {"commit": "0" * 40}}}}
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), provenance=legacy)
        done = propose(root)
        expect(done.returncode == 0, f"exit 0 (got {done.returncode}: {done.stderr})")
        fields = profile_of(root)["provenance"]["fields"]
        expect(set(fields["docs.roles.design"]) == {"state", "evidence"},
               "what this run wrote is still exactly state + evidence")
        expect(fields["source.root"] == legacy["fields"]["source.root"],
               "the entry it did not touch is left exactly as it was")
        again = propose(root, "source.root", "lib", GOOD)
        expect(again.returncode == 0 and set(profile_of(root)["provenance"]["fields"]
                                             ["source.root"]) == {"state", "evidence"},
               "re-proposing the legacy field replaces it with a whitelisted entry")


def main() -> int:
    for case in (case_a_proposal_is_written_as_inferred,
                 case_graders_no_trusted_state_no_stamp_keys,
                 case_forbidden_keys_are_refused_not_stripped,
                 case_missing_evidence_is_refused,
                 case_bare_filename_evidence_is_refused,
                 case_evidence_may_not_launder_the_human_vocabulary,
                 case_a_ratified_field_is_never_overwritten,
                 case_tied_candidates_are_refused,
                 case_no_proposals_is_exit_two,
                 case_no_profile_is_refused_not_created,
                 case_unknown_top_level_section_is_refused,
                 case_the_write_is_all_or_nothing,
                 case_dry_run_writes_nothing_but_still_refuses,
                 case_list_distinguishes_nothing_from_unproposed,
                 case_a_legacy_seeded_entry_does_not_block_a_proposal):
        case()
    if FAILURES:
        print(f"\n{len(FAILURES)} map-project case(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("\nall map-project cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
