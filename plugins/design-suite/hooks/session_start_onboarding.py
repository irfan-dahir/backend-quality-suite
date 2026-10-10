#!/usr/bin/env python3
"""SessionStart hook: notice an unconfigured project and tell Claude, write nothing.

The suite installs drop-in, but before this hook nothing fired when a project was
opened — every registered hook is PostToolUse. So an unconfigured project looked
exactly like a configured one until someone happened to type the right command.

WHAT IT DOES. Classifies the project directory into one of five states and, for
the states that need a next step, prints that step as session context:

  configured      .design-suite/profile.json exists          -> says nothing
  declined        .design-suite-onboarding-declined exists,  -> says nothing
                  or DESIGN_SUITE_NO_ONBOARDING is set
  partial         .design-suite/ exists, no profile.json     -> says so, points at doctor/init
  new             no source files found anywhere             -> offer /onboard-new-client
  existing        source files, no .design-suite/            -> offer /run-chain understand-existing-project
  unclassifiable  no project dir, home or filesystem root,   -> says it could not tell, and why
                  unreadable, or the scan budget ran out
                  before any source file was seen

WHY NEW vs EXISTING IS "ANY SOURCE FILE". The two paths differ in exactly one
thing: whether there is code to reverse-engineer. The existing-project chain
starts with a survey of source roots and token sources; on a tree with no source
it would survey nothing and report that as a finding. So the honest split is the
one the downstream chains depend on, not a guess at the project's age. A tree
with a README and a package.json but no code is "new" — there is nothing yet to
understand. A scan that hits its budget before seeing a single source file has
NOT shown the tree is empty, so it reports unclassifiable rather than "new":
"I didn't find any" and "there are none" must not look the same.

WRITES NOTHING, on every path, including the decline marker: the hook only ever
*reads* that marker. Onboarding writes config and docs, so under the suite's
blast-radius rule it is explicit — this hook notices and offers; the user says
yes before anything is written. The marker is written only on an explicit decline
from the user, by Claude in conversation, never by this file.

NEVER BREAKS A SESSION. Every path exits 0. Any exception is swallowed into a
one-line stderr note (visible in debug output only) and an empty stdout, so a
broken hook degrades to "no prompt", which is what a configured project gets.

Output contract (Claude Code hooks): for SessionStart, a JSON object on stdout
with hookSpecificOutput.additionalContext is added to Claude's context. Plain
stdout would also be accepted for this event; JSON is used so the intent is
explicit. Stdlib only; must not import bin/ (not on the path from hooks/).

Other harnesses: `--harness <name>` (written into that harness's hook config by
`design-suite hooks --harness X`) formats the same notice through
harness_output.py. Classification is unchanged. No flag means `claude` and the
original output, byte for byte. A harness with no session-start context channel
gets stderr only — this hook still writes nothing.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

MARKER_DIR = ".design-suite"
PROFILE = f"{MARKER_DIR}/profile.json"
DECLINE_FILE = ".design-suite-onboarding-declined"
DECLINE_ENV = "DESIGN_SUITE_NO_ONBOARDING"

# A session start must stay fast. Both budgets end the scan early; ending early
# without having seen source is "unclassifiable", never "new".
MAX_ENTRIES = 20000
MAX_SECONDS = 1.5

SOURCE_EXTS = {
    ".dart", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte",
    ".py", ".rb", ".go", ".rs", ".java", ".kt", ".kts", ".swift", ".m", ".mm",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".php", ".scala", ".ex", ".exs",
    ".css", ".scss", ".sass", ".less", ".html",
}
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "build", "dist", "out", "target",
    ".dart_tool", ".venv", "venv", "__pycache__", "Pods", ".gradle", ".idea",
    ".next", ".nuxt", "vendor", "coverage",
}


def project_dir(payload: dict) -> Path | None:
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd")
    if not raw:
        # Cursor names the project in `workspace_roots`, not `cwd`.
        roots = payload.get("workspace_roots")
        if isinstance(roots, list) and roots and isinstance(roots[0], str):
            raw = roots[0]
    return Path(raw) if raw else None


def scan_for_source(root: Path) -> str:
    """'found' | 'none' (complete scan, nothing) | 'budget' (gave up early)."""
    deadline = time.monotonic() + MAX_SECONDS
    seen = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    seen += 1
                    if seen > MAX_ENTRIES or time.monotonic() > deadline:
                        return "budget"
                    name = entry.name
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if name not in SKIP_DIRS and not name.startswith("."):
                                stack.append(Path(entry.path))
                        elif os.path.splitext(name)[1].lower() in SOURCE_EXTS:
                            return "found"
                    except OSError:
                        continue
        except OSError:
            if current == root:
                raise
            continue
    return "none"


def classify(root: Path | None, env: dict | None = None) -> tuple[str, str]:
    """(state, reason). Pure read; the only filesystem calls are stat/scandir."""
    env = os.environ if env is None else env
    if root is None:
        return "unclassifiable", "no project directory was given to the hook"
    try:
        root = root.resolve()
    except OSError as exc:
        return "unclassifiable", f"could not resolve {root}: {exc}"
    if not root.is_dir():
        return "unclassifiable", f"{root} is not a readable directory"
    if root == Path(root.anchor) or root == Path.home().resolve():
        return "unclassifiable", f"{root} is a home or filesystem root, not a project"
    if env.get(DECLINE_ENV):
        return "declined", f"{DECLINE_ENV} is set"
    if (root / DECLINE_FILE).exists():
        return "declined", f"{DECLINE_FILE} exists"
    if (root / PROFILE).is_file():
        return "configured", f"{PROFILE} exists"
    if (root / MARKER_DIR).is_dir():
        return "partial", f"{MARKER_DIR}/ exists but has no profile.json"
    try:
        result = scan_for_source(root)
    except OSError as exc:
        return "unclassifiable", f"could not list {root}: {exc}"
    if result == "found":
        return "existing", "source files present, no .design-suite/"
    if result == "none":
        return "new", "no source files anywhere in the tree"
    return "unclassifiable", (f"scan stopped at its budget ({MAX_ENTRIES} entries / "
                              f"{MAX_SECONDS}s) before finding any source file")


_DECLINE_NOTE = (
    f"If the user declines, do not raise this again unprompted. Only if they ask "
    f"not to be reminded in this project, create an empty `{DECLINE_FILE}` file at "
    f"the project root (or they can set {DECLINE_ENV}=1); never create it on your own."
)

MESSAGES = {
    "new": (
        "design-suite: this project has no source files and no `.design-suite/` "
        "config — it looks like a NEW project ({reason}). Nothing has been written. "
        "At a natural point, offer the user `/onboard-new-client` (or "
        "`/run-chain onboard-new-client` to keep position across sessions). Every "
        "step of it writes docs or config and waits for their sign-off. Do not "
        "start it without a yes. " + _DECLINE_NOTE
    ),
    "existing": (
        "design-suite: this project has source code but no `.design-suite/` config "
        "({reason}) — it is an EXISTING, unconfigured project. Nothing has been "
        "written. At a natural point, offer `/run-chain understand-existing-project`: "
        "survey the codebase, scaffold config from the survey, propose doc-role "
        "mappings, then build context docs one at a time — each writing step stops "
        "for the user's confirmation. Do not start it without a yes. " + _DECLINE_NOTE
    ),
    "partial": (
        "design-suite: `.design-suite/` exists but has no profile.json ({reason}), so "
        "most skills will refuse. Nothing has been written. If relevant, suggest "
        "`python3 \"${{CLAUDE_PLUGIN_ROOT}}/bin/doctor.py\"` to see what is missing, or "
        "resuming `/run-chain understand-existing-project`."
    ),
    "unclassifiable": (
        "design-suite: could not tell whether this project is new, existing, or "
        "configured ({reason}). Nothing has been written and no onboarding path is "
        "suggested. If the user asks about setting up the design suite, ask them "
        "which applies rather than guessing."
    ),
}


def render(state: str, reason: str) -> str | None:
    template = MESSAGES.get(state)
    return template.format(reason=reason) if template else None


def main(harness: str = "claude") -> int:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        state, reason = classify(project_dir(payload))
        text = render(state, reason)
        if text and harness != "claude":
            here = str(Path(__file__).resolve().parent)
            if here not in sys.path:
                sys.path.insert(0, here)
            import harness_output
            harness_output.session_start(harness, text)
        elif text:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": text}}))
    except Exception as exc:  # noqa: BLE001 — a hook must never break session start
        print(f"design-suite session_start_onboarding: {type(exc).__name__}: {exc}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    _harness = "claude"
    if len(sys.argv) > 1:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            import harness_output
            _harness = harness_output.parse_harness(sys.argv[1:])
        except Exception as exc:  # noqa: BLE001 — unknown adapter is a hard error
            print(f"design-suite session_start_onboarding.py: {exc}. The hook "
                  f"config is wrong; no onboarding check ran.", file=sys.stderr)
            sys.exit(1)
    sys.exit(main(_harness))
