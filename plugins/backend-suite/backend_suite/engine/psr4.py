"""PSR-4 namespace prefixes for PHP projects, read from composer.json.

Why this exists: `use App\Http\Controllers\AnimeController;` names a class by
namespace, not by path. A layer-boundary AUDIT phrases its rules as namespace
prefixes and matches them against the raw import (see the contract in
`adapters/php.py`), so the audit itself never needs this map — but a
*measurement* over the import graph does: to count which directory imports
which, every edge has to be attributed to a directory, and a bare namespace
carries none. Without the map every `use` in the tree reads as "external",
the graph has zero edges, and a proposal would be made from nothing while
claiming to be measured.

The contract mirrors `engine/aliases.py` — three states, never collapsed
into two:

  * a composer.json with a psr-4 autoload map        -> prefixes resolve;
  * a composer.json that exists but cannot be parsed -> `Psr4Error`
    (callers refuse, exit 2) — never "no map";
  * no composer.json at all                          -> an empty map: every
    `use` is external, which is the honest reading for a tree without
    Composer.

Only `autoload.psr-4` and `autoload-dev.psr-4` are read. Classmap and files
entries are deliberately not: a classmap is a generated file list, not a
declared namespace -> directory rule, and resolving through it would mean
trusting the artifact over the layout. A prefix with several directories
takes the first — the order composer.json declares is the project's own.
"""
from __future__ import annotations

import json
from pathlib import Path


class Psr4Error(Exception):
    """composer.json exists but could not be read as a psr-4 source of truth."""


class Psr4Map:
    """Namespace prefixes -> first declared directory (repo-relative)."""

    def __init__(self, prefixes: dict[str, list[str]], sources: list[str]) -> None:
        # Longest prefix first, so 'App\Extra\' wins over 'App\'.
        self._prefixes = sorted(prefixes.items(), key=lambda kv: -len(kv[0]))
        self.sources = list(sources)

    def __bool__(self) -> bool:
        return bool(self._prefixes)

    def match(self, spec: str) -> tuple[str, str] | None:
        """(repo-relative resolved file path, the prefix that matched) or None.

        The path is the shape this class maps to, not a claim the file exists:
        a layer rule matches by prefix, and the graph only needs the directory.
        """
        target = spec.lstrip("\\")
        for prefix, dirs in self._prefixes:
            if target.startswith(prefix):
                rest = target[len(prefix):].replace("\\", "/")
                return "/".join(part for part in (dirs[0], rest) if part) + ".php", prefix
        return None

    def handles(self, top_dir: str) -> list[str]:
        """Namespace roots whose imports attribute to files under `top_dir`.

        This is what makes a proposed layer rule enforceable by the audit: for
        a group at repo path `app/Http` mapped through prefix `App\\`, the
        handle is `App\\Http\\` — the exact prefix a raw `use` target starts
        with when it names a file in that group. The path form covers
        `require`d files; this covers `use` statements.
        """
        found = []
        for prefix, dirs in self._prefixes:
            base = dirs[0]
            if base == top_dir:
                rel = ""
            elif base == "":
                rel = top_dir  # a psr-4 mapping to the repo root covers all of it
            elif top_dir.startswith(base + "/"):
                rel = top_dir[len(base) + 1:]
            else:
                continue
            ns = prefix + rel.replace("/", "\\")
            if not ns.endswith("\\"):
                ns += "\\"
            if ns not in found:
                found.append(ns)
        return sorted(found)


def load(repo: Path) -> Psr4Map:
    """The psr-4 map of `repo`'s own composer.json. Raises `Psr4Error` when a
    composer.json exists but is not readable as one — callers refuse rather
    than continue with a map they merely failed to open."""
    composer = repo / "composer.json"
    if not composer.is_file():
        return Psr4Map({}, [])
    try:
        data = json.loads(composer.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise Psr4Error(f"composer.json is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise Psr4Error("composer.json is not a JSON object")

    prefixes: dict[str, list[str]] = {}
    sources: list[str] = []
    for section in ("autoload", "autoload-dev"):
        block = data.get(section)
        if block is None:
            continue
        if not isinstance(block, dict):
            raise Psr4Error(f"composer.json {section} is not an object")
        psr4 = block.get("psr-4")
        if psr4 is None:
            continue
        if not isinstance(psr4, dict):
            raise Psr4Error(f"composer.json {section}.'psr-4' is not an object")
        sources.append(f"composer.json {section}.'psr-4'")
        for prefix, dirs in psr4.items():
            if not isinstance(prefix, str) or not prefix:
                raise Psr4Error(
                    f"composer.json {section}.'psr-4' has a non-string prefix")
            if isinstance(dirs, str):
                dirs = [dirs]
            if (not isinstance(dirs, list) or not dirs
                    or not all(isinstance(d, str) for d in dirs)):
                raise Psr4Error(
                    f"composer.json {section}.'psr-4'[{prefix!r}] is not a string "
                    f"or a list of strings")
            key = prefix if prefix.endswith("\\") else prefix + "\\"
            cleaned = [d.strip("/") for d in dirs]
            cleaned = ["" if d == "." else d for d in cleaned]
            prefixes.setdefault(key, []).extend(cleaned)
    return Psr4Map(prefixes, sources)
