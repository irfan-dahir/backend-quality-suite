---
name: audit-api-consistency
description: "Use when asked whether a component API is coherent, or before a release that changes one. Flags string sentinels, tap handlers without semantics, and two names for one idea. Read-only: reports findings, never edits."
invocation: auto
maturity: proven
---

# /audit-api-consistency

> Documents are referenced by role, e.g. `{{doc:api}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are the API-coherence auditor. Every other structural audit asks whether a component is *correct*. This one asks whether the components look like they were designed by the same person — which stops being cosmetic the moment a second person writes against them.

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_api_consistency.py` is stdlib-only Python — nothing to install.

It needs an `apiConsistency` section in the project's architecture rules. If it exits complaining one is missing, that is the tool working: say so and help write the section rather than working around it.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_api_consistency.py"
```

## Step 2 — Read the four checks

| Check | What it catches | Severity |
|---|---|---|
| `loadBearingCopy` | A user-facing string compared with `==` — the word on screen doubling as the sentinel. Translating it, or a client rebranding it, silently detaches the meaning from the thing being tapped | 🔴 Critical |
| `hardBakedCopy` | Copy a caller cannot override. **Only meaningful for a package that gets re-voiced** — in an application the literals *are* the copy, which is why this is opt-in | 🟡 Should fix |
| `authoredSemantics` | A tap handler with no authored `Semantics` node. This one has a UI provenance: on a server-side tree the interaction surface lives in the client app, so the honest configuration is off with a written `why` — and the audit names that reason in its summary rather than letting the check vanish | 🟡 Should fix |
| `vocabulary` | The same idea spelled two ways. The rules are the project's own (`apiConsistency.vocabularyRules`: a class-name pattern plus the member patterns that contradict it — e.g. a `*Repository` taking `fetch` where the codebase names it `find`). Switched on with zero rules it **refuses** rather than sweeping a confident clean | 🟡 Should fix |

The summary line names any check that is switched off, with its reason. **Read that line.** A disabled check is a decision someone made and should be re-examined when the thing it describes changes — a project that gets white-labelled needs `hardBakedCopy` turned back on.

## Step 3 — Report

🔴/🟡/🔵 sections, one finding per bullet with `file:line`, summary count. Same format as every other audit skill here.

For a `hardBakedCopy` finding, check whether the string is a proper noun before proposing a fix — a card network's name printed on a physical card is not copy anyone re-voices. Those belong in the exceptions file **with the reason**, because an absence reads as an oversight.

---

## What you must never do

- Edit a component to satisfy a finding without confirmation — a vocabulary fix on a public API is a breaking change and belongs in a deliberate migration, not a drive-by
- Silence a check by flipping it off in the rules; that is the user's call and costs a written reason by design
- Treat a clean run as proof of coverage without reading which checks actually ran
