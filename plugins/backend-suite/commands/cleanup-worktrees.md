---
name: cleanup-worktrees
description: "Use after a session that fanned out worktree agents, or to find a worktree holding uncommitted work. Reports every git worktree (.claude/worktrees/ and ../suite-<topic>) and removes stale ones; refuses by name on locked, uncommitted, or unmerged ones. Dry-run by default; destructive under --apply."
invocation: explicit
maturity: unverified
---

# /cleanup-worktrees

Removing worktrees and deleting branches is destructive — this stays an
explicit command, never an auto-tier audit, per this project's own tier rule
(blast radius, not difficulty, decides tier).

## What this does

Runs `${CLAUDE_PLUGIN_ROOT}/bin/cleanup_worktrees.py`, which:

1. Lists **every** worktree `git worktree list` reports, and labels each with
   its origin:
   - `<primary>` — the repo's own checkout. Reported, never removable.
   - `<agent>` — under `.claude/worktrees/`, identified by **location** per
     `CLAUDE.md` rule 1 (the Agent tool names its own branches, so a
     name-based test would quietly stop matching). Removable when stale.
   - `<external>` — everything else, which is where rule 4's
     `../suite-<topic>` lands. Reported by default, removed only under
     `--include-external`.
2. For each, checks whether its branch is fully merged into the target branch
   (default `main`), or orphaned (branch no longer exists).
3. Refuses, **each refusal named in the output**, on a worktree that is
   locked (how an in-use worktree announces itself), has uncommitted or
   untracked changes, or has unmerged commits — regardless of age.
4. Reports uncommitted work **loudly**, in its own block, with the file count,
   the files, and the command to commit it to a branch first. That is the
   thing #137 lost; a one-line skip is the wrong volume for it.
5. Reports every worktree considered and why (removed / would-remove / skip /
   UNINSPECTABLE) — a run that finds nothing to do says so explicitly, it
   never looks the same as a run that silently skipped something.

### Why this covers siblings now (issue #140)

The script used to filter out everything outside `.claude/worktrees/` before
any logic ran. Rule 1 (identify agents by location) and rule 4 (put your own
worktrees at `../suite-<topic>`) are each correct, and they did not meet: the
project's own instructions produced worktrees its own cleanup tool could not
see. Measured on this repo: 8 worktrees present, `0 worktree(s) considered`.

## Step 1 — Preview

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cleanup_worktrees.py"
```

This is a dry run — nothing is removed. Read the output: every worktree is
listed as `would-remove` (merged/orphaned) or `skip` (unmerged, locked, dirty,
external, primary, or detached HEAD) with a reason, and any uncommitted work is
called out in its own block at the end.

**If that block appears, deal with it before anything else.** The lesson
recorded in #137: an uncommitted change in a worktree is not work, it is a
rumour of work — commit it to a branch the moment it is noticed, even against
a stale base.

## Step 2 — Confirm with the user before applying

Show the dry-run output and ask for explicit go-ahead before running with
`--apply` — this is a destructive, bulk operation and the user should see
exactly what will be removed first, per this project's persona/CLAUDE.md
preference for previewing before applying.

## Step 3 — Apply

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cleanup_worktrees.py" --apply
```

Removes each stale worktree (`git worktree remove --force`), deletes its
now-merged branch (unless `--keep-branch` is passed), and runs
`git worktree prune`.

## Useful flags

- `--target-branch <name>` — check merges against a branch other than `main`.
- `--max-age-days N` — also surface worktrees older than N days as candidates
  worth a look. This never overrides the unmerged-commits veto; it only adds
  visibility, it does not loosen safety.
- `--keep-branch` — remove the worktree directory but leave the branch alone.
- `--include-external` — permit removing stale worktrees outside
  `.claude/worktrees/`. They are always listed and always evaluated; this flag
  only lifts the removal refusal. Ask the user first — a `../suite-<topic>`
  worktree is theirs, not the tool's.
- `--remove-dirty` — remove worktrees with uncommitted or untracked changes.
  Destroys that work irrecoverably, is off by default, and is deliberately not
  implied by `--apply`.

## What you must never do

- Never pass `--include-external` without showing the user which external
  worktrees it would remove and getting explicit agreement. Listing them is
  the fix; deleting someone's own worktree by default is not.
- Never pass `--remove-dirty` to make a run "come out clean". The uncommitted
  files it destroys exist in no object database anywhere.
- Never remove a **locked** worktree by hand to work around the refusal. A
  lock means something is using it right now.
- Never run `--apply` without showing the dry-run output and getting explicit
  confirmation first.
- Never treat a worktree with unmerged commits as safe to remove because it
  is old — age is only ever a reason to mention a worktree, never a reason to
  remove one that still has unmerged work.
