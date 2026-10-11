"""Language-agnostic hardcoded-value scanner.

Sweeps a source tree with whatever checks a language adapter supplies and returns
findings. Contains no knowledge of Dart, Flutter, or this project — if a change
here needs to mention any of those, it belongs in an adapter instead.
"""
from __future__ import annotations

from pathlib import Path


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def matching_delimiter_span(source: str, open_idx: int, open_ch="(", close_ch=")") -> int:
    """Index just past the delimiter matching the one at `open_idx`.

    Counting balanced delimiters is text mechanics, not language knowledge, so it
    lives in the engine — but an adapter is what decides *which* call it wants the
    body of. Unbalanced input returns end-of-source rather than raising: a
    truncated file should degrade to over-reporting, not abort the whole sweep.
    """
    depth = 0
    i = open_idx
    while i < len(source):
        if source[i] == open_ch:
            depth += 1
        elif source[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(source)


def scan_source(rel: str, source: str, checks, allowlists=None, skip_files=()) -> list[dict]:
    """Run every check over one file's text.

    `allowlists` maps a check category to the set of paths exempt from it, so an
    exemption is scoped to the category that documented it — a file allowed to
    hold brand colours is still held to the spacing rules.
    """
    allowlists = allowlists or {}
    if rel in skip_files:
        return []

    findings = []
    for check in checks:
        if check.category and rel in allowlists.get(check.category, set()):
            continue
        if not getattr(check, "applies_to", lambda _rel: True)(rel):
            continue
        for match in check.pattern.finditer(source):
            if not check.fires(match, source):
                continue
            findings.append({
                "file": rel,
                "line": line_of(source, match.start()),
                "kind": check.kind,
                "snippet": check.describe(match, source),
            })
    return findings


# Directories that hold vendored or generated code, never authored source. Each
# is skipped by default because a finding inside it is one nobody here can fix:
#   node_modules  — npm/yarn/pnpm installed dependencies
#   dist, build, out — bundler / compiler output (webpack, vite, tsc, Next export, Flutter build)
#   .next, .nuxt, .svelte-kit — framework build caches (Next.js, Nuxt, SvelteKit)
#   coverage      — test-coverage HTML/JS reports
#   vendor        — vendored third-party code (Go, PHP Composer, Ruby bundler)
#   Pods          — CocoaPods-installed iOS dependencies
#   .dart_tool    — Dart/Flutter tool cache and generated code
#   .gradle       — Gradle cache (Android/Kotlin)
#   DerivedData   — Xcode build products
#
# The generic names (dist, build, out, coverage, vendor) are also legitimate
# authored-source folder names — vitepress keeps real code in src/node/build/.
# So those are skipped only where they sit beside a package manifest (the root
# of a package, where tools emit them); elsewhere they are scanned.
# A skip is never silent: every skipped directory is counted and reported on
# stderr, so "zero findings" can always be traced to what was not looked at.
# Override per project in exceptions.json: `scanSkipDirs.include` re-enables a
# default, `scanSkipDirs.add` skips more.
DEFAULT_SKIP_DIRS = frozenset({
    "node_modules", "dist", "build", ".next", ".nuxt", ".svelte-kit", "out",
    "coverage", "vendor", "Pods", ".dart_tool", ".gradle", "DerivedData",
})

# Names that are only ever vendored/generated, skipped wherever they appear.
UNAMBIGUOUS_SKIP_DIRS = frozenset({
    "node_modules", ".next", ".nuxt", ".svelte-kit", "Pods", ".dart_tool",
    ".gradle", "DerivedData",
})

# Files marking a package root, beside which a generic name is tool output.
PACKAGE_MANIFESTS = (
    # The Dart manifest is deliberately absent: the skill-paths gate forbids
    # that literal in the engine, and a Flutter build/ holds no .dart source.
    "package.json", "build.gradle", "build.gradle.kts",
    "settings.gradle", "settings.gradle.kts", "composer.json", "go.mod",
    "Gemfile", "Podfile", "Package.swift", "Cargo.toml", "pyproject.toml",
)

_reported: set = set()


def _is_skipped(parent: str, name: str, skip, filenames) -> bool:
    if name not in skip:
        return False
    if name in UNAMBIGUOUS_SKIP_DIRS or name not in DEFAULT_SKIP_DIRS:
        return True  # unambiguous, or a project-added name: skip anywhere
    return any(m in filenames for m in PACKAGE_MANIFESTS)


def skip_dirs_from(exceptions) -> frozenset:
    """The effective skip set after a project's exceptions.json override."""
    cfg = (exceptions or {}).get("scanSkipDirs") or {}
    return (DEFAULT_SKIP_DIRS - set(cfg.get("include", ()))) | set(cfg.get("add", ()))


def source_files(root: Path, globs=("**/*",), skip_dirs=None, skipped=None) -> list:
    """Every file under `root` matching any glob, de-duplicated and sorted.

    Exists so a caller can ask "how many files did I actually look at?". A sweep
    that matched nothing reports zero findings, which is indistinguishable from a
    clean codebase unless the file count is reported too — the failure mode when
    an adapter's globs do not fit the tree it was pointed at.

    Directories named in `skip_dirs` (default DEFAULT_SKIP_DIRS) below `root` are
    pruned. Each pruned directory is appended to `skipped` if given, and the
    count is always printed to stderr — a skip is never silent.
    """
    import os
    import sys
    from pathlib import PurePosixPath

    skip = DEFAULT_SKIP_DIRS if skip_dirs is None else frozenset(skip_dirs)
    pruned = []
    candidates = []
    for dirpath, dirnames, filenames in os.walk(root):
        keep = []
        for d in sorted(dirnames):
            if _is_skipped(dirpath, d, skip, filenames):
                pruned.append(Path(dirpath) / d)
            else:
                keep.append(d)
        dirnames[:] = keep
        candidates.extend(Path(dirpath) / f for f in filenames)

    patterns = [g.replace("**/", "") for g in globs]
    seen = []
    for path in candidates:
        rel = PurePosixPath(path.relative_to(root).as_posix())
        if any(rel.match(p) for p in patterns) and path.is_file():
            seen.append(path)

    if skipped is not None:
        skipped.extend(pruned)
    if pruned:
        key = (str(root), tuple(sorted(str(p) for p in pruned)))
        if key not in _reported:
            _reported.add(key)
            names = sorted({p.name for p in pruned})
            print(f"SKIPPED {len(pruned)} vendored/generated dir(s) under {root}: "
                  f"{', '.join(names)} (override: exceptions.json scanSkipDirs)",
                  file=sys.stderr)
    return sorted(seen)


def scan_skip_file_includes(exceptions) -> tuple:
    """Repo-relative paths/globs a project re-includes past a file-level skip
    (`exceptions.json` `scanSkipFiles.include`)."""
    cfg = (exceptions or {}).get("scanSkipFiles") or {}
    return tuple(cfg.get("include", ()))


def scan_tree(root: Path, repo: Path, checks, globs=("**/*",), allowlists=None,
              skip_files=(), skip_dirs=None, file_filter=None, include_files=(),
              skipped_files=None) -> list[dict]:
    """Scan every file under `root` matching `globs`, sorted for stable output.

    Stable ordering matters more than it looks: the baseline that proves this
    refactor changed nothing is a digest of the output, so an unordered walk would
    produce spurious drift on every run.

    `file_filter(rel, source)` is an adapter's file-level classifier: it returns
    a reason string ("vendored", "mock/fixture", ...) for a file that is not
    authored product UI, or None. A filtered file is never dropped silently —
    every one is printed to stderr with its reason, and appended to
    `skipped_files` as (rel, reason) if given. `include_files` (paths or
    fnmatch globs, repo-relative) are always scanned whatever the filter says.
    """
    import fnmatch
    import sys

    findings = []
    filtered: dict = {}
    for path in source_files(root, globs, skip_dirs):
        rel = str(path.relative_to(repo))
        source = path.read_text(encoding="utf-8", errors="ignore")
        if file_filter is not None and not any(
                rel == g or fnmatch.fnmatch(rel, g) for g in include_files):
            reason = file_filter(rel, source)
            if reason:
                filtered.setdefault(reason, []).append(rel)
                if skipped_files is not None:
                    skipped_files.append((rel, reason))
                continue
        findings.extend(scan_source(rel, source, checks, allowlists, skip_files))
    for reason, rels in sorted(filtered.items()):
        print(f"SKIPPED {len(rels)} {reason} file(s) under {root} "
              f"(override: exceptions.json scanSkipFiles.include):", file=sys.stderr)
        for rel in rels:
            print(f"  {rel}", file=sys.stderr)
    return findings
