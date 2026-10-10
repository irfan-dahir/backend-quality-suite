---
name: establish-interaction-spec
description: "Establish or update motion and haptic/sound conventions — the source of truth the token audit measures durations and curves against. High blast radius: sets new project-wide conventions, so let the user decide rather than invoking autonomously."
invocation: explicit
maturity: unverified
---

# /establish-interaction-spec

> Documents are referenced by role, e.g. `{{doc:motion}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" motion`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You establish (or update) the project's motion and non-visual feedback (haptics/sound) conventions — the source of truth `/audit-tokens`'s `duration`/`curve` checks are measured against. You produce `{{doc:motion}}`. **You never rewrite existing app code in this skill** — findings and proposed conventions get confirmed first, applied later (by hand or a future dedicated skill).

Mirrors `/establish-brand-voice`'s reverse-engineer-then-confirm shape, applied to motion instead of copy.

---

## Step 0 — Preconditions

1. Confirm you are on a feature branch (never `demo`/`main`) — this skill commits a new doc.
2. Check whether `{{doc:motion}}` already exists. If it does, this is an **update** — show the existing content and ask what's changing before touching anything.

## Step 1 — Gather evidence: motion

Read the motion block of the project's token source (`<tokens.source.path>` in the profile) — today that's `durationFast` (150ms), `durationMedium` (250ms), `durationSlow` (350ms), `curveStandard` (`Curves.easeInOut`), `curveEmphasized` (`Curves.easeOutBack`), `durationAssetEntrance` (420ms).

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_tokens.py"
```

Check the `duration`/`curve` findings in `.design-suite/tokens-findings.json` — these are real call sites not currently routed through the tokens above. Read each in context (not just the literal) to understand what motion it's actually producing, so the eventual spec describes real usage, not a guess. `card_preview.dart`'s CVV flip (`Duration(milliseconds: 400)` + `Curves.easeInOut`) is a known one, found during `/audit-tokens`'s own development — treat it as a first confirmed finding, not something to rediscover from scratch.

Also read `{{doc:design}}`'s `AppAsset` motion section (Tier A/Tier B split, the `popIn` preset) — this is the one place motion is already documented as a system, and the new spec should extend it rather than duplicate or contradict it.

## Step 2 — Gather evidence: haptics/sound

There is currently **zero** usage of `HapticFeedback.*`, `SystemSound.*`, or any audio package anywhere in `lib/` — confirmed by grep. This is genuinely greenfield, not reverse-engineering. **Do not invent conventions and present them as already-decided** — ask the user directly:

- Is haptic feedback in scope for this app at all? (Common candidates for a health app with an older-skewing audience: a light tap confirmation on primary actions, a firmer buzz on destructive/emergency confirmations — but don't assume, ask.)
- Is sound feedback in scope, or explicitly out (many users may have devices muted/expect a calm, non-intrusive app)?

If the user wants either, propose specific trigger points (e.g. "medium haptic on the emergency-value confirm sheet, matching the Urgent/Direct copy register from `{{doc:brand-voice}}` if it exists on this branch") and get explicit confirmation before writing them into the spec — same discipline as the copy skills' per-attribute sign-off.

## Step 3 — Draft `{{doc:motion}}`, attribute by attribute

```markdown
# Motion & Feedback — <Project Name>

## Motion tokens (from AppTokens)
[Table: token name, value, when to use it — pulled from app_theme.dart's real values]

## Motion grammar
[When to use durationFast vs Medium vs Slow; when curveStandard vs curveEmphasized;
how this relates to the AppAsset Tier A/Tier B split already in {{doc:design}}]

## Known violations (from /audit-tokens)
[List real duration/curve findings not yet routed through tokens — e.g. the
card_preview.dart CVV flip — as a starting cleanup list, not fixed here]

## Haptic feedback
[Either "Not in scope for this app" if the user declines, or specific
trigger points + intensity, confirmed with the user]

## Sound feedback
[Same — "Not in scope" or specific, confirmed trigger points]
```

Present each section for confirmation before finalizing — don't write the file until the user has signed off on all of it, same as `/establish-brand-voice`.

## Step 4 — Write, register, and commit

1. Write the confirmed content to `{{doc:motion}}`.
2. Check `{{doc:instructions}}`'s companion-document table and task-router table — add rows if `{{doc:motion}}` isn't listed.
3. Add a dated entry to `{{doc:decisions}}` under "Designer Workflow Automation" (or a new "Motion & Interaction" section if that fits better) recording what was established and why.
4. Commit per `{{doc:pr}}` conventions.

---

## What you must never do

- Invent haptic/sound conventions and write them into the spec without explicit user confirmation — this is genuinely greenfield, not something to reverse-engineer or assume
- Rewrite `card_preview.dart` (or any other flagged file) to fix the violation as part of this skill — that's a separate, deliberate follow-up
- Accept any spec section into the final doc without the user's explicit sign-off
- Contradict or duplicate `{{doc:design}}`'s existing `AppAsset` motion documentation — extend it
