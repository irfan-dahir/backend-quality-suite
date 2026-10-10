"""Where "every `audit_*.py` this plugin ships" is decided, once.

`repo_health.py` (issue #54) and `mcp/audit_server.py` (issue #67) both need the
same answer to "what audits exist and does this one support `--findings`" — and
both need it to stay one answer. Before this module existed that logic lived only
in `repo_health.py`; factoring it out here rather than importing `repo_health`
from the MCP server keeps a script that is meant to be run, not imported, from
also being a library.

Stdlib only, like everything else in `design_suite/engine`.
"""
from __future__ import annotations

import re
from pathlib import Path

BIN = Path(__file__).resolve().parents[2] / "bin"

# Scripts here that are not project audits and would misreport if run as one:
# no `argv`-driven main worth invoking headlessly, or they check the plugin's
# own repo rather than the project being audited.
NOT_AN_AUDIT = {
    "audit_skill_paths.py",  # checks THIS plugin's own skills, not the project
    "audit_safe_repairers.py",  # checks THIS plugin's own recommendation text
}

# Audits switched off because measurement showed they cannot be right as written.
#
# A disabled audit is NOT removed from `discover()`. It stays discoverable and
# every surface that would otherwise report a result for it must report that it
# is disabled and why — a check that silently stops running looks exactly like a
# check that runs and finds nothing, which is the governing principle's own
# failure mode (CLAUDE.md; docs/CONCEPTS.md "the finding that shapes everything").
#
# `reason` is one line for a table. `detail` is the measured evidence. `pathBack`
# is the bar the next person has to clear to re-enable it — written down here so
# re-enabling is a decision against evidence rather than someone's optimism.
DISABLED: dict[str, dict[str, str]] = {
    "audit_accessibility": {
        "reason": "disabled — 100% false positives measured on two projects (issue #104)",
        "detail": (
            "All 31 findings across two live consumer projects (25 on one, 6 on the other, "
            "judged independently) were `package:pdf` widgets checked against "
            "`accessibility_minimums.min_text_sp`, a SCREEN minimum that is meaningless for "
            "generated print output. Worse than the rate: on one of those projects every one "
            "of the 29 `fontSize:` literals under its source root is in a PDF-generating "
            "file, so the font_size check has zero true-positive capacity there "
            "— it is blind as well as noisy. The cause is that the scanner's font-size pattern "
            "has no notion of which framework's `TextStyle` it matched. "
            "RE-MEASURED 2026-10 on public OSS Flutter apps only (no consumer project was "
            "used): step 1 is done — `.design-suite/exceptions.json` "
            "`accessibility.excludeFilesImporting` lets a project declare its print library, "
            "and set-aside findings are counted, not dropped; on dart_pdf's demo it set aside "
            "all 23 PDF findings and left 0. Two further measured FP classes fixed: an "
            "IconButton labelled by an enclosing Tooltip/Semantics, or by a Tooltip / "
            "semanticLabel inside its icon. Fresh sample before those two fixes "
            "(lichess-org/mobile, openfoodfacts/smooth-app): 47 findings, 2 wrong (4.3%), 45 "
            "true positives. Second fresh sample after them (localsend, spotube): 10 findings, "
            "0 clearly wrong, 1 uncertain (<=10%); spotube's IconButton is shadcn_flutter's, "
            "not Material's — the same framework-blindness shape as the PDF case. One judge; "
            "min_text_sp=12 chosen by the measurer. Still off: the bar names real CONSUMER "
            "projects, and none was measured."
        ),
        "pathBack": (
            "1. Give the scanner a project-declared exclusion for PDF/print-generation code — "
            "declared in the consumer's own config (`.design-suite/`), never hardcoded in this "
            "plugin, per CLAUDE.md's no-project-literals rule. 2. Re-measure the false-positive "
            "rate on at least two real consumer projects and record it. 3. Re-enable only if it "
            "clears the bar issue #104 proposes (<=5% wrong) AND is shown to have non-zero "
            "true-positive capacity — a check that is 0% wrong because it finds nothing is not "
            "fixed. Delete this entry in the same commit that does all three."
        ),
    },
    "audit_copy": {
        "reason": "disabled — 73% of commit-gating findings wrong, measured on two projects (issues #104, #109)",
        "detail": (
            "Of the 26 findings that would actually gate a commit, 19 were wrong (73%); 81% "
            "of total output was noise. Measured independently on a second project, 93% of "
            "findings trace to one cause: `engine/copy.py`'s `classify()` returns "
            "\"microcopy\" unconditionally as soon as the adapter's keyword matched, but "
            "`message:`, `hintText:` and `helperText:` routinely carry body copy — so prose "
            "is judged by label rules. 13 of the 14 `title_case` findings are multi-sentence "
            "prose. The four rules that need no label-vs-body judgment produced 0 findings "
            "across 444 strings, so they carry none of the value and none of the risk; only "
            "`all_caps` showed true-positive capacity, at 9% of output. The distinction the "
            "rules encode — label copy vs. body copy — is not one the checker can make, so it "
            "guesses and then states the guess as a verdict. That is a shape, not a threshold. "
            "RE-MEASURED 2026-10 on public OSS Flutter apps only (no consumer project): "
            "classify() no longer treats a keyword as chrome — only kinds the project declares "
            "in exceptions.json `copy.chromeKinds` are; multi-sentence text and complete 3+-word "
            "sentences are content; letterless fragments and code comments are not copy "
            "(flutter/gallery's code_segments.dart produced 2,547 of its 2,683 findings); "
            "all_caps needs 3+ Latin cased letters (CJK text and '23.5MB' were flagged). Six "
            "apps (flutter_deer, ente auth, lichess, smooth-app, localsend, spotube) before: "
            "114 findings incl. 21 terminal_period, all on sentences. After: 87 findings, 41 "
            "wrong (47%) — nearly all title_case on brand, product, feature and person names, "
            "and all_caps on acronyms. all_caps alone: 18 findings, 5 wrong (28%). What is "
            "left is exactly the semantic judgement (load-bearing capital vs. slip) the path "
            "back says a regex cannot make."
        ),
        "pathBack": (
            "1. The microcopy/content split must stop treating an adapter keyword as proof of "
            "chrome — the classifier needs an actual signal, declared by the consumer project "
            "in its own `.design-suite/` config rather than hardcoded here (CLAUDE.md's "
            "no-project-literals rule). 2. `all_caps` must be measured separately from the "
            "rules that depend on that split, because it is the only one with demonstrated "
            "true-positive capacity and grading it with the others hides that. 3. Re-enable "
            "only on <=5% wrong AND demonstrated non-zero true-positive capacity, re-measured "
            "on two real consumer projects — a check that is 0% wrong because it finds nothing "
            "is silenced, not fixed. The documented path back is issue #109's option 3: "
            "re-scope the failing part as a skill under RFC-0002 3b-ii, because the "
            "distinction it fails at is semantic and belongs to a reader, not a regex. Delete "
            "this entry in the same commit that clears the bar."
        ),
    },
}


def disabled_reason(script: Path | str) -> dict[str, str] | None:
    """The DISABLED entry for an audit, or None if it is live.

    Accepts a path or a bare stem so every caller — the audit itself, the health
    dashboard, the debt roll-up — asks the same question of the same registry.
    The short name is accepted too (`accessibility` as well as
    `audit_accessibility`) because findings envelopes and a project's
    `debt.audits` list use the short form; a registry that only matched one
    spelling would let a disabled audit keep being graded under the other.
    """
    stem = script.stem if isinstance(script, Path) else str(script)
    if stem.endswith(".py"):
        stem = stem[:-3]
    return DISABLED.get(stem) or DISABLED.get(f"audit_{stem}")


def disabled_in_command(command: str | list | tuple | None) -> tuple[str, dict[str, str]] | None:
    """`(audit name, DISABLED entry)` for a hooks.map command that invokes a
    disabled audit, or None.

    A consumer's `.design-suite/hooks.map.json` registers audits by *command
    line*, not by name, so the surfaces that read that map (the pre-commit
    runner, the on-edit hook, `doctor.py`) cannot use `disabled_reason` directly.
    Without this they see only an exit code: exit 2 from a disabled audit is
    indistinguishable from exit 2 for any other reason, and a `reportWhen:
    "findings"` entry looks instead like an audit that ran and failed to write
    its envelope. Either way the developer is told a gate broke rather than that
    the check is switched off — so the fix looks like "repair the hook" instead
    of "remove the entry".

    Matched on the command's own argv rather than the entry's display `name`,
    because the name is free text a project writes for itself and matching it
    would be matching a project literal.
    """
    if not command:
        return None
    argv = command.split() if isinstance(command, str) else list(command)
    for arg in argv:
        stem = Path(str(arg)).stem
        if not stem.startswith("audit_"):
            continue
        if (entry := DISABLED.get(stem)) is not None:
            return stem, entry
    return None


ENGINE = Path(__file__).resolve().parent


def discover(bin_dir: Path | None = None) -> list[Path]:
    """Every `audit_*.py` this plugin ships, minus tests and non-audits.

    Globs `bin/` *and* one level into `design_suite/engine/`. `audit_mock_api.py`
    lives at `engine/mockapi/audit_mock_api.py`, not in `bin/`, because it is
    tightly coupled to sibling modules in that directory (`generate_openapi.py`,
    `mock_api_common.py`) via a directory-relative `sys.path` insert — moving it
    to `bin/` would sever that locality for no reason, so the glob was widened
    instead (issue #120). `discover()` is every derived surface's single source
    of "what audits exist" (this module's own docstring), so a script that lives
    one directory over from where the glob looks is not a smaller bug than a
    missing entry in a hand-maintained list — it is the same bug, since nothing
    here was hand-maintained to begin with. Verified: this audit found 9 critical
    contract drifts on a real consumer the day before it was found to be
    invisible to every dashboard that reads this function.

    Restricted to one level deep (`engine/*/audit_*.py`), not a recursive walk,
    so a coincidentally-named `audit_*.py` deep in test fixtures or scratch
    output can't be picked up silently.
    """
    directory = bin_dir or BIN
    found = list(directory.glob("audit_*.py"))
    found += ENGINE.glob("*/audit_*.py")
    return sorted(
        p for p in found
        if not p.stem.endswith("_test") and p.name not in NOT_AN_AUDIT
    )


def supports_findings_flag(script: Path) -> bool:
    """Whether this audit accepts `--findings` — grepped, not run, to check.

    Not every audit has been retrofitted onto the common envelope yet (see
    `findings.py`'s module docstring); a caller must not assume it and must
    handle both cases.
    """
    try:
        text = script.read_text()
    except OSError:
        return False
    return '"--findings"' in text or "'--findings'" in text


_ENVELOPE_NAME_RE = re.compile(
    # The first argument is whatever expression names the repo root — a bare
    # variable (REPO, repo) in most audits, but audit_mock_api.py calls
    # F.default_path(project_root(), "mock_api"): a function call, not a
    # name. Matching only \w+ silently missed it (issue #120's own test
    # caught this). Match up to the comma at parenthesis-depth 1 instead of
    # guessing at what shape the expression takes.
    r"""F\.default_path\(\s*[^,()]*(?:\([^)]*\)[^,()]*)*,\s*["']([^"']+)["']"""
)


def envelope_name(script: Path) -> str | None:
    """The findings-envelope name this audit actually writes under, or None.

    `script.stem.removeprefix("audit_")` looks like the envelope name and
    almost always is — but `audit_focus_order.py` writes under `focus-order`
    (a hyphen, not the underscore its own filename would suggest), and
    nothing enforces that the two ever match. A caller that assumed the stem
    (`repo_health.py` did, for every audit) gets a findings path that is
    never the one the audit wrote to: `before_mtime`/`after_mtime` never
    change, the envelope read finds nothing, and a genuine `findings` run is
    silently downgraded to `unclear`. Measured live against `audit_tokens.py`.

    Grepped from the actual `F.default_path(<repo-var>, "<name>")` call in the
    script's own source, the same way `supports_findings_flag` above is
    grepped rather than imported — so this can never drift from what the
    script does, the way a hand-maintained `{"audit_focus_order": "focus-
    order", ...}` dict one file away eventually would.
    """
    try:
        text = script.read_text()
    except OSError:
        return None
    match = _ENVELOPE_NAME_RE.search(text)
    return match.group(1) if match else None
