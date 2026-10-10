#!/usr/bin/env python3
"""Tests for propose_config.py — inferred values for init.py's TODO sections.

Each synthetic project goes through the real onboarding scripts (survey.py,
init.py --from-survey) first, so the TODOs under test are the ones a new user
actually gets. Paired assertions, per CLAUDE.md: every refusal is paired with the
positive case it must not swallow, and every "the audit now runs" is paired with
a planted violation the audit must still catch — a rule that runs and can never
fire is the vacuous pass this suite exists to prevent.

    python3 plugins/design-suite/bin/propose_config_test.py

Exit 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
FAILURES: list[str] = []


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def py(root: Path, script: str, *argv: str) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, str(BIN / script), *argv],
                          capture_output=True, text=True, cwd=root, env=env)


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def onboard(root: Path) -> None:
    for argv in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"]):
        subprocess.run(["git", *argv], cwd=root, capture_output=True)
    py(root, "survey.py", "--project-root", str(root))
    done = py(root, "init.py", "--from-survey", "--dir", str(root))
    assert (root / ".design-suite" / "profile.json").is_file(), done.stderr


def digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted((root / ".design-suite").glob("*.json")):
        h.update(p.read_bytes())
    return h.hexdigest()


def proposals(root: Path) -> tuple[int, dict]:
    done = py(root, "propose_config.py", "--json", "--dir", str(root))
    try:
        return done.returncode, json.loads(done.stdout)
    except ValueError:
        return done.returncode, {}


def sections(report: dict) -> set[str]:
    return {p["section"] for p in report.get("proposals", [])}


# --------------------------------------------------------------------------- #

def flutter(root: Path) -> None:
    files = {"pubspec.yaml": "name: app\ndependencies:\n  flutter:\n    sdk: flutter\n",
             "lib/main.dart": "import 'package:app/core/a.dart';\nvoid main() {}\n",
             "lib/core/a.dart": "class A {}\n", "lib/core/b.dart": "class B {}\n"}
    for f in ("one", "two"):
        files[f"lib/features/{f}/domain/entity.dart"] = "import '../../../core/a.dart';\nclass E {}\n"
        for i in range(3):
            files[f"lib/features/{f}/data/repo{i}.dart"] = (
                f"import 'package:app/features/{f}/domain/entity.dart';\n"
                "import 'package:app/core/b.dart';\nclass R {}\n")
        files[f"lib/features/{f}/presentation/pages/page.dart"] = (
            "import 'package:flutter/widgets.dart';\n"
            "Widget build() => AnimatedOpacity(opacity: 1, child: x);\n")
    write(root, files)


def test_flutter() -> None:
    print("flutter: layers, adapter seam, animated widgets")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        flutter(root)
        onboard(root)
        before = {a: py(root, f"{a}.py").returncode for a in
                  ("audit_layer_boundaries", "audit_adapter_pattern", "audit_reduced_motion")}
        expect(set(before.values()) == {2}, f"all three refuse before ({before})")

        snap = digest(root)
        code, rep = proposals(root)
        expect(code == 0, "preview exits 0 when something is proposed")
        expect(digest(root) == snap, "preview writes nothing")
        expect(sections(rep) == {"layerBoundaries", "adapterPattern", "animated_widgets"},
               f"proposes the three measurable sections ({sections(rep)})")
        by = {p["section"]: p for p in rep["proposals"]}
        rule = by["layerBoundaries"]["value"]["rules"][0]
        expect(rule["fromGlob"] == "lib/core/**" and rule["mustNotImport"] == ["lib/features/**"],
               f"layer rule is core -/-> features ({rule})")
        expect(by["animated_widgets"]["value"] == ["AnimatedOpacity"],
               "animated list is exactly what the source uses")
        labels = [e["label"] for e in by["adapterPattern"]["value"]["bannedImports"]]
        expect(any("domain" in l for l in labels) and any("core" in l for l in labels),
               f"screens banned from domain and core ({labels})")
        expect(not any("data" in l for l in labels),
               "nothing proposed for a layer with < MIN_EDGES importers")
        expect("notProposed" in rep and "errorHandling" in rep["notProposed"],
               "human-decision sections are listed, not guessed")
        expect(py(root, "propose_config.py", "--apply", "errorHandling").returncode == 2
               and digest(root) == snap, "--apply on an unproposed section refuses, writes nothing")

        done = py(root, "propose_config.py", "--apply", "all")
        expect(done.returncode == 0, "--apply all exits 0")
        arch = json.loads((root / ".design-suite/arch-rules.json").read_text())
        expect(arch["layerBoundaries"]["_provenance"]["state"] == "inferred"
               and set(arch["layerBoundaries"]["_provenance"]) == {"state", "evidence"},
               "written section carries only {state: inferred, evidence}")
        after = {a: py(root, f"{a}.py").returncode for a in before}
        expect(after["audit_layer_boundaries"] == 0 and after["audit_adapter_pattern"] == 0,
               f"structural audits now run clean ({after})")
        expect(after["audit_reduced_motion"] == 1,
               "reduced-motion audit now runs, and catches the unguarded AnimatedOpacity")

        write(root, {"lib/core/bad.dart": "import 'package:app/features/one/data/repo0.dart';\n",
                     "lib/features/one/presentation/pages/bad.dart":
                         "import '../../domain/entity.dart';\n"})
        expect(py(root, "audit_layer_boundaries.py").returncode == 1,
               "planted core->features import is caught")
        expect(py(root, "audit_adapter_pattern.py").returncode == 1,
               "planted screen->domain import is caught")

        snap = digest(root)
        arch["layerBoundaries"].pop("_provenance")
        (root / ".design-suite/arch-rules.json").write_text(json.dumps(arch))
        snap = digest(root)
        _, rep = proposals(root)
        expect("layerBoundaries" not in sections(rep),
               "a section a human owns (no inferred provenance, no TODO) is never re-proposed")
        expect(py(root, "propose_config.py", "--apply", "layerBoundaries").returncode == 2
               and digest(root) == snap, "and --apply on it refuses without writing")


def web(root: Path, kind: str, importers: int) -> None:
    ext = "vue" if kind == "vue" else "tsx"
    dep = '"vue": "^3"' if kind == "vue" else '"react": "^18"'
    files = {"package.json": '{"name":"w","dependencies":{%s},"devDependencies":{"vite":"^5"}}' % dep,
             "src/lib/format.ts": "export const f = 1;\n",
             "src/lib/api.ts": "export const g = 2;\n"}
    for i in range(importers):
        body = f"import {{ f }} from '../lib/format'\nexport const C{i} = f\n"
        files[f"src/components/C{i}.{ext}"] = (
            f"<script setup lang=\"ts\">\n{body}</script>\n" if ext == "vue" else body)
    write(root, files)


def test_web(kind: str) -> None:
    print(f"{kind}: layer rule from relative imports; no screens scope")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        web(root, kind, 6)
        onboard(root)
        expect(py(root, "audit_layer_boundaries.py").returncode == 2, "refuses before")
        code, rep = proposals(root)
        expect(code == 0 and "layerBoundaries" in sections(rep),
               f"layer rule proposed ({sections(rep)})")
        expect("adapterPattern" not in sections(rep)
               and "screens" in rep.get("notInferred", {}).get("adapterPattern", ""),
               "no adapterPattern without a screens scope — said why")
        expect("animated_widgets" not in sections(rep),
               "no animated list: the web adapter has no naming capability")
        py(root, "propose_config.py", "--apply", "layerBoundaries")
        expect(py(root, "audit_layer_boundaries.py").returncode == 0, "audit now runs clean")
        bad = "import { C0 } from '../components/C0'\n"
        write(root, {"src/lib/bad.ts": bad})
        expect(py(root, "audit_layer_boundaries.py").returncode == 1,
               "planted lib->components import is caught")


def test_weak_evidence() -> None:
    print("weak evidence: nothing proposed, exit 2, nothing written")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        web(root, "react", 2)
        onboard(root)
        snap = digest(root)
        code, rep = proposals(root)
        expect(code == 2, "exit 2 when nothing could be inferred")
        expect(not sections(rep), "no proposal under MIN_EDGES")
        expect("layerBoundaries" in rep.get("notInferred", {}), "the reason is reported")
        expect(digest(root) == snap, "nothing written")
        expect(py(root, "propose_config.py", "--apply", "all").returncode == 2
               and digest(root) == snap, "--apply all with nothing proposed is exit 2, not 0")


def main() -> int:
    test_flutter()
    for kind in ("react", "vue"):
        test_web(kind)
    test_weak_evidence()
    print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall cases hold")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
