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
# Both entries this shipped with (audit_accessibility, audit_copy) were removed
# with their scripts when this repo was re-domained from design-suite to the
# backend suite -- the registry stays, empty, because the surfaces that render
# it (MCP tools, skills catalogue, hooks map) must handle 'no disabled audits'
# as a first-class state rather than a surprise.
DISABLED: dict[str, dict[str, str]] = {}


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
