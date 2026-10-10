#!/usr/bin/env python3
"""Clean up stale git worktrees — every worktree, not just the agent-generated ones.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/cleanup_worktrees.py"                 # dry-run (default)
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/cleanup_worktrees.py" --apply         # actually remove
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/cleanup_worktrees.py" --include-external --apply
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/cleanup_worktrees.py" --target-branch main
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/cleanup_worktrees.py" --max-age-days 3

## Why this exists

The Agent tool's `isolation: "worktree"` option creates a real `git worktree`
per agent, under `.claude/worktrees/agent-<id>/`. A session that fans out N
agents ends up with N worktrees and N branches to clean up by hand afterwards
— `git worktree remove --force` on each one, then `git worktree prune`, then
deleting the now-merged branches. Doing that by hand, twice, for 20 worktrees
in one session is exactly the kind of repetitive mechanical task a script
should own instead.

## Scope: every worktree git reports (issue #140)

This script used to list *only* worktrees under `.claude/worktrees/`, and
filter every other one out before any logic ran. That was half of a correct
design, and the half that was missing cost real work.

Both halves, stated plainly:

  * `CLAUDE.md` rule 1 says agent worktrees are identified by **location**
    (`.claude/worktrees/`) rather than by branch-name prefix, because the Agent
    tool generates its own names (`worktree-agent-<hex>`) at dispatch time and
    a prefix can change out from under us. That reasoning is sound and is
    preserved exactly — see `classify()`.
  * `CLAUDE.md` rule 4 tells a human, or an orchestrator, to create a worktree
    at `git worktree add ../suite-<topic> main` — a **sibling** of the repo,
    nowhere near `.claude/worktrees/`.

So the project's own instructions produced worktrees the project's own cleanup
tool was structurally blind to. Measured on this repo: 8 worktrees present,
`0 worktree(s) considered`. The issue reports an earlier run of 19 present, 4
considered.

A worktree nothing prunes is where uncommitted work goes to die, and that is
not hypothetical: `/private/tmp/ads-mapfix` held a modified eval case, its
scaffold and a whole new case, none of it committed. It is now 88 empty
directories and zero files (#137). A sibling worktree with identical exposure
was rescued in time and turned out to carry a finding worth keeping.

So: **every worktree `git worktree list` reports is now considered**, and each
is classified by origin:

  * `primary`  — the repo's own main checkout. Considered, reported, and never
                 removable. Removing it is not a cleanup, it is an accident.
  * `agent`    — under `.claude/worktrees/`. Identified by location, per rule 1.
                 Removable when stale, as before.
  * `external` — everything else, which is where rule 4's `../suite-<topic>`
                 lands. Considered and reported by default, but **not removed
                 without `--include-external`**: a human's own worktree is
                 theirs, and "visible" is the fix this issue asked for, not
                 "deleted by default". The refusal is printed, never silent.

## The three refusals, each named

There is no silent skip anywhere in this script. Per this project's governing
principle — a cleanup that does nothing must never look the same as one that
checked and found nothing to do — every worktree considered is printed with a
verdict and a reason, including the ones it declines to touch.

1. **Locked.** `git worktree list --porcelain` reports `locked` (optionally
   with a reason). That is how an *in-use* worktree announces itself, and it
   is the check a hand-rolled filter forgets: cleaning up by hand for this
   issue removed a running agent's workspace because the filter asked "clean
   and merged?" and never asked "in use?". It happened to be clean and the
   agent recreated it, so nothing was lost. That is luck, not a check.

2. **Uncommitted or untracked changes.** Removal is `git worktree remove
   --force`, which deletes the directory including files git has never seen.
   "Merged" is a fact about the *branch*; the working tree can still hold
   never-committed work. `--remove-dirty` opts in to removing them anyway; it
   is off by default and deliberately **not** implied by `--apply`.

   This one is not merely skipped, it is **reported loudly** — with a file
   count, and with the lesson recorded in #137, at the point a person would
   need to hear it. A worktree holding uncommitted work is precisely the thing
   that was lost, so a quiet one-line skip would be the wrong volume. See
   `print_uncommitted_report()`.

3. **Unmerged commits.** The branch has commits not yet in the target branch.
   Never removed, no matter how old.

A detached-HEAD worktree is also never removed — there is no branch to verify
as merged — and a `git status` that could not be run at all is treated as
dirty and counted separately as `UNINSPECTABLE`, because "I could not look" is
a tool failure and not the same event as "I looked and decided to skip".

## Staleness, conservatively

A worktree is "stale" — a *candidate* for removal, subject to every veto above
— if either:

1. **Merged** — every commit on its branch is already an ancestor of the
   target branch (`git merge-base --is-ancestor <branch> <target>`).
2. **Orphaned** — the directory exists but the branch it was checked out on no
   longer exists.

`--max-age-days` is a softer heuristic, off by default: it only ever adds a
note to a worktree that is already being surfaced. Age alone never removes
anything and never overrides a veto.

## Dry-run by default

Matches this project's convention for previewing bulk/destructive operations:
`--dry-run` is implicit unless `--apply` is passed.

Stdlib only.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# Origins. `agent` is decided by directory location and nothing else, per
# CLAUDE.md rule 1 — never by branch-name prefix.
PRIMARY = "primary"
AGENT = "agent"
EXTERNAL = "external"

AGENT_SUBDIR = (".claude", "worktrees")

# The lesson from #137, printed verbatim where it is actionable rather than
# left in a doc nobody reads at the moment they need it.
LESSON_137 = (
    "an uncommitted change in a worktree is not work, it is a rumour of work "
    "— commit it to a branch the moment it is noticed, even against a stale base."
)


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run git, converting "could not even start" into a non-zero result.

    `subprocess.run` *raises* OSError when `cwd` does not exist, rather than
    returning a failing process — and a worktree directory that has been moved
    or deleted out from under git is exactly that case. Letting it propagate
    would crash the whole run partway through the list, so the remaining
    worktrees would never be reported at all: the governing principle's failure
    mode, reached via a traceback instead of a silent skip. Returning a failed
    process instead routes it to the UNINSPECTABLE path, which names it.
    """
    try:
        return subprocess.run(
            args, cwd=cwd or REPO, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        return subprocess.CompletedProcess(args, returncode=127, stdout="", stderr=str(exc))


@dataclass
class Worktree:
    path: Path
    branch: str | None  # None if detached HEAD
    head: str
    is_locked: bool = False
    lock_reason: str = ""
    origin: str = EXTERNAL


@dataclass
class Verdict:
    worktree: Worktree
    stale: bool
    action: str  # "remove" | "skip"
    reasons: list[str] = field(default_factory=list)
    # A routine skip (unmerged, dirty tree, locked) is a decision this script made
    # correctly. `git status` itself failing is a tool failure — the script could
    # not check, and defaulted to the safe answer, but that is not the same event
    # and must not be counted the same way in the summary line. Conflating the two
    # is exactly the "found nothing vs could not look" failure this whole batch of
    # fixes is about, one level up: a broken git invocation would read as an
    # ordinary skip instead of something the operator should investigate.
    inspection_failed: bool = False
    # Populated only for the uncommitted-work veto, so the loud report can give a
    # file count instead of an adjective.
    dirty_files: list[str] = field(default_factory=list)


def agent_worktrees_dir(repo: Path) -> Path:
    return repo.joinpath(*AGENT_SUBDIR)


def classify(path: Path, repo: Path, is_primary: bool) -> str:
    """Which of the three origins this worktree has.

    `agent` is a question about **location** and deliberately not about the
    branch name: the Agent tool picks `worktree-agent-<hex>` itself at dispatch
    time and nothing in this repo can override that, so a name-based test would
    silently stop matching if that prefix ever changed. This is the half of the
    original design that was right, kept exactly as it was.
    """
    if is_primary:
        return PRIMARY
    try:
        path.relative_to(agent_worktrees_dir(repo).resolve())
    except ValueError:
        return EXTERNAL
    return AGENT


def list_worktrees(repo: Path | None = None) -> list[Worktree]:
    """Parse `git worktree list --porcelain` — **all** of it.

    Nothing is filtered out here any more. Scope decisions are made per-worktree
    in `evaluate()`, where they can be printed with a reason, instead of by an
    invisible filter that made 15 of 19 worktrees indistinguishable from
    worktrees that did not exist (#140).
    """
    repo = repo or REPO
    result = run(["git", "worktree", "list", "--porcelain"], cwd=repo)
    if result.returncode != 0:
        raise SystemExit(f"git worktree list failed: {result.stderr.strip()}")

    worktrees: list[Worktree] = []
    cur: dict[str, str] = {}

    def flush():
        if not cur:
            return
        path = Path(cur["worktree"]).resolve()
        # git's porcelain output always lists the main worktree first.
        is_primary = not worktrees
        worktrees.append(
            Worktree(
                path=path,
                branch=cur.get("branch", "").removeprefix("refs/heads/") or None,
                head=cur.get("HEAD", ""),
                is_locked="locked" in cur,
                lock_reason=cur.get("locked", ""),
                origin=classify(path, repo, is_primary),
            )
        )

    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            flush()
            cur = {"worktree": line[len("worktree "):]}
        elif line.startswith("HEAD "):
            cur["HEAD"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch "):]
        elif line == "detached":
            cur["branch"] = ""
        elif line == "locked":
            cur["locked"] = ""
        elif line.startswith("locked "):
            cur["locked"] = line[len("locked "):]
    flush()
    return worktrees


def branch_exists(branch: str, repo: Path | None = None) -> bool:
    return run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo,
    ).returncode == 0


def is_merged(branch: str, target: str, repo: Path | None = None) -> bool:
    if not branch_exists(branch, repo):
        return False
    return run(["git", "merge-base", "--is-ancestor", branch, target], cwd=repo).returncode == 0


def dir_age_days(path: Path) -> float | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return (time.time() - mtime) / 86400


def dirty_files(path: Path) -> list[str] | None:
    """Uncommitted/untracked paths in the worktree, or None if git could not be asked.

    None means "I could not look", which the caller treats as dirty — because
    "I don't know whether there is work here" must never read as "there is none".
    Returning the paths rather than a bool is what lets the report say "3 files"
    instead of "dirty"; a count is what makes someone stop and go look.
    """
    result = run(["git", "status", "--porcelain"], cwd=path)
    if result.returncode != 0:
        return None
    return [ln[3:].strip() for ln in result.stdout.splitlines() if ln.strip()]


def evaluate(wt: Worktree, target: str, max_age_days: float = 0,
             remove_dirty: bool = False, include_external: bool = False,
             repo: Path | None = None) -> Verdict:
    # The primary checkout is considered and reported — it is a worktree and
    # pretending otherwise is how things go missing — but it is never a
    # candidate. There is no flag for this.
    if wt.origin == PRIMARY:
        return Verdict(
            wt, stale=False, action="skip",
            reasons=["this is the repository's primary checkout — never removable"],
        )

    # Refusal 1: locked. Checked first because a locked worktree is one that is
    # in use *right now*, and nothing downstream (clean, merged, ancient) makes
    # it safe to pull out from under whoever holds it.
    if wt.is_locked:
        detail = (f"worktree is locked ({wt.lock_reason.strip()})"
                  if wt.lock_reason.strip() else "worktree is locked")
        return Verdict(
            wt, stale=False, action="skip",
            reasons=[f"{detail} — a lock is how an in-use worktree announces itself; will not remove"],
        )

    # Refusal 2: uncommitted work. Checked BEFORE merged/orphaned and ranking
    # above both.
    #
    # Measured: removal is `git worktree remove --force`, which deletes the
    # directory including uncommitted and untracked files. "Merged" is a fact
    # about the branch, not about the working tree — a worktree whose branch is
    # fully merged can still hold in-progress, never-committed work, and this
    # script destroyed it without a word.
    dirty = dirty_files(wt.path)
    if dirty != [] and not remove_dirty:
        if dirty is None:
            detail = "could not be inspected with `git status` — treating as dirty"
        else:
            detail = f"has {len(dirty)} uncommitted or untracked file(s)"
        return Verdict(
            wt, stale=False, action="skip",
            reasons=[f"worktree {detail}; `git worktree remove --force` would "
                     f"delete them — will not remove (--remove-dirty overrides)"],
            inspection_failed=(dirty is None),
            dirty_files=dirty or [],
        )

    if wt.branch is None:
        # Detached HEAD worktree: no branch to check for unmerged commits against.
        # Treat conservatively — never auto-remove, always surface for a human.
        return Verdict(
            wt, stale=False, action="skip",
            reasons=["detached HEAD — no branch to verify as merged; needs manual review"],
        )

    if not branch_exists(wt.branch, repo):
        verdict = Verdict(
            wt, stale=True, action="remove",
            reasons=[f"branch '{wt.branch}' no longer exists — worktree is orphaned"],
        )
    elif is_merged(wt.branch, target, repo):
        verdict = Verdict(
            wt, stale=True, action="remove",
            reasons=[f"branch '{wt.branch}' is fully merged into '{target}'"],
        )
    else:
        # Refusal 3: unmerged commits mean the worktree is NEVER removed by this
        # script, no matter how old it is. Age is only ever a reason to *surface*
        # a worktree for a human, never a reason to remove one on its own.
        reasons = [f"branch '{wt.branch}' has commits not yet in '{target}' — unmerged, will not remove"]
        if max_age_days > 0:
            age = dir_age_days(wt.path)
            if age is not None and age >= max_age_days:
                reasons.append(
                    f"also aged out ({age:.1f}d >= {max_age_days}d) but that does not "
                    f"override the unmerged-commits veto"
                )
        return Verdict(wt, stale=False, action="skip", reasons=reasons)

    # Scope gate, applied only at the point of removal — deliberately *after*
    # the three refusals, so a sibling worktree holding uncommitted work reports
    # the uncommitted work (the thing that matters) rather than a flag hint.
    if verdict.action == "remove" and wt.origin == EXTERNAL and not include_external:
        verdict.action = "skip"
        verdict.reasons.append(
            "but it is outside .claude/worktrees/ — a human's own worktree "
            "(CLAUDE.md rule 4) is not removed without --include-external"
        )
    return verdict


def remove_worktree(wt: Worktree, repo: Path | None = None) -> tuple[bool, str]:
    result = run(["git", "worktree", "remove", "--force", str(wt.path)], cwd=repo)
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, ""


def delete_branch(branch: str, repo: Path | None = None) -> tuple[bool, str]:
    result = run(["git", "branch", "-D", branch], cwd=repo)
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, ""


def display_path(path: Path, repo: Path) -> Path:
    """Shorten paths under the repo, but never to a bare `.`.

    The script's own checkout is one of the worktrees it reports, and relative-
    ising it yields `.` — which in a list of absolute paths reads as a rendering
    bug rather than as "this one, the one you are standing in". Keep it absolute.
    """
    if path == repo or not path.is_relative_to(repo):
        return path
    return path.relative_to(repo)


def print_uncommitted_report(verdicts: list[Verdict], repo: Path) -> None:
    """Say the uncommitted-work finding loudly, where someone will act on it.

    A one-line `skip` in a list of twenty is not the volume this finding
    deserves. The thing that was lost in #137 was exactly this: files in a
    worktree that nothing pruned and nobody was told about. So the file count
    and the remedy are printed as their own block, after the per-worktree lines,
    with the command to run.
    """
    dirty = [v for v in verdicts if v.dirty_files]
    if not dirty:
        return
    total = sum(len(v.dirty_files) for v in dirty)
    print(f"\n!! UNCOMMITTED WORK in {len(dirty)} worktree(s) — "
          f"{total} file(s) total, none of it on a branch.")
    print(f"   Lesson recorded in #137: {LESSON_137}")
    for v in dirty:
        rel = display_path(v.worktree.path, repo)
        print(f"\n   {rel}  [{v.worktree.branch or '(detached)'}]  — {len(v.dirty_files)} file(s)")
        for name in v.dirty_files[:10]:
            print(f"       {name}")
        if len(v.dirty_files) > 10:
            print(f"       ... and {len(v.dirty_files) - 10} more")
        print(f"       commit it first:  git -C {rel} checkout -b wip/<topic> && "
              f"git -C {rel} add -A && git -C {rel} commit -m 'wip: rescue uncommitted work'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target-branch", default="main", help="Branch to check merges against (default: main)")
    parser.add_argument("--max-age-days", type=float, default=0, help="Also surface worktrees older than N days (0 disables; never overrides the unmerged-commits veto)")
    parser.add_argument("--apply", action="store_true", help="Actually remove stale worktrees and delete their branches. Default is dry-run.")
    # Opt-in only, and deliberately not implied by --apply: the whole point of
    # the dirty check is that the destructive default was the bug.
    parser.add_argument("--remove-dirty", action="store_true",
                        help="Also remove worktrees with uncommitted or untracked changes. "
                             "Destroys that work irrecoverably. Off by default.")
    parser.add_argument("--include-external", action="store_true",
                        help="Also remove stale worktrees outside .claude/worktrees/ (e.g. a "
                             "'../suite-<topic>' sibling). They are always listed and always "
                             "evaluated; this flag only permits removing them.")
    parser.add_argument("--keep-branch", action="store_true", help="Remove the worktree but leave its (now-merged) branch in place.")
    args = parser.parse_args(argv)

    dry_run = not args.apply
    repo = REPO

    if not (repo / ".git").exists():
        raise SystemExit(f"not a git repo (or missing .git): {repo}")

    if not branch_exists(args.target_branch, repo) and run(
        ["git", "rev-parse", "--verify", "--quiet", args.target_branch], cwd=repo
    ).returncode != 0:
        raise SystemExit(f"target branch/ref '{args.target_branch}' does not exist")

    # NOTE: there is deliberately no "`.claude/worktrees/` does not exist, so
    # nothing to do" early return any more. That return was the loudest form of
    # this bug: on a repo with eight sibling worktrees and no agent worktrees it
    # printed "Nothing to do" and exited 0.
    worktrees = list_worktrees(repo)
    mode = "DRY RUN" if dry_run else "APPLY"
    scope = ("all worktrees" if args.include_external
             else "all worktrees (external ones reported, not removed)")
    print(f"[{mode}] scanning {scope} against target '{args.target_branch}'")

    if not worktrees:
        print("git worktree list reported no worktrees at all — that is unusual; "
              "even a plain clone reports its primary checkout. Investigate.")
        return 1

    verdicts = [evaluate(wt, args.target_branch, args.max_age_days,
                         args.remove_dirty, args.include_external, repo)
                for wt in worktrees]

    removed, skipped, failed, uninspectable = 0, 0, 0, 0
    by_origin: dict[str, int] = {PRIMARY: 0, AGENT: 0, EXTERNAL: 0}
    for v in verdicts:
        by_origin[v.worktree.origin] = by_origin.get(v.worktree.origin, 0) + 1
        rel = display_path(v.worktree.path, repo)
        branch_label = v.worktree.branch or "(detached)"
        origin_label = f"<{v.worktree.origin}>"
        reason_text = "; ".join(v.reasons)

        if v.action == "remove":
            if dry_run:
                print(f"  would-remove  {origin_label:<10} {rel}  [{branch_label}]  — {reason_text}")
                removed += 1
            else:
                ok, err = remove_worktree(v.worktree, repo)
                if not ok:
                    print(f"  FAILED        {origin_label:<10} {rel}  [{branch_label}]  — remove failed: {err}")
                    failed += 1
                    continue
                print(f"  removed       {origin_label:<10} {rel}  [{branch_label}]  — {reason_text}")
                removed += 1
                if v.worktree.branch and not args.keep_branch and branch_exists(v.worktree.branch, repo):
                    bok, berr = delete_branch(v.worktree.branch, repo)
                    if bok:
                        print(f"                deleted branch '{v.worktree.branch}'")
                    else:
                        print(f"                could not delete branch '{v.worktree.branch}': {berr}")
        else:
            label = "UNINSPECTABLE" if v.inspection_failed else "skip"
            print(f"  {label:<13} {origin_label:<10} {rel}  [{branch_label}]  — {reason_text}")
            skipped += 1
            if v.inspection_failed:
                uninspectable += 1

    if not dry_run and removed:
        prune = run(["git", "worktree", "prune"], cwd=repo)
        if prune.returncode != 0:
            print(f"  warning: git worktree prune failed: {prune.stderr.strip()}")
        else:
            print("  ran: git worktree prune")

    print_uncommitted_report(verdicts, repo)

    verb = "would remove" if dry_run else "removed"
    print(f"\n{len(worktrees)} worktree(s) considered "
          f"({by_origin[PRIMARY]} primary, {by_origin[AGENT]} agent, "
          f"{by_origin[EXTERNAL]} external): "
          f"{removed} {verb}, {skipped} skipped, {failed} failed.")
    if uninspectable:
        print(f"  {uninspectable} of those skips could not be inspected with `git status` — "
              f"that is a tool failure, not a decision. Investigate before assuming they are clean.")
    if dry_run and removed:
        print("Re-run with --apply to actually remove them.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
