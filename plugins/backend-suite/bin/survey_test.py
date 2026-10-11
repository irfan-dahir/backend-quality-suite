#!/usr/bin/env python3
"""Tests for survey.py, built around a planted directory rather than a clean run.

A completeness check that reports nothing on a clean tree proves nothing: 0
findings before and 0 findings after look identical whether the check works or
not. So every assertion here is paired — a clean fixture that must report
nothing, and the *same* fixture with one directory added that must report it.

    python3 plugins/backend-suite/bin/survey_test.py

Exits 0 when every case holds, 1 otherwise. Stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SURVEY = Path(__file__).resolve().parent / "survey.py"
FAILURES: list[str] = []


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SURVEY), *args],
                          capture_output=True, text=True)


def expect(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        FAILURES.append(what)


def fixture(tmp: Path) -> Path:
    root = tmp / "project"
    (root / ".backend-suite").mkdir(parents=True)
    (root / "src").mkdir()
    # Source files the declared adapter can actually read: a capability answered
    # "no" and a capability nobody could answer must be distinguishable, and the
    # only way to hold that line in a fixture is to give the clean case a tree
    # with real source in it.
    (root / "src" / "a.dart").write_text("class A {}\n")
    (root / ".backend-suite" / "profile.json").write_text(json.dumps({
        "adapters": {"lang": "dart"},
        "source": {"root": "src", "sharedComponentDir": "src/shared/components/"},
        "prose": "This project has no extras/ directory and never will.",
    }))
    (root / "src" / "shared" / "components").mkdir(parents=True)
    (root / "src" / "shared" / "components" / "b.dart").write_text("class B {}\n")
    return root


def run_in(cwd: Path, *args: str, project_dir: Path | None = None) -> subprocess.CompletedProcess:
    """Run survey from `cwd` with no inherited project hints.

    The test itself may run under Claude Code, which exports CLAUDE_PROJECT_DIR;
    inheriting it would make every default-resolution case survey this repo.
    """
    env = {k: v for k, v in os.environ.items()
           if k != "CLAUDE_PROJECT_DIR" and not k.startswith("GIT_")}
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return subprocess.run([sys.executable, str(SURVEY), *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    return path.resolve()


def flutter_project(path: Path) -> Path:
    root = git_repo(path)
    (root / "pubspec.yaml").write_text("name: demo\ndependencies:\n  flutter:\n    sdk: flutter\n")
    (root / "lib").mkdir()
    (root / "lib" / "main.dart").write_text("void main() {}\n")
    return root


def surveyed_root(result: subprocess.CompletedProcess) -> str | None:
    try:
        return json.loads(result.stdout)["sourceStamp"]["projectRoot"]
    except (ValueError, KeyError, TypeError):
        return None


def default_resolution_cases() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp).resolve()

        print("default root: an unconfigured project surveys itself")
        proj = flutter_project(tmpdir / "fresh")
        r = run_in(proj / "lib", "--json", "--stdout")
        expect(r.returncode == 0, f"exit 0 on an unconfigured project (got {r.returncode}: {r.stderr.strip()[:200]})")
        expect(surveyed_root(r) == str(proj), "sourceStamp.projectRoot is the git root of the cwd")
        expect(not (proj / ".backend-suite").exists(), "--stdout wrote nothing")

        print("default root: CLAUDE_PROJECT_DIR is honoured")
        r = run_in(proj, "--json", "--stdout", project_dir=proj)
        expect(r.returncode == 0 and surveyed_root(r) == str(proj), "surveys CLAUDE_PROJECT_DIR")
        other = git_repo(tmpdir / "elsewhere")
        r = run_in(other, "--json", "--stdout", project_dir=proj)
        expect(r.returncode == 2 and "CLAUDE_PROJECT_DIR" in r.stderr,
               "cwd outside CLAUDE_PROJECT_DIR is exit 2, named")

        print("default root: never the enclosing configured repo")
        outer = git_repo(tmpdir / "outer")
        (outer / ".backend-suite").mkdir()
        (outer / ".backend-suite" / "profile.json").write_text("{}")
        inner = flutter_project(outer / "vendor" / "inner")
        r = run_in(inner / "lib", "--json", "--stdout")
        expect(r.returncode == 0 and surveyed_root(r) == str(inner),
               "a git repo nested in a configured repo surveys the inner repo")
        loose = outer.parent / "plain-outer"
        (loose / ".backend-suite").mkdir(parents=True)
        (loose / "sub").mkdir()
        r = run_in(loose / "sub", "--json", "--stdout")
        expect(r.returncode == 2 and str(loose) in r.stderr and surveyed_root(r) is None,
               "a non-git dir under a configured dir is exit 2, naming the ancestor — no survey")

        print("--check on an unconfigured project still refuses")
        r = run_in(proj, "--check")
        expect(r.returncode == 2 and "--check" in r.stderr and "no .backend-suite/" in r.stderr,
               "exit 2 with a reason naming the missing config")

        print("--project-root still overrides")
        r = run_in(other, "--json", "--stdout", "--project-root", str(proj), project_dir=other)
        expect(r.returncode == 0 and surveyed_root(r) == str(proj),
               "--project-root beats CLAUDE_PROJECT_DIR and the cwd")


def main() -> int:
    default_resolution_cases()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        root = fixture(tmpdir)

        print("check: a tree that declares everything it has")
        result = run("--check", "--project-root", str(root))
        # Exit-0-on-clean needs a loadable adapter: the fixture names `dart`,
        # which no longer ships, so the honest current state is exit 1 with
        # capabilities-not-examined -- loud, never silent. The clean-run leg
        # returns when the php adapter lands (SWAP-PLAN.md).
        expect(result.returncode == 1,
               f"an absent adapter is not clean (got {result.returncode})")
        expect("capabilities-not-examined" in result.stdout,
               "the absent adapter is reported as unexamined, not ignored")

        print("check: the same tree with one directory planted")
        (root / "extras").mkdir()
        (root / "extras" / "img.txt").touch()
        result = run("--check", "--project-root", str(root))
        expect(result.returncode == 1, "exit 1 once an undeclared directory exists")
        expect("extras/" in result.stdout, "names the planted directory")
        expect("prose" in result.stdout,
               "reports the prose sentence asserting the directory does not exist — a "
               "contradicted assertion, which a substring sweep over config text would "
               "have treated as a declaration and stayed silent about")

        print("check: an ancestor declaration does not discharge the sibling claim")
        (root / "src" / "shared" / "format").mkdir()
        (root / "src" / "shared" / "format" / "c.py").touch()
        result = run("--check", "--project-root", str(root))
        expect("src/shared/format/" in result.stdout,
               "reports a sibling of a declared directory even though `source.root` is "
               "an ancestor of it")

        # The undeclared-capability routing cases (a router the profile's
        # source.routesFile does not declare, and the convergence case that
        # declaring it silences the finding) need a loadable language adapter
        # to answer "does this code route?". They are re-authored against the
        # php adapter and a routes/ fixture in Phase D -- SWAP-PLAN.md.

        # The fixture the whole capability seam exists for: an adapter that
        # cannot reach an answer must say so. If it returned False here the
        # finding above would disappear and the run would read as clean, which is
        # the failure this issue is about, rebuilt one layer down.
        print("check: an adapter that cannot answer raises rather than saying no")
        unreadable = tmpdir / "unreadable"
        (unreadable / ".backend-suite").mkdir(parents=True)
        (unreadable / "lib").mkdir()
        (unreadable / "lib" / "generated.g.dart").write_text("// generated only\n")
        (unreadable / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "dart"},
            "source": {"root": "lib", "routesFile": None},
        }))
        result = run("--check", "--project-root", str(unreadable), "--json")
        findings = json.loads(result.stdout)["findings"]
        kinds = {f["kind"] for f in findings}
        # capability-undetermined (adapter loaded, THIS tree unanswerable)
        # cannot be reached while no adapter loads; the invariants that still
        # hold are the two below. Full leg with a php fixture: SWAP-PLAN.md.
        expect("undeclared-capability" not in kinds and "declared-capability-unused" not in kinds,
               "no answer is invented when nothing could be examined")
        expect(result.returncode == 1, "an unexamined capability keeps the run non-clean")

        print("check: an adapter with no capability support is reported, not skipped")
        nocap = tmpdir / "nocap"
        (nocap / ".backend-suite").mkdir(parents=True)
        (nocap / ".backend-suite" / "profile.json").write_text(json.dumps({"project": {}}))
        result = run("--check", "--project-root", str(nocap), "--json")
        kinds = {f["kind"] for f in json.loads(result.stdout)["findings"]}
        expect("capabilities-not-examined" in kinds,
               "a project naming no adapter is reported as unexamined rather than clean")

        print("check: a schema that accepts keys it never describes")
        schema_project = tmpdir / "schema"
        (schema_project / ".backend-suite").mkdir(parents=True)
        (schema_project / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "dart"},
            "tokens": {"accessor": "X", "roleAccessor": "Y"},
        }))
        (schema_project / ".backend-suite" / "profile.schema.json").write_text(json.dumps({
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "adapters": {"type": "object", "properties": {"lang": {"type": "string"}},
                             "additionalProperties": False},
                "tokens": {"type": "object", "properties": {"accessor": {"type": "string"}}},
            },
        }))
        result = run("--check", "--project-root", str(schema_project), "--json")
        hits = [f for f in json.loads(result.stdout)["findings"]
                if f["kind"] == "schema-accepts-undescribed-keys"]
        expect(len(hits) == 1 and hits[0]["keys"] == ["roleAccessor"],
               "reports the one object whose document carries a key the schema neither "
               "describes nor forbids, and not every permissive object in the file")

        print("check: the same schema, nothing undescribed in the document")
        (schema_project / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "dart"}, "tokens": {"accessor": "X"},
        }))
        result = run("--check", "--project-root", str(schema_project), "--json")
        hits = [f for f in json.loads(result.stdout)["findings"]
                if f["kind"] == "schema-accepts-undescribed-keys"]
        expect(not hits, "permissiveness alone is not a finding — the drift has to be real")

        # The bare-name rule, measured into existence: see declared_paths'
        # "THE BARE-NAME RULE". Every assertion here is paired with a control,
        # because a rule that widens what counts as a declaration can only fail
        # by making a genuine finding disappear, and a disappeared finding is
        # invisible by construction.
        print("check: a bare single-segment declaration is a declaration")
        bn = tmpdir / "barename"
        (bn / ".backend-suite").mkdir(parents=True)
        for d in ("qa", "sidecar", "decoy", "genuine"):
            (bn / d).mkdir()
            (bn / d / "f.txt").touch()
        # qa/ gets two children so the argv control below has something to fail
        # on: if `qa/sweep` were read as a declaration, qa/ would acquire an
        # implicit completeness claim and qa/other/ would be reported.
        for sub in ("sweep", "other"):
            (bn / "qa" / sub).mkdir(parents=True)
            (bn / "qa" / sub / "t.txt").touch()
        (bn / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "dart"},
            "project": {"name": "decoy"},          # a bare NON-path value…
            "adapterNamed": "genuine",             # …and another, under a key
            "source": {"testRoot": "qa"},
            "pipelines": {"anything": "sidecar"},
            "verification": {"goldensUpdateCommand": ["tool", "test", "qa/sweep"]},
        }))
        result = run("--check", "--project-root", str(bn), "--json")
        paths = {f.get("path") for f in json.loads(result.stdout)["findings"]}
        expect("qa/" not in paths,
               "source.testRoot: 'qa' declares qa/ — a path-valued key with no slash in "
               "its value is still a declaration (22% of findings were this)")
        expect("sidecar/" not in paths,
               "pipelines.<anything>: 'sidecar' declares sidecar/ — the container is "
               "path-valued by role even though the key name carries no path signal")
        # CONTROL 1 — a bare string under a key that is NOT path-valued must not
        # suppress anything, even when a directory of that name exists.
        expect("decoy/" in paths,
               "CONTROL: project.name: 'decoy' does NOT declare decoy/, though the "
               "directory exists — a non-path key's value is not a path")
        expect("genuine/" in paths,
               "CONTROL: an arbitrary key's bare value does not discharge a genuine "
               "finding by colliding with a directory name")
        # CONTROL 2 — argv tokens make no declarations and no implicit claims.
        expect(not any((p or "").startswith("qa/") for p in paths),
               "CONTROL: a path inside a *Command argv makes no completeness claim "
               "about its parent, so qa/'s subdirectories are not reported as siblings")

        print("check: a bare name that names nothing on disk declares nothing")
        prof = bn / ".backend-suite" / "profile.json"
        doc = json.loads(prof.read_text())
        doc["source"]["testRoot"] = "nowhere"
        prof.write_text(json.dumps(doc))
        result = run("--check", "--project-root", str(bn), "--json")
        paths = {f.get("path") for f in json.loads(result.stdout)["findings"]}
        expect("qa/" in paths,
               "CONTROL: existence is required too — a path-valued key pointing at a "
               "directory that is not there cannot cover the one that is")

        print("check: refuses rather than reporting clean")
        bare = tmpdir / "bare"
        bare.mkdir()
        result = run("--check", "--project-root", str(bare))
        expect(result.returncode == 2, "exit 2 on a project with no .backend-suite/")
        expect(not (bare / ".backend-suite").exists(), "--check wrote nothing")

        print("survey: refuses to guess on a zero-state project")
        result = run("--stdout", "--project-root", str(bare))
        expect(result.returncode == 0, "the survey itself still runs")
        report = json.loads(result.stdout)
        expect(report["stack"]["stack"] is None, "no stack is claimed without a manifest")
        fields = {item["field"] for item in report["couldNotDetermine"]}
        expect("stack" in fields, "the undetermined stack is reported, not defaulted")
        expect(bool(report["sourceStamp"]["generatedBy"]), "carries a source stamp")

        print("survey: a manifest decides the stack, a census never does")
        (root / "pubspec.yaml").write_text("name: fixture\n")
        (root / "lib").mkdir()
        (root / "lib" / "main.dart").touch()
        for i in range(20):
            (root / "src" / f"noise{i}.py").touch()
        result = run("--stdout", "--project-root", str(root))
        report = json.loads(result.stdout)
        expect(report["stack"]["stack"] == "dart/flutter",
               "the manifest wins over a census dominated by another language")
        expect(report["stack"]["candidateAdapter"] is None,
               "no adapter is proposed while the plugin ships none")

        print("survey: an adapter that ships is an adapter the survey can reach")
        # The defect this controls for: `adapters/tsx.py` shipped, availableAdapters
        # listed it, and MANIFESTS still mapped package.json to no adapter — so
        # every JS/TS project was told "no adapter in this plugin" while the plugin
        # was printing the adapter's name two lines below. Until a language adapter
        # ships here (php, for data-API projects), the honest state is: none
        # available, none proposed, and adapters.lang reported as undetermined.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import survey as S  # noqa: E402

        expect(S.language_adapters() == [],
               "no language adapter ships yet — the loader must find nothing to pick")
        expect(S.adapter_reachability() == [],
               "every language adapter that ships is named by some root manifest — "
               "an adapter no manifest can reach can never be proposed")

        node = tmpdir / "node"
        (node / "src").mkdir(parents=True)
        (node / "package.json").write_text('{"name": "fixture"}\n')
        (node / "src" / "a.tsx").write_text("export const A = () => null;\n")
        report = json.loads(run("--stdout", "--project-root", str(node)).stdout)
        expect(report["stack"]["stack"] == "javascript/typescript",
               "a root package.json still decides the stack")
        expect(report["stack"]["candidateAdapter"] is None,
               "no adapter is proposed on a stack this plugin ships none for")
        fields = {item["field"] for item in report["couldNotDetermine"]}
        expect("adapters.lang" in fields,
               "adapters.lang is reported as undeterminable until an adapter ships")

        print("survey: writes exactly one file, and only survey.json")
        before = {p.name for p in (root / ".backend-suite").iterdir()}
        expect(run("--project-root", str(root)).returncode == 0, "the write path runs")
        after = {p.name for p in (root / ".backend-suite").iterdir()}
        expect(after - before == {"survey.json"},
               "survey.json is the only file written — never profile.json or a manifest")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("survey.py: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
