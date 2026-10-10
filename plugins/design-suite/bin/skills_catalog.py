#!/usr/bin/env python3
"""Generate docs/SKILLS.md — the *user-facing* catalogue.

    python3 plugins/design-suite/bin/skills_catalog.py           # write docs/SKILLS.md
    python3 plugins/design-suite/bin/skills_catalog.py --check   # exit 1 if stale
    python3 plugins/design-suite/bin/skills_catalog.py --html    # write docs/design-suite-guide.html
    python3 plugins/design-suite/bin/skills_catalog.py --html --check

## Why a sibling of catalog.py rather than a mode inside it

`catalog.py` answers a maintainer's question — does every component declare its
fields, do the two disabled-registries agree, is every template reachable by a
role. Its output is organised by plugin, and its `--check` is really a
declaration gate that happens to also diff a file.

This file answers a different question, for a different reader: *what can I
type, will it fire on its own, and can I trust it yet.* It needs three data
sources `catalog.py` has no reason to touch — `repo_health.py`'s audit discovery,
the agents' `tools:` grants, and a description trimmed out of matcher-speak into
something a human reads once. Threading a second reader's grouping, a second
maturity vocabulary and three extra sources through `catalog.render()` would
contort it into a two-audience template engine, and the maturity-parity and
templates checks would then run twice per CI job for no gain.

So: a sibling that **imports** `catalog.py` for frontmatter parsing and
component collection. There is still exactly one parser and one collector; what
differs is only the rendering and the extra sources. Nothing here re-derives a
fact `catalog.py` already derives.

Stdlib only, like every other script here.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
REPO = BIN.parents[2]
PLUGINS = REPO / "plugins"
OUT = REPO / "docs" / "SKILLS.md"
OUT_HTML = REPO / "docs" / "design-suite-guide.html"
ROLES_JSON = PLUGINS / "design-suite" / "templates" / "docs" / "roles.json"

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
import catalog  # noqa: E402  - same directory, stdlib-only, no side effects on import

# Plain-language markers. Deliberately NOT catalog.py's maintainer vocabulary:
# "⚪ unverified" tells a maintainer that no evidence file exists; it tells a
# user nothing about what to *do*. "use with review" does.
MATURITY_LABEL = {
    "proven": "✅ proven",
    "unverified": "⚠️ use with review",
    "experimental": "⚠️ experimental",
    "pointer": "pointer — runs nothing here",
    "disabled": "🔴 off",
}

# Sentence openers that begin a *trigger* clause — text written for Claude's
# matcher, not for a human reading a table. Everything from such a sentence
# onwards is dropped; the capability half in front of it is kept verbatim.
TRIGGER_OPENERS = (
    "use when", "use after", "use before", "use this", "use it",
    "start here when", "run when", "use whenever",
)

# Job-to-be-done buckets for the cheat sheet.
#
# HONEST NOTE, restated in the generated file: **no frontmatter field encodes a
# job-to-be-done.** The frontmatter carries name/description/invocation/maturity
# and nothing else, so this grouping cannot be read off it. Rather than invent a
# second editorial registry to drift against the first, the rules below derive
# the bucket from two things that already exist and are already gated:
#
#   1. the command's own *name* — `audit-*`, `*-asset`, `*mock-api*` are
#      naming conventions the repo already enforces in other gates;
#   2. `catalog.GROUPS`, the editorial grouping `catalog.py` already maintains
#      and renders into docs/CATALOG.md.
#
# Name rules run first because they are mechanical; the GROUPS map is the
# fallback; anything neither answers lands in a visible "Other" bucket rather
# than being silently dropped.
BUCKETS = ["Audit", "Document", "Generate", "Assets", "Mock API", "Workflow", "Other"]

NAME_RULES: list[tuple[str, str]] = [
    (r"mock-api", "Mock API"),
    (r"(^|-)asset(s)?$", "Assets"),
    (r"^audit-", "Audit"),
]

GROUP_BUCKET = {
    "Audits — read-only, report-never-fix": "Audit",
    "Repair — generates a diff, never applies it": "Generate",
    "Documentation lifecycle": "Document",
    "Discovery — what a project is, and what its config has stopped describing": "Workflow",
    "Establishing conventions — brand-sensitive": "Document",
    "Building": "Generate",
    "Assets — the 3D pipeline": "Assets",
    "Copy": "Document",
    "Playbooks": "Workflow",
    "Capture — what a session produced": "Document",
    "Demos and reporting": "Generate",
    "PR workflow": "Workflow",
}


def one_liner(description: str, limit: int = 170) -> str:
    """The capability half of a description, as one readable line.

    Descriptions here are written for Claude's matcher: capability text, then a
    "Use when asked to…" trigger clause. The trigger clause is the half that is
    useless in a table a human scans, so it is dropped — but nothing is
    rewritten, because an invented description is exactly the hand-written claim
    this file exists to abolish.
    """
    text = " ".join(description.split())
    # Split on sentence ends, keeping the terminator.
    parts = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for part in parts:
        low = part.lower().lstrip("*_ ")
        if any(low.startswith(o) for o in TRIGGER_OPENERS):
            break
        kept.append(part)
    if not kept:  # a description that is *only* a trigger clause: keep it rather than blank
        kept = parts[:1]
    # Greedy: take whole sentences while they fit, so a short opener like
    # "Pointer, not an implementation." keeps the sentence that explains it.
    out = kept[0].strip()
    for extra in kept[1:]:
        if len(out) + 1 + len(extra) > limit:
            break
        out = f"{out} {extra.strip()}"
    out = out.replace('\\"', '"').replace("\\'", "'")
    if len(out) > limit:
        cut = out[:limit].rsplit(" ", 1)[0]
        out = cut.rstrip(" ,;:—-") + "…"
    return out.replace("|", "\\|")


def agent_tools() -> dict[str, str]:
    """{agent name: its `tools:` grant}, read from frontmatter, never asserted.

    The claim "the agents are read-only" is only worth printing if it is
    measured, so the grant is read and rendered; `render()` then checks it
    rather than trusting the sentence.
    """
    out: dict[str, str] = {}
    for plugin_dir in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        for f in sorted((plugin_dir / "agents").glob("*.md")):
            meta = catalog.frontmatter(f) or {}
            out[meta.get("name", f.stem)] = meta.get("tools", "")
    return out


WRITE_TOOLS = {"write", "edit", "notebookedit", "bash", "multiedit"}


def audits() -> tuple[list[dict], list[str]]:
    """Every audit, from `repo_health.py --list`. Never hand-listed.

    A hand-listed audit table would be wrong the first time an audit is added,
    and would be wrong *silently* — which is the one failure mode this repo
    treats as unacceptable. So the list comes from the same discovery the MCP
    server and `/repo-health` use.
    """
    proc = subprocess.run(
        [sys.executable, str(BIN / "repo_health.py"), "--list"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return [], [f"repo_health.py --list exited {proc.returncode}: "
                    f"{proc.stderr.strip() or '(no stderr)'} — the audit table cannot be "
                    f"generated, and an empty audit table must never be published as "
                    f"'no audits'"]
    rows: list[dict] = []
    problems: list[str] = []
    commands = {p.stem for p in (PLUGINS / "design-suite" / "commands").glob("*.md")}
    for line in proc.stdout.strip().splitlines():
        cells = line.split("\t")
        if len(cells) < 5:
            problems.append(f"repo_health.py --list: unparseable row {line!r}")
            continue
        name, state, _findings, _reason, script = cells[:5]
        slug = name.replace("_", "-")
        rows.append({
            "name": name,
            "slug": slug,
            "state": state,
            "script": script,
            "command": slug if slug in commands else None,
        })
    if not rows:
        problems.append("repo_health.py --list produced no audits — refusing to publish "
                        "an empty audit table, which would read as 'this suite audits "
                        "nothing'")
    return rows, problems


def disabled_detail() -> tuple[dict, list[str]]:
    registry, failure = catalog.disabled_registry()
    if failure:
        return {}, [f"SKILLS: {failure} — the disabled audits cannot be named with their "
                    f"measured reason, and an unnamed disabled audit reads as a live one"]
    return registry, []


def hooks() -> tuple[list[dict], list[str]]:
    """Registered hooks, from each plugin's hooks/hooks.json."""
    rows: list[dict] = []
    problems: list[str] = []
    for plugin_dir in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        f = plugin_dir / "hooks" / "hooks.json"
        if not f.is_file():
            continue
        cfg = json.loads(f.read_text())
        for event, matchers in (cfg.get("hooks") or {}).items():
            for m in matchers:
                for h in m.get("hooks", []):
                    rows.append({
                        "plugin": plugin_dir.name,
                        "event": event,
                        "matcher": m.get("matcher", "*"),
                        "script": re.sub(r".*/(\w+\.py).*", r"\1", h.get("command", "")),
                        "message": h.get("statusMessage", ""),
                    })
    if not rows:
        problems.append("no hooks found in any hooks.json — refusing to publish an "
                        "empty hooks table")
    return rows, problems


def bucket_of(name: str, group_index: dict[str, str]) -> str:
    for pattern, bucket in NAME_RULES:
        if re.search(pattern, name):
            return bucket
    group = group_index.get(name)
    if group and group in GROUP_BUCKET:
        return GROUP_BUCKET[group]
    return "Other"


def group_index() -> dict[str, str]:
    return {n: title for title, names in catalog.GROUPS for n in names}


def skill_rows(data: dict) -> list[dict]:
    rows = []
    for plugin, entry in sorted(data.items()):
        for s in entry["skills"]:
            rows.append(dict(s, plugin=plugin))
    return sorted(rows, key=lambda r: r["name"])


def agent_rows(data: dict) -> list[dict]:
    rows = []
    for plugin, entry in sorted(data.items()):
        for a in entry["agents"]:
            rows.append(dict(a, plugin=plugin))
    return sorted(rows, key=lambda r: r["name"])


def render(data: dict) -> tuple[str, list[str]]:
    problems: list[str] = []
    skills = skill_rows(data)
    agents = agent_rows(data)
    audit_rows, p = audits(); problems += p
    registry, p = disabled_detail(); problems += p
    hook_rows, p = hooks(); problems += p
    grants = agent_tools()
    gi = group_index()

    auto = [s for s in skills if s["invocation"] == "auto"]
    explicit = [s for s in skills if s["invocation"] == "explicit"]
    with_command = [a for a in audit_rows if a["command"]]
    without_command = [a for a in audit_rows if not a["command"]]
    off = [a for a in audit_rows if a["state"] != "live"]

    L: list[str] = []
    add = L.append
    add("# What you can run")
    add("")
    add("**Generated — do not edit by hand.** Regenerate with "
        "`python3 plugins/design-suite/bin/skills_catalog.py`; CI fails if this file is "
        "stale, exactly as it does for `docs/CATALOG.md`.")
    add("")
    add("The user-facing companion to [CATALOG.md](./CATALOG.md). That one is organised "
        "for a maintainer, by plugin; this one is organised around what you type and "
        "whether you can trust the answer. Every row below is read from the components' "
        "own frontmatter, from `repo_health.py`'s audit discovery, and from each plugin's "
        "`hooks/hooks.json` — nothing here is typed by hand, because hand-written claims "
        "about this repo's own contents have been wrong repeatedly.")
    add("")
    add(f"**{len(skills)} slash commands · {len(agents)} agents · {len(audit_rows)} audits "
        f"· {len(hook_rows)} hooks.**")
    add("")
    add("### What the maturity markers mean")
    add("")
    add("| Marker | Means |")
    add("|---|---|")
    add("| ✅ proven | There is recorded evidence of a real end-to-end run |")
    add("| ⚠️ use with review | Nobody has confirmed it end to end. Not a claim it is "
        "broken — read what it produces before acting on it |")
    add("| ⚠️ experimental | Known rough edges. Read its own file first |")
    add("| pointer — runs nothing here | Not an implementation. It tells you where the "
        "real thing lives |")
    add("| 🔴 off | Switched off. It refuses (exit 2) rather than running, for a measured "
        "reason stated in its own file |")
    add("")

    add("## Commands that can fire on their own")
    add("")
    add(f"These **{len(auto)}** are marked `invocation: auto`: Claude may run them from "
        "plain language, without you naming them, because they are read-only or ask "
        "before writing. You can still type them.")
    add("")
    add("| Slash command | What it does | Fires | Maturity | Plugin |")
    add("|---|---|---|---|---|")
    for s in auto:
        add(f"| `/{s['name']}` | {one_liner(s['description'])} | auto | "
            f"{MATURITY_LABEL.get(s['maturity'], s['maturity'])} | `{s['plugin']}` |")
    add("")

    add("## Commands that wait for you to ask")
    add("")
    add(f"These **{len(explicit)}** are marked `invocation: explicit`: they generate "
        "content, set project-wide conventions, or touch brand, so they never start "
        "themselves. Type them.")
    add("")
    add("| Slash command | What it does | Fires | Maturity | Plugin |")
    add("|---|---|---|---|---|")
    for s in explicit:
        add(f"| `/{s['name']}` | {one_liner(s['description'])} | explicit | "
            f"{MATURITY_LABEL.get(s['maturity'], s['maturity'])} | `{s['plugin']}` |")
    add("")

    add("## Agents")
    add("")
    granted = {a["name"]: [t.strip() for t in grants.get(a["name"], "").split(",") if t.strip()]
               for a in agents}
    writers = sorted(n for n, t in granted.items()
                     if any(x.lower() in WRITE_TOOLS for x in t))
    if writers:
        problems.append(
            "agents " + ", ".join(writers) + " hold a writing tool — the read-only "
            "sentence in docs/SKILLS.md would be false, so the generator refuses rather "
            "than printing it")
    grant_text = "; ".join(f"`{n}` → {', '.join(t) or '(no tools: key)'}"
                           for n, t in sorted(granted.items()))
    add(f"All {len(agents)} are read-only, and that is checked rather than asserted: each "
        f"one's `tools:` grant is {grant_text}. None is granted `Write`, `Edit` or `Bash`, "
        f"so none can change a file. They report; you decide.")
    add("")
    add("| Agent | What it does | Fires | Maturity | Plugin |")
    add("|---|---|---|---|---|")
    for a in agents:
        add(f"| `{a['name']}` | {one_liner(a['description'])} | {a['invocation']} | "
            f"{MATURITY_LABEL.get(a['maturity'], a['maturity'])} | `{a['plugin']}` |")
    add("")

    add("## Audits")
    add("")
    add(f"**{len(audit_rows)} audits**, enumerated by `python3 "
        f"plugins/design-suite/bin/repo_health.py --list` — the same discovery "
        f"`/repo-health` and the MCP audit server use, so this table cannot disagree with "
        f"what actually runs.")
    add("")
    add(f"**{len(with_command)} of them have a matching `/audit-…` command; "
        f"{len(without_command)} do not.** The ones that do not are not hidden and not "
        f"broken — they are simply reachable another way: `/repo-health` (which runs all "
        f"of them), the MCP audit server in `plugins/design-suite/mcp/audit_server.py`, "
        f"the edit-triggered hook, or running the script directly. The column below says "
        f"which, per audit.")
    add("")
    add("| Audit | Live? | Reachable how | Backing script |")
    add("|---|---|---|---|")
    for a in audit_rows:
        live = "live" if a["state"] == "live" else "🔴 off"
        if a["command"]:
            how = f"`/{a['command']}`, `/repo-health`, MCP, or the script directly"
        else:
            how = "`/repo-health`, MCP, or the script directly — **no slash command**"
        add(f"| `{a['name']}` | {live} | {how} | `{a['script']}` |")
    add("")
    add(f"### The {len(off)} switched off, and why")
    add("")
    add("A disabled audit stays discoverable on purpose. A check that quietly stopped "
        "running looks exactly like a check that ran and found nothing, so every surface "
        "has to name it.")
    add("")
    add("| Audit | Measured reason |")
    add("|---|---|")
    for a in off:
        reason = (registry.get(a["name"], {}) or {}).get(
            "reason", "switched off — no reason recorded in audit_discovery.DISABLED")
        add(f"| `{a['name']}` | {reason.replace('|', chr(92) + '|')} |")
    add("")

    add("## Hooks")
    add("")
    events = sorted({h["event"] for h in hook_rows})
    add(f"**{len(hook_rows)} hooks**, read from each plugin's `hooks/hooks.json` — the "
        f"file that actually registers them, on `{'`, `'.join(events)}`. Every one is "
        f"advisory: a `PostToolUse` hook prints a reminder after a tool call, a "
        f"`SessionStart` hook adds a note to Claude's context when a session opens, and "
        f"none of them edits, writes, blocks, or fails anything.")
    add("")
    add("| Hook | Plugin | Fires on | What you see |")
    add("|---|---|---|---|")
    for h in hook_rows:
        matcher = h["matcher"].replace("|", "\\|")
        add(f"| `{h['script']}` | `{h['plugin']}` | {h['event']} on "
            f"`{matcher}` | {h['message'].replace('|', chr(92) + '|')} |")
    add("")
    unexplained = sorted(set(events) - {"PostToolUse", "SessionStart"})
    if unexplained:
        problems.append(
            f"hooks are registered for {unexplained}, which the hooks sentence in "
            f"docs/SKILLS.md does not describe — extend it before publishing")

    add("## Cheat sheet")
    add("")
    add("Every slash command, by the job you came here to do. Names only.")
    add("")
    add("*How this grouping is derived:* **no frontmatter field encodes a "
        "job-to-be-done** — components declare `name`, `description`, `invocation` and "
        "`maturity`, and nothing more. Rather than invent a second editorial list to "
        "drift against the first, the buckets come from two things that already exist: "
        "the command's own name (`audit-…`, `…-asset`, `…mock-api…`, which other gates "
        "already depend on), and failing that, `GROUPS` in `catalog.py` — the grouping "
        "already maintained for `docs/CATALOG.md`. Anything neither rule places lands in "
        "**Other**, visibly, rather than being dropped.")
    add("")
    buckets: dict[str, list[str]] = {b: [] for b in BUCKETS}
    for s in skills:
        buckets[bucket_of(s["name"], gi)].append(s["name"])
    for b in BUCKETS:
        if not buckets[b]:
            continue
        add(f"**{b}** ({len(buckets[b])}) — "
            + " · ".join(f"`/{n}`" for n in sorted(buckets[b])))
        add("")
    placed = sum(len(v) for v in buckets.values())
    if placed != len(skills):
        problems.append(f"cheat sheet placed {placed} of {len(skills)} commands")
    add(f"{placed} of {len(skills)} commands placed.")
    add("")
    return "\n".join(L) + "\n", problems


# ---------------------------------------------------------------------------
# HTML mode — docs/design-suite-guide.html
#
# The guide is a hand-designed page, not a report. Its HTML, CSS, copy and
# layout are authored and reviewed; only the *facts* in it are derivable. So it
# is not regenerated from scratch — it is its own template. Marked regions
# (`<!--gen:key-->…<!--gen:/key-->`, `/*gen:key*/…/*gen:/key*/` inside the
# script) are replaced in place; everything outside them is authored prose and
# is carried through byte-for-byte.
#
# What deliberately stays hand-written, and why (rule: say it, never leave it
# silently hand-written):
#
#   * the masthead date — a publication date is not derivable from frontmatter,
#     and deriving it from the clock would make `--check` flap daily;
#   * the two disabled audits' measured failure rates, the hooks.map.json
#     history, the `/scaffold-screen` exception, the exit-code contract, the
#     install recipes, the "say this and this fires" examples — judgement and
#     measurement, none of it in any frontmatter field;
#   * "30 commands installed against 50 shipped" in the version section — that
#     is a historical measurement on one machine. Re-deriving the 50 would
#     silently rewrite what was actually observed.
#
# The disabled-audit table is authored prose, so the generator cross-checks it
# instead of emitting it: every audit discovery reports as off must be named
# somewhere in the page, or that is a problem.
# ---------------------------------------------------------------------------

# The page's own maturity vocabulary, keyed the way its JS `M` map is keyed.
# Deliberately a *mapping* from the frontmatter vocabulary rather than a second
# copy of it: a maturity value with no entry here is a hard error, because the
# alternative is a row that quietly renders with no maturity at all.
HTML_MATURITY_KEY = {
    "proven": "proven",
    "unverified": "review",
    "experimental": "experimental",
    "pointer": "pointer",
    "disabled": "off",
}

# key -> (css class, label). Must stay in step with the `M` map in the page's
# own script; `render_html` checks that rather than trusting it.
HTML_MATURITY_TAG = {
    "proven": ("t-ok", "✅ proven"),
    "review": ("t-warn", "⚠ use with review"),
    "experimental": ("t-warn", "⚠ experimental"),
    "pointer": ("t-plain", "pointer"),
    "off": ("t-off", "🔴 off"),
}

WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


class MaturityMappingError(ValueError):
    """A maturity value the HTML page has no vocabulary for.

    Raised, not collected: a missing mapping must not be recoverable into a row
    that renders blank, because a blank maturity cell reads as "fine".
    """


def html_maturity(maturity: str) -> str:
    try:
        return HTML_MATURITY_KEY[maturity]
    except KeyError:
        raise MaturityMappingError(
            f"maturity {maturity!r} has no mapping in HTML_MATURITY_KEY — "
            f"docs/design-suite-guide.html cannot render it, and a row with an "
            f"unrenderable maturity must never be dropped silently") from None


def word(n: int) -> str:
    return WORDS[n] if 0 <= n < len(WORDS) else str(n)


def esc(text: str) -> str:
    """HTML-escape. `one_liner` escapes pipes for markdown; undo that here."""
    text = text.replace("\\|", "|")
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def js(text: str) -> str:
    """A JS string literal that cannot terminate the surrounding <script>."""
    return json.dumps(text.replace("\\|", "|"), ensure_ascii=False).replace("</", "<\\/")


def roles_count() -> tuple[int, list[str]]:
    try:
        spec = json.loads(ROLES_JSON.read_text())
    except (OSError, ValueError) as exc:
        return 0, [f"roles.json unreadable ({exc}) — the doc-role count in the guide "
                   f"cannot be derived, and a wrong role count is exactly the kind of "
                   f"hand-written number this generator exists to abolish"]
    roles = spec.get("roles") or {}
    if not roles:
        return 0, ["roles.json declares no roles — refusing to print '0 roles' in the guide"]
    return len(roles), []


MARKER = r"<!--gen:{k}-->(?:.*?)<!--gen:/{k}-->"
MARKER_JS = r"/\*gen:{k}\*/(?:.*?)/\*gen:/{k}\*/"


def substitute(template: str, regions: dict[str, str]) -> tuple[str, list[str]]:
    """Replace every marked region. Unknown or unused markers are problems.

    A marker the generator does not fill would leave a hand-written number
    wearing a generated costume; a region the generator fills that the page does
    not contain means a fact silently stopped being published. Both refuse.
    """
    problems: list[str] = []
    out = template
    for key, value in regions.items():
        hits = 0
        for pattern, wrap in ((MARKER, "<!--gen:{k}-->{v}<!--gen:/{k}-->"),
                              (MARKER_JS, "/*gen:{k}*/{v}/*gen:/{k}*/")):
            rx = re.compile(pattern.format(k=re.escape(key)), re.DOTALL)
            out, n = rx.subn(lambda _m, k=key, v=value, w=wrap: w.format(k=k, v=v), out)
            hits += n
        if not hits:
            problems.append(
                f"docs/design-suite-guide.html has no <!--gen:{key}--> region — the "
                f"generator computes that value but the page does not use it, so the "
                f"page is publishing something else")
    present = set(re.findall(r"<!--gen:([a-z0-9-]+)-->", out))
    present |= set(re.findall(r"/\*gen:([a-z0-9-]+)\*/", out))
    unfilled = sorted(present - set(regions))
    if unfilled:
        problems.append(
            "docs/design-suite-guide.html marks regions the generator does not fill: "
            + ", ".join(unfilled) + " — a marked region that nothing fills is a "
            "hand-written value that looks generated")
    return out, problems


def html_regions(data: dict) -> tuple[dict[str, str], list[str]]:
    problems: list[str] = []
    skills = skill_rows(data)
    agents = agent_rows(data)
    audit_rows, p = audits(); problems += p
    hook_rows, p = hooks(); problems += p
    n_roles, p = roles_count(); problems += p
    gi = group_index()

    auto = [s for s in skills if s["invocation"] == "auto"]
    explicit = [s for s in skills if s["invocation"] == "explicit"]
    auto_agents = [a for a in agents if a["invocation"] == "auto"]
    off = [a for a in audit_rows if a["state"] != "live"]

    rows = []
    for s in auto + explicit:
        rows.append("[{},{},{},{},{}],".format(
            js("/" + s["name"]), js(one_liner(s["description"])), js(s["invocation"]),
            js(html_maturity(s["maturity"])), js(s["plugin"])))
    rows[-1] = rows[-1].rstrip(",")
    data_array = "\n" + "\n".join(rows) + "\n"

    agent_html = []
    for a in agents:
        cls, label = HTML_MATURITY_TAG[html_maturity(a["maturity"])]
        agent_html.append(
            f'        <tr><td class="cmd"><code>{esc(a["name"])}</code></td>'
            f'<td class="what">{esc(one_liner(a["description"]))}</td>'
            f'<td><span class="tag t-plain">{a["invocation"]}</span></td>'
            f'<td><span class="tag {cls}">{label}</span></td></tr>')

    hook_html = []
    for h in hook_rows:
        hook_html.append(
            f'        <tr><td class="cmd"><code>{esc(h["script"])}</code></td>'
            f'<td>{esc(h["plugin"])}</td>'
            f'<td>{esc(h["event"])} on <code>{esc(h["matcher"].replace("|", " | "))}</code></td>'
            f'<td class="what">{esc(h["message"])}</td></tr>')

    buckets: dict[str, list[str]] = {b: [] for b in BUCKETS}
    for s in skills:
        buckets[bucket_of(s["name"], gi)].append(s["name"])
    cheat = []
    for b in BUCKETS:
        if not buckets[b]:
            continue
        names = " · ".join(f"/{n}" for n in sorted(buckets[b]))
        cheat.append(f"    <div><h3>{esc(b)} · {len(buckets[b])}</h3>"
                     f"<p>{esc(names)}</p></div>")
    placed = sum(len(v) for v in buckets.values())
    if placed != len(skills):
        problems.append(f"guide cheat sheet placed {placed} of {len(skills)} commands")

    regions = {
        "n-commands": str(len(skills)),
        "n-auto": str(len(auto)),
        "n-audits": str(len(audit_rows)),
        "n-agents": str(len(agents)),
        "w-agents": word(len(agents)),
        "n-auto-agents": str(len(auto_agents)),
        "n-hooks": str(len(hook_rows)),
        "w-hooks": word(len(hook_rows)).capitalize(),
        "w-off-audits": word(len(off)),
        "n-roles": str(n_roles),
        "agent-rows": "\n" + "\n".join(agent_html) + "\n      ",
        "hook-rows": "\n" + "\n".join(hook_html) + "\n      ",
        "cheat-rows": "\n" + "\n".join(cheat) + "\n  ",
        "data": data_array,
    }
    return regions, problems


def render_html(data: dict, template: str) -> tuple[str, list[str]]:
    regions, problems = html_regions(data)
    out, p = substitute(template, regions); problems += p

    # The page ships its own copy of the maturity vocabulary, in JS. Check it
    # agrees rather than assuming it does.
    for key, (cls, _label) in HTML_MATURITY_TAG.items():
        if not re.search(rf"\b{key}:\['{cls}'", out):
            problems.append(f"the guide's JS `M` map has no {key} → {cls} entry, so rows "
                            f"with that maturity would render blank")

    # The disabled-audit table is authored prose (measured failure rates are not
    # in any frontmatter). Authored, therefore checked: an audit that gets
    # switched off and is not named here would go unmentioned on the page.
    audit_rows, _ = audits()
    for a in audit_rows:
        if a["state"] != "live" and f"/{a['slug']}</code>" not in out:
            problems.append(
                f"audit {a['name']} is switched off but docs/design-suite-guide.html "
                f"never names it — a disabled audit that no surface mentions reads as "
                f"one that ran and found nothing")
    return out, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed output is stale")
    ap.add_argument("--html", action="store_true",
                    help="write docs/design-suite-guide.html instead of docs/SKILLS.md")
    args = ap.parse_args(argv)

    data, problems = catalog.collect()
    out_path = OUT_HTML if args.html else OUT

    if args.html:
        if not out_path.is_file():
            print(f"skills_catalog: {out_path.relative_to(REPO)} is missing — it is its "
                  f"own template (authored HTML with marked regions) and cannot be "
                  f"regenerated from nothing; restore it from git", file=sys.stderr)
            return 1
        rendered, render_problems = render_html(data, out_path.read_text())
    else:
        rendered, render_problems = render(data)
    problems += render_problems

    if problems:
        print("skills_catalog: problems\n", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        return 1

    flag = " --html" if args.html else ""
    if args.check:
        if not out_path.is_file():
            print(f"skills_catalog: {out_path.relative_to(REPO)} does not exist — run "
                  f"`python3 plugins/design-suite/bin/skills_catalog.py{flag}`",
                  file=sys.stderr)
            return 1
        if out_path.read_text() != rendered:
            print(f"skills_catalog: {out_path.relative_to(REPO)} is stale — run "
                  f"`python3 plugins/design-suite/bin/skills_catalog.py{flag}` and commit "
                  f"the result", file=sys.stderr)
            return 1
        print("skills_catalog: up to date.")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered)
    print(f"skills_catalog: wrote {out_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
