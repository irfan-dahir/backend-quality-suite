#!/usr/bin/env python3
"""survey.py finds the UI, not the server — one fixture per measured failure.

A held-out run of survey → init --from-survey → audit_tokens on six public
projects got zero findings on all six (docs/MEASUREMENT-2026-10-08-web-adapter-
held-out.md §2). Each fixture below is the SHAPE of one of those failures, with
no project's name or code in it:

  * rails_react      — a Gemfile at the root made a React+SCSS app read as Ruby.
  * backend_frontend — a workspace whose backend package outranked its frontend.
  * apps_and_store   — `apps/web` lost to a component-heavy `packages/app-store`.
  * nested_assets    — a Python repo with the UI under `app/javascript`.
  * two_apps         — two sibling UI apps: both are proposed, as source.roots.
  * no_ui (CONTROL)  — a server-only repo: nothing is proposed, and it says so.
  * tie (CONTROL)    — two equally-strong non-app UI dirs: candidates listed,
                       nothing seeded.

And end to end: init --from-survey seeds a root and an adapter as `inferred`,
fills the colour-token list from the adapter's own token_names(), and
audit_tokens then RUNS (exit 0/1) with no manual edit.

    python3 plugins/design-suite/bin/survey_ui_roots_test.py
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


def pkg(root: Path, rel: str, deps: dict) -> None:
    write(root, f"{rel}/package.json" if rel else "package.json",
          json.dumps({"name": rel or "root", "dependencies": deps}))


def components(root: Path, rel: str, n: int, suffix: str = ".tsx") -> None:
    for i in range(n):
        write(root, f"{rel}/C{i}{suffix}",
              "export const C = () => <div style={{color: '#ff0000'}} />;\n")


def server(root: Path, rel: str, n: int, suffix: str = ".ts") -> None:
    for i in range(n):
        write(root, f"{rel}/s{i}{suffix}", "export const x = 1;\n")


def survey(root: Path) -> dict:
    out = subprocess.run([sys.executable, str(BIN / "survey.py"), "--project-root",
                          str(root), "--stdout"], capture_output=True, text=True, env=ENV)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


def rails_react(tmp: Path) -> Path:
    root = tmp / "rails_react"
    write(root, "Gemfile", "source 'https://rubygems.org'\ngem 'rails'\n")
    pkg(root, "", {"react": "18", "react-dom": "18", "@rails/webpacker": "5"})
    server(root, "app/models", 60, ".rb")
    server(root, "app/controllers", 40, ".rb")
    components(root, "app/javascript/components", 30, ".jsx")
    for i in range(10):
        write(root, f"app/javascript/styles/s{i}.scss", "a { color: #fff; }\n")
    return root


def backend_frontend(tmp: Path) -> Path:
    root = tmp / "backend_frontend"
    write(root, "package.json", json.dumps({"name": "ws", "workspaces": ["packages/*"]}))
    pkg(root, "packages/backend", {"fastify": "4", "typeorm": "0.3"})
    server(root, "packages/backend/src", 120)
    components(root, "packages/backend/src/email", 3)
    pkg(root, "packages/frontend", {"vue": "3", "vite": "5"})
    components(root, "packages/frontend/src", 40, ".vue")
    server(root, "packages/frontend/src/scripts", 20)
    return root


def apps_and_store(tmp: Path) -> Path:
    root = tmp / "apps_and_store"
    write(root, "package.json",
          json.dumps({"name": "mono", "workspaces": ["apps/*", "packages/*"]}))
    pkg(root, "apps/web", {"next": "14", "react": "18"})
    components(root, "apps/web/components", 50)
    pkg(root, "packages/app-store", {"react": "18"})
    components(root, "packages/app-store", 70)
    pkg(root, "packages/lib", {"zod": "3"})
    server(root, "packages/lib", 40)
    return root


def nested_assets(tmp: Path) -> Path:
    root = tmp / "nested"
    write(root, "pyproject.toml", "[project]\nname='x'\n")
    server(root, "src/app", 80, ".py")
    pkg(root, "", {"vue": "3"})
    components(root, "app/javascript", 25, ".vue")
    return root


def two_apps(tmp: Path) -> Path:
    root = tmp / "two_apps"
    write(root, "package.json", json.dumps({"name": "mono", "workspaces": ["apps/*"]}))
    for name in ("admin", "site"):
        pkg(root, f"apps/{name}", {"next": "14", "react": "18"})
        components(root, f"apps/{name}/src", 30)
    return root


def no_ui(tmp: Path) -> Path:
    root = tmp / "no_ui"
    write(root, "go.mod", "module x\n")
    server(root, "cmd", 40, ".go")
    return root


def tie(tmp: Path) -> Path:
    root = tmp / "tie"
    for name in ("alpha", "beta"):
        pkg(root, f"libs/{name}", {"react": "18"})
        components(root, f"libs/{name}/src", 20)
    return root


def chosen(report: dict) -> list[str]:
    return report["uiRoots"]["chosen"]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)

        print("rails + react: the UI stack, not the Gemfile")
        r = survey(rails_react(t))
        expect(chosen(r) == ["app/javascript"], f"chooses app/javascript (got {chosen(r)})")
        expect(r["stack"]["candidateAdapter"] == "web",
               f"adapter is web for .jsx+.scss (got {r['stack']['candidateAdapter']})")
        expect(r["stack"].get("uiStackDecision", {}).get("provenance") == "inferred",
               "the override is recorded, and recorded as inferred")
        expect("ruby" in r["stack"].get("candidateStacks", []),
               "the server stack is still reported, not hidden")

        print("workspace: frontend over backend")
        r = survey(backend_frontend(t))
        expect(chosen(r) == ["packages/frontend/src"], f"chooses the frontend (got {chosen(r)})")
        expect(r["uiRoots"]["confidence"] >= 0.6, "with seedable confidence")

        print("monorepo: apps/web over packages/app-store")
        r = survey(apps_and_store(t))
        expect(chosen(r) == ["apps/web"], f"chooses apps/web (got {chosen(r)})")
        expect("packages/app-store" in r["uiRoots"].get("runnersUp", []),
               "and names the runner-up it beat")

        print("python server with UI in app/javascript")
        r = survey(nested_assets(t))
        expect(chosen(r) == ["app/javascript"], f"chooses app/javascript (got {chosen(r)})")
        expect(r["stack"]["candidateAdapter"] == "web", "adapter web, not python's none")

        print("two sibling apps: source.roots")
        r = survey(two_apps(t))
        expect(sorted(chosen(r)) == ["apps/admin/src", "apps/site/src"],
               f"both apps proposed (got {chosen(r)})")

        print("CONTROL: server-only repository")
        r = survey(no_ui(t))
        expect(chosen(r) == [] and any(u["field"] == "uiRoots" for u in r["couldNotDetermine"]),
               "proposes nothing and says why")
        expect(r["stack"]["stack"] == "go", "the manifest stack is untouched")

        print("CONTROL: an undecidable ranking proposes, never picks")
        r = survey(tie(t))
        expect(len(r["uiRoots"]["candidates"]) >= 2, "both candidates are listed with evidence")
        expect(r["uiRoots"]["confidence"] < 0.6
               and any(u["field"] == "uiRoots" for u in r["couldNotDetermine"]),
               "confidence is below the seed bar and the gap is reported")

        print("end to end: init --from-survey -> audit_tokens runs with no edits")
        root = rails_react(t / "e2e")
        write(root, "app/javascript/styles/theme.css",
              "@theme {\n  --color-brand: #123456;\n  --color-ink: #000000;\n}\n")
        init = subprocess.run([sys.executable, str(BIN / "init.py"), "--dir", str(root),
                               "--from-survey"], capture_output=True, text=True, env=ENV)
        expect(init.returncode == 0, f"init exits 0 (got {init.returncode}: {init.stderr[-200:]})")
        profile = json.loads((root / ".design-suite/profile.json").read_text())
        fields = profile["provenance"]["fields"]
        expect(profile["source"]["root"] == "app/javascript"
               and fields["source.root"]["state"] == "inferred",
               "source.root seeded as inferred")
        expect(profile["adapters"]["lang"] == "web"
               and fields["adapters.lang"]["state"] == "inferred",
               "adapters.lang seeded as inferred")
        expect(all(e["state"] == "inferred" for e in fields.values()), "nothing ratified")
        config = json.loads((root / ".design-suite/design-audit-config.json").read_text())
        names = config["token_categories"]["color"]["names"]
        expect(not any("TODO" in n for v in names.values() for n in v),
               f"TODO_TOKEN_NAME placeholders replaced (got {names})")
        audit = subprocess.run([sys.executable, str(BIN / "audit_tokens.py")], cwd=root,
                               capture_output=True, text=True,
                               env={**ENV, "CLAUDE_PROJECT_DIR": str(root)})
        expect(audit.returncode in (0, 1),
               f"audit_tokens runs (exit {audit.returncode}: {audit.stderr[-300:]})")

        print("CONTROL: a token set the adapter cannot determine leaves the TODO")
        root = backend_frontend(t / "e2e2")
        subprocess.run([sys.executable, str(BIN / "init.py"), "--dir", str(root),
                        "--from-survey"], capture_output=True, text=True, env=ENV)
        config = json.loads((root / ".design-suite/design-audit-config.json").read_text())
        names = config["token_categories"]["color"]["names"]
        expect(any("TODO" in n for v in names.values() for n in v),
               "no theme -> placeholders stay (no invented list)")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("survey UI roots: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
