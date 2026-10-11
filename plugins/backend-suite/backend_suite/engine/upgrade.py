"""What changed between two revisions of this suite, in the terms a consumer feels.

This is the pre-merge half of the upgrade capability: given two revisions of
*this* repository, report every change that would alter what a consumer project
experiences when it reinstalls. It reads git blobs; it never checks anything out,
never runs an audit, and never touches a consumer project.

## Why it exists — the incident it is built from

A merge to `main` reached live client CI carrying four changes that were each
correct in isolation and none of which anything flagged:

  * `audit_tokens.py` went from `return 0` unconditionally to
    `return 1 if findings else 0`. Every consumer that had been green on hardcoded
    values went red, in CI, with no warning.
  * `audit_error_handling.py` went from `return 1 if critical else 0` to
    `return 1 if findings else 0` — same shape, different line, and invisible to
    anything that only looked at *which* exit codes a script can return, because
    that set did not change.
  * `audit_accessibility` and `audit_copy` entered
    `audit_discovery.DISABLED`, so both now exit 2 where they used to exit 0 or 1.
  * The ratchet audits stopped absorbing new findings on `--update-baseline`
    without `--accept-new`, so a runbook line that used to write a baseline now
    refuses with exit 2.

Those four are the categories below, and they are deliberately derived from what
happened rather than invented: `e14048a..ba7029e` is the range in which all four
landed, and it is this module's regression fixture. A check that reports nothing
across that range is broken, not reassuring — which is the same rule the rest of
this repo is organised around.

## How each category is detected

  `exit-contract-changed`   The *exit contract* of a script: the SET of codes it
                            can reach, the distinct conditions choosing between
                            them, and how many places exit non-zero. Sites are
                            `return <code>`, `sys.exit(...)`, `raise SystemExit`
                            (`SystemExit("msg")` is 1, `SystemExit()` is 0) and
                            `raise Refused(...)` (2). An argument that cannot be
                            resolved is "dynamic", compared as text and named in
                            the report's notes — never dropped. A set rather than
                            the list of sites, so another `return 0` is not a
                            break (the audit_on_edit false positive); conditions
                            kept, so audit_error_handling's widened condition
                            still is. A library module's change (engine/arch.py)
                            is graded critical when an audit imports it.

  `output-path-moved`       The default of an `--out`-style argparse flag, or a
                            module-level `*_OUT` / `DEFAULT_OUT` constant, changed
                            (as normalised source text, so a respelling of the
                            same path over-reports rather than under-reports).
                            A flag whose argparse default is `None` is resolved
                            through the `args.<dest> or <expr>` that supplies its
                            real default: a module constant is substituted, and
                            `pipelines.out_path(_, "key", "f")` becomes
                            `<pipelines.key>/f`. Anything else is compared as
                            text and labelled `dynamic:` — reported, never
                            dropped. Literal argparse defaults were all this saw
                            before, so four audits' report moves went unflagged.

  `audit-newly-disabled`    A key added to `audit_discovery.DISABLED`, read out of
                            that module's source with `ast` at each revision. Never
                            imported and never executed: the old revision's module
                            is not importable alongside the new one, and executing
                            a revision to ask what it does is a different and worse
                            kind of check.

  `config-key-newly-required`  A string added to any `required` array anywhere in
                            `templates/profile.schema.json`. A consumer's profile
                            that validated before and does not now is a break even
                            though no code changed.

  `script-removed` / `flag-removed`   A `bin/*.py` present at the old revision and
                            absent at the new one; an `add_argument("--x")` present
                            at the old revision and absent at the new one. Both are
                            invocations in somebody's hook map or runbook that stop
                            working.

  `new-gating-flag`         A script that gained a flag *and* gained exit-2
                            expressions in the same revision — the shape of
                            `--accept-new`: an action that used to succeed now
                            refuses until a new word is added to the command line.
                            Reported as should-fix rather than critical because the
                            shape is suggestive, not conclusive.

## Cannot-determine is 2, and never 0

Every path that cannot read a revision raises `CannotDetermine`. A compatibility
check that cannot see the old version must not report "compatible" — that is the
governing principle (CLAUDE.md, docs/CONCEPTS.md) applied to upgrades: silence and
a clean bill of health must never look the same.

Stdlib only, like everything else here.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

# Where this plugin's own files sit inside the repository. A path prefix, not a
# filesystem constant: every read below goes through `git show <rev>:<path>`.
PLUGIN_PREFIX = "plugins/backend-suite"

SCHEMA_PATH = f"{PLUGIN_PREFIX}/templates/profile.schema.json"
DISCOVERY_PATH = f"{PLUGIN_PREFIX}/backend_suite/engine/audit_discovery.py"

# Exit codes a script is allowed to be *making a contract with*. A `return 7` is
# not part of this suite's vocabulary, and a `return 200` is somebody's HTTP
# status, not an exit code.
EXIT_CODES = frozenset(range(0, 6))

# Severity vocabulary mirrors engine/findings.py rather than inventing a second one.
CRITICAL = "critical"
SHOULD_FIX = "should-fix"


class CannotDetermine(Exception):
    """The comparison could not be made at all — always exit 2, never exit 0.

    Carries the human-readable reason, because a refusal that does not say what
    it could not see is only marginally better than a silent pass.
    """


# --------------------------------------------------------------------------- git


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env
        raise CannotDetermine(f"git {' '.join(args)} failed in {repo}: {exc}") from exc


def resolve_rev(repo: Path, rev: str) -> str:
    """The full SHA for a revision, or `CannotDetermine`.

    Resolved once and reused so that a report names the commit it actually read,
    not the branch name the caller typed — a branch moves, and a report that
    cannot be re-run against the same two objects is not evidence.
    """
    proc = _git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}")
    if proc.returncode != 0:
        raise CannotDetermine(
            f"cannot resolve revision {rev!r} in {repo}: {proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def read_blob(repo: Path, rev: str, path: str) -> str | None:
    """A file's contents at a revision, or None when it did not exist there.

    None is a real answer (the file was added or removed) and is distinguished
    from an unreadable repository, which raises.
    """
    proc = _git(repo, "show", f"{rev}:{path}")
    if proc.returncode == 0:
        return proc.stdout
    err = proc.stderr.lower()
    if "does not exist" in err or "exists on disk, but not in" in err or "path" in err:
        return None
    raise CannotDetermine(f"cannot read {path} at {rev}: {proc.stderr.strip()}")


def list_scripts(repo: Path, rev: str) -> list[str]:
    """Every Python file this plugin ships at a revision, tests excluded.

    Tests are excluded because a removed test is not a consumer-visible change,
    and their exit expressions are about the test harness, not the contract.
    """
    proc = _git(repo, "ls-tree", "-r", "--name-only", rev, "--", PLUGIN_PREFIX)
    if proc.returncode != 0:
        raise CannotDetermine(
            f"cannot list the tree at {rev}: {proc.stderr.strip()}"
        )
    out = []
    for line in proc.stdout.splitlines():
        if not line.endswith(".py") or line.endswith("_test.py"):
            continue
        out.append(line)
    if not out:
        raise CannotDetermine(
            f"{rev} carries no Python files under {PLUGIN_PREFIX} — that is not a "
            f"revision of this plugin, so nothing can be compared"
        )
    return sorted(out)


def is_audit(path: str) -> bool:
    """Whether a shipped path is one of the audits a consumer's CI invokes.

    Matches both homes an audit can live in: `bin/audit_*.py`, and one level into
    the engine (`backend_suite/engine/mockapi/audit_mock_api.py`) — the same two
    places `audit_discovery.discover()` globs, for the same reason.
    """
    name = Path(path).name
    return name.startswith("audit_") and name.endswith(".py")


# ------------------------------------------------------------------ source facts


# Names whose call or `raise` ends the process. `Refused` is
# `backend_suite/engine/refusal.Refused`, a SystemExit subclass that always exits
# 2 whatever message it carries; it is matched by name because the old revision
# cannot be imported to ask.
_SYSTEM_EXIT = "SystemExit"
_REFUSED = "Refused"
_EXIT_CALLS = frozenset({"exit", "_exit"})

# A conditional expression or an unresolvable code is part of the contract as
# its normalised source text; a plain literal is part of it only as the code it
# yields. That split is the whole fix for the audit_on_edit false positive: ten
# `return 0` lines and one `return 0` are the same contract.
DYNAMIC = "dynamic"


def _module_int_constants(tree: ast.Module) -> dict[str, int]:
    """Module-level `NAME = <int>` (and `A, B = 0, 1`) bindings in EXIT_CODES.

    Only UPPER_CASE names, because `return REFUSED` is a contract and `return n`
    is a helper returning data. An imported constant is not resolved — it is
    not visible in this blob — and a `return` of it is therefore not collected;
    a `sys.exit`/`SystemExit` of it is reported as dynamic, never dropped.
    """
    out: dict[str, int] = {}

    def bind(target, value):
        if isinstance(target, ast.Name) and target.id.isupper() \
                and isinstance(value, ast.Constant) and type(value.value) is int \
                and value.value in EXIT_CODES:
            out[target.id] = value.value
        elif isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple) \
                and len(target.elts) == len(value.elts):
            for t, v in zip(target.elts, value.elts):
                bind(t, v)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target, node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            bind(node.target, node.value)
    return out


def _codes(node: ast.AST, consts: dict[str, int]) -> set[int] | None:
    """The exit codes a `return` value yields, or None if it is not an exit code."""
    if isinstance(node, ast.Constant) and type(node.value) is int \
            and node.value in EXIT_CODES:
        return {node.value}
    if isinstance(node, ast.Name) and node.id in consts:
        return {consts[node.id]}
    if isinstance(node, ast.IfExp):
        body, orelse = _codes(node.body, consts), _codes(node.orelse, consts)
        if body is not None and orelse is not None:
            return body | orelse
    return None


def _is_message(node: ast.AST | None) -> bool:
    """A string the source spells as a string: a literal, an f-string, `str(x)`,
    or a `+`/`%` concatenation with one of those. Anything else is unresolved."""
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id == "str":
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return _is_message(node.left) or _is_message(node.right)
    return False


def _exit_arg_codes(node: ast.AST | None, consts: dict[str, int]) -> set[int] | None:
    """Codes for the argument of `sys.exit(...)` / `SystemExit(...)`.

    Python's own rule: no argument or None is 0, an int is itself, anything else
    (a message string) is printed and exits 1. None returned means "cannot be
    resolved from the source" — the caller reports it as dynamic.
    """
    if node is None or (isinstance(node, ast.Constant) and node.value is None):
        return {0}
    if _is_message(node):
        return {1}
    if isinstance(node, ast.IfExp):
        body = _exit_arg_codes(node.body, consts)
        orelse = _exit_arg_codes(node.orelse, consts)
        if body is not None and orelse is not None:
            return body | orelse
        return None
    return _codes(node, consts)


def _callee_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def exit_sites(source: str, *, origin: str = "<source>") -> list[dict]:
    """Every place a script decides its exit code, each resolved to codes.

    A site is `{"text", "codes", "condition", "dynamic"}`:

      * `return <code>` / `return <a> if <c> else <b>` — as before, plus
        module-level UPPER_CASE int constants (`return REFUSED`).
      * `sys.exit(...)` / `exit(...)` / `os._exit(...)` / `parser.exit(...)`.
      * `raise SystemExit`, `raise SystemExit(...)` — `SystemExit("msg")` is
        **1**, `SystemExit()` is 0, `SystemExit(2)` is 2.
      * `raise Refused(...)` — always 2.

    `sys.exit(main())` where `main` is a function defined in the same blob is a
    delegation, not a site: `main`'s own returns are already collected. Any
    other argument that cannot be resolved is a site with `dynamic` set and
    `codes` empty — reported, never silently dropped (the governing principle).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CannotDetermine(f"{origin} does not parse: {exc}") from exc

    consts = _module_int_constants(tree)
    local_funcs = {n.name for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def norm(node: ast.AST) -> str:
        return " ".join(ast.unparse(node).split())

    def condition(node: ast.AST | None) -> str | None:
        return norm(node) if isinstance(node, ast.IfExp) else None

    def exit_site(label: str, arg: ast.AST | None) -> dict | None:
        if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) \
                and arg.func.id in local_funcs:
            return None  # delegation to a local function whose returns we read
        codes = _exit_arg_codes(arg, consts)
        if _is_message(arg):
            shown = "<message>"  # rewording a message is not a contract change
        else:
            shown = "" if arg is None else norm(arg)
        text = f"{label}({shown})"
        if codes is None:
            return {"text": text, "codes": [], "condition": None,
                    "dynamic": norm(arg)}
        if not text.endswith(f"({next(iter(codes))})") or len(codes) > 1:
            text += f" -> {','.join(str(c) for c in sorted(codes))}"
        return {"text": text, "codes": sorted(codes),
                "condition": condition(arg), "dynamic": None}

    found: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            codes = _codes(node.value, consts)
            if codes is not None:
                found.append({"text": f"return {norm(node.value)}",
                              "codes": sorted(codes),
                              "condition": condition(node.value), "dynamic": None})
        elif isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc
            name = _callee_name(exc.func) if isinstance(exc, ast.Call) \
                else _callee_name(exc)
            if name == _REFUSED:
                found.append({"text": "raise Refused(...) -> 2", "codes": [2],
                              "condition": None, "dynamic": None})
            elif name == _SYSTEM_EXIT:
                arg = exc.args[0] if isinstance(exc, ast.Call) and exc.args else None
                site = exit_site("raise SystemExit", arg)
                if site is not None:
                    found.append(site)
        elif isinstance(node, ast.Call) and _callee_name(node.func) in _EXIT_CALLS:
            # `exit` as a bare name or an attribute (sys.exit, parser.exit);
            # `_exit` only as os._exit. A zero-argument `.exit()` that is not
            # sys's is rare enough to accept as 0, which is what sys.exit() is.
            if isinstance(node.func, ast.Name) and node.func.id != "exit":
                continue
            label = norm(node.func)
            site = exit_site(label, node.args[0] if node.args else None)
            if site is not None:
                found.append(site)
    found.sort(key=lambda s: s["text"])
    return found


def exit_expressions(source: str, *, origin: str = "<source>") -> list[str]:
    """Every exit site's normalised text, sorted. Kept for display and for
    `new-gating-flag`, which counts refusal sites rather than comparing codes."""
    return [s["text"] for s in exit_sites(source, origin=origin)]


def exit_contract(sites: list[dict]) -> dict:
    """What a consumer can observe: the SET of reachable codes, the distinct
    conditions that choose between them, and every unresolvable expression.

    A set, not the list of sites: adding another `return 0` to a script that
    already exits 0 changes nothing a consumer sees (measured: audit_on_edit.py
    was flagged for exactly that). Conditions stay in because a widened
    condition with the same code set is a real break (audit_error_handling,
    `return 1 if critical else 0` -> `return 1 if findings else 0`).
    """
    return {
        "codes": sorted({c for s in sites for c in s["codes"]}),
        "conditions": sorted({s["condition"] for s in sites if s["condition"]}),
        DYNAMIC: sorted({s["dynamic"] for s in sites if s["dynamic"]}),
        # How many distinct places can produce a NON-zero code, per code set.
        # Counted, because a new `return 2` in a script that already had one is
        # a new refusal on a tree that used to pass (audit_tokens' unscanned-
        # stack refusal is exactly that). Zero sites are excluded, because
        # another way to exit 0 is the audit_on_edit false positive.
        "failingSites": sorted(Counter(
            ",".join(map(str, s["codes"])) for s in sites
            if any(c != 0 for c in s["codes"])).items()),
    }


_OUT_FLAG = re.compile(r"^--(?:[a-z0-9-]+-)?(?:out|output)(?:-[a-z0-9-]+)?$")
_OUT_CONST = re.compile(r"^(?:[A-Z0-9_]+_)?OUT(?:PUT)?(?:_[A-Z0-9_]+)?$")


def _dest(flag: str, node: ast.Call) -> str:
    explicit = next((k.value.value for k in node.keywords if k.arg == "dest"
                     and isinstance(k.value, ast.Constant)), None)
    return explicit or flag.lstrip("-").replace("-", "_")


def _effective_default(expr: ast.AST, consts: dict[str, ast.AST]) -> str:
    """Normalised text for the default an `args.x or <expr>` supplies."""
    if isinstance(expr, ast.Name) and expr.id in consts:
        expr = consts[expr.id]
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return repr(expr.value)
    if (isinstance(expr, ast.Call) and _callee_name(expr.func) == "out_path"
            and len(expr.args) == 3
            and all(isinstance(a, ast.Constant) and isinstance(a.value, str)
                    for a in expr.args[1:])):
        return repr(f"<pipelines.{expr.args[1].value}>/{expr.args[2].value}")
    return "dynamic: " + " ".join(ast.unparse(expr).split())


def output_paths(source: str, *, origin: str = "<source>") -> dict[str, str]:
    """Default output locations a consumer may read: `--out`-style argparse
    defaults and module-level `*_OUT` / `DEFAULT_OUT` constants.

    Values are normalised source text, not evaluated: `f"{MARKER}/x.json"`
    stays an f-string because MARKER is imported and not visible in this blob.
    A refactor that spells the same path differently therefore shows as moved;
    that over-reports on purpose rather than under-reporting a real move.

    `default=None` is not the default a consumer sees: the script supplies it
    later as `args.out or <expr>`. That expression is what is recorded (see
    `_effective_default`) — otherwise every move written that way is invisible.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CannotDetermine(f"{origin} does not parse: {exc}") from exc

    consts: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            consts[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None \
                and isinstance(node.target, ast.Name):
            consts[node.target.id] = node.value

    # `args.<dest> or <expr>` anywhere: the real default of a None-default flag.
    fallbacks: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) \
                and len(node.values) >= 2 and isinstance(node.values[0], ast.Attribute):
            fallbacks.setdefault(node.values[0].attr, node.values[-1])

    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee_name(node.func) == "add_argument":
            names = [a.value for a in node.args
                     if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            flag = next((n for n in names if _OUT_FLAG.match(n)), None)
            if flag is None:
                continue
            default = next((k.value for k in node.keywords if k.arg == "default"),
                           None)
            is_none = default is None or (isinstance(default, ast.Constant)
                                          and default.value is None)
            fallback = fallbacks.get(_dest(flag, node))
            if is_none and fallback is not None:
                out[flag] = _effective_default(fallback, consts)
            elif default is not None:
                out[flag] = " ".join(ast.unparse(default).split())
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and _OUT_CONST.match(t.id):
                    out[t.id] = " ".join(ast.unparse(node.value).split())
    return out


def imported_modules(source: str) -> set[str]:
    """Dotted names a blob imports, for propagating a library's exit change to
    the audits that call it. Parse failures are raised by the callers above."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
    return out


def _module_dotted(path: str) -> str | None:
    """`plugins/backend-suite/backend_suite/engine/arch.py` -> `backend_suite.engine.arch`."""
    marker = "backend_suite/"
    if marker not in path or not path.endswith(".py"):
        return None
    tail = path[path.index(marker):-3].replace("/", ".")
    return tail[:-len(".__init__")] if tail.endswith(".__init__") else tail


def flags(source: str, *, origin: str = "<source>") -> set[str]:
    """Every `--flag` the script declares to argparse.

    Read from `add_argument` calls rather than grepped for `--`, so a flag named
    in a docstring or a help string is not mistaken for one the parser accepts.
    That distinction is the whole subject of `audit_prose_flags.py`, and getting
    it wrong here would make this check assert the very thing that audit exists
    to disprove.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CannotDetermine(f"{origin} does not parse: {exc}") from exc

    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if name != "add_argument":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                    and arg.value.startswith("--"):
                out.add(arg.value)
    return out


def disabled_audits(source: str, *, origin: str = "<source>") -> set[str]:
    """The keys of `audit_discovery.DISABLED` at one revision.

    Parsed with `ast`, never imported: the old revision's module cannot be
    imported alongside the installed one under the same name, and asking a
    revision what it does by running it is how a check acquires side effects.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CannotDetermine(f"{origin} does not parse: {exc}") from exc

    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "DISABLED" for t in targets):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            raise CannotDetermine(
                f"{origin}: DISABLED is not a dict literal, so its members cannot "
                f"be read without executing the module"
            )
        out = set()
        for key in value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                out.add(key.value)
            else:
                raise CannotDetermine(
                    f"{origin}: a DISABLED key is computed rather than literal — "
                    f"refusing to guess the disabled set"
                )
        return out
    raise CannotDetermine(f"{origin}: no DISABLED assignment found")


def required_config_keys(source: str, *, origin: str = "<source>") -> set[str]:
    """Every required property in the profile schema, as `<json pointer>::<key>`.

    Qualified by location because `required: ["path"]` under two different
    `$defs` are two different obligations, and collapsing them to `path` would
    report one as satisfied by the other.
    """
    try:
        schema = json.loads(source)
    except ValueError as exc:
        raise CannotDetermine(f"{origin} is not valid JSON: {exc}") from exc

    out: set[str] = set()

    def walk(node, pointer: str) -> None:
        if isinstance(node, dict):
            required = node.get("required")
            if isinstance(required, list):
                for key in required:
                    if isinstance(key, str):
                        out.add(f"{pointer or '/'}::{key}")
            for k, v in node.items():
                walk(v, f"{pointer}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{pointer}[{i}]")

    walk(schema, "")
    return out


# ------------------------------------------------------------------- the surface


# Reading one revision is a few hundred `git show` calls, and a caller comparing
# several ranges asks for the same revision repeatedly. Keyed by the resolved SHA,
# never by the caller's revision string: a branch name means a different object
# tomorrow, and a cache keyed on it would answer for the wrong commit.
_SURFACE_CACHE: dict[tuple[str, str], dict] = {}


def surface(repo: Path, rev: str) -> dict:
    """Everything about one revision that a consumer can collide with."""
    sha = resolve_rev(repo, rev)
    cached = _SURFACE_CACHE.get((str(repo.resolve()), sha))
    if cached is not None:
        # `rev` is the caller's spelling of the same object; keep theirs so the
        # report says what they asked for.
        return dict(cached, rev=rev)
    scripts: dict[str, dict] = {}
    for path in list_scripts(repo, sha):
        source = read_blob(repo, sha, path)
        if source is None:  # pragma: no cover - ls-tree just said it exists
            continue
        sites = exit_sites(source, origin=f"{path}@{rev}")
        scripts[path] = {
            "exits": [s["text"] for s in sites],
            "contract": exit_contract(sites),
            "flags": flags(source, origin=f"{path}@{rev}"),
            "outputs": output_paths(source, origin=f"{path}@{rev}"),
            "imports": imported_modules(source),
            "isAudit": is_audit(path),
        }

    # A mechanism that did not exist yet at a revision holds nothing — that is a
    # fact about the revision, not a gap in this check, so it is an empty set
    # *with a note* rather than either a silent empty set or a refusal. The note
    # is carried into the report because "no audit was disabled" and "there was
    # no way to disable an audit" are different sentences and the reader is
    # entitled to both. An unreadable or computed registry still refuses: that is
    # a mechanism that exists and will not answer.
    notes: list[str] = []
    discovery = read_blob(repo, sha, DISCOVERY_PATH)
    if discovery is None:
        disabled: set = set()
        notes.append(
            f"{DISCOVERY_PATH} does not exist at {rev}: the disabled-audit "
            f"registry had not been introduced, so no audit could be disabled "
            f"by it at that revision"
        )
    else:
        disabled = disabled_audits(discovery, origin=f"{DISCOVERY_PATH}@{rev}")

    schema = read_blob(repo, sha, SCHEMA_PATH)
    if schema is None:
        required: set = set()
        notes.append(
            f"{SCHEMA_PATH} does not exist at {rev}: no profile key was schema-"
            f"required at that revision"
        )
    else:
        required = required_config_keys(schema, origin=f"{SCHEMA_PATH}@{rev}")

    result = {
        "rev": rev,
        "sha": sha,
        "scripts": scripts,
        "disabled": disabled,
        "requiredConfigKeys": required,
        "notes": notes,
    }
    _SURFACE_CACHE[(str(repo.resolve()), sha)] = result
    return result


def _finding(category: str, severity: str, subject: str, detail: str,
             **extra) -> dict:
    record = {
        "category": category,
        "severity": severity,
        "subject": subject,
        "detail": detail,
    }
    record.update(extra)
    return record


def compare(repo: Path, old_rev: str, new_rev: str) -> dict:
    """The full pre-merge compatibility report between two revisions.

    Raises `CannotDetermine` rather than returning an empty finding list when
    either side cannot be read.
    """
    old, new = surface(repo, old_rev), surface(repo, new_rev)
    findings: list[dict] = []

    # 1. Newly disabled audits. Checked first because a newly-disabled audit's
    #    exit expressions are irrelevant — its script is not what changed.
    for name in sorted(new["disabled"] - old["disabled"]):
        findings.append(_finding(
            "audit-newly-disabled", CRITICAL, name,
            f"{name} is in audit_discovery.DISABLED at {new_rev} and was not at "
            f"{old_rev}. It now refuses with exit 2 wherever a consumer invokes "
            f"it — in a hooks map, in CI, in a runbook — where it previously "
            f"exited 0 or 1. Exit 2 is not a pass and must not be graded as one.",
        ))

    # 2. Newly required config keys. A key required inside a section that is
    #    itself optional only binds a consumer that declares that section — so it
    #    is reported, because a consumer that DOES declare it breaks, but not at
    #    the same severity as a key every profile must now carry. Over-grading the
    #    conditional ones would train a reader to skim the list, which is how a
    #    real one gets missed.
    top_level = {k.split("::", 1)[1] for k in new["requiredConfigKeys"]
                 if k.startswith("/::")}
    for key in sorted(new["requiredConfigKeys"] - old["requiredConfigKeys"]):
        pointer, name = key.split("::", 1)
        section = pointer.split("/properties/")[1].split("/")[0] \
            if "/properties/" in pointer else None
        unconditional = pointer == "/" or (section in top_level)
        if unconditional:
            findings.append(_finding(
                "config-key-newly-required", CRITICAL, key,
                f"{name} is required by profile.schema.json at {new_rev} and was "
                f"not at {old_rev}, in a section every profile must carry. Every "
                f"consumer profile written against the old schema now fails "
                f"validation until a human supplies the value.",
            ))
        else:
            findings.append(_finding(
                "config-key-newly-required", SHOULD_FIX, key,
                f"{name} is required by profile.schema.json at {new_rev} and was "
                f"not at {old_rev}, inside an optional section. It binds only a "
                f"consumer that declares that section — and breaks that consumer "
                f"completely.",
                conditional=True,
            ))

    # 3. Per-script contract changes.
    for path in sorted(set(old["scripts"]) | set(new["scripts"])):
        before, after = old["scripts"].get(path), new["scripts"].get(path)
        if before is not None and after is None:
            findings.append(_finding(
                "script-removed", CRITICAL, path,
                f"{path} shipped at {old_rev} and does not at {new_rev}. Any hook "
                f"map, CI step or runbook naming it now fails to start.",
            ))
            continue
        if before is None:
            continue  # A new script breaks nobody's existing invocation.

        removed_flags = sorted(before["flags"] - after["flags"])
        for flag in removed_flags:
            findings.append(_finding(
                "flag-removed", CRITICAL, f"{path} {flag}",
                f"{path} accepted {flag} at {old_rev} and does not at {new_rev}. "
                f"argparse exits 2 on an unrecognised flag, so an existing "
                f"invocation now looks like a refusal it never made.",
            ))

        bc, ac = before["contract"], after["contract"]
        if bc != ac:
            # A library module (engine/arch.py, mock_api_common.py) changing how
            # it exits changes every audit that imports it — grade by who calls it.
            dotted = _module_dotted(path)
            importers = sorted(
                p for p, s in new["scripts"].items()
                if s["isAudit"] and p != path and dotted
                and any(m == dotted or m.startswith(dotted + ".")
                        or dotted.endswith("." + m) for m in s["imports"])
            ) if not (before["isAudit"] or after["isAudit"]) else []
            audit_facing = before["isAudit"] or after["isAudit"] or bool(importers)
            severity = CRITICAL if audit_facing else SHOULD_FIX
            parts = []
            if bc["codes"] != ac["codes"]:
                parts.append(f"reachable exit codes {bc['codes']} -> {ac['codes']}")
            if bc["conditions"] != ac["conditions"]:
                parts.append("the conditions choosing between them changed")
            if bc["codes"] == ac["codes"] and bc["failingSites"] != ac["failingSites"]:
                parts.append(f"the number of places that exit non-zero changed "
                             f"{dict(bc['failingSites'])} -> "
                             f"{dict(ac['failingSites'])}, so a tree that exited "
                             f"one way may now exit another")
            if bc[DYNAMIC] != ac[DYNAMIC]:
                parts.append("its unresolvable exit expressions changed")
            extra = {}
            if importers:
                extra["importedByAudits"] = importers
            findings.append(_finding(
                "exit-contract-changed", severity, path,
                f"{path}: {'; '.join(parts)}. A consumer grading this script by "
                f"exit code sees a different verdict on an unchanged tree."
                + (f" Reached through: {', '.join(importers)}." if importers else ""),
                before=sorted(set(before["exits"])), after=sorted(set(after["exits"])),
                beforeCodes=bc["codes"], afterCodes=ac["codes"],
                **extra,
            ))

        for key in sorted(set(before["outputs"]) & set(after["outputs"])):
            if before["outputs"][key] != after["outputs"][key]:
                findings.append(_finding(
                    "output-path-moved", CRITICAL, f"{path} {key}",
                    f"{path}'s default output for {key} moved. Anything a consumer "
                    f"has reading the old location (a CI step, a script, a captured "
                    f"baseline) now reads a file that is no longer written.",
                    before=before["outputs"][key], after=after["outputs"][key],
                ))

        added_flags = sorted(after["flags"] - before["flags"])
        # Counted, not set-membership: the ratchet audits already refused with
        # `return 2` for other reasons before `--accept-new` existed, so asking
        # "is this expression new" answered no and the whole category missed the
        # regression it was written for. Asking "are there MORE of them" sees the
        # added refusal branch. Measured against e14048a..ba7029e, which is why
        # this is a comment and not a preference.
        before_counts = Counter(before["exits"])
        after_counts = Counter(after["exits"])
        new_refusals = sorted(
            e for e in after_counts
            if "2" in e and after_counts[e] > before_counts[e]
        )
        if added_flags and new_refusals:
            findings.append(_finding(
                "new-gating-flag", SHOULD_FIX, path,
                f"{path} gained {', '.join(added_flags)} and gained a refusal path "
                f"in the same revision. That is the shape of an action that used "
                f"to succeed and now refuses until the new flag is passed — check "
                f"whether an existing invocation still does what it did.",
                addedFlags=added_flags, newRefusals=new_refusals,
            ))

    # Unresolvable exit expressions are compared as text, and that is a weaker
    # comparison than codes — so it is said, every run, rather than implied.
    unresolved = {p: s["contract"][DYNAMIC] for p, s in new["scripts"].items()
                  if s["contract"][DYNAMIC]}
    new_notes = list(new["notes"])
    if unresolved:
        count = sum(len(v) for v in unresolved.values())
        new_notes.append(
            f"{count} exit expression(s) in {len(unresolved)} script(s) at {new_rev} "
            f"could not be resolved to an exit code and are compared as source "
            f"text only: " + "; ".join(f"{Path(p).name}: {', '.join(v)}"
                                       for p, v in sorted(unresolved.items())))

    return {
        "unresolved": unresolved,
        "old": {"rev": old_rev, "sha": old["sha"], "notes": old["notes"]},
        "new": {"rev": new_rev, "sha": new["sha"], "notes": new_notes},
        "findings": findings,
        "counts": {
            severity: sum(1 for f in findings if f["severity"] == severity)
            for severity in (CRITICAL, SHOULD_FIX)
        },
    }
