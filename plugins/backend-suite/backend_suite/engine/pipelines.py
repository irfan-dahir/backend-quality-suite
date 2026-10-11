"""Where a project keeps each sidecar pipeline's directory.

Every audit used to spell its own output directory into an `argparse` default:

    p.add_argument("--out", default="token_pipeline/findings.json")
    p.add_argument("--out", default="copy_pipeline/inventory.json")
    p.add_argument("--out", default="mock_api/findings.json")

which is the quiet defect this suite exists to forbid. Nothing errors on a
project that keeps its token pipeline somewhere else — the audit writes a
findings file into a directory that project has never heard of, the baseline
diff compares it against nothing, and the run reads exactly like a clean one.
The `--dir` flags next to these already did the right thing (`default=None`,
resolved from `source.root` in the profile); only `--out` was left behind.

The profile key is `pipelines.<name>`, which already existed and is already the
mechanism the asset pipeline uses (`pipelines.assets`, see
`engine/assets/pipeline.py`) and which `survey.py` already reports on by name.
This module just gives the remaining pipelines the same treatment through one
resolver instead of five scattered string defaults.

DEFAULTS is the one place a directory name is written down, and the names in it
are the conventional ones rather than any particular project's: `survey.py`'s
bare-name rule already lists `pipelines.mockApi: "mock_api"` and
`pipelines.copy: "copy_pipeline"` as the conventional declarations it must
recognise. A fallback is not the same defect as a silent assumption *because it
is overridable and named* — a project that keeps its pipeline elsewhere says so
once in its profile and every audit follows. It is exempted in
`bin/audit_skill_paths.py` on exactly that basis, and the exemption is keyed to
this file so the moment someone re-scatters these strings the gate fires again.
"""
from __future__ import annotations

from pathlib import Path

# Conventional sidecar directory names. Overridden per project by `pipelines.<key>`.
DEFAULTS = {
    "tokens": "token_pipeline",
    "copy": "copy_pipeline",
    "mockApi": "mock_api",
    "assets": "asset_pipeline",
}


def directory(profile: dict, key: str) -> str:
    """The project-relative directory for pipeline `key`, from its profile.

    Returns a plain string rather than a Path because callers thread it through
    `--out`-style arguments, which are project-relative strings by contract.
    """
    if key not in DEFAULTS:
        # Refuse rather than inventing a directory: an unknown pipeline key is a
        # caller bug, and guessing one would create a directory nothing reads.
        raise KeyError(
            f"unknown pipeline {key!r} — known: {', '.join(sorted(DEFAULTS))}")
    configured = (profile.get("pipelines", {}) or {}).get(key)
    return str(configured or DEFAULTS[key])


def out_path(profile: dict, key: str, filename: str) -> str:
    """`<pipeline dir>/<filename>`, the shape every audit's `--out` default wants."""
    return f"{directory(profile, key)}/{filename}"


def resolve(repo: Path, profile: dict, key: str) -> Path:
    """Absolute pipeline directory, for engines that hold Path constants."""
    return Path(repo) / directory(profile, key)
