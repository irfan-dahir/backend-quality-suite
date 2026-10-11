#!/usr/bin/env python3
"""Generate docs/CATALOG.md from what the plugins actually contain.

Why this is generated rather than written: a catalogue is a list of
file-existence facts, which is the single most drift-prone kind of documentation
there is. This repo has already produced three wrong hand-written claims about
its own contents — two consecutive corrections to one status banner, and a
"17 of 24 commands moved" that was really 19. Prose cannot be trusted with this;
a script can.

    python3 plugins/backend-suite/bin/catalog.py            # write docs/CATALOG.md
    python3 plugins/backend-suite/bin/catalog.py --check     # exit 1 if stale

`--check` is what CI runs, so a component added without its declared fields, or
a catalogue left unregenerated, fails the build instead of quietly misdescribing
the suite.

Reads, per skill/agent, from YAML frontmatter:
  name, description  — already required for Claude Code to load the component
  invocation         — auto | explicit  (see the app's autonomous-vs-explicit policy)
  maturity           — proven | unverified | experimental | pointer | disabled

Hooks are enumerated from each plugin's hooks/hooks.json instead, because that
file is the actual source of truth for whether a hook is registered at all —
the thing worth asserting about a hook. They carry no invocation field: a hook
is automatic by definition.

Stdlib only, like every other script here.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGINS = REPO / "plugins"
OUT = REPO / "docs" / "CATALOG.md"

VALID_INVOCATION = {"auto", "explicit"}
VALID_MATURITY = {"proven", "unverified", "experimental", "pointer", "disabled"}

# Why `proven` is NOT gated on an evidence file here (ROADMAP A2, deliberately
# not built):
#
# `verify.py` writes evidence to `<consumer-project>/.backend-suite/evidence/
# <component>.json` — in the project a component was run against, never in this
# plugin repo. This repo has no `.backend-suite/` directory and no committed
# evidence of any kind, so `--check`, which runs here, has nothing to look at. A
# gate written as "require an evidence file" would therefore be a gate that
# passes because it cannot see — the precise failure this file exists to stop.
#
# The two designs that would work both need something that does not exist yet:
#   * an evidence *manifest* committed into this repo, summarising real runs.
#     `verify.py` HAS run for real — 44 records in each consumer's
#     `.backend-suite/evidence/`, dated 2026-09-14 (mobile 10 verified / 6 failed
#     / 28 refused; portal 8 / 9 / 27). This comment used to say it had only run
#     against a synthetic fixture, and that was false by the time it was cited.
#     The real obstacle is that those records are gitignored inside the
#     CONSUMER repos, so this repo has nowhere to read them from; a manifest
#     here would be hand-copied, and a hand-copied manifest is the assertion A2
#     exists to replace. Separately, a mechanical verify.py run is not the real
#     end-to-end run `proven` means (docs/CONCEPTS.md), so even readable
#     evidence would not by itself justify the tier;
#   * the gate running per-consumer (where the evidence lives) and *reporting*
#     rather than gating — which is a different tool from this one, since
#     `catalog.py` has no consumer project to point at.
#
# So A2 stays unbuilt, and this comment is the statement of what it needs:
# `verify.py --all` run for real against at least one consumer project, and a
# decided home for the resulting evidence that this repo can actually read.
# Until then `proven` remains an assertion, and saying so here is more honest
# than a check that always passes.

MATURITY_LABEL = {
    "proven": "✅ proven",
    "unverified": "⚪ unverified",
    "experimental": "⚠️ experimental",
    "pointer": "↗️ pointer",
    # Not a degree of confidence — a switch. It is off, and the catalogue has to
    # say so, or a component that cannot run reads as one that simply has not
    # been vouched for yet.
    "disabled": "⛔ disabled",
}

# Grouping is editorial — it is the one part of this file a human chooses, so it
# lives here rather than in 21 separate frontmatter blocks. A component not
# listed falls into "Other", which is visible rather than silently dropped.
GROUPS = [
    ("Audits — read-only, report-never-fix", [
        "audit-tokens", "audit-accessibility", "audit-semantics", "audit-focus-order", "audit-copy",
        "audit-mock-api", "audit-contrast", "audit-claude-md-drift",
    ]),
    # Separate from both "Audits" and "Building": these read an audit's findings
    # and emit a patch, and the distinction from the group above is the whole
    # point — an audit reports, a repair generates, and neither applies anything.
    ("Repair — generates a diff, never applies it", ["repair-tokens"]),
    ("Interchange — DTCG token files", ["export-tokens-dtcg", "import-tokens-dtcg"]),
    ("Documentation lifecycle", ["review-docs", "sync-docs", "bootstrap-design-docs"]),
    ("Discovery — what a project is, and what its config has stopped describing", ["survey"]),
    ("Establishing conventions — brand-sensitive", [
        "establish-brand-voice", "establish-interaction-spec",
    ]),
    ("Building", ["scaffold-screen", "wire-endpoint", "sync-mock-api", "promote-component", "suggest-component"]),
    ("Assets — the 3D pipeline", [
        "audit-assets", "add-asset", "generate-asset", "animate-asset",
    ]),
    ("Copy", ["rewrite-copy"]),
    ("Playbooks", ["onboard-new-client", "run-chain"]),
    # No group for design-critic: GROUPS applies to skills, and agents render in
    # their own section. An entry here for an agent is silently dead config.
    ("Capture — what a session produced", [
        "session-decisions", "log-decision", "capture-backlog",
    ]),
    ("Demos and reporting", [
        "design-debt", "generate-walkthrough", "generate-client-readiness",
    ]),
    ("PR workflow", ["draft-pr-description", "design-review-pr"]),
]


def frontmatter(path: Path) -> dict | None:
    """Parse the frontmatter block without a YAML dependency.

    Only flat `key: value` pairs are needed here, and every field this reads is
    written by hand in that shape. A quoted description keeps its quotes stripped.
    """
    text = path.read_text()
    if not text.startswith("---"):
        return None
    try:
        end = text.index("\n---\n", 3)
    except ValueError:
        return None
    meta: dict = {}
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key.strip()] = value
    return meta


def disabled_registry() -> tuple[dict, str | None]:
    """`audit_discovery.DISABLED`, or `({}, reason)` if it cannot be read.

    Imported rather than re-parsed so there is exactly one registry. If the
    import fails the caller must report that — an unreadable registry means the
    parity check below did not run, and a check that did not run must never be
    reported as a check that passed.
    """
    plugin_root = PLUGINS / "backend-suite"
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))
    try:
        from backend_suite.engine import audit_discovery
    except Exception as exc:  # noqa: BLE001 - any failure is the same finding
        return {}, f"cannot import backend_suite.engine.audit_discovery ({exc})"
    return dict(audit_discovery.DISABLED), None


def maturity_parity(data: dict) -> list[str]:
    """Cross-check the two places a component can be switched off.

    There are two registries of "this is disabled" and they are keyed
    differently: `audit_discovery.DISABLED` by *script stem*
    (`audit_accessibility`), and `maturity: disabled` by *component name*
    (`audit-accessibility`) in frontmatter. Nothing used to compare them, so a
    script disabled in the registry whose command still claimed `proven` shipped
    green — the catalogue then reports a result for a check that refuses to run,
    which is exactly the silence the registry's own docstring forbids.

    The two keyings map onto each other by kebab/snake case, which is the only
    correspondence there is; a component with no backing `bin/<stem>.py` is not
    an audit and is left alone.
    """
    problems: list[str] = []
    registry, failure = disabled_registry()
    if failure:
        return [f"maturity parity: {failure} — the disabled-registry parity check "
                f"did not run, which is not the same as passing"]

    bin_dir = PLUGINS / "backend-suite" / "bin"
    # name -> maturity, across every plugin: the registry is backend-suite's, but
    # a command in any plugin could name a backend-suite audit script.
    declared: dict[str, str] = {}
    for entry in data.values():
        for comp in entry["skills"] + entry["agents"]:
            declared[comp["name"]] = comp["maturity"]

    for name, maturity in sorted(declared.items()):
        stem = name.replace("-", "_")
        if not (bin_dir / f"{stem}.py").is_file():
            continue  # not backed by an audit script; the registry cannot speak for it
        in_registry = stem in registry
        if in_registry and maturity != "disabled":
            problems.append(
                f"{name}: frontmatter says maturity={maturity!r} but "
                f"audit_discovery.DISABLED lists {stem!r} — the catalogue would "
                f"report a live component for a script that refuses with exit 2")
        elif not in_registry and maturity == "disabled":
            problems.append(
                f"{name}: frontmatter says maturity='disabled' but {stem!r} is not "
                f"in audit_discovery.DISABLED — the script still runs, so every "
                f"other surface reports its findings as live")

    # The other direction: a registry entry no component mirrors. The catalogue
    # is one of the surfaces the registry's docstring requires to name it, and
    # it can only do that through a component.
    for stem in sorted(registry):
        if stem.replace("_", "-") not in declared:
            problems.append(
                f"audit_discovery.DISABLED lists {stem!r} but no component is named "
                f"{stem.replace('_', '-')!r} — the catalogue cannot name it as "
                f"disabled, so its silence reads as absence")

    return problems


def collect() -> tuple[dict, list[str]]:
    """{plugin: {"skills": [...], "agents": [...], "hooks": [...]}}, plus problems."""
    out: dict = {}
    problems: list[str] = []

    for plugin_dir in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        entry = {"skills": [], "agents": [], "hooks": []}

        for kind, subdir in (("skills", "commands"), ("agents", "agents")):
            for f in sorted((plugin_dir / subdir).glob("*.md")):
                meta = frontmatter(f)
                if meta is None:
                    problems.append(f"{f.relative_to(REPO)}: no frontmatter block")
                    continue
                for field, allowed in (("invocation", VALID_INVOCATION),
                                       ("maturity", VALID_MATURITY)):
                    if field not in meta:
                        problems.append(
                            f"{f.relative_to(REPO)}: missing '{field}' "
                            f"(one of {sorted(allowed)})")
                    elif meta[field] not in allowed:
                        problems.append(
                            f"{f.relative_to(REPO)}: {field}={meta[field]!r} "
                            f"is not one of {sorted(allowed)}")
                if not meta.get("description"):
                    problems.append(f"{f.relative_to(REPO)}: empty description")
                entry[kind].append({
                    "name": meta.get("name", f.stem),
                    "description": meta.get("description", ""),
                    "invocation": meta.get("invocation", "?"),
                    "maturity": meta.get("maturity", "?"),
                })

        hooks_file = plugin_dir / "hooks" / "hooks.json"
        if hooks_file.is_file():
            try:
                cfg = json.loads(hooks_file.read_text())
            except ValueError as exc:
                problems.append(f"{hooks_file.relative_to(REPO)}: invalid JSON ({exc})")
                cfg = {}
            for event, matchers in (cfg.get("hooks") or {}).items():
                for m in matchers:
                    for h in m.get("hooks", []):
                        script = re.sub(r'.*/(\w+\.py).*', r"\1", h.get("command", ""))
                        entry["hooks"].append({
                            "event": event,
                            "matcher": m.get("matcher", "*"),
                            "script": script,
                            "message": h.get("statusMessage", ""),
                        })
        elif (plugin_dir / "hooks").is_dir() and any((plugin_dir / "hooks").glob("*.py")):
            problems.append(
                f"{plugin_dir.relative_to(REPO)}/hooks/: has .py files but no hooks.json — "
                "they are inert until registered")

        out[plugin_dir.name] = entry
    return out, problems


def render(data: dict) -> str:
    total_skills = sum(len(v["skills"]) for v in data.values())
    total_agents = sum(len(v["agents"]) for v in data.values())
    total_hooks = sum(len(v["hooks"]) for v in data.values())

    L: list[str] = []
    add = L.append
    add("# Catalogue")
    add("")
    add("**Generated — do not edit by hand.** Regenerate with "
        "`python3 plugins/backend-suite/bin/catalog.py`; CI fails if this file is stale.")
    add("")
    add("A catalogue is a list of file-existence facts, and hand-written prose about those "
        "has already gone wrong three times in this project's history. So it is generated "
        "from the plugins' own frontmatter instead.")
    add("")
    add(f"**{total_skills} skills · {total_agents} agents · {total_hooks} hooks** "
        f"across {len(data)} plugins.")
    add("")
    summary, _ = templates()
    if summary:
        add(summary)
        add("")
    add("## How to read this")
    add("")
    add("**Invocation** — `auto` means Claude may run it from plain language, without you "
        "naming it, because it is read-only or asks before writing. `explicit` means it "
        "waits for a real decision from you: brand voice, project-wide conventions, and "
        "generated content that someone has to approve.")
    add("")
    add("**Maturity** is deliberately visible rather than buried:")
    add("")
    add("| | Means |")
    add("|---|---|")
    add("| ✅ proven | Recorded evidence of a real end-to-end run |")
    add("| ⚪ unverified | **No such evidence found — not a claim it is broken.** "
        "It may work fine; nobody has confirmed it |")
    add("| ⚠️ experimental | Known rough edges. Read its own file before relying on it |")
    add("| ↗️ pointer | Not an implementation. Tells you where the real thing lives |")
    add("| ⛔ disabled | **Switched off. It refuses (exit 2) rather than running.** Not a confidence level — a decision, taken against measured evidence. Its own file states the reason and the bar for re-enabling it |")
    add("")

    for plugin, entry in sorted(data.items()):
        add(f"## `{plugin}`")
        add("")
        by_name = {s["name"]: s for s in entry["skills"]}
        grouped = set()

        for title, names in GROUPS:
            rows = [by_name[n] for n in names if n in by_name]
            if not rows:
                continue
            grouped.update(r["name"] for r in rows)
            add(f"### {title}")
            add("")
            add("| Skill | Invocation | Maturity | What it does |")
            add("|---|---|---|---|")
            for r in rows:
                add(f"| `/{r['name']}` | {r['invocation']} | "
                    f"{MATURITY_LABEL.get(r['maturity'], r['maturity'])} | {r['description']} |")
            add("")

        ungrouped = [s for s in entry["skills"] if s["name"] not in grouped]
        if ungrouped:
            add("### Other")
            add("")
            add("Not assigned to a group in `catalog.py`. Visible rather than dropped.")
            add("")
            add("| Skill | Invocation | Maturity | What it does |")
            add("|---|---|---|---|")
            for r in ungrouped:
                add(f"| `/{r['name']}` | {r['invocation']} | "
                    f"{MATURITY_LABEL.get(r['maturity'], r['maturity'])} | {r['description']} |")
            add("")

        if entry["agents"]:
            add("### Agents")
            add("")
            add("| Agent | Invocation | Maturity | What it does |")
            add("|---|---|---|---|")
            for r in entry["agents"]:
                add(f"| `{r['name']}` | {r['invocation']} | "
                    f"{MATURITY_LABEL.get(r['maturity'], r['maturity'])} | {r['description']} |")
            add("")

        if entry["hooks"]:
            add("### Hooks")
            add("")
            add("Automatic by definition, so they carry no invocation tier. They are "
                "harness-only: they nudge, they never edit. Listed from `hooks/hooks.json`, "
                "which is what actually registers them — a hook script present but "
                "unregistered does nothing, and that is the failure worth catching.")
            add("")
            add("| Event | Matcher | Script | Nudge |")
            add("|---|---|---|---|")
            for h in entry["hooks"]:
                add(f"| {h['event']} | `{h['matcher']}` | `{h['script']}` | {h['message']} |")
            add("")

    # There used to be a hand-written "Not included" table here, listing what the
    # suite cannot do. It went stale exactly the way every other hand-written
    # claim in this project has: it said Tailwind token *enumeration* "is not
    # done" long after `adapters/tailwind_theme.py` was written to do it, and
    # `tsx.token_names()` was wired to delegate to it under its own CI gate. The
    # claim was prose living inside the generator, laundered through a generated
    # file — so `--check` compared it only against itself and could never
    # falsify it. That is the failure mode this file's own header says generation
    # exists to prevent, reproduced inside the generator.
    #
    # It is deleted rather than re-derived because nothing here can check it:
    # a capability *absence* ("this adapter cannot enumerate X") is not a
    # file-existence fact, which is the only kind of fact catalog.py is able to
    # assert. Any data file of such claims would be the same prose one
    # indirection further away. It also carried a consumer project's name, which
    # CLAUDE.md's no-project-literals rule forbids in the universal plugin.
    #
    # The honest content keeps living where it *can* be falsified: each adapter's
    # own module docstring, next to the code, covered by that adapter's
    # self-test gate; and the asset pipeline's `check` subcommand, which probes
    # for its external binaries at runtime instead of asserting their absence.
    add("## What this catalogue does not tell you")
    add("")
    add("Every row above is a file-existence fact, which is all a generator can honestly "
        "assert. **Capability limits are not listed here** — a claim that something "
        "*cannot* be done is not checkable from the filesystem, and a stale one of those "
        "already shipped in this file once. Read them where they are gated instead:")
    add("")
    add("- **Per-language limits** — each adapter's module docstring in "
        "`backend_suite/adapters/`, beside the code and covered by that adapter's own "
        "self-test.")
    add("- **External toolchain** (Blender, `cwebp`, `rsvg-convert`) — run "
        "`pipeline.py check`, which probes for them rather than asserting anything.")
    add("- **Whether a component has ever actually been run** — the `maturity` column, "
        "and `verify.py` for the evidence behind it.")
    add("")
    return "\n".join(L) + "\n"


def templates() -> tuple[str, list[str]]:
    """(summary line, problems). Coverage computed, never asserted in prose.

    The previous hand-written claim in the templates README said "the four written
    are the ones the tooling depends on" while the inventory directly below it
    listed seven. That is exactly the class of error catalog.py exists to remove,
    so template coverage is now derived from roles.json the same way the component
    tables are derived from frontmatter.
    """
    problems: list[str] = []
    spec_path = PLUGINS / "backend-suite" / "templates" / "docs" / "roles.json"
    if not spec_path.is_file():
        return "", [f"{spec_path.relative_to(REPO)}: missing — "
                    "template coverage cannot be checked"]

    spec = json.loads(spec_path.read_text())
    roles = spec.get("roles", {})
    external = spec.get("externalPlugin", {})
    kinds = [k for k in spec.get("archetypes", {}) if not k.startswith("_")]

    # A role may legitimately have no template — it is scaffolding, and a document
    # another repo owns has nothing to scaffold. What must never happen is that
    # absence reading as coverage, so the count below is of templates that exist,
    # and the roles without one are named rather than subtracted silently.
    uncovered: list[str] = []
    covered = 0
    for role, entry in sorted(roles.items()):
        filename = entry.get("template")
        if filename is None:
            uncovered.append(role)
            if not entry.get("noTemplateReason"):
                problems.append(
                    f"roles.json: role {role!r} has no template and no "
                    f"'noTemplateReason' — an unexplained gap is indistinguishable "
                    f"from an oversight")
            continue
        if not (spec_path.parent / filename).is_file():
            problems.append(f"roles.json: role {role!r} declares {filename}, "
                            f"which does not exist")
        else:
            covered += 1
        page = entry.get("pageTemplate")
        if page and not (spec_path.parent / page).is_file():
            problems.append(f"roles.json: role {role!r} declares pageTemplate "
                            f"{page}, which does not exist")

    for role, entry in sorted(roles.items()):
        if entry.get("group") not in spec.get("groups", {}):
            problems.append(f"roles.json: role {role!r} declares no known 'group'")
        declared_kinds = entry.get("archetypes", {})
        missing = [k for k in kinds if k not in declared_kinds]
        if missing:
            problems.append(f"roles.json: role {role!r} says nothing about "
                            f"{', '.join(missing)} — every role must state its "
                            f"applicability for every archetype, since an omission "
                            f"reads the same as 'not applicable'")

    for role, ref in sorted(external.items()):
        target = PLUGINS / ref["plugin"] / "templates" / "docs" / ref["template"]
        if not target.is_file():
            problems.append(f"roles.json: role {role!r} declares "
                            f"{ref['plugin']}/{ref['template']}, which does not exist")

    # An orphan template is a real finding, not tidiness: /bootstrap-design-docs
    # installs by role, so a template no role names is unreachable.
    # `pageTemplate` counts as declared: a role like `components` emits an index
    # plus one page per component, so a second template is reachable through the
    # same role. Without this it would read as an orphan and tempt someone to
    # delete a template that is genuinely installed.
    declared = {e.get("template") for e in roles.values()}
    declared |= {e.get("pageTemplate") for e in roles.values()}
    for f in sorted(spec_path.parent.glob("*.template")):
        if f.name not in declared:
            problems.append(
                f"templates/docs/{f.name}: not declared for any role in roles.json — "
                f"unreachable, because templates are installed by role")

    total_roles = len(roles) + len(external)
    every = list(roles.values()) + list(external.values())
    per_group = ", ".join(
        f"{g} {sum(1 for e in every if e.get('group') == g)}"
        for g in sorted(k for k in spec.get("groups", {}) if not k.startswith("_")))
    per_kind = []
    for kind in sorted(kinds):
        applicable = sum(
            1 for e in list(roles.values()) + list(external.values())
            if e.get("archetypes", {}).get(kind) in {"expected", "optional"})
        per_kind.append(f"{kind} {applicable}")

    summary = (
        f"**{covered + len(external)} documentation templates** across "
        f"**{total_roles} roles** — {covered} in `backend-suite`, "
        f"{len(external)} in `house-style`. "
        f"{len(uncovered)} role(s) have no template and cannot be scaffolded: "
        f"{', '.join(f'`{r}`' for r in uncovered)}. "
        f"Vocabulary by group: {per_group}. "
        f"Roles applicable per archetype: {', '.join(per_kind)}.")
    return summary, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed catalogue is stale or fields are missing")
    args = ap.parse_args()

    data, problems = collect()
    problems += templates()[1]
    problems += maturity_parity(data)
    if problems:
        print("catalog: declaration problems\n", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        print("\nEvery skill and agent must declare 'invocation' and 'maturity' in its "
              "frontmatter, and every hooks/ directory with scripts needs a hooks.json.",
              file=sys.stderr)
        return 1

    rendered = render(data)

    if args.check:
        if not OUT.is_file():
            print(f"catalog: {OUT.relative_to(REPO)} does not exist — run catalog.py",
                  file=sys.stderr)
            return 1
        if OUT.read_text() != rendered:
            print(f"catalog: {OUT.relative_to(REPO)} is stale — run "
                  "`python3 plugins/backend-suite/bin/catalog.py` and commit the result",
                  file=sys.stderr)
            return 1
        print("catalog: up to date.")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(rendered)
    print(f"catalog: wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
