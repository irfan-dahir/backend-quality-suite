"""Onboarding and chain tools for the backend-suite MCP server.

Why these are MCP *tools* and not prompts: the harness support matrix
(docs/research/harness-support-matrix-2026-10-08.md) found tools are the only
MCP primitive every MCP-capable harness supports; prompts are patchy. So the
SessionStart onboarding offer, the survey/init/map steps and the chain driver
are all exposed here as tools, and the Claude-only hook stays as it was.

Thin wrappers, by rule. Every tool shells out to an existing script under
`bin/` (or, for `project_status`, imports the SessionStart hook's own
`classify()`), so no classification, survey, scaffolding or sequencing logic
is duplicated here. What this file owns is only the *preview/apply contract*
for tools that write:

  * A writing tool called without `confirm: true` runs its script against a
    scratch COPY of the project, diffs the copy before/after, and returns the
    exact planned writes plus a `preview_id`. The real project is not touched.
  * The `preview_id` is a SHA-256 over the tool, its arguments, the project
    root, a hash of the project's current contents, and the path + content
    hash of every planned write. The planned bytes are stored under the
    system temp dir, keyed by that id.
  * Applying needs `confirm: true` AND that `preview_id`. The id must be known,
    must have been produced by the same tool with the same arguments, and the
    project must be byte-for-byte unchanged since the preview (stale preview →
    refuse). Only then are exactly the previewed bytes written — the script is
    not re-run, so a model cannot apply something other than what was shown.

Every refusal is an MCP error result with a named reason, never an empty
success (the governing principle: a tool that did nothing must not look like
one that did its job).

LIMITATIONS
  * The scratch copy skips the same heavyweight directories the SessionStart
    hook skips (`.git`, `node_modules`, `build`, ...). A script that wrote into
    one of those would have that write missed by the preview — none of the
    wrapped scripts do today. Projects over the copy budget refuse to preview
    rather than previewing partially.
  * Self-tested over stdio JSON-RPC only (bin/mcp_onboarding_test.py), not
    against a real MCP client.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = MCP_DIR.parent
BIN = PLUGIN_ROOT / "bin"
HOOK = PLUGIN_ROOT / "hooks" / "session_start_onboarding.py"

PREVIEW_STORE = Path(tempfile.gettempdir()) / "backend-suite-mcp-previews"
MAX_FILES = 20000
MAX_BYTES = 200 * 1024 * 1024
TIMEOUT = 300.0


class Refusal(Exception):
    """A named refusal, surfaced to the client as an MCP error result."""


def _hook():
    spec = importlib.util.spec_from_file_location("_ds_session_start_onboarding", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def target_root() -> Path:
    """The same directory the SessionStart hook would classify."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def _run(args: list[str], root: Path, timeout: float = TIMEOUT) -> tuple[int | None, str, str]:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    try:
        p = subprocess.run([sys.executable, *args], cwd=root, env=env,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return None, "", f"timed out after {timeout:.0f}s"


def _script_result(name: str, code, out: str, err: str, real: Path | None = None,
                   scratch: Path | None = None) -> dict:
    def fix(s: str) -> str:
        return s.replace(str(scratch), str(real)) if scratch and real else s
    if code is None:
        raise Refusal(f"{name} timed out: {err}")
    if code == 2:
        raise Refusal(f"{name} refused (exit 2): {fix(err or out).strip()}")
    if code not in (0, 1):
        raise Refusal(f"{name} crashed (exit {code}): {fix(err or out).strip()[-2000:]}")
    return {"script": name, "exitCode": code, "stdout": fix(out).strip(), "stderr": fix(err).strip()}


# --- read-only tools --------------------------------------------------------

def project_status(args: dict) -> dict:
    hook = _hook()
    root = target_root()
    state, reason = hook.classify(root)
    result = {
        "projectRoot": str(root),
        "state": state,
        "reason": reason,
        "offer": hook.render(state, reason),
        "instruction": ("OFFER onboarding to the user if the state calls for it; never start "
                        "it. Every onboarding step writes files and needs the user's yes."),
    }
    if state != "configured":
        result["audits"] = None
        result["auditsNote"] = (f"audits not run: project is {state!r}, not configured, so every "
                                "audit would refuse. This is not a clean result.")
        return result
    if not args.get("include_audits", True):
        result["audits"] = None
        result["auditsNote"] = "audits not run: include_audits was false. Not a clean result."
        return result
    code, out, err = _run([str(BIN / "repo_health.py"), "--json"], root)
    if code is None or not out.strip():
        raise Refusal(f"repo_health.py produced no report (exit {code}): {err.strip()[-1000:]}")
    try:
        report = json.loads(out)
    except ValueError as exc:
        raise Refusal(f"repo_health.py output was not JSON: {exc}")
    rows = report.get("audits", [])
    result["audits"] = {
        "configured": [r["audit"] for r in rows if r.get("status") not in ("refused", "disabled")],
        "refusing": [{"audit": r["audit"], "why": r.get("message")}
                     for r in rows if r.get("status") == "refused"],
        "disabled": [{"audit": r["audit"], "why": r.get("message")}
                     for r in rows if r.get("status") == "disabled"],
        "rows": rows,
    }
    return result


def survey(args: dict) -> dict:
    root = target_root()
    cmd = [str(BIN / "survey.py"), "--project-root", str(root)]
    if args.get("check"):
        cmd += ["--check", "--json"]
    return _script_result("survey.py", *_run(cmd, root))


def resolve_role(args: dict) -> dict:
    root = target_root()
    cmd = [str(BIN / "resolve.py")]
    if args.get("role"):
        cmd.append(str(args["role"]))
    else:
        cmd.append("--all")
    return _script_result("resolve.py", *_run(cmd, root))


def doctor(args: dict) -> dict:
    root = target_root()
    return _script_result("doctor.py", *_run([str(BIN / "doctor.py")], root))


def repo_health(args: dict) -> dict:
    root = target_root()
    cmd = [str(BIN / "repo_health.py"), "--json"]
    if args.get("filter"):
        cmd += ["-k", str(args["filter"])]
    res = _script_result("repo_health.py", *_run(cmd, root))
    try:
        res["report"] = json.loads(res.pop("stdout"))
    except ValueError:
        pass
    return res


def chain_status(args: dict) -> dict:
    root = target_root()
    return _script_result("chain.py", *_run(
        [str(BIN / "chain.py"), "status", _chain(args), "--json"], root))


def chain_next(args: dict) -> dict:
    root = target_root()
    return _script_result("chain.py", *_run(
        [str(BIN / "chain.py"), "next", _chain(args), "--json"], root))


def _chain(args: dict) -> str:
    chain = args.get("chain")
    if not chain:
        raise Refusal("missing required argument 'chain'")
    return str(chain)


# --- preview / apply --------------------------------------------------------

def _skip(name: str) -> bool:
    return name in _hook().SKIP_DIRS


def _snapshot(root: Path) -> dict[str, str]:
    skip = _hook().SKIP_DIRS
    out: dict[str, str] = {}
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.is_symlink() or not p.is_file():
                continue
            data = p.read_bytes()
            total += len(data)
            if len(out) >= MAX_FILES or total > MAX_BYTES:
                raise Refusal(f"project exceeds the preview budget ({MAX_FILES} files / "
                              f"{MAX_BYTES // (1024 * 1024)} MB); refusing to preview partially")
            out[p.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    return out


def _tree_hash(snap: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest()


def _argv(tool: str, args: dict, root: Path, tmp: Path) -> list[str]:
    if tool == "init_from_survey":
        cmd = [str(BIN / "init.py"), "--dir", str(root), "--from-survey"]
        if args.get("name"):
            cmd += ["--name", str(args["name"])]
        if args.get("force"):
            cmd.append("--force")
        return cmd
    if tool == "map_project":
        cmd = [str(BIN / "map_project.py"), "--dir", str(root)]
        if args.get("proposals") is not None:
            f = tmp / "proposals.json"
            f.write_text(json.dumps(args["proposals"]))
            return cmd + ["--proposals", str(f)]
        for key in ("field", "value", "evidence"):
            if args.get(key) is None:
                raise Refusal(f"map_project needs either 'proposals' or field/value/evidence; "
                              f"missing {key!r}")
        cmd += ["--field", str(args["field"]), "--value", str(args["value"]),
                "--evidence", str(args["evidence"])]
        for c in args.get("candidates") or []:
            cmd += ["--candidate", str(c)]
        return cmd
    if tool == "chain_checkpoint":
        if not args.get("step"):
            raise Refusal("missing required argument 'step'")
        action = args.get("action", "done")
        if action not in ("done", "skip"):
            raise Refusal(f"action must be 'done' or 'skip', not {action!r}")
        cmd = [str(BIN / "chain.py"), action, _chain(args), str(args["step"])]
        if args.get("note"):
            cmd += ["--note", str(args["note"])]
        return cmd
    raise Refusal(f"unknown writing tool {tool!r}")


_PLAN_KEYS = {"init_from_survey": ("name", "force"),
              "map_project": ("proposals", "field", "value", "evidence", "candidates"),
              "chain_checkpoint": ("chain", "step", "action", "note")}


def _plan(tool: str, args: dict) -> dict:
    root = target_root()
    if not root.is_dir():
        raise Refusal(f"{root} is not a directory")
    plan_args = {k: args.get(k) for k in _PLAN_KEYS[tool] if args.get(k) is not None}
    base = _snapshot(root)
    work = Path(tempfile.mkdtemp(prefix="ds-preview-"))
    try:
        scratch = work / "project"
        shutil.copytree(root, scratch, symlinks=True,
                        ignore=lambda d, names: [n for n in names if _skip(n)])
        before = _snapshot(scratch)
        code, out, err = _run(_argv(tool, plan_args, scratch, work), scratch)
        script = _script_result(Path(_argv(tool, plan_args, scratch, work)[0]).name,
                                code, out, err, root, scratch)
        after = _snapshot(scratch)
        writes = {}
        for rel in sorted(set(before) | set(after)):
            if before.get(rel) != after.get(rel):
                writes[rel] = after.get(rel)  # None = delete
        id_src = {"tool": tool, "args": plan_args, "root": str(root),
                  "base": _tree_hash(base), "writes": writes}
        pid = hashlib.sha256(json.dumps(id_src, sort_keys=True).encode()).hexdigest()
        store = PREVIEW_STORE / pid
        if store.exists():
            shutil.rmtree(store)
        (store / "files").mkdir(parents=True)
        for rel, h in writes.items():
            if h is not None:
                dest = store / "files" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(scratch / rel, dest)
        (store / "manifest.json").write_text(json.dumps(id_src, sort_keys=True))
        return {"preview_id": pid, "script": script, "writes": writes, "root": root,
                "plan_args": plan_args}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _preview_text(plan: dict) -> dict:
    store = PREVIEW_STORE / plan["preview_id"] / "files"
    files = []
    for rel, h in plan["writes"].items():
        entry = {"path": rel, "action": "delete" if h is None else "write", "sha256": h}
        if h is not None:
            data = (store / rel).read_bytes()
            try:
                entry["content"] = data.decode("utf-8")
            except UnicodeDecodeError:
                entry["content"] = f"<{len(data)} bytes, binary>"
        files.append(entry)
    return files


def writing_tool(tool: str, args: dict) -> dict:
    if not args.get("confirm"):
        plan = _plan(tool, args)
        return {
            "mode": "preview",
            "projectRoot": str(plan["root"]),
            "wroteNothing": True,
            "preview_id": plan["preview_id"],
            "plannedWrites": _preview_text(plan),
            "scriptOutput": plan["script"],
            "next": ("Show these planned writes to the user. Only if they say yes, call this "
                     "tool again with the same arguments plus confirm: true and this preview_id."),
        }
    pid = args.get("preview_id")
    if not pid:
        raise Refusal("confirm: true requires a preview_id from a preview call of this tool; "
                      "refusing to write anything the user has not been shown")
    store = PREVIEW_STORE / str(pid)
    manifest_path = store / "manifest.json"
    if "/" in str(pid) or not manifest_path.is_file():
        raise Refusal(f"unknown preview_id {pid!r}: no stored preview (expired or never made); "
                      "preview again")
    manifest = json.loads(manifest_path.read_text())
    root = target_root()
    plan_args = {k: args.get(k) for k in _PLAN_KEYS[tool] if args.get(k) is not None}
    if manifest["tool"] != tool or manifest["args"] != plan_args or manifest["root"] != str(root):
        raise Refusal("preview_id does not match this call: it was made for a different tool, "
                      "arguments, or project; preview again")
    if _tree_hash(_snapshot(root)) != manifest["base"]:
        raise Refusal("stale preview: the project changed since the preview was made; "
                      "preview again so the user sees what would actually be written")
    written = []
    for rel, h in manifest["writes"].items():
        dest = root / rel
        if h is None:
            if dest.exists():
                dest.unlink()
            written.append({"path": rel, "action": "delete"})
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(store / "files" / rel, dest)
            written.append({"path": rel, "action": "write", "sha256": h})
    shutil.rmtree(store, ignore_errors=True)
    return {"mode": "applied", "projectRoot": str(root), "preview_id": pid, "written": written}


# --- registry ---------------------------------------------------------------

_NONE = {"type": "object", "properties": {}, "additionalProperties": False}
_CONFIRM = {
    "confirm": {"type": "boolean", "description": "Apply. Requires preview_id. Default false = preview only."},
    "preview_id": {"type": "string", "description": "The id returned by the preview of this exact call."},
}
_WRITE_NOTE = (" PREVIEW BY DEFAULT: without confirm it writes nothing and returns the exact "
               "planned writes plus a preview_id. Applying requires a second call with "
               "confirm: true and that preview_id, after the user has seen and approved the "
               "preview; a stale or mismatched preview_id is refused.")

TOOLS = {
    "project_status": (project_status, {
        "description": (
            "Read-only. Classify this project the same way the backend-suite SessionStart hook "
            "does (configured / new / existing / partial / declined / unclassifiable) and, when "
            "configured, list which audits are configured, refusing (with why), or disabled. "
            "Writes nothing. Call it at the start of a session in any harness. If the state is "
            "new, existing or partial, OFFER onboarding to the user — never start it yourself; "
            "every onboarding step writes files and needs the user's explicit yes. If declined, "
            "do not raise onboarding."),
        "inputSchema": {"type": "object", "properties": {
            "include_audits": {"type": "boolean", "description": "Run repo_health for the audit list (default true)."}},
            "additionalProperties": False}}),
    "survey": (survey, {
        "description": ("Survey the project (bin/survey.py). Writes ONLY .backend-suite/survey.json "
                        "and nothing else; with check: true it writes nothing and diffs disk "
                        "against the declared config."),
        "inputSchema": {"type": "object", "properties": {"check": {"type": "boolean"}},
                        "additionalProperties": False}}),
    "resolve_role": (resolve_role, {
        "description": "Read-only. Resolve a doc role to its path (bin/resolve.py); no role = all roles. Refuses if unresolvable.",
        "inputSchema": {"type": "object", "properties": {"role": {"type": "string"}},
                        "additionalProperties": False}}),
    "doctor": (doctor, {
        "description": "Read-only. Run bin/doctor.py: config health, untrusted (inferred) fields, unresolved paths.",
        "inputSchema": _NONE}),
    "repo_health": (repo_health, {
        "description": ("Report-only. Run every audit fresh (bin/repo_health.py --json): which are "
                        "clean, have findings, refused, or disabled. Writes only audit report files."),
        "inputSchema": {"type": "object", "properties": {"filter": {"type": "string", "description": "only audits whose name contains this"}},
                        "additionalProperties": False}}),
    "init_from_survey": (lambda a: writing_tool("init_from_survey", a), {
        "description": ("Scaffold .backend-suite/ from the survey (bin/init.py --from-survey); every "
                        "seeded field is written 'inferred'." + _WRITE_NOTE),
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string"}, "force": {"type": "boolean"}, **_CONFIRM},
            "additionalProperties": False}}),
    "map_project": (lambda a: writing_tool("map_project", a), {
        "description": ("Record doc-role / project-kind / token-source proposals in the profile as "
                        "'inferred' (bin/map_project.py). Pass either proposals (list of "
                        "{field, value, evidence, candidates}) or field/value/evidence." + _WRITE_NOTE),
        "inputSchema": {"type": "object", "properties": {
            "proposals": {"type": "array", "items": {"type": "object"}},
            "field": {"type": "string"}, "value": {"type": "string"},
            "evidence": {"type": "string"},
            "candidates": {"type": "array", "items": {"type": "string"}}, **_CONFIRM},
            "additionalProperties": False}}),
    "chain_status": (chain_status, {
        "description": "Read-only. Every step of a chain (e.g. onboard-new-client, understand-existing-project) with its status (bin/chain.py status).",
        "inputSchema": {"type": "object", "properties": {"chain": {"type": "string"}},
                        "required": ["chain"], "additionalProperties": False}}),
    "chain_next": (chain_next, {
        "description": ("Read-only. The next step of a chain, or the checkpoint blocking it (bin/chain.py "
                        "next). Never runs the step: you run its skill in conversation."),
        "inputSchema": {"type": "object", "properties": {"chain": {"type": "string"}},
                        "required": ["chain"], "additionalProperties": False}}),
    "chain_checkpoint": (lambda a: writing_tool("chain_checkpoint", a), {
        "description": ("Record a chain step's outcome (bin/chain.py done/skip). A checkpointed step "
                        "never advances on one call: the first applied 'done' records the run and "
                        "leaves it awaiting sign-off; a second applied 'done' records the user's "
                        "sign-off and lets the chain move on. Only apply after the user has "
                        "actually approved that step's output." + _WRITE_NOTE),
        "inputSchema": {"type": "object", "properties": {
            "chain": {"type": "string"}, "step": {"type": "string"},
            "action": {"type": "string", "enum": ["done", "skip"], "description": "default done"},
            "note": {"type": "string"}, **_CONFIRM},
            "required": ["chain", "step"], "additionalProperties": False}}),
}


def list_tools() -> list[dict]:
    return [{"name": n, **spec} for n, (_, spec) in TOOLS.items()]


def call(name: str, args: dict) -> tuple[dict, bool]:
    """(result, is_error). Refusals become error results carrying the reason."""
    fn = TOOLS[name][0]
    try:
        return fn(args or {}), False
    except Refusal as exc:
        return {"tool": name, "refused": True, "reason": str(exc)}, True
