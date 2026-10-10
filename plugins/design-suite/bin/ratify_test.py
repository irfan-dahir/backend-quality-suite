#!/usr/bin/env python3
"""Tests for ratify.py — the writing half of RFC-0002 §3b provenance.

Paired assertions throughout, for the reason CLAUDE.md gives: a ratification
tool that refuses everything and one that ratifies correctly both leave a test
suite full of non-zero exit codes looking healthy. So every refusal case is
paired with the positive case it must NOT swallow, and every success case
asserts what actually landed in the profile rather than just the exit code.

The sharpest case in here is the no-op: running the same ratification twice must
not print success the second time. "Nothing was ratified" and "everything was
already ratified" reading the same is the governing failure applied to this
command itself.

    python3 plugins/design-suite/bin/ratify_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
RATIFY = BIN / "ratify.py"
DOCTOR = BIN / "doctor.py"
SCHEMA = BIN.parent / "templates" / "profile.schema.json"
FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


BASE = {
    "profileVersion": 1,
    "project": {"name": "Fixture", "framework": "none"},
    "adapters": {"lang": "dart"},
    "source": {"root": "lib", "fileGlob": "**/*.dart"},
    "tokens": {"source": {"kind": "file", "path": "lib/tokens.dart"},
               "accessor": "AppTokens"},
    "docs": {"manifest": ".design-suite/docs.manifest.json"},
}


def fixture(tmp: Path, provenance: dict | None = None) -> Path:
    """A healthy project, in a real repository so HEAD can be stamped."""
    root = tmp / "project"
    (root / ".design-suite").mkdir(parents=True)
    (root / "lib").mkdir()
    (root / "lib" / "tokens.dart").touch()
    (root / ".design-suite" / "docs.manifest.json").write_text(json.dumps({"roles": {}}))
    (root / ".design-suite" / "profile.schema.json").write_text(SCHEMA.read_text())
    profile = json.loads(json.dumps(BASE))
    if provenance is not None:
        profile["provenance"] = provenance
    (root / ".design-suite" / "profile.json").write_text(json.dumps(profile, indent=2))
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    return root


def run(root: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RATIFY), "--dir", str(root), *argv],
                          capture_output=True, text=True, cwd=str(root))


def profile_of(root: Path) -> dict:
    return json.loads((root / ".design-suite" / "profile.json").read_text())


def entry_of(root: Path, dotted: str) -> dict:
    return ((profile_of(root).get("provenance") or {}).get("fields") or {}).get(dotted, {})


INFERRED = {"fields": {"source.root": {"state": "inferred",
                                       "evidence": "only directory with .dart files"}}}


def case_approves_an_inferred_field() -> None:
    print("approving a field a machine proposed")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), INFERRED)
        out = run(root, "source.root", "--by", "Ada")
        entry = entry_of(root, "source.root")
        expect(out.returncode == 0, f"exits 0 (got {out.returncode}: {out.stderr.strip()})")
        expect(entry.get("state") == "approved", "the state becomes 'approved'")
        expect(entry.get("by") == "Ada", "the ratifier is recorded")
        expect(entry.get("value") == "lib",
               "the ratified value is snapshotted, so a later edit is CONTRADICTED")
        expect(bool((entry.get("verifiedAgainst") or {}).get("commit")),
               "the tree it was ratified against is stamped as a commit")
        expect(entry.get("evidence") == "only directory with .dart files",
               "the machine's argument survives approval — it is what was reviewed")
        expect("inferred → approved" in out.stdout, "the transition is named in the output")
        # The whole point of the state: doctor must stop calling it untrusted.
        doc = subprocess.run([sys.executable, str(DOCTOR)], capture_output=True,
                            text=True, cwd=str(root))
        expect("source.root: inferred" not in doc.stdout,
               "doctor no longer reports the field as an unratified guess")


def case_no_op_is_refused() -> None:
    print("running the identical ratification twice")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), INFERRED)
        first = run(root, "source.root", "--by", "Ada")
        second = run(root, "source.root", "--by", "Ada")
        expect(first.returncode == 0, "the first run succeeds")
        expect(second.returncode == 1, f"the second is refused (got {second.returncode})")
        expect("changes nothing" in second.stderr,
               "and says so — a ratification that ratified nothing must not print success")
        expect("ratified:" not in second.stdout, "the success line is not printed")


def case_unknown_field_is_refused() -> None:
    print("ratifying a field the profile does not have")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), INFERRED)
        out = run(root, "source.rootz", "--by", "Ada")
        expect(out.returncode == 1, f"refused (got {out.returncode})")
        expect("ratification of nothing" in out.stderr, "names why it is empty")
        expect("provenance" in profile_of(root)
               and "source.rootz" not in (profile_of(root)["provenance"]["fields"]),
               "and writes no entry for it")


def case_approving_an_unproposed_field_is_refused() -> None:
    print("approving a field nothing proposed")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), INFERRED)
        out = run(root, "tokens.accessor", "--by", "Ada")
        expect(out.returncode == 1, f"refused (got {out.returncode})")
        expect("--declare" in out.stderr, "points at the state that IS honest here")
        declared = run(root, "tokens.accessor", "--declare", "--by", "Ada")
        expect(declared.returncode == 0, "and --declare is accepted for the same field")
        expect(entry_of(root, "tokens.accessor").get("state") == "declared",
               "recorded as 'declared', not 'approved' — nobody reviewed a proposal")


def case_declaring_over_an_inference_is_refused() -> None:
    print("claiming authorship of a value a machine proposed")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), INFERRED)
        out = run(root, "source.root", "--declare", "--by", "Ada")
        expect(out.returncode == 1, f"refused (got {out.returncode})")
        expect("erase" in out.stderr or "inferred" in out.stderr,
               "because it would erase that the value was ever inferred")
        forced = run(root, "source.root", "--declare", "--by", "Ada", "--force")
        expect(forced.returncode == 0, "--force allows it deliberately")
        expect(entry_of(root, "source.root").get("state") == "declared",
               "and then the state really changes")


def case_reapproval_is_refused_without_force() -> None:
    print("approving an already-approved field")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), INFERRED)
        run(root, "source.root", "--by", "Ada")
        again = run(root, "source.root", "--by", "Grace")
        expect(again.returncode == 1, f"refused (got {again.returncode})")
        expect("already approved" in again.stderr, "names the state it is already in")
        forced = run(root, "source.root", "--by", "Grace", "--force")
        expect(forced.returncode == 0, "--force re-stamps it")
        expect(entry_of(root, "source.root").get("by") == "Grace",
               "against the new ratifier")


def case_missing_path_is_refused() -> None:
    print("ratifying a path that is not there")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), {"fields": {
            "tokens.source.path": {"state": "inferred", "evidence": "guessed"}}})
        (root / "lib" / "tokens.dart").unlink()
        out = run(root, "tokens.source.path", "--by", "Ada")
        expect(out.returncode == 1, f"refused (got {out.returncode})")
        expect("CONTRADICTED" in out.stderr,
               "because approving it writes a false human assertion doctor flags on sight")
        expect(entry_of(root, "tokens.source.path").get("state") == "inferred",
               "the entry is left as the guess it is")


def case_unsigned_is_refused() -> None:
    print("ratifying without saying who")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), INFERRED)
        out = run(root, "source.root")
        expect(out.returncode == 1, f"refused (got {out.returncode})")
        expect("--by" in out.stderr, "and asks for an attribution")


def case_no_git_is_exit_two() -> None:
    print("ratifying where HEAD cannot be read")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), INFERRED)
        # Remove the repository, leaving a tree with nothing to stamp against.
        subprocess.run(["rm", "-rf", str(root / ".git")], check=True)
        out = run(root, "source.root", "--by", "Ada", "--dir", str(root))
        expect(out.returncode == 2,
               f"exit 2 — refused, not answered weakly (got {out.returncode})")
        expect("staleness" in out.stderr,
               "because an unstamped approval's staleness can never be computed")
        expect(entry_of(root, "source.root").get("state") == "inferred",
               "and nothing is written")


def case_list_distinguishes_empty_from_unreviewed() -> None:
    print("--list on three different profiles")
    with tempfile.TemporaryDirectory() as tmp:
        bare = fixture(Path(tmp) / "a", None)
        out = run(bare, "--list")
        expect(out.returncode == 0, "exits 0 on a profile with no provenance block")
        expect("NO provenance block" in out.stdout,
               "and says the block is absent rather than printing an empty list")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(Path(tmp), INFERRED)
        out = run(root, "--list")
        expect("inferred      source.root" in out.stdout, "lists the inferred field")
        expect("only directory with .dart files" in out.stdout,
               "with the argument a ratifier has to review")
        expect("1 inferred," in out.stdout, "and counts what is outstanding")
        run(root, "source.root", "--by", "Ada")
        after = run(root, "--list")
        expect("0 inferred," in after.stdout,
               "after ratification the count drops — a listing whose zero is stated, "
               "not implied by silence")
        expect("field(s) carry a human decision" in after.stdout,
               "and the ratified-of-total count always prints")


def main() -> int:
    for case in (case_approves_an_inferred_field,
                 case_no_op_is_refused,
                 case_unknown_field_is_refused,
                 case_approving_an_unproposed_field_is_refused,
                 case_declaring_over_an_inference_is_refused,
                 case_reapproval_is_refused_without_force,
                 case_missing_path_is_refused,
                 case_unsigned_is_refused,
                 case_no_git_is_exit_two,
                 case_list_distinguishes_empty_from_unreviewed):
        case()
    if FAILURES:
        print(f"\n{len(FAILURES)} ratification case(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("\nall ratification cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
