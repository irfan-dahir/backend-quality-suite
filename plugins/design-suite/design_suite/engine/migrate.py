"""Moving one consumer project from one suite version to another, measurably.

Two halves, deliberately separated, because they have opposite blast radii:

  `measure()`   Runs the audits from BOTH suite versions against the consumer's
                tree and diffs exit codes and finding counts. Read-only, and read-
                only in the strong sense: it never runs anything inside the
                consumer's own directory at all. See "the copy" below.

  `apply()`     Writes, one named action at a time, after a human has said so.

## Why measuring cannot just run in place

Most audits write a findings envelope under `.design-suite/findings/` as a matter
of course — `repo_health.py` relies on exactly that. Running them twice in a
consumer's tree to *decide whether to upgrade* would therefore leave that tree
holding output from a version the project has not adopted, and would overwrite
the envelopes `/design-debt` grades. The measurement would have changed the thing
it was measuring, and the decision it exists to inform would no longer be
reversible.

So each version runs against its own copy of the consumer tree, made under the
system temporary directory, and the report names both copies. Reversibility is
the entire point of the exercise: nothing here should require a `git checkout` to
undo, because the consumer may have uncommitted work and because a measurement
that needs undoing is a measurement nobody will run twice.

## Why `init.py --force` is never used to apply

`init.py --force` rewrites `profile.json` from the template wholesale (see
`init.py`'s write loop), discarding every declared and ratified value the project
has accumulated — the provenance model's entire content. Upgrading a project's
config must therefore be a set of specific, individually refusable file copies,
which is what `apply()` is. There is no action here that writes `profile.json`.

## Every action is individually reportable and refusable

`apply()` returns one row per action with its own status, and `--only` / `--skip`
select between them. An action that will not run says why in its own row rather
than being dropped from the list — a plan that silently shortens is the same
failure as an audit that silently skips.

Stdlib only, like everything else here.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from . import audit_discovery, upgrade
from .upgrade import CannotDetermine

PLUGIN_PREFIX = upgrade.PLUGIN_PREFIX

# Directories never worth copying into a scratch tree: build output and package
# caches, which are large, and `.git`, which is large and irrelevant — no audit
# reads history. An audit that DID need history would have to be given the real
# tree, and that is a decision, not a default.
IGNORED_DIRS = (
    ".git", "node_modules", "build", ".dart_tool", ".venv", "venv",
    "__pycache__", ".next", "dist", ".gradle", "Pods", ".claude",
)

# The actions `apply()` knows how to take. Names are the CLI's `--only` vocabulary.
ACTIONS = ("sync-schema", "scaffold-hooks-map", "declare-config-keys", "rebaseline")

PROFILE = "profile.json"
SCHEMA = "profile.schema.json"
HOOKS_MAP = "hooks.map.json"
DOT = ".design-suite"


# ------------------------------------------------------------------ materialising


def materialize(repo: Path, rev: str, dest: Path) -> Path:
    """Extract one revision's plugin tree into `dest`, returning the plugin root.

    `git archive` into a tarball rather than `git worktree add`: a worktree
    registers itself in the repository's administrative files, which is a write
    to the suite repo in order to read it, and leaves something to clean up if
    this process dies. An archive is inert.
    """
    sha = upgrade.resolve_rev(repo, rev)
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "_tree.tar"
    with archive.open("wb") as fh:
        proc = subprocess.run(
            ["git", "-C", str(repo), "archive", "--format=tar", sha, "--", PLUGIN_PREFIX],
            stdout=fh, stderr=subprocess.PIPE, text=False, timeout=300,
        )
    if proc.returncode != 0:
        raise CannotDetermine(
            f"cannot export {rev} from {repo}: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    with tarfile.open(archive) as tar:
        tar.extractall(dest)
    archive.unlink()
    root = dest / PLUGIN_PREFIX
    if not (root / "bin").is_dir():
        raise CannotDetermine(
            f"{rev} exported no {PLUGIN_PREFIX}/bin — that is not a revision of "
            f"this plugin, so it cannot be measured against"
        )
    return root


def copy_consumer(consumer: Path, dest: Path) -> Path:
    """A scratch copy of the consumer tree. The original is never opened for write.

    Raises rather than copying a directory with no `.design-suite/`: a project
    that has not adopted the suite has no upgrade to measure, and measuring one
    anyway would produce a page of refusals that say nothing about the upgrade.
    """
    if not (consumer / DOT).is_dir():
        raise CannotDetermine(
            f"{consumer} has no {DOT}/ directory — it has not adopted the suite, "
            f"so there is no version-to-version difference to measure"
        )
    ignore = shutil.ignore_patterns(*IGNORED_DIRS)
    shutil.copytree(consumer, dest, ignore=ignore, symlinks=True,
                    ignore_dangling_symlinks=True)
    return dest


# ------------------------------------------------------------------- running one


def discover_audits(plugin_root: Path) -> dict[str, Path]:
    """`{stem: path}` for the audits a materialised plugin tree ships.

    Globs the same two homes `audit_discovery.discover()` does, but against a
    root passed in rather than this module's own — the point of the exercise is
    to ask a *different* version what it ships, and the installed copy's
    module-level constants cannot answer that. `NOT_AN_AUDIT` is reused from the
    installed registry rather than re-listed: it names scripts that audit the
    plugin itself, and a second copy of that list is the hand-maintained registry
    this repo keeps getting bitten by.
    """
    found = list((plugin_root / "bin").glob("audit_*.py"))
    found += (plugin_root / "design_suite" / "engine").glob("*/audit_*.py")
    return {
        p.stem: p for p in sorted(found)
        if not p.stem.endswith("_test") and p.name not in audit_discovery.NOT_AN_AUDIT
    }


def disabled_at(plugin_root: Path) -> set[str]:
    """The DISABLED set of a materialised plugin tree, read from its own source.

    Empty — with the caller expected to note it — when that tree has no registry
    module at all, for the same reason `upgrade.surface()` treats that case as a
    fact about the revision rather than a refusal.
    """
    path = plugin_root / "design_suite" / "engine" / "audit_discovery.py"
    if not path.is_file():
        return set()
    return upgrade.disabled_audits(path.read_text(), origin=str(path))


def run_audit(script: Path, tree: Path, timeout: float) -> dict:
    """One audit, from one version, against one scratch tree.

    Status vocabulary is `repo_health.py`'s, unchanged and for the same reasons:
    the verdict comes from the process's own exit code and is never re-derived by
    reading its output, and exit 2 is `refused`, never folded into `clean`.
    """
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tree)
    supports = audit_discovery.supports_findings_flag(script)
    cmd = [sys.executable, str(script)] + (["--findings"] if supports else [])
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(tree), capture_output=True, text=True,
                              timeout=timeout, env=env)
        code: int | None = proc.returncode
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
    except subprocess.TimeoutExpired:
        code, tail = None, [f"timed out after {timeout:.0f}s"]
    except OSError as exc:
        code, tail = None, [str(exc)]

    status = {0: "clean", 1: "findings", 2: "refused"}.get(code, "crashed")

    count = None
    if supports:
        name = audit_discovery.envelope_name(script) or script.stem.removeprefix("audit_")
        envelope = tree / DOT / "findings" / f"{name}.json"
        if envelope.is_file():
            try:
                count = len(json.loads(envelope.read_text()).get("findings", []))
            except (OSError, ValueError):
                count = None

    return {
        "status": status,
        "exitCode": code,
        "findingsCount": count,
        "durationSeconds": round(time.time() - t0, 2),
        "message": tail[-1] if tail else None,
    }


def _side(plugin_root: Path, tree: Path, stems: list[str], timeout: float) -> dict:
    audits = discover_audits(plugin_root)
    disabled = disabled_at(plugin_root)
    out: dict[str, dict] = {}
    for stem in stems:
        if stem in disabled:
            # Never run, never graded — the disabled row exists so that "switched
            # off" cannot be read as "found nothing", which is the same rule
            # repo_health.py's disabled row is built on.
            out[stem] = {"status": "disabled", "exitCode": None,
                         "findingsCount": None, "durationSeconds": 0.0,
                         "message": "in audit_discovery.DISABLED at this version"}
        elif stem not in audits:
            out[stem] = {"status": "absent", "exitCode": None,
                         "findingsCount": None, "durationSeconds": 0.0,
                         "message": "this version does not ship this audit"}
        else:
            out[stem] = run_audit(audits[stem], tree, timeout)
    return out


def measure(consumer: Path, repo: Path, old_rev: str, new_rev: str,
            *, only: str | None = None, timeout: float = 120.0,
            workdir: Path | None = None) -> dict:
    """Run both versions' audits against copies of the consumer and diff them.

    The consumer's own tree is read once, to copy it. Nothing under it is opened
    for writing, and the returned report names the two scratch trees so the
    reader can see that for themselves rather than taking this docstring's word.
    """
    consumer, repo = consumer.resolve(), repo.resolve()
    base = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="suite-upgrade-"))
    base.mkdir(parents=True, exist_ok=True)

    old_root = materialize(repo, old_rev, base / "old-suite")
    new_root = materialize(repo, new_rev, base / "new-suite")
    old_tree = copy_consumer(consumer, base / "old-tree")
    new_tree = copy_consumer(consumer, base / "new-tree")

    stems = sorted(set(discover_audits(old_root)) | set(discover_audits(new_root)))
    if only:
        stems = [s for s in stems if only.lower() in s.lower()]
    if not stems:
        raise CannotDetermine(
            f"no audit matched {only!r} in either version. Nothing ran, which is "
            f"not the same as nothing having changed"
        )

    old_side = _side(old_root, old_tree, stems, timeout)
    new_side = _side(new_root, new_tree, stems, timeout)

    rows = []
    for stem in stems:
        before, after = old_side[stem], new_side[stem]
        if before["status"] != after["status"]:
            verdict = "status-changed"
        elif before["exitCode"] != after["exitCode"]:
            verdict = "exit-changed"
        elif before["findingsCount"] != after["findingsCount"]:
            verdict = "count-changed"
        elif before["status"] in ("refused", "crashed", "disabled", "absent"):
            # Same non-answer on both sides is not agreement that the tree is
            # clean; it is two silences. Named so it cannot be counted as one.
            verdict = "no-answer-either-side"
        else:
            verdict = "unchanged"
        rows.append({"audit": stem, "before": before, "after": after,
                     "verdict": verdict})

    return {
        "consumer": str(consumer),
        "repo": str(repo),
        "old": {"rev": old_rev, "sha": upgrade.resolve_rev(repo, old_rev),
                "tree": str(old_tree), "plugin": str(old_root)},
        "new": {"rev": new_rev, "sha": upgrade.resolve_rev(repo, new_rev),
                "tree": str(new_tree), "plugin": str(new_root)},
        "readOnly": True,
        "note": (
            "Both runs used throwaway copies of the consumer tree, listed above "
            "as `tree`. The consumer's own directory was read to make those "
            "copies and was never written to — audits write findings envelopes "
            "by default, and a measurement that leaves output behind is not a "
            "reversible one."
        ),
        "audits": rows,
        "changed": [r["audit"] for r in rows if r["verdict"] != "unchanged"],
    }


# ------------------------------------------------------------------------ apply


def _row(action: str, status: str, detail: str, **extra) -> dict:
    record = {"action": action, "status": status, "detail": detail, "writes": []}
    record.update(extra)
    return record


def _sync_schema(consumer: Path, plugin_root: Path, write: bool) -> dict:
    src = plugin_root / "templates" / SCHEMA
    dest = consumer / DOT / SCHEMA
    if not src.is_file():
        return _row("sync-schema", "refused",
                    f"the target version ships no {src.name} at {src}")
    if dest.is_file() and dest.read_text() == src.read_text():
        return _row("sync-schema", "clean",
                    f"{dest} already matches the target version's schema")
    if not write:
        return _row("sync-schema", "planned",
                    f"would copy {src} to {dest} (this one file only — never "
                    f"init.py --force, which rewrites profile.json wholesale)",
                    writes=[str(dest)])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text())
    return _row("sync-schema", "applied", f"copied the target schema to {dest}",
                writes=[str(dest)])


def _scaffold_hooks_map(consumer: Path, plugin_root: Path, write: bool) -> dict:
    dest = consumer / DOT / HOOKS_MAP
    src = plugin_root / "templates" / "dot-design-suite" / f"{HOOKS_MAP}.template"
    if dest.exists():
        return _row("scaffold-hooks-map", "clean",
                    f"{dest} already exists — a project's own hook map is never "
                    f"overwritten by an upgrade")
    if not src.is_file():
        return _row("scaffold-hooks-map", "refused",
                    f"the target version ships no template at {src}")
    if not write:
        return _row("scaffold-hooks-map", "planned",
                    f"would scaffold {dest} from {src}", writes=[str(dest)])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text())
    return _row("scaffold-hooks-map", "applied", f"scaffolded {dest}",
                writes=[str(dest)])


def _declare_config_keys(consumer: Path, plugin_root: Path, write: bool) -> dict:
    """Name every newly-required profile key the consumer lacks. Writes nothing.

    Deliberately a refusal rather than an edit, even under `--apply`: a required
    key's *value* is a fact about the project — a source root, a token file, a
    framework — and inventing one produces a profile that validates and lies,
    which `doctor.py` exists because of. Writing `"TODO"` would be the same thing
    with a longer fuse.
    """
    schema_path = plugin_root / "templates" / SCHEMA
    profile_path = consumer / DOT / PROFILE
    if not schema_path.is_file():
        return _row("declare-config-keys", "refused",
                    f"the target version ships no {SCHEMA}, so its required keys "
                    f"cannot be read")
    if not profile_path.is_file():
        return _row("declare-config-keys", "refused",
                    f"{profile_path} does not exist — this project has no profile "
                    f"to upgrade. That is an adoption, which is a different "
                    f"operation with a different tool, and deliberately not this "
                    f"one's to start")
    try:
        profile = json.loads(profile_path.read_text())
        schema = json.loads(schema_path.read_text())
    except ValueError as exc:
        return _row("declare-config-keys", "refused",
                    f"cannot read the profile or schema as JSON: {exc}")

    required = [k for k in schema.get("required", []) if isinstance(k, str)]
    missing = sorted(k for k in required if k not in profile)
    if not missing:
        return _row("declare-config-keys", "clean",
                    "the profile carries every top-level key the target version "
                    "requires")
    return _row(
        "declare-config-keys", "refused",
        "the target version requires top-level profile keys this project does "
        "not declare: " + ", ".join(missing) + ". Their values are project facts "
        "only a human can supply, so nothing was written — add them, then re-run.",
        missingKeys=missing,
    )


def _rebaseline(consumer: Path, plugin_root: Path, write: bool,
                accept_new_for: tuple[str, ...], timeout: float) -> list[dict]:
    """Re-run each ratchet audit's `--update-baseline`, one row per audit.

    `--accept-new` is added only for audits the caller named, one at a time. That
    flag's whole purpose is that absorbing a new finding into a baseline is a
    sentence someone wrote (`engine/ratchet.py`), so a blanket "accept
    everything" option would hand back exactly what that guard took away.
    """
    rows: list[dict] = []
    for stem, script in sorted(discover_audits(plugin_root).items()):
        if "--update-baseline" not in upgrade.flags(script.read_text(), origin=str(script)):
            continue
        short = stem.removeprefix("audit_")
        accepted = stem in accept_new_for or short in accept_new_for
        cmd = [sys.executable, str(script), "--update-baseline"]
        if accepted:
            cmd.append("--accept-new")
        if not write:
            rows.append(_row(f"rebaseline:{short}", "planned",
                             f"would run: {' '.join(cmd)}"
                             + ("" if accepted else " (no --accept-new: it will "
                                "refuse if the new version finds anything new, "
                                "which is the point)")))
            continue
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(consumer)
        try:
            proc = subprocess.run(cmd, cwd=str(consumer), capture_output=True,
                                  text=True, timeout=timeout, env=env)
        except (OSError, subprocess.SubprocessError) as exc:
            rows.append(_row(f"rebaseline:{short}", "failed", str(exc)))
            continue
        tail = (proc.stderr or proc.stdout or "").strip()
        if proc.returncode == 0:
            rows.append(_row(f"rebaseline:{short}", "applied",
                             f"baseline updated"
                             + (" with --accept-new, as named by the caller"
                                if accepted else ""),
                             writes=["(this audit's own baseline file)"]))
        elif proc.returncode == 2:
            rows.append(_row(f"rebaseline:{short}", "refused",
                             tail.splitlines()[-1] if tail else
                             "refused with exit 2 and said nothing"))
        else:
            rows.append(_row(f"rebaseline:{short}", "failed",
                             f"exit {proc.returncode}: "
                             + (tail.splitlines()[-1] if tail else "")))
    if not rows:
        rows.append(_row("rebaseline", "clean",
                         "the target version ships no audit that takes "
                         "--update-baseline"))
    return rows


def apply(consumer: Path, plugin_root: Path, *, write: bool = False,
          only: tuple[str, ...] = (), skip: tuple[str, ...] = (),
          accept_new_for: tuple[str, ...] = (), timeout: float = 120.0) -> dict:
    """Run the selected migration actions. `write=False` plans and changes nothing.

    An action excluded by `--only`/`--skip` is still listed, with status
    `skipped`. A plan that silently shortens when you filter it is a plan you
    cannot check, and this is the surface where somebody is deciding what to let
    touch their project.
    """
    consumer = consumer.resolve()
    if not (consumer / DOT).is_dir():
        raise CannotDetermine(
            f"{consumer} has no {DOT}/ directory — nothing to migrate")

    unknown = sorted((set(only) | set(skip)) - set(ACTIONS))
    if unknown:
        raise CannotDetermine(
            f"unknown action(s): {', '.join(unknown)}. Known: {', '.join(ACTIONS)}")

    rows: list[dict] = []
    for action in ACTIONS:
        if (only and action not in only) or action in skip:
            rows.append(_row(action, "skipped", "excluded by the caller's selection"))
            continue
        if action == "sync-schema":
            rows.append(_sync_schema(consumer, plugin_root, write))
        elif action == "scaffold-hooks-map":
            rows.append(_scaffold_hooks_map(consumer, plugin_root, write))
        elif action == "declare-config-keys":
            rows.append(_declare_config_keys(consumer, plugin_root, write))
        elif action == "rebaseline":
            rows += _rebaseline(consumer, plugin_root, write, accept_new_for, timeout)

    return {
        "consumer": str(consumer),
        "plugin": str(plugin_root),
        "wrote": bool(write),
        "actions": rows,
        "refused": [r["action"] for r in rows if r["status"] == "refused"],
        "failed": [r["action"] for r in rows if r["status"] == "failed"],
        "pending": [r["action"] for r in rows if r["status"] == "planned"],
    }
