"""Import extraction and scaffold detection shared by the structural audits.

`audit_adapter_pattern` and `audit_layer_boundaries` both ask "what does this
file import?". How a language spells an import is a fact about the language, so
the regex lives on the adapter (`IMPORT_RE`, group(s) = target). An adapter
without one cannot answer, and the audit refuses (exit 2) rather than scanning
with another language's regex and reporting a confident zero.
"""
from __future__ import annotations

from pathlib import Path

from backend_suite.engine.refusal import Refused


def import_re(adapter, audit: str):
    rx = getattr(adapter, "IMPORT_RE", None)
    if rx is None:
        raise Refused(
            f"the {getattr(adapter, 'NAME', '?')!r} language adapter declares no IMPORT_RE, "
            f"so it cannot say what a file imports — this structural audit cannot run on "
            f"this stack.", audit)
    return rx


def require_path_imports(adapter, audit: str) -> None:
    """Refuse when the adapter's import targets are module/package names, not paths.

    A path-rooted layer rule (`mustNotImport: src/data/**`) can only be matched
    against an import that names a file. Swift (`import DataLayer`) and Kotlin
    (`import com.x.data.Repo`) name modules and packages; a module is not a
    directory, so every import would resolve to "external", the sweep would find
    nothing, and the audit would print clean over a tree it never checked.
    """
    if getattr(adapter, "IMPORT_TARGETS", "path") != "path":
        raise Refused(
            f"the {getattr(adapter, 'NAME', '?')!r} adapter's imports name modules or "
            f"packages, not file paths, so a directory-rooted layer rule cannot be "
            f"matched against them — refusing rather than reporting every import as "
            f"external and the tree as clean.", audit)


def import_targets(rx, text: str) -> list[tuple[int, str]]:
    """[(1-based line, target)] for every import the adapter's regex finds."""
    out = []
    for m in rx.finditer(text):
        target = next((g for g in m.groups() if g), None)
        if target:
            out.append((text.count("\n", 0, m.start()) + 1, target))
    return out


def suffixes(adapter) -> tuple[str, ...]:
    """File suffixes the adapter audits, from its FILE_GLOBS (`**/*.ext`)."""
    out = []
    for g in getattr(adapter, "FILE_GLOBS", ()):
        tail = g.rsplit("/", 1)[-1]
        if tail.startswith("*.") and "*" not in tail[1:]:
            out.append(tail[1:])
    return tuple(out)


def adapter_files(root: Path, adapter, pattern: str | None = None) -> list[Path]:
    """Files under `root` the adapter can read. With `pattern`, files matching
    that glob (relative to root) filtered to the adapter's suffixes; without
    it, every adapter-suffixed file under root."""
    sfx = suffixes(adapter)
    if pattern:
        if pattern.endswith("**"):
            pattern += "/*"  # 'dir/**' alone yields directories only
        found = root.glob(pattern)
    else:
        found = (p for s in sfx for p in root.rglob(f"*{s}"))
    # vendor/ is Composer-installed third-party code, exactly as node_modules
    # is to JS: the php adapter sources it for nothing, and walking it would
    # bury a measurement under other people's trees. survey.py and the
    # session-start hook skip it for the same reason.
    skip = {"node_modules", "vendor", ".git", "build", "dist", ".dart_tool",
            ".next", ".nuxt"}
    return sorted({p for p in found if p.is_file() and p.name.endswith(sfx)
                   and not skip.intersection(p.relative_to(root).parts)})


def placeholder(value) -> bool:
    """True for an unfilled `init.py` scaffold value ("TODO: ..."), recursively."""
    if isinstance(value, str):
        return value.strip().upper().startswith("TODO")
    if isinstance(value, dict):
        return any(placeholder(v) for k, v in value.items() if not str(k).startswith("_"))
    if isinstance(value, (list, tuple)):
        return any(placeholder(v) for v in value)
    return False
