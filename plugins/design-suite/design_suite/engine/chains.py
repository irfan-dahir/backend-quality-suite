"""Sequencing and checkpoint bookkeeping for multi-skill playbooks.

`/onboard-new-client` is an ordered sequence of four skills. It has always been
correct about what to run and in what order, and entirely unable to remember where
you are in it — a session that stops after step 2 resumes with nothing but prose.

This engine holds the position. It does **not** run skills: skills are invoked by
the assistant in conversation, not by Python, and pretending otherwise would make
this a worse version of the Workflow tool. What it does is keep the sequence, the
state, and — the part that actually matters — the checkpoints.

CHECKPOINTS DEFAULT TO ON, and that is the whole design problem rather than a
detail. `/establish-brand-voice` requires attribute-by-attribute sign-off and
"never accepts a draft wholesale"; `/onboard-new-client` states plainly that it
"never silently chain[s] them end-to-end without checking in between". A runner
that advanced past those would break the contract of the skills it is composing,
so advancing past a checkpoint requires an explicit acknowledgement recorded in
the state file. Opting out is per-step, declared in the chain, and visible.

Stdlib only.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_VERSION = 1

CHAINS_DIR = ".design-suite/chains"
STATE_FILE = ".design-suite/chain-state.json"

PENDING = "pending"
AWAITING_ACK = "awaiting-acknowledgement"
DONE = "done"
SKIPPED = "skipped"

ON_FAIL_HALT = "halt"
ON_FAIL_SKIP = "skip"


class ChainError(Exception):
    """A chain that cannot be run as written. Raised rather than worked around:
    a half-understood chain that runs anyway is how a sequence silently skips the
    step someone depended on."""


def chain_path(repo: Path, name: str, plugin_root: Path | None = None) -> Path:
    """Project chains win over shipped ones.

    A project that has tailored `onboard-new-client` to its own conventions should
    get its version, not the template — same precedence as everything else here.
    """
    local = repo / CHAINS_DIR / f"{name}.json"
    if local.is_file():
        return local
    if plugin_root:
        shipped = plugin_root / "templates" / "chains" / f"{name}.json"
        if shipped.is_file():
            return shipped
    raise ChainError(
        f"no chain named {name!r} in {CHAINS_DIR}/ or the suite's templates/chains/."
    )


def load(path: Path) -> dict:
    try:
        chain = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ChainError(f"{path} is not readable JSON: {exc}") from exc

    steps = chain.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ChainError(f"{path} declares no steps")

    seen = set()
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ChainError(f"{path} step {index} is not an object")
        step_id = step.get("id")
        if not step_id:
            raise ChainError(f"{path} step {index} has no id")
        if step_id in seen:
            raise ChainError(f"{path} has two steps with id {step_id!r}")
        seen.add(step_id)
        if not step.get("skill"):
            raise ChainError(f"{path} step {step_id!r} names no skill")
        on_fail = step.get("onFail", ON_FAIL_HALT)
        if on_fail not in (ON_FAIL_HALT, ON_FAIL_SKIP):
            raise ChainError(f"{path} step {step_id!r} has unknown onFail {on_fail!r}")
    return chain


def read_state(repo: Path) -> dict:
    path = repo / STATE_FILE
    if not path.is_file():
        return {}
    try:
        raw = path.read_text()
    except OSError as exc:
        raise ChainError(
            f"{STATE_FILE} exists but could not be read: {exc}. Refusing to "
            f"continue: treating this as 'no run yet' would restart a chain that "
            f"may be most of the way done, and say nothing about it.") from exc
    try:
        state = json.loads(raw)
    except ValueError as exc:
        raise ChainError(
            f"{STATE_FILE} is not valid JSON: {exc}. This chain's recorded "
            f"position is unreadable, which is NOT the same as no position — "
            f"fix the file, or discard the position deliberately with: "
            f"chain.py reset <chain>") from exc
    if not isinstance(state, dict):
        raise ChainError(
            f"{STATE_FILE} is valid JSON but not an object, so it records no "
            f"chain positions. Fix it, or discard it with: chain.py reset <chain>")
    return state


def read_state_forgiving(repo: Path) -> dict:
    """`read_state`, but an unreadable file is discarded rather than raised on.

    Exists for exactly one caller — `reset`, whose entire job is to throw the
    position away. Refusing to reset because the thing being reset is corrupt
    would leave a project with no way out except deleting the file by hand.

    Nothing else may use this. The forgiveness is safe here only because the
    caller is about to destroy the value anyway.
    """
    try:
        return read_state(repo)
    except ChainError:
        return {}


def orphaned_steps(chain: dict, state: dict, name: str) -> list[str]:
    """Recorded step ids this chain no longer defines.

    The chain-drifted-underneath-the-state case. A step renamed in the definition
    loses its recorded outcome — the schema says so of `id` — and that is
    tolerable, but only if it is *visible*. Silently dropping the record makes a
    step someone completed reappear as pending with no explanation, which is a
    sequence quietly asking for work to be redone.
    """
    defined = {step["id"] for step in chain.get("steps", [])}
    recorded = state.get("chains", {}).get(name, {}).get("steps", {})
    return sorted(set(recorded) - defined)


def missing_skills(chain: dict, known: set) -> list:
    """`"step-id -> skill"` for every step naming a skill not in `known`.

    A chain is a promise that running it in order produces a set-up project. A
    step naming a skill that does not exist breaks that promise at the moment the
    chain reaches it — three steps in, after the expensive ones — rather than at
    the moment it is loaded. Checking up front turns a mid-run dead end into a
    refusal before anything has happened.

    `known` is passed in rather than discovered here, because what counts as an
    available skill depends on what is installed, which is a question for the CLI
    and not for the sequencing engine.
    """
    return [f"{step['id']} -> {step['skill']}"
            for step in chain.get("steps", [])
            if step["skill"] not in known]


def write_state(repo: Path, state: dict) -> None:
    path = repo / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")


def _chain_state(state: dict, name: str) -> dict:
    return state.setdefault("chains", {}).setdefault(name, {"steps": {}})


def status(chain: dict, state: dict, name: str) -> list[dict]:
    """Every step with its current position in the run."""
    recorded = _chain_state(state, name)["steps"]
    rows = []
    for step in chain["steps"]:
        step_id = step["id"]
        rows.append({
            "id": step_id,
            "skill": step["skill"],
            "checkpoint": step.get("checkpoint", True),
            "status": recorded.get(step_id, {}).get("status", PENDING),
            "note": recorded.get(step_id, {}).get("note"),
            "purpose": step.get("purpose"),
            "decisionPoint": step.get("decisionPoint"),
        })
    return rows


def next_step(chain: dict, state: dict, name: str) -> dict | None:
    """The step to run now, or None when the chain is finished.

    Returns the step whose predecessor is resolved. A checkpointed step that has
    run but not been acknowledged blocks here rather than being stepped over —
    that block is the feature.
    """
    recorded = _chain_state(state, name)["steps"]
    for step in chain["steps"]:
        current = recorded.get(step["id"], {}).get("status", PENDING)
        if current in (DONE, SKIPPED):
            continue
        return {
            **step,
            "status": current,
            "checkpoint": step.get("checkpoint", True),
            "blocked": current == AWAITING_ACK,
        }
    return None


def mark(repo: Path, chain: dict, name: str, step_id: str, status_value: str,
         note: str | None = None) -> dict:
    """Record a step's outcome.

    A checkpointed step cannot go straight to `done`: it lands on
    `awaiting-acknowledgement` and needs a second, explicit call to clear. Two
    calls where one would do is the point — the second one is a human saying the
    step's own sign-off actually happened.
    """
    if status_value not in (PENDING, AWAITING_ACK, DONE, SKIPPED):
        raise ChainError(f"unknown status {status_value!r}")

    step = next((s for s in chain["steps"] if s["id"] == step_id), None)
    if step is None:
        raise ChainError(f"chain {name!r} has no step {step_id!r}")

    state = read_state(repo)
    recorded = _chain_state(state, name)["steps"]
    current = recorded.get(step_id, {}).get("status", PENDING)

    if (status_value == DONE and step.get("checkpoint", True)
            and current != AWAITING_ACK):
        status_value = AWAITING_ACK

    entry = {"status": status_value}
    if note:
        entry["note"] = note
    recorded[step_id] = entry
    write_state(repo, state)
    return entry


def reset(repo: Path, name: str) -> None:
    # The one caller allowed to tolerate an unreadable state file: discarding the
    # position is the whole operation, so refusing on the grounds that the
    # position is unreadable would leave no way out but deleting the file by hand.
    state = read_state_forgiving(repo)
    state.setdefault("chains", {}).pop(name, None)
    write_state(repo, state)
