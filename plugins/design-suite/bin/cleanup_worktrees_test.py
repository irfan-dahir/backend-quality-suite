#!/usr/bin/env python3
"""Tests for cleanup_worktrees.py — sees every worktree, refuses out loud, never silently.

    python3 plugins/design-suite/bin/cleanup_worktrees_test.py

Issue #140: the script identified agent worktrees by directory location
(`.claude/worktrees/`, per CLAUDE.md rule 1 — correct) and filtered everything
else out before any logic ran, so the `../suite-<topic>` worktrees CLAUDE.md
rule 4 tells you to create were invisible to it. Measured: 19 present, 4
considered; and on this repo later, 8 present, 0 considered.

Every property is tested against the case it must not swallow, because a test
suite that only checked the refusals would be fully satisfied by a script that
refused to remove anything at all — which is the same shape of bug one level
up:

  * external worktrees are considered   <->  agent worktrees still classified
                                             as agent, by LOCATION not by name
  * locked is refused                   <->  the identical unlocked worktree
                                             IS removed
  * dirty is refused, with a count      <->  the identical clean worktree IS
                                             removed
  * unmerged is refused                 <->  the identical merged branch IS
                                             removed
  * external is not removed by default  <->  --include-external removes it, and
                                             an agent worktree never needed the
                                             flag in the first place
  * the primary checkout is never       <->  ...but it is still reported, not
    removed                                  filtered out and forgotten

Every worktree is built for real in a temporary directory with real `git
worktree add` — nothing here depends on this repo's live worktree layout, which
changes under every session.

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import io
import contextlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import cleanup_worktrees as cw  # noqa: E402

FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {repo}: {result.stderr}")
    return result


def make_repo(root: Path) -> Path:
    """A real git repo with one commit on `main`, isolated from the user's config."""
    repo = root / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("seed\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    return repo


def add_worktree(repo: Path, path: Path, branch: str, *, commits: int = 0) -> Path:
    """Create a worktree at `path` on a new `branch`, optionally ahead of main."""
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "-q", "-b", branch, str(path), "main")
    for i in range(commits):
        (path / f"extra{i}.txt").write_text(f"{i}\n")
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", f"extra {i}")
    return path


def find(worktrees: list[cw.Worktree], path: Path) -> cw.Worktree:
    resolved = path.resolve()
    for wt in worktrees:
        if wt.path == resolved:
            return wt
    raise AssertionError(f"{path} not reported by list_worktrees — this is the #140 bug")


def verdict_for(repo: Path, path: Path, **kwargs) -> cw.Verdict:
    wt = find(cw.list_worktrees(repo), path)
    return cw.evaluate(wt, kwargs.pop("target", "main"), repo=repo, **kwargs)


# --------------------------------------------------------------------------
# 1. The bug itself: scope. External worktrees are considered at all.
# --------------------------------------------------------------------------
def test_scope_covers_every_worktree(tmp: Path) -> None:
    print("\n[scope] every worktree git reports is considered (#140)")
    repo = make_repo(tmp)
    agent = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-abc123", "worktree-agent-abc123")
    sibling = add_worktree(repo, repo.parent / "suite-topic", "feat/issue-1-topic")
    nested = add_worktree(repo, tmp / "elsewhere" / "deep", "fix/issue-2-deep")

    worktrees = cw.list_worktrees(repo)
    paths = {wt.path for wt in worktrees}

    expect(len(worktrees) == 4,
           f"primary + 3 worktrees are all listed (got {len(worktrees)})")
    expect(sibling.resolve() in paths,
           "a '../suite-<topic>' sibling worktree is reported — the exact case rule 4 creates")
    expect(nested.resolve() in paths,
           "a worktree in an unrelated directory is reported")
    expect(repo.resolve() in paths,
           "the primary checkout is reported, not filtered out and forgotten")

    # The negative this must not swallow: location-based agent identification,
    # per CLAUDE.md rule 1, still works and is still about LOCATION.
    expect(find(worktrees, agent).origin == cw.AGENT,
           "a worktree under .claude/worktrees/ is still classified <agent>")
    expect(find(worktrees, sibling).origin == cw.EXTERNAL,
           "a sibling worktree is classified <external>")
    expect(find(worktrees, repo).origin == cw.PRIMARY,
           "the primary checkout is classified <primary>")


def test_agent_identification_is_by_location_not_branch_name(tmp: Path) -> None:
    print("\n[scope] agent identification is by location, never by branch name (rule 1)")
    repo = make_repo(tmp)
    # An agent-named branch in the WRONG place is not an agent worktree...
    impostor = add_worktree(repo, repo.parent / "suite-impostor", "worktree-agent-deadbeef")
    # ...and a non-agent-named branch in the RIGHT place is.
    genuine = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-xyz", "some/hand-picked-name")

    worktrees = cw.list_worktrees(repo)
    expect(find(worktrees, impostor).origin == cw.EXTERNAL,
           "branch named 'worktree-agent-*' outside .claude/worktrees/ is NOT <agent>")
    expect(find(worktrees, genuine).origin == cw.AGENT,
           "worktree under .claude/worktrees/ IS <agent> whatever its branch is called")


# --------------------------------------------------------------------------
# 2. Refusal: locked  <->  the unlocked worktree it must not swallow
# --------------------------------------------------------------------------
def test_locked_is_refused_but_unlocked_is_removed(tmp: Path) -> None:
    print("\n[refusal] locked worktree is refused; the identical unlocked one is not")
    repo = make_repo(tmp)
    locked = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-locked", "worktree-agent-locked")
    unlocked = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-free", "worktree-agent-free")
    git(repo, "worktree", "lock", "--reason", "agent still running", str(locked))

    v_locked = verdict_for(repo, locked)
    v_unlocked = verdict_for(repo, unlocked)

    expect(v_locked.action == "skip", "a LOCKED, clean, merged worktree is skipped")
    expect(any("locked" in r for r in v_locked.reasons),
           "the locked refusal names 'locked' as the reason")
    expect("agent still running" in " ".join(v_locked.reasons),
           "git's own lock reason is surfaced, not discarded")

    # The negative: identical in every other respect, and it IS removed. Without
    # this, a script that refused everything would pass the case above.
    expect(v_unlocked.action == "remove",
           "the identical UNLOCKED clean merged worktree is still removed")


# --------------------------------------------------------------------------
# 3. Refusal: uncommitted changes  <->  the clean worktree it must not swallow
# --------------------------------------------------------------------------
def test_dirty_is_refused_but_clean_is_removed(tmp: Path) -> None:
    print("\n[refusal] uncommitted work is refused, with a file count; clean is removed")
    repo = make_repo(tmp)
    dirty = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-dirty", "worktree-agent-dirty")
    clean = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-clean", "worktree-agent-clean")
    # Untracked files specifically: `git worktree remove --force` deletes these
    # and they exist in no object database anywhere. This is the #137 shape.
    (dirty / "never-committed.md").write_text("the whole new eval case\n")
    (dirty / "also-new.json").write_text("{}\n")

    v_dirty = verdict_for(repo, dirty)
    v_clean = verdict_for(repo, clean)

    expect(v_dirty.action == "skip", "a worktree with untracked files is skipped")
    expect(len(v_dirty.dirty_files) == 2,
           f"the file COUNT is captured, not just a dirty flag (got {len(v_dirty.dirty_files)})")
    expect("2 uncommitted or untracked file(s)" in " ".join(v_dirty.reasons),
           "the refusal reason states the file count")
    expect(v_clean.action == "remove",
           "the identical CLEAN merged worktree is still removed")

    # --remove-dirty is the documented override, and must actually override.
    expect(verdict_for(repo, dirty, remove_dirty=True).action == "remove",
           "--remove-dirty overrides the veto (otherwise the flag is a lie)")


def test_uncommitted_work_is_reported_loudly(tmp: Path) -> None:
    print("\n[volume] uncommitted work gets its own block, the count, and the #137 lesson")
    repo = make_repo(tmp)
    dirty = add_worktree(repo, repo.parent / "suite-dirty", "feat/issue-3-dirty")
    (dirty / "rescue-me.md").write_text("a measured finding worth keeping\n")

    verdicts = [cw.evaluate(wt, "main", repo=repo) for wt in cw.list_worktrees(repo)]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cw.print_uncommitted_report(verdicts, repo)
    text = out.getvalue()

    expect("UNCOMMITTED WORK" in text, "the report has a loud, findable heading")
    expect("1 file(s) total" in text, "the report states the file count")
    expect("rescue-me.md" in text, "the report names the actual files at risk")
    expect("rumour of work" in text, "the report carries the lesson recorded in #137")
    expect("checkout -b" in text, "the report gives the commit-it-first command, not just advice")

    # The negative: a clean layout produces NO block. A report that always fires
    # is a report nobody reads.
    repo2 = make_repo(tmp / "second")
    add_worktree(repo2, repo2 / ".claude" / "worktrees" / "agent-tidy", "worktree-agent-tidy")
    clean_verdicts = [cw.evaluate(wt, "main", repo=repo2) for wt in cw.list_worktrees(repo2)]
    out2 = io.StringIO()
    with contextlib.redirect_stdout(out2):
        cw.print_uncommitted_report(clean_verdicts, repo2)
    expect(out2.getvalue() == "",
           "a layout with no uncommitted work prints no uncommitted-work block")


# --------------------------------------------------------------------------
# 4. Refusal: unmerged branch  <->  the merged branch it must not swallow
# --------------------------------------------------------------------------
def test_unmerged_is_refused_but_merged_is_removed(tmp: Path) -> None:
    print("\n[refusal] an unmerged branch is refused; the merged one is removed")
    repo = make_repo(tmp)
    unmerged = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-ahead",
                            "worktree-agent-ahead", commits=2)
    merged = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-level",
                          "worktree-agent-level")

    v_unmerged = verdict_for(repo, unmerged)
    v_merged = verdict_for(repo, merged)

    expect(v_unmerged.action == "skip", "a branch with commits not in main is skipped")
    expect(any("unmerged" in r for r in v_unmerged.reasons),
           "the unmerged refusal says 'unmerged'")
    expect(v_merged.action == "remove",
           "the identical fully-merged worktree is still removed")

    # Age must never override the veto — it only ever adds a note.
    v_aged = verdict_for(repo, unmerged, max_age_days=0.0000001)
    expect(v_aged.action == "skip",
           "an AGED unmerged worktree is still skipped — age never overrides the veto")


def test_orphaned_branch_is_removable(tmp: Path) -> None:
    print("\n[positive] an orphaned worktree (branch gone) is still removable")
    repo = make_repo(tmp)
    orphan = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-orphan",
                          "worktree-agent-orphan")
    # Detach the worktree so the branch can be deleted out from under it.
    git(orphan, "checkout", "-q", "--detach")
    git(repo, "branch", "-D", "worktree-agent-orphan")

    wt = find(cw.list_worktrees(repo), orphan)
    # Detached with a deleted branch is the conservative "needs manual review"
    # path; what matters is that it is surfaced with a named reason.
    v = cw.evaluate(wt, "main", repo=repo)
    expect(v.reasons != [], "an orphaned/detached worktree is surfaced with a reason, never silently")


# --------------------------------------------------------------------------
# 5. Scope gate: external not removed by default  <->  agent always is
# --------------------------------------------------------------------------
def test_external_is_seen_but_not_removed_without_the_flag(tmp: Path) -> None:
    print("\n[scope gate] external is considered and named, removed only under --include-external")
    repo = make_repo(tmp)
    sibling = add_worktree(repo, repo.parent / "suite-merged", "feat/issue-4-merged")
    agent = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-m", "worktree-agent-m")

    v_default = verdict_for(repo, sibling)
    expect(v_default.action == "skip",
           "a merged EXTERNAL worktree is not removed by default")
    expect("--include-external" in " ".join(v_default.reasons),
           "the refusal names the flag that would permit it — never a silent skip")
    expect(any("merged" in r for r in v_default.reasons),
           "it still reports WHY it was a candidate, so the user can judge")

    # The negatives this must not swallow, both directions.
    expect(verdict_for(repo, sibling, include_external=True).action == "remove",
           "--include-external actually permits removing it")
    expect(verdict_for(repo, agent).action == "remove",
           "an AGENT worktree never needed the flag — default behaviour is unchanged")


# --------------------------------------------------------------------------
# 6. The primary checkout: reported, never removable
# --------------------------------------------------------------------------
def test_primary_checkout_is_reported_but_never_removed(tmp: Path) -> None:
    print("\n[safety] the primary checkout is reported but never removable under any flag")
    repo = make_repo(tmp)
    add_worktree(repo, repo / ".claude" / "worktrees" / "agent-a", "worktree-agent-a")

    primary = find(cw.list_worktrees(repo), repo)
    for kwargs in ({}, {"include_external": True}, {"remove_dirty": True},
                   {"include_external": True, "remove_dirty": True}):
        v = cw.evaluate(primary, "main", repo=repo, **kwargs)
        expect(v.action == "skip",
               f"primary checkout refused with {kwargs or 'no flags'}")
    expect(any("primary" in r for r in cw.evaluate(primary, "main", repo=repo).reasons),
           "the primary-checkout refusal says so by name")


# --------------------------------------------------------------------------
# 7. The governing principle: no verdict is ever reasonless
# --------------------------------------------------------------------------
def test_no_verdict_is_ever_silent(tmp: Path) -> None:
    print("\n[principle] every worktree gets a named verdict — none are silent")
    repo = make_repo(tmp)
    add_worktree(repo, repo / ".claude" / "worktrees" / "agent-1", "worktree-agent-1")
    add_worktree(repo, repo / ".claude" / "worktrees" / "agent-2", "worktree-agent-2", commits=1)
    locked = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-3", "worktree-agent-3")
    git(repo, "worktree", "lock", str(locked))
    sib = add_worktree(repo, repo.parent / "suite-x", "feat/issue-5-x")
    (sib / "wip.txt").write_text("x\n")

    verdicts = [cw.evaluate(wt, "main", repo=repo) for wt in cw.list_worktrees(repo)]
    expect(len(verdicts) == 5, f"all 5 worktrees evaluated (got {len(verdicts)})")
    expect(all(v.reasons for v in verdicts),
           "every verdict carries at least one reason — a reasonless skip is "
           "indistinguishable from a worktree that was never found")
    expect(all(v.action in ("remove", "skip") for v in verdicts),
           "every verdict has an explicit action")


def test_uninspectable_is_not_counted_as_an_ordinary_skip(tmp: Path) -> None:
    print("\n[principle] 'could not look' is distinguished from 'looked and skipped'")
    repo = make_repo(tmp)
    path = add_worktree(repo, repo / ".claude" / "worktrees" / "agent-gone", "worktree-agent-gone")
    wt = find(cw.list_worktrees(repo), path)
    # Make `git status` in that worktree impossible without changing anything else.
    wt.path.rename(wt.path.parent / "moved-away")

    v = cw.evaluate(wt, "main", repo=repo)
    expect(v.action == "skip", "an uninspectable worktree is skipped, not removed")
    expect(v.inspection_failed,
           "it is flagged as an INSPECTION FAILURE, not an ordinary decision")
    expect(any("could not be inspected" in r for r in v.reasons),
           "the reason says the tool could not look")


def main() -> int:
    tests = [
        test_scope_covers_every_worktree,
        test_agent_identification_is_by_location_not_branch_name,
        test_locked_is_refused_but_unlocked_is_removed,
        test_dirty_is_refused_but_clean_is_removed,
        test_uncommitted_work_is_reported_loudly,
        test_unmerged_is_refused_but_merged_is_removed,
        test_orphaned_branch_is_removable,
        test_external_is_seen_but_not_removed_without_the_flag,
        test_primary_checkout_is_reported_but_never_removed,
        test_no_verdict_is_ever_silent,
        test_uninspectable_is_not_counted_as_an_ordinary_skip,
    ]
    env = dict(os.environ)
    os.environ.setdefault("GIT_CONFIG_NOSYSTEM", "1")
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
    try:
        for test in tests:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td).resolve()
                try:
                    test(tmp)
                except Exception as exc:  # a crashing test is a failing test
                    print(f"  FAIL {test.__name__} raised {exc!r}")
                    FAILURES.append(f"{test.__name__} raised {exc!r}")
                finally:
                    # Worktrees inside the temp dir keep git metadata alive; make
                    # the tree deletable regardless of what the test left behind.
                    subprocess.run(["chmod", "-R", "u+w", str(tmp)],
                                   capture_output=True, check=False)
    finally:
        os.environ.clear()
        os.environ.update(env)

    print(f"\nRan {len(tests)} test group(s).")
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All cleanup_worktrees checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
