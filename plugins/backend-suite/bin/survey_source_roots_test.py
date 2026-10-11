#!/usr/bin/env python3
"""survey.py decides SOURCE roots for backend audits — and init seeds from them.

Re-authored from the purged design-suite `survey_ui_roots_test.py`. That
suite ranked UI directories (component files, stylesheets, UI-framework
dependencies) and init.py seeded `source.root` / `source.roots` /
`adapters.lang` from the UI ranking. The re-domain removed the UI machinery
entirely (the history note in survey.py says why): nothing in the backend
suite reads `uiRoots`, and the UI-first seeding preference pointed backend
audits at frontend directories on polyglot repositories — a php repo with a
`resources/js` frontend would have been seeded to audit the frontend.

What replaces it, pinned here:

  * `sourceRoots` ranking: a conventional root holding files scores 0.8, an
    empty one 0.2, a declared workspace member 0.7 — and init.py seeds only a
    single candidate at or above its 0.8 bar;
  * the e2e: survey -> init --from-survey seeds adapters.lang / source.root /
    source.fileGlob as `inferred`, and a live php-backed audit then runs —
    refusing at its rules-section TODO, which proves the seeded profile
    fields loaded (every other refusal names adapters.lang, source.root or
    source.fileGlob);
  * controls: a stack whose adapter does not ship leaves adapters.lang a TODO
    (an unknown adapter is a hard error downstream, not a default), and a
    repository with no conventional source directory proposes nothing and
    says so in couldNotDetermine.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/survey_source_roots_test.py"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
FAILURES: list[str] = []
ENV = {k: v for k, v in os.environ.items()
       if k != "CLAUDE_PROJECT_DIR" and not k.startswith("GIT_")}


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def write(root: Path, rel: str, text: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def php_files(root: Path, rel: str, n: int) -> None:
    for i in range(n):
        write(root, f"{rel}/Thing{i}.php", "<?php\n")


def survey(root: Path) -> dict:
    out = subprocess.run([sys.executable, str(BIN / "survey.py"), "--project-root",
                          str(root), "--stdout"], capture_output=True, text=True, env=ENV)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


def plain_php(tmp: Path) -> Path:
    root = tmp / "plain_php"
    write(root, "composer.json",
          json.dumps({"name": "fixture/api", "autoload": {"psr-4": {"App\\": "src/"}}}))
    (root / "src").mkdir(parents=True)
    php_files(root, "src", 12)
    return root


def php_monorepo(tmp: Path) -> Path:
    root = tmp / "php_monorepo"
    write(root, "package.json",
          json.dumps({"name": "ws", "workspaces": ["packages/*"]}))
    write(root, "composer.json", json.dumps({"name": "fixture/api"}))
    php_files(root, "packages/api/src", 30)
    write(root, "packages/web/package.json", json.dumps({"name": "web"}))
    for i in range(6):
        write(root, f"packages/web/w{i}.js", "export const w = 1;\n")
    return root


def no_conventional_root(tmp: Path) -> Path:
    root = tmp / "no_conventional_root"
    write(root, "composer.json", json.dumps({"name": "fixture/api"}))
    # Real sources, but not under the conventional `src/`.
    php_files(root, "app/Http", 8)
    return root


def frontend_only(tmp: Path) -> Path:
    root = tmp / "frontend_only"
    write(root, "package.json",
          json.dumps({"name": "fixture/web", "dependencies": {"react": "18"}}))
    (root / "src").mkdir(parents=True)
    for i in range(10):
        write(root, f"src/C{i}.tsx", "export const C = () => null;\n")
    return root


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)

        print("survey: a conventional source root with files is the strong candidate")
        r = survey(plain_php(t))
        expect(r["stack"]["stack"] == "php"
               and r["stack"]["candidateAdapter"] == "php",
               "composer.json decides the stack and proposes the php adapter")
        roots = r["sourceRoots"]
        expect(len(roots) == 1 and roots[0]["path"] == "src"
               and roots[0]["confidence"] == 0.8,
               f"one candidate, src at 0.8 (got {roots})")
        expect("uiRoots" not in r,
               "the removed UI ranking stays removed from the report")

        print("survey: a monorepo's members rank below the seed bar — nothing is seeded")
        r = survey(php_monorepo(t))
        expect(r["stack"]["stack"] is None
               and r["stack"]["candidateStacks"] == ["javascript/typescript", "php"],
               "two disagreeing manifests: no stack claimed, both named")
        expect(r["stack"]["candidateAdapter"] is None,
               "and no adapter proposed while the stack is undecided")
        expect(all(c["confidence"] < 0.8 for c in r["sourceRoots"]),
               f"every member candidate scores below the 0.8 seed bar (got {r['sourceRoots']})")
        fields = {u["field"] for u in r["couldNotDetermine"]}
        expect("sourceRoots" in fields and "stack" in fields,
               "both gaps are reported, not defaulted")

        print("survey: no conventional source directory proposes nothing and says so")
        r = survey(no_conventional_root(t))
        expect(r["sourceRoots"] == [], "an empty candidate list is an answer")
        fields = {u["field"] for u in r["couldNotDetermine"]}
        expect("sourceRoots" in fields,
               "the missing conventional root is named in couldNotDetermine")

        print("CONTROL: a stack whose adapter does not ship leaves the lang a TODO")
        r = survey(frontend_only(t))
        expect(r["stack"]["candidateAdapter"] is None,
               "tsx is mapped but not present — no adapter proposed")
        reasons = " ".join(u["why"] for u in r["couldNotDetermine"]
                           if u["field"] == "adapters.lang")
        expect("tsx" in reasons and "not present in this plugin" in reasons,
               f"the gap names the missing adapter (got {reasons!r})")

        print("e2e: init --from-survey seeds the php profile, and a live audit runs")
        root = plain_php(t / "e2e")
        init = subprocess.run([sys.executable, str(BIN / "init.py"), "--dir", str(root),
                               "--from-survey"], capture_output=True, text=True, env=ENV)
        expect(init.returncode == 0,
               f"init exits 0 (got {init.returncode}: {init.stderr[-200:]})")
        profile = json.loads((root / ".backend-suite" / "profile.json").read_text())
        fields = profile["provenance"]["fields"]
        expect(profile["adapters"]["lang"] == "php"
               and fields["adapters.lang"]["state"] == "inferred",
               "adapters.lang seeded as inferred")
        expect(profile["source"]["root"] == "src"
               and fields["source.root"]["state"] == "inferred",
               "source.root seeded as inferred")
        expect(profile["source"]["fileGlob"] == "**/*.php"
               and fields["source.fileGlob"]["state"] == "inferred",
               "source.fileGlob seeded as inferred — the php stack is in "
               "FILE_GLOB_BY_STACK, so a seeded profile can actually be audited")
        expect(all(e["state"] == "inferred" for e in fields.values()),
               "every seeded field is inferred; nothing is ratified")
        expect("roots" not in profile["source"],
               "source.roots is not seeded — the UI multi-root path is gone")
        expect(profile["project"]["framework"].startswith("php")
               and "inferred" in profile["project"]["framework"]
               and fields["project.framework"]["state"] == "inferred",
               "framework seeded as an inferred starting point naming its own "
               "incompleteness — a human ratifying it rewrites the free text")

        # The audit every seeded profile must be able to reach: it refuses at
        # its rules-section TODO, naming errorHandling — not adapters.lang,
        # source.root or source.fileGlob, which are what a missing seed would
        # have named instead.
        audit = subprocess.run(
            [sys.executable, str(BIN / "audit_error_handling.py")], cwd=root,
            capture_output=True, text=True,
            env={**ENV, "CLAUDE_PROJECT_DIR": str(root)})
        out = audit.stdout + audit.stderr
        expect(audit.returncode == 2,
               f"audit_error_handling refuses, never fakes a pass (got {audit.returncode})")
        expect("errorHandling" in out and "TODO" in out,
               f"the refusal names the rules-section scaffold (got {out[-300:]!r})")
        expect("adapters.lang" not in out and "source.root" not in out
               and "fileGlob" not in out,
               "the seeded profile fields loaded — no profile-field refusal")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("survey source roots: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
