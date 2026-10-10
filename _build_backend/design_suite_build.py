"""In-tree PEP 517 build backend for the `design-suite` CLI. Stdlib only.

Why not setuptools: the engine's modules locate their data by walking up from
their own file (`parents[2] / "templates"`), so the package only works when it
sits inside a complete plugin tree. setuptools cannot ship files from outside a
package directory without layout gymnastics, and needing it means `pip install
.` needs the network. This backend has `requires = []`, so a fresh offline venv
can install the suite.

Wheel layout:

    design_suite_plugin/          <- the whole plugins/design-suite/ tree
        bin/ templates/ design_suite/ commands/ ...
    design_suite_plugin.pth       <- puts design_suite_plugin/ on sys.path
    design_suite-<v>.dist-info/   <- entry point: design-suite = design_suite.cli:main

so `import design_suite` resolves to the copy *inside* the tree, and every
`parents[N]` lookup lands where it does in the plugin. Test files and caches
are left out; nothing else is.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "design-suite"
NAME = "design_suite"
TREE = "design_suite_plugin"


def _version() -> str:
    return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]


def _metadata() -> str:
    return (
        "Metadata-Version: 2.1\n"
        "Name: design-suite\n"
        f"Version: {_version()}\n"
        "Summary: Project-agnostic design-system and documentation audits, usable from any agent harness.\n"
        "License: MIT\n"
        "Requires-Python: >=3.9\n"
    )


def _shipped():
    for p in sorted(PLUGIN.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(PLUGIN)
        if "__pycache__" in rel.parts or p.suffix == ".pyc" or p.name.endswith("_test.py"):
            continue
        yield p, rel


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_sdist(config_settings=None):
    return []


def _dist_info() -> str:
    return f"{NAME}-{_version()}.dist-info"


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    d = Path(metadata_directory) / _dist_info()
    d.mkdir(parents=True, exist_ok=True)
    (d / "METADATA").write_text(_metadata())
    (d / "entry_points.txt").write_text("[console_scripts]\ndesign-suite = design_suite.cli:main\n")
    return d.name


def _record_line(arc: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{arc},sha256={digest},{len(data)}"


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = f"{NAME}-{_version()}-py3-none-any.whl"
    di = _dist_info()
    files: list[tuple[str, bytes]] = []
    for p, rel in _shipped():
        files.append((f"{TREE}/{rel.as_posix()}", p.read_bytes()))
    files.append((f"{TREE}.pth", f"{TREE}\n".encode()))
    files.append((f"{di}/METADATA", _metadata().encode()))
    files.append((f"{di}/WHEEL", b"Wheel-Version: 1.0\nGenerator: design_suite_build\n"
                                  b"Root-Is-Purelib: true\nTag: py3-none-any\n"))
    files.append((f"{di}/entry_points.txt",
                  b"[console_scripts]\ndesign-suite = design_suite.cli:main\n"))
    record = [_record_line(a, d) for a, d in files] + [f"{di}/RECORD,,"]
    with zipfile.ZipFile(Path(wheel_directory) / name, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in files:
            info = zipfile.ZipInfo(arc, date_time=(2020, 1, 1, 0, 0, 0))
            info.external_attr = (0o755 if arc.endswith((".py", ".sh")) else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
        z.writestr(f"{di}/RECORD", "\n".join(record) + "\n")
    return name


def build_sdist(sdist_directory, config_settings=None):
    base = f"design_suite-{_version()}"
    name = f"{base}.tar.gz"
    with tarfile.open(Path(sdist_directory) / name, "w:gz") as t:
        def add(path: Path, arc: str):
            t.add(str(path), arcname=f"{base}/{arc}", recursive=False)
        for f in ("pyproject.toml", "LICENSE", "README.md"):
            add(REPO / f, f)
        for p in sorted((REPO / "_build_backend").glob("*.py")):
            add(p, f"_build_backend/{p.name}")
        for p, rel in _shipped():
            add(p, f"plugins/design-suite/{rel.as_posix()}")
        info = tarfile.TarInfo(f"{base}/PKG-INFO")
        data = _metadata().encode()
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    return name
