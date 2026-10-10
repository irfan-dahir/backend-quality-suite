---
name: audit-reduced-motion
description: "Use when asked to check reduced-motion support or accessibility of animations. Finds animated nodes (per the design-audit config) that never check a reduced-motion signal. Never changes your code; saves its report to .design-suite/reduced-motion-findings.json on every run."
invocation: auto
maturity: unverified
---

# /audit-reduced-motion

> **What it writes.** This audit never edits source, but every plain run
> (no flag needed) saves its raw report to `.design-suite/reduced-motion-findings.json` (override with `--out`),
> and `--findings` additionally writes the envelope under `.design-suite/findings/`.
> Those files are what `/design-debt` and the MCP server read, so they are
> written deliberately. Keep them out of git — they quote your source.

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

You are the reduced-motion wiring auditor. Motion tokens and curves are `/audit-tokens`'s job; this skill checks a narrower, separate thing — whether an animated node actually **honors** a reduced-motion signal (Flutter's `MediaQuery.of(context).disableAnimations` / `MediaQuery.disableAnimationsOf(context)`), not whether its duration/curve is tokenised.

**You report; you do not edit code without confirmation.** See `{{doc:motion}}` (if established via `/establish-interaction-spec`) for this project's motion conventions.

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/audit_reduced_motion.py` is stdlib-only Python — nothing to install.

This audit is config-driven for the one thing that cannot be inferred from code alone: **which widget/class names count as "animated"** at all. That list lives in the project's design-audit config file (named by `audits.configFile` in `.design-suite/profile.json`), under `token_categories.motion.animated_widgets`. If that key is missing or empty, the script refuses to run rather than silently reporting zero findings — per this repo's governing principle, "an audit that reports nothing must never be indistinguishable from a clean codebase." If you see that refusal, the fix is to add the project's real animated-widget names to that config key (e.g. `"AnimationController"`, `"AnimatedSwitcher"`, `"AnimatedOpacity"`, `"SlideTransition"`), not to make this skill guess.

## Step 1 — Gather state

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_reduced_motion.py"
```

For every match of a configured animated-widget name, the script looks in a window of nearby source (same lookback/lookahead shape as `/audit-tokens`'s entrance-curve check) for a reduced-motion signal. No signal nearby is reported as a `reduced_motion_unwired` finding.

`.design-suite/reduced-motion-findings.json` is the raw output; regenerate fresh rather than trusting a stale copy.

## Step 2 — Read each finding in context

A nearby match is a heuristic, not proof — read the surrounding widget to confirm:
- The animation genuinely runs unconditionally (a false positive: the reduced-motion check is wired several methods away, e.g. hoisted into a shared base class or mixin the regex window cannot see).
- Whether the right fix is gating the animation itself (skip straight to end state) or just shortening its duration — both count as "honoring" the signal, and the finding does not distinguish them.

## Step 3 — Report

Same format as every other audit skill in this repo (`/audit-tokens`, `/audit-accessibility`): 🔴/🟡/🔵 sections, one finding per bullet with `file:line`, summary count.
- 🟡 Should fix: any animated node with no reduced-motion check nearby — this is an accessibility gap (vestibular-disorder users rely on the OS-level "reduce motion" setting actually working), not a style nitpick.
- 🔵 FYI: a finding that turns out to be a false positive from Step 2 (check wired outside the lookback window) — note it so a human can decide whether to widen the window or accept the exception, rather than silently dropping it.

If nothing is animated in the project at all, that is a real "clean" result and should be reported as such — distinct from the config-missing refusal in Step 0, which must never be reported as clean.
