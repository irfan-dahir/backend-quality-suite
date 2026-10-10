"""Import-path aliases for JS/TS projects: tsconfig/jsconfig `paths` + `baseUrl`,
and vite/webpack `resolve.alias`.

Why this exists: `import { api } from '@/data/api'` is a bare specifier. A
boundary audit that does not know `@` means `src` reads it as a third-party
package and skips it — every violation written through the alias is missed,
silently, and the run prints clean. That is the governing principle's failure
shape exactly, so the contract here is:

  * an alias config that exists and is understood  -> resolved;
  * an alias config that exists and is NOT understood -> `AliasConfigError`
    (callers refuse, exit 2) — never "no aliases";
  * no alias config at all -> no aliases. Callers that then see an
    alias-*shaped* specifier (`@/x`, `~/x`, `#/x`) should refuse too.

Deliberately stdlib-only and conservative: a vite alias whose value is not a
string literal (a variable, a regex `find`, a function) is "not understood",
not guessed at.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ALIAS_SHAPED = ("@/", "~/", "#/")
_TS_CONFIG_GLOBS = ("tsconfig.json", "tsconfig.*.json", "jsconfig.json", "jsconfig.*.json")
_BUNDLER_CONFIGS = tuple(f"{n}.config.{e}" for n in ("vite", "vitest", "webpack")
                         for e in ("js", "ts", "mjs", "mts", "cjs", "cts"))
_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".d.ts", ".json", ".css", ".scss")


class AliasConfigError(Exception):
    """An alias config exists but could not be parsed."""


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments (string-aware) and trailing commas."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _load_jsonc(path: Path) -> dict:
    try:
        data = json.loads(_strip_jsonc(path.read_text(errors="replace")))
    except (OSError, ValueError) as e:
        raise AliasConfigError(f"{path.name}: not parseable as JSON-with-comments ({e})") from e
    if not isinstance(data, dict):
        raise AliasConfigError(f"{path.name}: top level is not an object")
    return data


def _ts_aliases(repo: Path, cfg: Path, seen: set) -> tuple[list, list]:
    """(alias rules, baseUrl dirs) from one tsconfig, following extends/references."""
    cfg = cfg.resolve()
    if cfg in seen or not cfg.is_file():
        return [], []
    seen.add(cfg)
    data = _load_jsonc(cfg)
    rules, bases = [], []
    ext = data.get("extends")
    for e in ([ext] if isinstance(ext, str) else ext or []):
        if isinstance(e, str) and e.startswith("."):
            p = cfg.parent / e
            if not p.is_file() and p.suffix != ".json":
                p = p.with_name(p.name + ".json")
            r, b = _ts_aliases(repo, p, seen)
            rules, bases = rules + r, bases + b
        # A package extends (`@tsconfig/node20`) is a shared compiler preset;
        # those do not declare project paths, and resolving node_modules is
        # out of scope.
    for ref in data.get("references") or []:
        if isinstance(ref, dict) and isinstance(ref.get("path"), str):
            p = cfg.parent / ref["path"]
            r, b = _ts_aliases(repo, p / "tsconfig.json" if p.is_dir() else p, seen)
            rules, bases = rules + r, bases + b
    co = data.get("compilerOptions") or {}
    if not isinstance(co, dict):
        raise AliasConfigError(f"{cfg.name}: compilerOptions is not an object")
    base_url = co.get("baseUrl")
    base = (cfg.parent / base_url) if isinstance(base_url, str) else cfg.parent
    if isinstance(base_url, str):
        bases.append(base)
    paths = co.get("paths") or {}
    if not isinstance(paths, dict):
        raise AliasConfigError(f"{cfg.name}: compilerOptions.paths is not an object")
    for key, targets in paths.items():
        if not (isinstance(targets, list) and targets and all(isinstance(t, str) for t in targets)):
            raise AliasConfigError(f"{cfg.name}: paths[{key!r}] is not a list of strings")
        rules.append(("ts", key, [base / t for t in targets]))
    return rules, bases


_STR = r"""(['"`])((?:\\.|(?!\1).)*)\1"""


def _balanced(text: str, start: int) -> str | None:
    """The bracketed text starting at text[start] ('{' or '['), or None."""
    pairs = {"{": "}", "[": "]", "(": ")"}
    stack, i, q = [], start, None
    while i < len(text):
        c = text[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c in "'\"`":
            q = c
        elif c in pairs:
            stack.append(pairs[c])
        elif stack and c == stack[-1]:
            stack.pop()
            if not stack:
                return text[start:i + 1]
        i += 1
    return None


def _split_top(body: str) -> list[str]:
    parts, depth, cur, q, i = [], 0, [], None, 0
    while i < len(body):
        c = body[i]
        if q:
            cur.append(c)
            if c == "\\" and i + 1 < len(body):
                cur.append(body[i + 1])
                i += 2
                continue
            if c == q:
                q = None
        elif c in "'\"`":
            q = c
            cur.append(c)
        elif c in "{[(":
            depth += 1
            cur.append(c)
        elif c in "}])":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


def _path_value(expr: str, cfg: Path) -> Path:
    """A replacement expression -> a filesystem path, or AliasConfigError.

    Understood: a string literal ('/src' is project-root-relative in vite);
    path.resolve/join(__dirname, 'a', 'b'); fileURLToPath(new URL('./src',
    import.meta.url)). Anything else is not guessed at."""
    expr = expr.strip()
    lit = re.fullmatch(_STR, expr, re.S)
    if lit:
        s = lit.group(2)
        return cfg.parent / s.lstrip("/") if s.startswith("/") else cfg.parent / s
    m = re.fullmatch(r"(?:path\.)?(?:resolve|join)\((.*)\)", expr, re.S)
    if m:
        args = _split_top(m.group(1))
        if args and args[0] in ("__dirname", "process.cwd()", "'.'", '"."'):
            args = args[1:]
        segs = [re.fullmatch(_STR, a, re.S) for a in args]
        if args and all(segs):
            return cfg.parent.joinpath(*[s.group(2) for s in segs])
    m = re.fullmatch(r"fileURLToPath\(\s*new\s+URL\(\s*" + _STR + r"\s*,\s*import\.meta\.url\s*\)\s*\)",
                     expr, re.S)
    if m:
        return cfg.parent / m.group(2)
    raise AliasConfigError(f"{cfg.name}: alias value `{expr[:60]}` is not a literal path "
                           f"this resolver understands")


def _bundler_aliases(cfg: Path) -> list:
    text = cfg.read_text(errors="replace")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    rules = []
    for m in re.finditer(r"\balias\s*:\s*", text):
        body = _balanced(text, m.end())
        if body is None:
            raise AliasConfigError(f"{cfg.name}: `alias:` is not an object/array literal "
                                   f"(a variable or call) — cannot read it")
        inner = body[1:-1]
        if body.startswith("{"):
            for entry in _split_top(inner):
                if entry.startswith("..."):
                    raise AliasConfigError(f"{cfg.name}: alias spread `{entry[:40]}` cannot be read")
                km = re.match(r"(?:" + _STR + r"|([\w$]+))\s*:\s*(.*)$", entry, re.S)
                if not km:
                    raise AliasConfigError(f"{cfg.name}: alias entry `{entry[:40]}` cannot be read")
                key = km.group(2) if km.group(1) else km.group(3)
                rules.append(("bundler", key, [_path_value(km.group(4), cfg)]))
        else:
            for entry in _split_top(inner):
                fm = re.search(r"\bfind\s*:\s*" + _STR, entry, re.S)
                rm = re.search(r"\breplacement\s*:\s*(.*?)\s*(?:,\s*\w+\s*:|}\s*$)", entry, re.S)
                if not (fm and rm):
                    raise AliasConfigError(f"{cfg.name}: alias entry `{entry[:40]}` has a non-literal "
                                           f"find (regex?) or no replacement — cannot read it")
                rules.append(("bundler", fm.group(2), [_path_value(rm.group(1), cfg)]))
    return rules


class Aliases:
    def __init__(self, repo: Path, rules: list, bases: list, sources: list):
        self.repo = repo.resolve()
        self.rules = sorted(rules, key=lambda r: -len(r[1]))
        self.bases = bases
        self.sources = sources  # config files that contributed

    def __bool__(self) -> bool:
        return bool(self.rules or self.bases)

    def _exists(self, p: Path) -> bool:
        return p.exists() or any(p.with_name(p.name + e).exists() for e in _EXTS)

    def resolve(self, spec: str) -> Path | None:
        """A bare specifier -> absolute path, or None when no alias applies."""
        for kind, key, targets in self.rules:
            hit = None
            if kind == "ts":
                if "*" in key:
                    pre, post = key.split("*", 1)
                    if spec.startswith(pre) and spec.endswith(post) and len(spec) >= len(pre) + len(post):
                        star = spec[len(pre):len(spec) - len(post) if post else None]
                        hit = [Path(str(t).replace("*", star, 1)) for t in targets]
                elif spec == key:
                    hit = targets
            else:  # vite/webpack: exact, or key + '/'
                if spec == key:
                    hit = targets
                elif spec.startswith(key.rstrip("/") + "/"):
                    rest = spec[len(key.rstrip("/")) + 1:]
                    hit = [t / rest for t in targets]
            if hit:
                for h in hit:
                    if self._exists(h):
                        return h.resolve()
                return hit[0].resolve()
        for b in self.bases:
            if self._exists(b / spec):
                return (b / spec).resolve()
        return None


def load(repo: Path) -> Aliases:
    """Every alias config at the project root. Raises AliasConfigError."""
    rules, bases, sources, seen = [], [], [], set()
    for g in _TS_CONFIG_GLOBS:
        for cfg in sorted(repo.glob(g)):
            r, b = _ts_aliases(repo, cfg, seen)
            rules, bases = rules + r, bases + b
            sources.append(cfg.name)
    for name in _BUNDLER_CONFIGS:
        cfg = repo / name
        if cfg.is_file():
            r = _bundler_aliases(cfg)
            rules += r
            sources.append(name)
    return Aliases(repo, rules, bases, sources)
