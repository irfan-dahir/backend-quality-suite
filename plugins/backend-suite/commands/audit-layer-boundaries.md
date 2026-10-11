---
name: audit-layer-boundaries
description: "Mechanically check that no shared layer imports the feature code that consumes it — the layering inversion that blocks extracting that layer into a package. Rules and directories come from this project's arch-rules.json. Ratcheted against a committed baseline: new violations fail, known ones are listed. Never changes your code; saves its report to .backend-suite/layer-boundaries-findings.json on every run. Use when asked whether the layering still holds, or before an extraction."
invocation: auto
maturity: unverified
---

# /audit-layer-boundaries

> **What it writes.** This audit never edits source, but every plain run
> (no flag needed) saves its raw report to `.backend-suite/layer-boundaries-findings.json` (override with `--out`),
> and `--findings` additionally writes the envelope under `.backend-suite/findings/`.
> Those files are what `/quality-debt` and the MCP server read, so they are
> written deliberately. Keep them out of git — they quote your source.

> Documents are referenced by role, e.g. `{{doc:api-standard}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api-standard`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are the layer-boundary auditor. A package cannot import its consumer. When a
"shared" layer reaches into one feature's private classes or domain entities,
two things are true at once: that layer can no longer be extracted into a
standalone package, and the word "shared" has quietly stopped being accurate.

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_layer_boundaries.py` is stdlib-only Python —
nothing to install.

Every rule it enforces comes from this project's architecture rules
(`audits.archRulesFile` in the profile), section `layerBoundaries`. The script
names no project's directory layout.

| Key | Meaning |
|---|---|
| `rules[].from` | Directory the rule applies to |
| `rules[].fromGlob` | Alternative to `from` (the spelling `init.py` scaffolds): a glob, relative to the repo root, selecting the files the rule applies to. If both are set, `from` wins |
| `rules[].mustNotImport` | Import root(s) that layer may not import — a single string or a list. On a PHP project a root may be a namespace prefix (`App\Http\`, matched by prefix against raw `use` targets) or a repo-rooted path (matched against `require`d files); both forms can appear in one rule |
| `rules[].why` | Optional rationale shown in each violation message |
| `baseline` | Path to the ratchet baseline (default `.backend-suite/baselines/layer-boundaries.json`) |

Every rule in `rules` is enforced — an earlier version read `rules[0]` only,
which made a second rule configuration that did nothing while the run printed
clean.

**Known limit:** a fully-qualified reference written inline in PHP
(`new \App\Http\Thing()`) is not treated as an import — the `use` statement is
the convention there; a violation spelled only through an inline FQN is missed,
so do not read a clean run on such a codebase as proof.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_layer_boundaries.py"
```

Every spelling the adapter declares is caught — the absolute package/module
form and the relative form on Dart/JS stacks, `use` namespaces and `require`d
paths on PHP — because real repositories mix them and catching only one would
make the gate's green mean less than it appears to.

## Step 2 — Understand the ratchet before you read the count

Known violations live in a committed baseline. The audit **fails only on
violations that are not in it**. So:

- A passing run does **not** mean zero violations. It means zero *new* ones.
  Report the baselined count alongside the new count, every time — a report
  that prints only "0 new" lets a long-standing inversion read as a clean
  layer.
- A baselined violation that no longer exists is worth a 🔵: the baseline is
  now over-claiming, and shrinking it is the point of a ratchet.

`--update-baseline` rewrites that file. It is the one destructive-ish thing
here, it is never what a plain audit run does, and it must not be run without
explicit confirmation — accepting a violation into the baseline is a decision
about what this project tolerates, not a cleanup step.

Exit **2** means the audit refused. It refuses when:

- there is no `layerBoundaries` section, or `rules` is empty;
- `rules[0]` still holds `init.py`'s `TODO` placeholders;
- the rule names neither `from` nor `fromGlob`, or `mustNotImport` is empty;
- no language adapter matches this project, the adapter cannot read imports, or
  the package's import prefix cannot be determined;
- the `from` directory does not exist, or **zero files** are in scope.

Refused is not clean.

## Step 3 — Report

🔴/🟡/🔵 sections, one finding per bullet with `file:line` and the importing
rule's `why`, plus two counts: new violations and baselined ones.

- 🔴 Critical: a new violation — it was not there when the baseline was taken.
- 🟡 Should fix: a baselined violation, named so it stays visible.
- 🔵 FYI: a baseline entry matching nothing any more.

---

## What you must never do

- Run `--update-baseline` without explicit confirmation, or as a way of making
  a red run go green
- Report "passed" without the baselined count beside it
- Report exit 2 (refused) as a clean run
- Rewrite an import to a relative path to dodge the check — the absolute and
  relative forms are both caught precisely so that is not a fix
