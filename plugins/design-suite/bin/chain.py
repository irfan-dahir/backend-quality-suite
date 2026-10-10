#!/usr/bin/env python3
"""Drive a multi-skill playbook, one step at a time, without losing your place.

    python3 bin/chain.py status onboard-new-client
    python3 bin/chain.py next onboard-new-client
    python3 bin/chain.py done onboard-new-client brand-voice
    python3 bin/chain.py ack  onboard-new-client brand-voice   # clears a checkpoint
    python3 bin/chain.py skip onboard-new-client design-docs --note "docs already exist"
    python3 bin/chain.py reset onboard-new-client

This never invokes a skill. The assistant runs the skill in conversation; this
records where the sequence got to, so a chain survives a session ending halfway.

Thin entry point — the sequencing and checkpoint rules live in
`design_suite/engine/chains.py`.

## Exit codes

    0   the action succeeded
    2   refused — no such chain, a chain that cannot be run as written, an
        unreadable state file, or a step naming a skill that does not exist

There is no exit 1: this records position, it does not judge a project, so it has
nothing to report a *finding* about.

## The refusal that used to not be one

An unreadable `.design-suite/chain-state.json` was silently treated as "no run
yet", so a chain five steps in reported `Next:` step 1 in exactly the tone of one
that had never started. That is fixed in the engine (`chains.read_state`); this
file's job is to surface the resulting `ChainError` as exit 2 rather than a
traceback, on every path that reads state — which now includes `status` and
`next`, not only `load`.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys

import os
from pathlib import Path

from _bootstrap import PLUGIN_ROOT, project_root  # noqa: E402

from design_suite.project import MARKER  # noqa: E402

#: Actions that only READ position. They may run on a project that has no
#: `.design-suite/` yet — that is exactly where understand-existing-project
#: starts, and `status`/`next` refusing there meant the chain could not even
#: show its first step. Every writing action still requires the marker, so a
#: chain never creates `.design-suite/` as a side effect of recording state.
READ_ONLY_ACTIONS = ("status", "next")


def _configured_root() -> Path | None:
    """`project_root()`'s answer, without its refusal: None when unconfigured."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    here = Path.cwd().resolve()
    for candidate in ([Path(env)] if env else []) + [here, *here.parents]:
        if (candidate / MARKER).is_dir():
            return candidate
    return None


def resolve_repo(action: str) -> Path:
    """The project whose chain position to read or write.

    A configured project resolves exactly as every other tool resolves it. An
    unconfigured one resolves only for a read-only action, and then the way
    `survey.py` resolves it (`--project-root`-less: CLAUDE_PROJECT_DIR, else the
    git root, else the working directory) — the same project the chain's first
    step will survey. Anything else refuses through `project_root()`.
    """
    found = _configured_root()
    if found is not None:
        return found
    if action in READ_ONLY_ACTIONS:
        import survey  # bin/ is on sys.path; imported lazily, it is not small
        return survey.resolve_root(None)
    return project_root()


REPO: Path = Path(".")  # set in main(), once the action is known

from design_suite.engine import chains as C  # noqa: E402

MARK = {C.PENDING: "·", C.AWAITING_ACK: "⏸", C.DONE: "✅", C.SKIPPED: "⤼"}


def known_skills() -> set:
    """Every skill name this installation can actually run.

    A skill is a command markdown file. Both locations are consulted because a
    project may define its own — the same precedence `chain_path` already applies
    to chain definitions, and a chain tailored by a project will name skills
    tailored by that project.
    """
    names = set()
    for directory in (REPO / ".claude" / "commands", PLUGIN_ROOT / "commands"):
        if directory.is_dir():
            names |= {path.stem for path in directory.glob("*.md")}
    return names


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("action", choices=["status", "next", "done", "ack", "skip", "reset"])
    ap.add_argument("chain")
    ap.add_argument("step", nargs="?")
    ap.add_argument("--note")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    global REPO
    REPO = resolve_repo(args.action)

    try:
        path = C.chain_path(REPO, args.chain, PLUGIN_ROOT)
        chain = C.load(path)
    except C.ChainError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.action == "reset":
        # Deliberately before the skill check: a chain that has become unrunnable
        # is exactly a chain someone needs to be able to clear.
        C.reset(REPO, args.chain)
        print(f"{args.chain}: position cleared")
        return 0

    # Checked once, up front, for every action that advances or reports on a run.
    # A step naming a skill that does not exist is a dead end three steps in,
    # after the expensive ones; saying so now costs nothing and saves that.
    #
    # An installation where NO commands directory is readable yields an empty set,
    # which would flag every step. That is a broken installation, not a broken
    # chain, so it is not reported as one — the check is skipped and stays silent
    # about the chain rather than manufacturing findings about it.
    available = known_skills()
    if available:
        missing = C.missing_skills(chain, available)
        if missing:
            print(f"{path} names skills that do not exist here: "
                  f"{', '.join(missing)}.\nThis chain cannot be run as written — "
                  f"a step whose skill is missing stalls the sequence at the point "
                  f"it is reached, not at the point it is loaded.",
                  file=sys.stderr)
            return 2

    if args.action in ("done", "ack", "skip"):
        if not args.step:
            print(f"{args.action} needs a step id", file=sys.stderr)
            return 2
        target = {"done": C.DONE, "ack": C.DONE, "skip": C.SKIPPED}[args.action]
        try:
            entry = C.mark(REPO, chain, args.chain, args.step, target, args.note)
        except C.ChainError as exc:
            print(exc, file=sys.stderr)
            return 2
        if entry["status"] == C.AWAITING_ACK:
            print(f"{args.step}: run recorded, but this step is a checkpoint — it is not "
                  f"complete until its own sign-off has actually happened.\n"
                  f"Confirm with: chain.py ack {args.chain} {args.step}")
        else:
            print(f"{args.step}: {entry['status']}")
        return 0

    try:
        state = C.read_state(REPO)
    except C.ChainError as exc:
        print(exc, file=sys.stderr)
        return 2

    # Never silent. A recorded step the definition no longer has is a chain that
    # drifted underneath its own state; the outcome is lost either way, but a lost
    # outcome nobody was told about reappears as pending work someone redoes.
    for orphan in C.orphaned_steps(chain, state, args.chain):
        print(f"note: recorded step {orphan!r} is no longer defined by this chain "
              f"— its outcome is no longer tracked.", file=sys.stderr)

    if args.action == "status":
        rows = C.status(chain, state, args.chain)
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0
        print(f"{chain.get('name', args.chain)} — {chain.get('description', '')}".rstrip(" —"))
        for row in rows:
            flag = " (checkpoint)" if row["checkpoint"] else ""
            note = f"  — {row['note']}" if row["note"] else ""
            print(f"  {MARK.get(row['status'], '?')} {row['id']}: /{row['skill']}{flag}{note}")
        return 0

    step = C.next_step(chain, state, args.chain)
    if args.json:
        print(json.dumps(step, indent=2))
        return 0
    if step is None:
        print(f"{args.chain}: every step is resolved.")
        return 0
    if step["blocked"]:
        print(f"{step['id']} ran but is awaiting sign-off — this step's own confirmation "
              f"has to happen before the chain moves on.\n"
              f"Clear it with: chain.py ack {args.chain} {step['id']}")
        return 0

    print(f"Next: {step['id']} — /{step['skill']}")
    if step.get("purpose"):
        print(f"  Purpose: {step['purpose']}")
    if step.get("decisionPoint"):
        print(f"  Ask first: {step['decisionPoint']}")
    if step.get("checkpoint", True):
        print("  Checkpoint: this step needs explicit sign-off before the chain continues.")
    if step.get("skipIf"):
        print(f"  Skip if: {step['skipIf']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
