#!/usr/bin/env python3
"""Fail if this plugin ever recommends a repair it has not vetted as safe.

This exists because it already happened, twice, at the worst possible severity:
a recommendation that DELETES data rather than one that merely misfires.

  * Issue #109: `audit_copy`'s `title_case` rule shipped a suggested rewrite that
    lowercased declared proper nouns — the fix corrupted correct text.
  * Issue #116: an `audit_mock_api` finding ended "— run `sync_mock_api.py
    <contract>`". `sync_mock_api.py` propagates fixture -> mock unconditionally.
    In two contracts the FIXTURE was the side that had rotted, so following the
    finding's own advice deleted a real attachment URL and a medication's
    weekly-cadence field from the mock everyone demos against.

Both times the text that caused the damage was not doing anything exotic — it
was an ordinary sentence naming a script as the fix. Nothing checked whether the
script it named could be trusted with that sentence. This is that check.

Three rules:

  1. A "run `<script>`" / "Fix with: `<script>`" sentence anywhere under bin/,
     backend_suite/engine/, hooks/, commands/, or agents/ must name a script that
     appears in templates/safe-repairers.json — keyed on the invocation actually
     written (a bare script name, or a script plus a specific flag; see that
     file's schema for why the two are different entries).

  2. Same rule for a "run `/<skill-name>`" sentence naming a plugin skill as
     something to run.

  3. Being *unlisted* is not automatically a problem: EXEMPT (below) covers
     sentences this gate's own regexes catch that are not actually a repair
     recommendation for a destructive action — a diagnostic ("run doctor.py
     first"), a prerequisite in the same tool's own workflow ("run `pipeline.py
     setup`"), a provenance comment quoting now-removed text, or an explicit
     prohibition ("Auto-run `/sync-mock-api` on the user's behalf" appears
     inside a "What you must never do" list). Every exemption carries a reason,
     same as `audit_skill_paths.py`'s EXEMPT — an exemption nobody can see the
     reasoning for is how a real finding gets suppressed for years.

**What this gate cannot decide for you.** Whether a script actually deserves an
allowlist entry is a judgement call about what it writes and how it fails — this
gate only enforces that judgement was written down and attached, not that it was
correct. Read `templates/safe-repairers.schema.json` before adding an entry: R1
and R2 are the two properties that make a repair recommendation survivable, and
an entry that just asserts "safe" without naming the actual mechanism is a rubber
stamp, not a review.

**What this gate does not check**: whether the CONSUMING project's own
`.backend-suite/hooks.map.json` names an unvetted `fixHint`/`repair.command` —
that is `doctor.py`'s job (see `check_fix_hints_are_safe` there), because the
consumer, not this plugin, is the one asserting that value.

    python3 plugins/backend-suite/bin/audit_safe_repairers.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGINS = REPO / "plugins"
ALLOWLIST = REPO / "plugins" / "backend-suite" / "templates" / "safe-repairers.json"

SCAN_DIRS = ("bin", "backend_suite/engine", "hooks", "commands", "agents")

# "run `foo.py`", "run foo.py", "Fix with: foo.py", "re-run foo.py" — a script
# named as something to execute. `(?:re-)?run` covers "re-run export_palette.py",
# which is the same shape of sentence as "run" and must be checked the same way.
# The word itself must be its own token (leading \b), not a suffix of a longer
# word ("Auto-run" — see EXEMPT for why that specific sentence is not this rule's
# business despite matching the regex; narrowing the regex to exclude it would
# also exclude "Re-run", which is a real instance of the same shape).
SCRIPT_RUN = re.compile(
    r"\b(?:re-)?run\b\s*:?\s*`?([A-Za-z_][A-Za-z0-9_./-]*\.(?:py|sh))"
    r"((?:\s+[A-Za-z0-9_.<>{}/-]+)*)", re.IGNORECASE)
FIX_WITH = re.compile(
    r"[Ff]ix(?:ed)? with:?\s*`?([A-Za-z_][A-Za-z0-9_./-]*\.(?:py|sh))")
SKILL_RUN = re.compile(r"\b(?:re-)?run\b\s*`?(/[a-z][a-z0-9-]*)")

# Files this gate reads itself, plus the allowlist and its schema — none of
# these are prose a human wrote to recommend a fix, they are the machinery, and
# scanning them would report the regex's own source as a violation of itself
# (the exact self-reference audit_skill_paths.py already routes around).
SELF_EXEMPT_NAMES = {Path(__file__).name, "audit_safe_repairers_test.py"}

# Exemptions. Every entry needs a reason. Keyed by (file basename, substring of
# the matched text) — same convention as audit_skill_paths.EXEMPT, on purpose:
# this is the same shape of gate for a different rule, and a second exemption
# vocabulary invented here would be one more thing to keep in sync with that one.
EXEMPT: list[tuple[str, str, str]] = [
    ("upgrade-apply.md", "Run `init.py --force",
     "A PROHIBITION, not a recommendation: the line is an entry in that "
     "command's 'What you must never do' list, and the command's whole premise "
     "is that `init.py --force` rewrites profile.json wholesale and so is never "
     "used to apply a migration. Forbidding a destructive action is the "
     "opposite of recommending one, and rewording it to dodge this matcher "
     "would make the prohibition harder to find than the thing it prohibits."),
    ("catalog.py", "run catalog.py",
     "catalog.py --check's own stderr message, telling a developer to "
     "regenerate a GENERATED file (docs/CATALOG.md) from source frontmatter — "
     "CLAUDE.md rule 5's own prescribed fix for exactly this staleness. "
     "Deterministic, idempotent, and writes only the one file it is the "
     "generator for; there is no other side it could pick a wrong winner "
     "between."),
    ("init.py", "Run `doctor.py",
     "doctor.py is read-only: it reports problems and writes nothing. "
     "Recommending it is a diagnostic, not a repair."),
    ("map_project.py", "run doctor.py to tell those",
     "doctor.py is read-only: it reports problems and writes nothing. Same "
     "exemption, same reason, as init.py's above — and the sentence exists to "
     "stop --list's 'no field carries a proposal' being read as 'everything "
     "was already ratified', which is a diagnostic distinction, not a fix."),
    ("map_project.py", "run init.py",
     "The refusal printed when there is NO .backend-suite/profile.json at all, "
     "naming the scaffolder as the step that has to happen first — mapping is "
     "not onboarding. Bare init.py (no --force) refuses to overwrite any file "
     "that already exists and exits 1 (bin/init.py line 288, checked when this "
     "exemption was written), so on the only path that can print this sentence "
     "there is nothing on disk for it to lose."),
    ("doctor.py", "run bin/install_precommit_hook.py",
     "install_precommit_hook.py is additive (installs a git hook) and refuses "
     "to overwrite a hook it did not create (checked when this exemption was "
     "written) — there is no project data for it to lose."),
    ("audit_mock_api.py", "run sync_mock_api.py",
     "PROVENANCE, same convention as audit_skill_paths.py's doctor.py "
     "exemptions: this is a comment recording the OLD finding text, removed "
     "for exactly this reason (issue #116), so a future editor does not "
     "reintroduce it by accident. The comment quoting the retired sentence is "
     "the fix, not a live recommendation — see the surrounding lines, which "
     "end 'Do not re-add a repair command here.'"),
    ("mock_api_reminders.py", "run audit_mock_api.py",
     "audit_mock_api.py is read-only — it reports drift and writes nothing. "
     "Recommending it is a diagnostic, not a repair."),
    ("animate-asset.md", "run `python3",
     "Step 0 precondition check (pipeline.py check) for this skill's OWN "
     "explicit-tier workflow, not a fix for a finding raised elsewhere."),
    ("animate-asset.md", "run `pipeline.py setup",
     "Installs local tooling (git-lfs, ffmpeg) the skill needs to run at all — "
     "a prerequisite, not a repair for anything the skill or an audit found."),
    ("pipeline.py", "re-run export_palette.py",
     "export_palette.py regenerates palette.json, a generated artifact, from "
     "the manifest — the same regenerate-don't-edit shape as catalog.py, not a "
     "cross-source merge that could pick a wrong winner."),
    ("pipeline.py", "run: pipeline.py setup",
     "Installs local tooling (git-lfs/ffmpeg) this same script needs — a "
     "prerequisite for the tool to run, not a repair."),
    ("encode.py", "run: pipeline.py setup",
     "Same tooling-install prerequisite as pipeline.py's own doctor check, "
     "reported from the encode step instead — install_precommit_hook.py-style "
     "additive setup, nothing to lose."),
    ("pipeline.py", "run `pipeline.py animate",
     "Names the next step in this tool's OWN multi-stage workflow (animate "
     "before verify-motion) — sequencing, not a repair for a finding."),
    ("decline_doc.py", "run init.py",
     "init.py only scaffolds NEW `.backend-suite/` files from templates and "
     "never overwrites an existing one (see its own docstring) — additive, "
     "nothing to lose."),
    ("audit-mock-api.md", "run `/sync-mock-api",
     "The full sentence is 'Auto-run `/sync-mock-api` on the user's behalf' "
     "under a 'What you must never do' heading — it PROHIBITS auto-running the "
     "skill, it does not recommend it (SCRIPT_RUN/SKILL_RUN match on the word "
     "'run', which is also the tail of 'Auto-run', so the matched text starts "
     "mid-word). The regex cannot tell a command from a prohibition of the same "
     "command, and narrowing it to try would risk missing the next real "
     "instance of this exact wording used as an instruction — see this file's "
     "own module docstring for that tradeoff."),
    ("rewrite-copy.md", "run `/establish-brand-voice",
     "establish-brand-voice only creates or updates the brand-voice doc — its "
     "own description is explicit that it 'never rewrites existing copy'. "
     "Nothing for it to destroy; it is a missing-prerequisite pointer, not a "
     "repair for a finding."),
    ("map-project.md", "run `/survey",
     "/survey only reads the project tree and writes survey.json, a report — "
     "same shape as recommending any other read-only audit."),
    ("ratify.py", "run init.py",
     "Same additive-scaffolding pointer decline_doc.py's exemption covers: "
     "init.py only creates NEW `.backend-suite/` files and never overwrites an "
     "existing one, and this sentence fires only when there is no profile at "
     "all — there is nothing on disk for it to lose."),
    ("ratify.py", "run doctor.py",
     "doctor.py is read-only: it reports problems and writes nothing, the same "
     "grounds as init.py's existing doctor.py exemption. Here it is a pointer "
     "at where the remaining untrusted fields are listed in context, after a "
     "ratification succeeded — a diagnostic, not a repair."),
    ("check_mock.sh", "run `/audit-mock-api",
     "/audit-mock-api is read-only (produces a report, per its own "
     "description) — recommending it is a diagnostic pointer, not a repair."),
]


def exempt(basename: str, matched: str) -> str | None:
    for f, needle, reason in EXEMPT:
        if f == basename and needle in matched:
            return reason
    return None


def load_allowlist() -> dict[str, dict]:
    """{invocation: entry}, or exit loudly if the allowlist itself is broken.

    A missing or malformed allowlist must not be read as "nothing is
    allowlisted, so everything fails closed" OR as "the check could not run, so
    let everything through" — either silent fallback is the same trap this
    plugin keeps naming, so this refuses instead of guessing which one you
    meant.
    """
    if not ALLOWLIST.is_file():
        sys.exit(f"audit_safe_repairers: no allowlist at "
                  f"{ALLOWLIST.relative_to(REPO)} — cannot tell a vetted repair "
                  f"from an unvetted one, so refusing rather than passing every "
                  f"script silently")
    try:
        data = json.loads(ALLOWLIST.read_text())
    except ValueError as exc:
        sys.exit(f"audit_safe_repairers: {ALLOWLIST.relative_to(REPO)} is not "
                  f"valid JSON ({exc})")
    entries = data.get("entries")
    if not isinstance(entries, list):
        sys.exit(f"audit_safe_repairers: {ALLOWLIST.relative_to(REPO)} has no "
                  f"'entries' array")

    by_invocation: dict[str, dict] = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            sys.exit(f"audit_safe_repairers: entries[{i}] is not an object")
        invocation = entry.get("invocation")
        if not invocation:
            sys.exit(f"audit_safe_repairers: entries[{i}] has no 'invocation'")
        # R1/R2 must be substantive, not a rubber stamp. minLength in the schema
        # says the same thing; enforced here too because nothing currently runs
        # JSON Schema validation over this file (no `jsonschema` dependency —
        # stdlib only, like every other gate here).
        for field in ("r1", "r2", "reason"):
            value = entry.get(field, "")
            if not isinstance(value, str) or len(value.strip()) < 10:
                sys.exit(
                    f"audit_safe_repairers: entry {invocation!r} has no "
                    f"substantive {field!r} — an allowlist entry with nothing "
                    f"behind it is a rubber stamp, not a review (see "
                    f"templates/safe-repairers.schema.json)")
        by_invocation[invocation] = entry
    return by_invocation


def _covered(script: str, args: str, allowlist: dict[str, dict]) -> bool:
    """Whether this exact invocation is vetted.

    A bare-script entry ("generate_openapi.py") covers every invocation of that
    script. A flagged entry ("generate_openapi.py --check") covers ONLY that
    exact flag — recommending the same script with no flag, or a different
    flag, is a different invocation and must have its own entry. This is the
    whole point of keying on `invocation` rather than on the script name alone:
    a script can be safe under one flag and destructive under another (the
    schema's own worked example is `sync_mock_api.py`, whose `--check` mode is
    report-only while its default mode is the one issue #116 is about), and an
    allowlist keyed only on the script name would launder the unsafe form in
    under the safe one's attestation.
    """
    args = args.strip()
    if script in allowlist:
        return True  # bare entry: every invocation of this script is vetted
    full = f"{script} {args}".strip()
    return full in allowlist


def scan_files():
    for sub in SCAN_DIRS:
        root = PLUGINS / "backend-suite" / sub
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix not in (".py", ".sh", ".md"):
                continue
            if path.name in SELF_EXEMPT_NAMES:
                continue
            yield path


def main() -> int:
    allowlist = load_allowlist()
    problems: list[str] = []
    allowed: list[str] = []

    for path in scan_files():
        text = path.read_text()
        rel = path.relative_to(REPO)

        for m in SCRIPT_RUN.finditer(text):
            script, args = m.group(1), m.group(2)
            hit = m.group(0).strip()
            reason = exempt(path.name, hit)
            if reason:
                allowed.append(f"{rel}: {hit!r} — {reason}")
                continue
            if _covered(script, args, allowlist):
                allowed.append(
                    f"{rel}: {hit!r} — {script} is on the safe-repairers "
                    f"allowlist")
                continue
            problems.append(
                f"{rel}: recommends running {script!r} ({hit!r}) but it is not "
                f"in templates/safe-repairers.json and no EXEMPT entry names why "
                f"it isn't a repair recommendation. Either add a vetted entry "
                f"(templates/safe-repairers.schema.json says what R1/R2 need to "
                f"say), or add an EXEMPT entry to this file explaining why this "
                f"sentence is not a repair for a destructive action")

        for m in FIX_WITH.finditer(text):
            script = m.group(1)
            hit = m.group(0).strip()
            reason = exempt(path.name, hit)
            if reason:
                allowed.append(f"{rel}: {hit!r} — {reason}")
                continue
            if _covered(script, "", allowlist):
                allowed.append(
                    f"{rel}: {hit!r} — {script} is on the safe-repairers "
                    f"allowlist")
                continue
            problems.append(
                f"{rel}: \"Fix with\" names {script!r} ({hit!r}), which is not "
                f"in templates/safe-repairers.json. A fix recommendation is "
                f"exactly the sentence shape that caused issues #109 and #116 — "
                f"vet it first")

        for m in SKILL_RUN.finditer(text):
            skill = m.group(1)
            hit = m.group(0).strip()
            reason = exempt(path.name, hit)
            if reason:
                allowed.append(f"{rel}: {hit!r} — {reason}")
                continue
            if skill in allowlist:
                allowed.append(
                    f"{rel}: {hit!r} — {skill} is on the safe-repairers "
                    f"allowlist")
                continue
            problems.append(
                f"{rel}: recommends running {skill!r} ({hit!r}) as a fix, but "
                f"it is not in templates/safe-repairers.json and no EXEMPT "
                f"entry names why it isn't. A skill recommended as a repair can "
                f"write just as destructively as a script — vet it the same way")

    if allowed:
        print(f"safe repairers: {len(allowed)} recommendation(s) accounted for:")
        for a in allowed:
            print(f"  · {a}")
        print()

    if problems:
        print("safe repairers: unvetted repair recommendation(s)\n", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        print(f"\n{len(problems)} problem(s). A recommendation naming an unvetted "
              "script or skill as a fix is how issues #109 and #116 happened — "
              "see this file's module docstring.", file=sys.stderr)
        return 1

    print(f"safe repairers: {len(allowed)} recommendation(s) scanned across "
          f"{', '.join(SCAN_DIRS)} — every one is either vetted in "
          f"templates/safe-repairers.json or exempted above with a reason.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
