"""Flutter asset registration, via `flutter: assets:` in pubspec.yaml.

Implements `AssetAdapterProtocol`. Stdlib only — no PyYAML, because the whole
engine is dependency-free and pubspec's assets block is a flat list of scalars
under two known keys, which does not need a YAML parser. What it *does* need is
care about indentation, since that is the only thing distinguishing a top-level
`assets:` from the one nested under `flutter:`.

## The subtlety that makes a naive implementation wrong

Flutter lets you register a **directory** and get every file under it:

    flutter:
      assets:
        - assets/images/

The originating project does exactly that. So `is_registered("assets/images/x.webp")`
must return True even though that exact path appears nowhere in pubspec.yaml. An
implementation that only matched literal paths would report every asset in the
library as unregistered — hundreds of false findings, on a project that is
correctly configured.

Directory entries are recognised by a trailing `/`, which is Flutter's own
convention for them.

## Resolution variants

`assets/images/2.0x/foo.webp` is Flutter's resolution-aware sibling of
`assets/images/foo.webp`. It is covered by the same directory registration and is
not a separate asset, so callers should register the base path and let Flutter find
the variants. This adapter does not treat a variant as its own entry.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..base import CapabilityError

NAME = "flutter_pubspec"
MANIFEST_DEFAULT = "asset_pipeline"

_FLUTTER_KEY = re.compile(r"^flutter:\s*$")
_ASSETS_KEY = re.compile(r"^(\s+)assets:\s*$")
_LIST_ITEM = re.compile(r"^(\s+)-\s*(\S.*?)\s*$")


def _pubspec(ctx) -> Path:
    return Path(ctx.repo) / "pubspec.yaml"


def asset_root(ctx) -> str:
    """Where bundled assets live.

    From the profile when declared, so a project that keeps them elsewhere is not
    overridden by this adapter's default.
    """
    declared = (ctx.profile.get("assets", {}) or {}).get("root")
    return declared or "assets"


def manifest_path(ctx) -> str:
    """The pipeline's own record of what exists and how it was produced."""
    pipelines = ctx.profile.get("pipelines", {}) or {}
    return f"{pipelines.get('assets', MANIFEST_DEFAULT)}/manifest.json"


def local_manifest_path(ctx) -> str:
    """Gitignored working state.

    Its absence means "nothing rendered locally yet", NOT "no assets registered".
    Conflating those was called out in the protocol spec as the most likely thing
    to get wrong, so it gets its own accessor rather than being inferred.
    """
    pipelines = ctx.profile.get("pipelines", {}) or {}
    return f"{pipelines.get('assets', MANIFEST_DEFAULT)}/manifest.local.json"


def _scan(lines: list[str]) -> tuple[list[str], int | None, int | None]:
    """(entries, assets_indent, index of the last line belonging to the block).

    One scan, used by both `registered_entries` and `register`, because the first
    version of this file had two and they disagreed: the reader correctly closed
    the list at the sibling `fonts:` key, the writer did not, so a new entry got
    inserted into the fonts block — where it registered nothing. Sharing the scan
    is what makes that impossible rather than merely fixed.
    """
    entries: list[str] = []
    in_flutter = False
    assets_indent: int | None = None
    last_line: int | None = None

    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        if _FLUTTER_KEY.match(line):
            in_flutter, assets_indent = True, None
            continue

        # Any other top-level key ends the flutter: block.
        if not line[0].isspace():
            in_flutter, assets_indent = False, None
            continue

        if not in_flutter:
            continue

        m = _ASSETS_KEY.match(line)
        if m:
            assets_indent = len(m.group(1))
            last_line = i
            continue

        if assets_indent is None:
            continue

        item = _LIST_ITEM.match(line)
        indent = len(line) - len(line.lstrip())
        if item and indent > assets_indent:
            entries.append(item.group(2).strip("'\""))
            last_line = i
        elif indent <= assets_indent:
            # A sibling key such as `fonts:` closes the list.
            assets_indent = None
    return entries, assets_indent, last_line


def registered_entries(ctx) -> list[str]:
    """Every path declared under `flutter: assets:`, in file order.

    Raises if pubspec.yaml is absent — a Flutter project without one is not a
    situation to paper over with an empty list.
    """
    path = _pubspec(ctx)
    if not path.is_file():
        raise CapabilityError(
            "registered_entries", NAME,
            f"no pubspec.yaml at {path} — is adapters.assets right for this project?")
    return _scan(path.read_text().splitlines())[0]


def is_registered(ctx, path: str) -> bool:
    """Whether the build system declares this asset.

    Matches a literal entry OR any directory entry that is a prefix of `path` —
    see the module docstring for why the second case is not optional.
    """
    rel = str(path).lstrip("./")
    for entry in registered_entries(ctx):
        if entry.endswith("/"):
            if rel.startswith(entry):
                return True
        elif rel == entry:
            return True
    return False


def register(ctx, path: str) -> None:
    """Declare an asset. Idempotent — the asset skills are re-run routinely.

    Deliberately does the least possible: if `path` is already covered, including
    by a directory entry, this is a no-op. Rewriting pubspec.yaml when nothing
    needs to change is how a tool ends up with a diff on every run.
    """
    if is_registered(ctx, path):
        return

    pubspec = _pubspec(ctx)
    lines = pubspec.read_text().splitlines()
    rel = str(path).lstrip("./")

    entries, indent, last_line = _scan(lines)
    if last_line is None:
        raise CapabilityError(
            "register", NAME,
            "pubspec.yaml has no `flutter: assets:` block. Creating one means "
            "guessing where it belongs in a file a human maintains — add the "
            "block by hand once, then this becomes idempotent.")

    # `indent` is None when a sibling key closed the list, so recover it from the
    # `assets:` key rather than from wherever the scan happened to stop.
    if indent is None:
        for line in lines:
            m = _ASSETS_KEY.match(line.rstrip())
            if m:
                indent = len(m.group(1))
                break

    lines.insert(last_line + 1, f"{' ' * (indent + 2)}- {rel}")
    pubspec.write_text("\n".join(lines) + "\n")
