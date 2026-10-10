#!/usr/bin/env python3
"""A generic MCP server that exposes this plugin's own audits as MCP tools.

    python3 plugins/design-suite/mcp/audit_server.py

This is the smallest honest v1 from issue #67's research comment, after the
initial recommendation to defer was overridden: "one generic server that shells
out to `audit_*.py --findings` and returns JSON, not a reimplementation of
profile/tier logic." It is a thin wrapper, nothing more:

  * discovery is `design_suite.engine.audit_discovery.discover()` — the exact
    function `repo_health.py` (issue #54) already uses, factored out rather
    than reimplemented, so "which scripts count as an audit" has one answer;
  * each tool call is `python3 <script>.py --findings` (or, for the audits
    that do not yet support that flag — see LIMITATIONS below — a plain
    invocation with the caveat surfaced in the result, never silently
    upgraded to look structured when it is not);
  * nothing here resolves a profile, picks an adapter, or grades a finding.
    That logic belongs to the audit scripts and to `design_debt.py`; this
    server does not know it exists.

## Protocol

Implements the Model Context Protocol's stdio transport directly: newline-
delimited JSON-RPC 2.0 on stdin/stdout, handling exactly the three messages a
tools-only server needs (`initialize`, `notifications/initialized`,
`tools/list`, `tools/call`). See LIMITATIONS for why this is hand-rolled
instead of built on the official `mcp` Python SDK.

## LIMITATIONS — read before extending this file

1. **No MCP SDK — by necessity, not preference.** Every script under
   `plugins/design-suite/bin/` is stdlib-only by explicit, repeated rule
   (`repo_health.py`'s own docstring: "Stdlib only, like everything else
   here"; the same is true of `audit_discovery.py`). The real `mcp` package
   (`pip install mcp`) is not installed in this environment and is not a
   stdlib module — adding it as a dependency would be the first non-stdlib
   dependency this plugin has ever taken on, for infrastructure the original
   research recommended deferring. Rather than quietly adding that dependency,
   this file hand-implements the minimal slice of the MCP stdio protocol
   (JSON-RPC 2.0 framing, `initialize`/`tools/list`/`tools/call`) using only
   `json`, `sys`, and `subprocess`. That is a real tradeoff: this server does
   not get the official SDK's request validation, capability negotiation
   nuances, SSE transport, or future-protocol-version handling for free, and
   any of those gaps would need to be re-litigated by hand if they matter
   later. If this ever graduates past exploration, taking the `mcp` SDK
   dependency for real (and deciding what "stdlib only" then means for this
   one directory) is the honest next step, not a longer hand-rolled protocol
   implementation.

2. **`--findings` support is not uniform across audits.** At the time this was
   written, these `audit_*.py` scripts do NOT accept `--findings` (grepped via
   `audit_discovery.supports_findings_flag`, same check `repo_health.py`
   uses): `audit_api_consistency.py`, `audit_claude_md_drift.py`,
   `audit_proposal_status.py`, `audit_unused_tokens.py`,
   `audit_unwired_roles.py`. Calling one of those tools runs the script with
   no flags and returns its raw stdout/stderr tail plus exit code, tagged
   `"structured": false` — never a fabricated findings envelope. This mirrors
   exactly what `repo_health.py` already does (`supportsFindingsEnvelope`),
   because inventing a different convention here would be a second copy of
   that same "does this audit support the envelope" fact to drift out of
   sync with the first.

3. **Not tested end-to-end against a real MCP client.** No MCP client (Claude
   Desktop, an SDK client) was available in this environment. Testing here
   was: (a) unit-level, calling this file's own `list_tools()` /
   `call_tool()` functions directly; (b) protocol-level, driving the script's
   stdin/stdout as a subprocess with hand-written JSON-RPC frames matching the
   `initialize` → `notifications/initialized` → `tools/list` → `tools/call`
   sequence a real client would send. That is not the same as a real client
   round-trip and should be treated as `self-tested`
   (`templates/verification-tier.schema.json`), not `cross-verified`.

4. **One process per call, no session state, no cancellation.** Each
   `tools/call` blocks on a `subprocess.run` with a fixed timeout and returns
   once the audit exits. There is no streaming of partial output and no way
   to cancel a running audit from the client side. Fine for audits that run in
   seconds; not fine as a general job-runner.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = MCP_DIR.parent
BIN = PLUGIN_ROOT / "bin"

if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from design_suite.engine import audit_discovery  # noqa: E402
from design_suite.engine import findings as F  # noqa: E402
from design_suite.project import project_root  # noqa: E402

if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))
import onboarding_tools  # noqa: E402  - onboarding/chain tools (preview/apply contract)

INSTRUCTIONS = (
    "design-suite: call project_status first. If it reports new/existing/partial, OFFER "
    "onboarding; never start it without the user's yes. Writing tools preview by default and "
    "apply only with confirm: true plus the preview_id the user saw. An audit that refuses or "
    "is disabled (INERT) is not a clean result."
)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "design-suite-audits"
SERVER_VERSION = "0.1.0"
DEFAULT_TIMEOUT = 120.0


def _tool_name(script: Path) -> str:
    return script.stem


def list_tools() -> list[dict]:
    """One MCP tool per discovered audit. No input required by any of them —
    a project's own profile decides what an audit looks at, per CLAUDE.md's
    own rule that this plugin never re-reads or overrides that itself."""
    tools = []
    for script in audit_discovery.discover(BIN):
        structured = audit_discovery.supports_findings_flag(script)
        off = audit_discovery.disabled_reason(script)
        if off:
            # Listed, not hidden: a tool that silently disappeared would leave an
            # agent unable to tell "this check is switched off" from "this check
            # ran and found nothing" — the governing principle's own failure.
            tools.append({
                "name": _tool_name(script),
                "description": (f"DISABLED - {off['reason']}. Calling it refuses (exit 2) "
                                f"and reports nothing about this project. {off['detail']} "
                                f"Path back: {off['pathBack']}"),
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            })
            continue
        note = (
            "Returns the common findings envelope (design_suite/engine/findings.py) as JSON."
            if structured else
            "This audit does not yet support --findings; returns raw stdout/stderr "
            "tail and exit code instead of a structured envelope."
        )
        tools.append({
            "name": _tool_name(script),
            "description": f"Run {script.name} against this project. {note}",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        })
    return tools


def call_tool(name: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Shell out to one audit and return its result. Pure passthrough:

    * resolves nothing about the project — the audit script itself does that,
      via its own `_bootstrap.project_root()`, exactly as it would run from a
      terminal or a skill;
    * classifies run status the same way `repo_health.py` does, from the
      audit's OWN exit code, never by re-parsing stdout.
    """
    scripts = {s.stem: s for s in audit_discovery.discover(BIN)}
    script = scripts.get(name)
    if script is None:
        return {"error": f"no such audit tool: {name!r}. Known: {sorted(scripts)}"}

    repo = project_root()
    structured = audit_discovery.supports_findings_flag(script)
    # Not always script.stem with "audit_" stripped — audit_focus_order.py
    # writes under "focus-order" (a hyphen). Same defect as repo_health.py's
    # run_one() had; see audit_discovery.envelope_name's docstring.
    envelope_name = audit_discovery.envelope_name(script) or script.stem.removeprefix("audit_")
    findings_path = F.default_path(repo, envelope_name)
    before_mtime = findings_path.stat().st_mtime if findings_path.is_file() else None

    cmd = [sys.executable, str(script)]
    if structured:
        cmd.append("--findings")

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=timeout)
        code, timed_out = proc.returncode, False
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-20:]
    except subprocess.TimeoutExpired:
        code, timed_out, tail = None, True, [f"timed out after {timeout:.0f}s"]
    duration = round(time.time() - t0, 2)

    if audit_discovery.disabled_reason(script):
        # Exit 2 alone would read as "this project has not configured it";
        # disabled means the check itself is switched off for everyone.
        status = "disabled"
    elif timed_out:
        status = "crashed"
    elif code == 0:
        status = "clean"
    elif code == 1:
        status = "findings"
    elif code == 2:
        status = "refused"
    else:
        status = "crashed"

    result = {
        "audit": script.stem,
        "exitCode": code,
        "status": status,
        "durationSeconds": duration,
        "structured": False,
    }

    envelope = None
    if structured and findings_path.is_file():
        after_mtime = findings_path.stat().st_mtime
        if before_mtime is None or after_mtime != before_mtime:
            try:
                envelope = json.loads(findings_path.read_text())
            except (OSError, ValueError):
                envelope = None

    if envelope is not None:
        result["structured"] = True
        result["envelope"] = envelope
    else:
        result["output"] = "\n".join(tail)
        if structured and status == "findings":
            # Same gap repo_health.py calls "unclear": the script claims
            # --findings support but did not update the envelope this run.
            result["status"] = "unclear"

    return result


# --- Minimal JSON-RPC 2.0 over stdio (the MCP transport) -------------------

def _send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _respond(request_id, result=None, error=None) -> None:
    message = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    _send(message)


def _handle(request: dict) -> None:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        _respond(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        })
    elif method == "notifications/initialized":
        pass  # notification, no response
    elif method == "tools/list":
        _respond(request_id, {"tools": list_tools() + onboarding_tools.list_tools()})
    elif method == "tools/call":
        tool_name = params.get("name")
        if tool_name in onboarding_tools.TOOLS:
            try:
                result, is_error = onboarding_tools.call(tool_name, params.get("arguments") or {})
            except Exception as exc:  # noqa: BLE001 - report, don't crash the server
                _respond(request_id, None, {"code": -32603, "message": f"{type(exc).__name__}: {exc}"})
                return
            _respond(request_id, {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
                "isError": is_error,
            })
            return
        try:
            result = call_tool(tool_name)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the server
            _respond(request_id, None, {"code": -32603, "message": str(exc)})
            return
        is_error = result.get("status") in ("crashed", "unclear") or "error" in result
        _respond(request_id, {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": is_error,
        })
    elif request_id is not None:
        _respond(request_id, None, {"code": -32601, "message": f"unknown method: {method!r}"})
    # else: unknown notification, silently ignored per JSON-RPC convention


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue  # not a valid frame; nothing sane to respond with
        _handle(request)
    return 0


if __name__ == "__main__":
    sys.exit(main())
