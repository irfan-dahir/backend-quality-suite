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

        # The undeclared-capability routing cases: a router the profile's
        # source.routesFile points at that does NOT declare routes, and the
        # convergence case where declaring routes silences the finding.
        # The php adapter scans source.root for routing signatures
        # (Route::get, $router->get, @Route/@Get attributes on controllers).
        print("check: undeclared routing capability is reported")
        unrouted = tmpdir / "unrouted"
        (unrouted / ".backend-suite").mkdir(parents=True)
        (unrouted / "src").mkdir()
        (unrouted / "src" / "Http" / "Controllers").mkdir(parents=True)
        # Controller WITHOUT any routing attribute → no routing evidence
        (unrouted / "src" / "Http" / "Controllers" / "ThingController.php").write_text(
            "<?php\nnamespace App\\Http\\Controllers;\n"
            "class ThingController { public function index() {} }\n")
        (unrouted / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "php"},
            "source": {"root": "src", "routesFile": "routes/web.php"},
        }))
        result = run("--check", "--project-root", str(unrouted), "--json")
        findings = json.loads(result.stdout)["findings"]
        kinds = {f["kind"] for f in findings}
        # Profile declares routesFile (capability declared) but source tree
        # has no routing signatures → capability is "unused" (declared but no evidence)
        # Only check ROUTING capabilities (routing, laravel_routing)
        routing_kinds = {f["kind"] for f in findings if f.get("capability") in ("routing", "laravel_routing")}
        expect("declared-capability-unused" in routing_kinds,
               f"reports declared-capability-unused for routing when no signatures (routing kinds: {routing_kinds})")
        expect(result.returncode == 1, "unexamined capability keeps the run non-clean")

        print("check: convergence — declaring routes (via attribute) silences the finding")
        routed = tmpdir / "routed"
        (routed / ".backend-suite").mkdir(parents=True)
        (routed / "src" / "Http" / "Controllers").mkdir(parents=True)
        (routed / "src" / "Http" / "Controllers" / "OrdersController.php").write_text(
            "<?php\nnamespace App\\Http\\Controllers;\n"
            "#[Get('/orders')]\n"
            "class OrdersController { public function index() {} }\n")
        (routed / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "php"},
            "source": {"root": "src", "routesFile": "routes/web.php"},
        }))
        result = run("--check", "--project-root", str(routed), "--json")
        findings = json.loads(result.stdout)["findings"]
        # Convergence: the ROUTING capability findings should disappear.
        routing_kinds = {f["kind"] for f in findings if f.get("capability") in ("routing", "laravel_routing")}
        expect("declared-capability-unused" not in routing_kinds and "undeclared-capability" not in routing_kinds,
               f"convergence: routing attribute silences the routing finding (routing kinds: {routing_kinds})")
        # The fixture is NOT Laravel (no composer daravel/framework, no artisan,
        # no Illuminate usage), so the Laravel-only capabilities
        # (eloquent_models, form_requests, api_resources, policies) are not even
        # offered — a non-Laravel PHP tree is neither measured nor excused for
        # them. The minimal fixture therefore converges to a fully clean run.
        expect(result.returncode == 0,
               f"a minimal non-Laravel PHP fixture with routing converges fully "
               f"(got {result.returncode}: {[f.get('capability', f['kind']) for f in findings]})")

        print("check: a Laravel project still gets its Laravel capabilities examined")
        laravel = tmpdir / "laravel"
        (laravel / ".backend-suite").mkdir(parents=True)
        (laravel / "src" / "Http" / "Controllers").mkdir(parents=True)
        (laravel / "src" / "Http" / "Controllers" / "OrdersController.php").write_text(
            "<?php\nnamespace App\\Http\\Controllers;\n"
            "use Illuminate\\Http\\Request;\n"
            "class OrdersController { public function index(Request $r) {} }\n")
        (laravel / "routes").mkdir()
        (laravel / "routes" / "web.php").write_text(
            "<?php\nRoute::get('/orders', [OrdersController::class, 'index']);\n")
        (laravel / "composer.json").write_text(json.dumps({
            "require": {"laravel/framework": "^11.0"},
        }))
        (laravel / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "php"},
            "source": {"root": "src", "routesFile": "routes/web.php"},
        }))
        result = run("--check", "--project-root", str(laravel), "--json")
        findings = json.loads(result.stdout)["findings"]
        cap_kinds = {f.get("capability"): f["kind"] for f in findings}
        expect(cap_kinds.get("eloquent_models") == "declared-capability-unused"
               and cap_kinds.get("form_requests") == "declared-capability-unused",
               "a Laravel project's source.root capabilities are still examined "
               "(Eloquent models, FormRequest, ... are declared but absent) "
               f"(cap kinds: {cap_kinds})")
        expect(cap_kinds.get("laravel_routing") != "declared-capability-unused",
               "Laravel routing with a declared routes file holding a Route::get "
               "is present, not unused")

        # The capability-undetermined case: adapter loaded, source.root set,
        # but NO source files to read → the adapter must refuse (raise
        # CapabilityError), not return False. If it returned False the finding
        # would disappear and the run would read as clean — the exact failure
        # the capability seam exists to prevent.
        print("check: an adapter that cannot answer raises rather than saying no")
        unreadable = tmpdir / "unreadable"
        (unreadable / ".backend-suite").mkdir(parents=True)
        (unreadable / "src").mkdir()  # empty dir — no .php files
        (unreadable / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "php"},
            "source": {"root": "src", "routesFile": "routes/web.php"},
        }))
        result = run("--check", "--project-root", str(unreadable), "--json")
        findings = json.loads(result.stdout)["findings"]
        kinds = {f["kind"] for f in findings}
        # capability-undetermined: adapter loaded but THIS tree unanswerable
        expect("capability-undetermined" in kinds or "undeclared-capability" in kinds,
               f"adapter that cannot answer refuses (kinds: {kinds})")
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
            "audits": {"exceptionsFile": "e.json", "bogusFile": "b.json"},
        }))
        (schema_project / ".backend-suite" / "profile.schema.json").write_text(json.dumps({
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "adapters": {"type": "object", "properties": {"lang": {"type": "string"}},
                             "additionalProperties": False},
                "audits": {"type": "object", "properties": {"exceptionsFile": {"type": "string"}}},
            },
        }))
        result = run("--check", "--project-root", str(schema_project), "--json")
        hits = [f for f in json.loads(result.stdout)["findings"]
                if f["kind"] == "schema-accepts-undescribed-keys"]
        expect(len(hits) == 1 and hits[0]["keys"] == ["bogusFile"],
               "reports the one object whose document carries a key the schema neither "
               "describes nor forbids, and not every permissive object in the file")

        print("check: the same schema, nothing undescribed in the document")
        (schema_project / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "dart"}, "audits": {"exceptionsFile": "e.json"},
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
        # was printing the adapter's name two lines below. `php` now ships for
        # data-API projects; the same two controls hold it reachable, via
        # composer.json in the MANIFESTS table.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import survey as S  # noqa: E402

        expect(S.language_adapters() == ["php"],
               "the registry's language adapters are discovered — php ships")
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
               "adapters.lang is reported as undeterminable when the mapped "
               "adapter does not ship")

        phpfix = tmpdir / "phpfix"
        (phpfix / "src").mkdir(parents=True)
        (phpfix / "composer.json").write_text('{"name": "fixture/api"}\n')
        (phpfix / "src" / "Thing.php").write_text("<?php\n")
        report = json.loads(run("--stdout", "--project-root", str(phpfix)).stdout)
        expect(report["stack"]["stack"] == "php",
               "a root composer.json still decides the stack")
        expect(report["stack"]["candidateAdapter"] == "php",
               "the shipped php adapter is proposed on a composer.json project")

        print("survey: writes exactly one file, and only survey.json")
        before = {p.name for p in (root / ".backend-suite").iterdir()}
        expect(run("--project-root", str(root)).returncode == 0, "the write path runs")
        after = {p.name for p in (root / ".backend-suite").iterdir()}
        expect(after - before == {"survey.json"},
               "survey.json is the only file written — never profile.json or a manifest")

        print("check: a derived survey.json is not read back as config")
        # Regression: survey.py --check crashed on the first real consumer
        # (jikan). survey.json is the survey's own derived output and carries an
        # ABSOLUTE projectRoot; config_files used to read it as an authored
        # declaration, and check()'s sibling walk then resolved that absolute
        # path as a sibling's parent and iterated the HOME directory, dying on
        # ~/.Trash with "not in the subpath of".
        derived = tmpdir / "derived"
        (derived / ".backend-suite").mkdir(parents=True)
        (derived / "src").mkdir()
        (derived / "src" / "a.php").write_text("<?php\n")
        (derived / ".backend-suite" / "survey.json").write_text(json.dumps({
            "surveyVersion": 1,
            "sourceStamp": {
                "generatedBy": "bin/survey.py v1",
                "projectRoot": str(derived.resolve()),
                "commit": "abcd",
            },
            "stack": {"stack": "php", "candidateAdapter": "php"},
            "sourceRoots": [{"path": "src", "files": 1, "why": "fixture", "confidence": 0.8}],
            "documents": {"documents": []},
            "filesSeen": 1,
            "couldNotDetermine": [],
        }))
        (derived / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "php"},
            "source": {"root": "src"},
        }))
        result = run("--check", "--project-root", str(derived), "--json")
        expect(result.returncode in (0, 1) and "Traceback" not in result.stderr
               and "not in the subpath of" not in result.stderr,
               f"--check runs to a verdict with a survey.json present "
               f"(got {result.returncode}: {result.stderr.strip()[:200]})")
        expect(json.loads(result.stdout).get("projectRoot"),
               "--json identifies the project it checked")

        print("check: an absolute declaration cannot escape the sibling walk")
        # Defence-in-depth: an authored profile with an absolute path value
        # (forbidden by profile.schema.json, but a profile can drift) must be
        # skipped by rule 2, never iterated as a parent outside the project.
        absroot = tmpdir / "absroot"
        (absroot / ".backend-suite").mkdir(parents=True)
        (absroot / "src").mkdir()
        (absroot / "src" / "a.php").write_text("<?php\n")
        escape = tmpdir / "escape-parent"
        (escape / "stray").mkdir(parents=True)
        (escape / "stray" / "f.txt").touch()
        (absroot / ".backend-suite" / "profile.json").write_text(json.dumps({
            "adapters": {"lang": "php"},
            "source": {"root": "src"},
            "pipelines": {"absScan": str(escape.resolve())},
        }))
        result = run("--check", "--project-root", str(absroot), "--json")
        expect(result.returncode in (0, 1) and "Traceback" not in result.stderr
               and "not in the subpath of" not in result.stderr,
               f"an absolute declared path never makes the sibling walk leave the "
               f"project (got {result.returncode}: {result.stderr.strip()[:200]})")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s).")
        return 1
    print("survey.py: all cases hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
