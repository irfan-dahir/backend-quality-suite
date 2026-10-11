#!/usr/bin/env python3
"""Wire the suite's portable hooks into a non-Claude harness, or into git.

    backend-suite hooks --status [--json]           per-harness WIRED / NOT WIRED
    backend-suite hooks --harness codex             preview: print the config, write nothing
    backend-suite hooks --harness codex --apply     write it into the project
    backend-suite hooks --git [--refusals warn] [--force] [--uninstall]
                                                   opt-in git pre-commit fallback

EXPLICIT tier: `--apply` and `--git` write into the project (or its .git/), so
they run only when a person asks. Without them this prints and writes nothing.

## What gets written, and what only gets printed

Paths and formats come from docs/research/harness-support-matrix-2026-10-08.md
(see backend_suite/engine/harness_hooks.py for the table). Only a harness whose
hook file format that document states completely is written — today, Codex
(`.codex/hooks.json`, "same shape as Claude Code"). Cursor, VS Code, Gemini CLI
and Devin Desktop have an UNVERIFIED part, so `--apply` refuses for them with
exit 2 and prints the snippet plus exactly which part to check on the vendor
page. Claude Code needs nothing: the plugin's own hooks/hooks.json wires it.

The generated command names the harness explicitly (`--harness X`); the hooks
never infer which harness called them.

Commands embed the absolute path of this install's hooks/ directory, because
only Claude Code expands ${CLAUDE_PLUGIN_ROOT}. Re-run after reinstalling the
suite somewhere else.

An existing hooks file is merged, never overwritten: our event groups are
appended only where no command already names our script, and a file that is
not valid JSON is a refusal (exit 2), not a rewrite.

## --git

The harness-independent backstop: delegates to install_precommit_hook.py (which
never overwrites a hook it did not write without --force, and has --uninstall).
`--refusals warn` makes an audit that refuses (exit 2) during pre-commit report
loudly without blocking the commit; the default, `block`, blocks it — an audit
that checked nothing has not passed.

Exit: 0 done/preview, 1 a write failed or the git installer refused, 2 refused
(unknown harness, unverified format under --apply, malformed existing file).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import PLUGIN_ROOT  # noqa: E402
from backend_suite.engine import harness_hooks as HH  # noqa: E402

HOOKS_DIR = PLUGIN_ROOT / "hooks"
EXIT_REFUSED = 2


def preview_or_apply(harness: str, repo: Path, apply: bool) -> int:
    spec = HH.HARNESSES[harness]
    body = HH.snippet(harness, HOOKS_DIR)
    target = repo / spec["file"]
    if spec["mode"] == "plugin":
        print("claude: nothing to write — the backend-suite plugin's hooks/hooks.json "
              "wires session-start and after-edit when the plugin is enabled. "
              "Check with: backend-suite hooks --status")
        return 0
    print(f"# {harness}: {spec['file']}   (format source: {HH.RESEARCH} {spec['doc']})")
    print(json.dumps(body, indent=2))
    if spec.get("note"):
        print(f"# note: {spec['note']}")
    if spec["mode"] == "instructions":
        print(f"\n# UNVERIFIED: {spec['unverified']}\n"
              f"# Confirm against the vendor page linked in {HH.RESEARCH} {spec['doc']}, "
              f"then place it by hand. Nothing written.")
        if apply:
            print(f"refusing --apply for {harness}: its hook-file format is not fully "
                  f"documented in {HH.RESEARCH}, and a file in a guessed shape would be "
                  f"ignored silently — a wired-looking project that audits nothing.",
                  file=sys.stderr)
            return EXIT_REFUSED
        return 0
    if not apply:
        print(f"\n# preview only — re-run with --apply to write {target}")
        return 0
    existing: dict = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                raise ValueError("top level is not an object")
        except (OSError, ValueError) as exc:
            print(f"refusing to touch {target}: could not parse it ({exc}). Fix it, "
                  f"or merge the snippet above by hand.", file=sys.stderr)
            return EXIT_REFUSED
    try:
        merged, changed = HH.merge_into(existing, body)
    except ValueError as exc:
        print(f"refusing to touch {target}: {exc}.", file=sys.stderr)
        return EXIT_REFUSED
    if not changed:
        print(f"already wired: {target}")
        return 0
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"could not write {target}: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {target}")
    return 0


def git(repo: Path, args: argparse.Namespace) -> int:
    argv = [sys.executable, str(PLUGIN_ROOT / "bin" / "install_precommit_hook.py"),
            "--dir", str(repo)]
    if args.uninstall:
        argv.append("--uninstall")
    if args.force:
        argv.append("--force")
    if args.refusals:
        argv += ["--refusals", args.refusals]
    return subprocess.call(argv)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--harness", help=f"one of: {', '.join(HH.HARNESSES)}")
    mode.add_argument("--git", action="store_true", help="opt-in git pre-commit hook")
    mode.add_argument("--status", action="store_true", help="per-harness wiring")
    ap.add_argument("--apply", action="store_true", help="write (default: preview)")
    ap.add_argument("--dir", default=".", help="project root (default: cwd)")
    ap.add_argument("--json", action="store_true", help="--status as JSON")
    ap.add_argument("--uninstall", action="store_true", help="--git: remove it")
    ap.add_argument("--force", action="store_true",
                    help="--git: replace a pre-commit hook this suite did not write")
    ap.add_argument("--refusals", choices=("block", "warn"),
                    help="--git: whether an audit refusal (exit 2) blocks the commit")
    args = ap.parse_args(argv)
    repo = Path(args.dir).resolve()

    if args.status:
        st = HH.status(repo)
        print(json.dumps(st, indent=2) if args.json else HH.render(st))
        return 0
    if args.git:
        return git(repo, args)
    if args.harness not in HH.HARNESSES:
        print(f"unknown harness {args.harness!r}; expected one of "
              f"{', '.join(HH.HARNESSES)}", file=sys.stderr)
        return EXIT_REFUSED
    return preview_or_apply(args.harness, repo, args.apply)


if __name__ == "__main__":
    sys.exit(main())
