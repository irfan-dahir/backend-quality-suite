---
name: audit-unwired-roles
description: "Use when asked whether the theming contract is real, or which design-system colour roles a project never uses. Finds semantic colour roles defined but read by nothing. Read-only: reports findings, never edits."
invocation: auto
maturity: proven
---

# /audit-unwired-roles

> Documents are referenced by role, e.g. `{{doc:design}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" design`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You audit the *other* direction from `/audit-tokens`. That one catches a literal where a role belongs; this one catches a role nothing ever asks for. Both end the same way — someone changes a brand value and nothing on screen moves.

**You report; you do not edit code without confirmation.**

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_unwired_roles.py` is stdlib-only Python.

It resolves the role list through the package manager's own map. **If dependencies are not installed it refuses to run rather than reporting clean** — every role would otherwise look wired and the audit would pass by being blind. Install dependencies and re-run; do not work around the refusal.

## Step 1 — Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_unwired_roles.py"
```

When the roles come from a design-system **package**, that package's own source is swept too, and the summary gains two lines: `read here` and `read upstream`. A role only the package's theme factory or a component reads is **wired** — the app gets it by using the component, and a brand changing it still moves the app. Scanning the app alone named eight of nineteen roles unread on a real consumer and every one of them was wired, which is why the upstream sweep is not optional: if the package is configured and its source cannot be found, the script refuses rather than sweeping less.

## Step 2 — Read the two lists differently

**`UNWIRED`** — roles the project *claims* (listed in `unwiredRoles.requiredRoles`) and reads nowhere. These fail. Either read the role somewhere, drop the claim, or exempt it with a reason.

**`unread here`** — roles the design system offers that this project has never needed. These never fail, and in a consuming app they are usually information rather than a defect: they say which parts of the system this product does not use. Report them; do not propose wiring a role in just to clear the line.

The difference between the two lists is entirely `requiredRoles`. A project with an empty one is saying "report, do not fail" — which is a reasonable starting position and a bad permanent one. If you see an empty list with a note saying it should be filled in once someone has read the report, and you are reading the report, that is the moment.

## Step 3 — Report

🔴/🟡/🔵 sections. Put failing roles under 🔴 and unread-here roles under 🔵 with a one-line note on what each is for, so the reader can decide which ones the product should be using.

---

## What you must never do

- Wire a role into a component purely to clear a finding — that is a fake consumer and the audit will pass while meaning nothing
- Add an exemption without a reason. An exemption is a debt, not a verdict, and one whose justification has quietly expired is indistinguishable from a role nobody noticed
- Report a refusal-to-run as a clean result
