---
name: audit-contrast
description: "Use when asked whether colour contrast is compliant, or before shipping a palette change. Scores declared foreground/background pairs against WCAG ratios from the project's token source; refuses (exit 2) rather than passing when it cannot resolve them. Read-only: reports findings, never edits."
invocation: auto
maturity: unverified
---

# /audit-contrast

Run it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_contrast.py"
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_contrast.py" --json
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_contrast.py" --findings
```

It reads the pair list from this project's `.design-suite/contrast-pairs.json`,
resolves each pair's two tokens through the adapter against the palette declared
in the profile's `tokens.source`, and scores the WCAG 2.1 contrast ratio.

## What it reports

One record per declared pair — **passing ones included**. This audit reports
*checks*, not violations, so its findings envelope carries
`reports: "checks"`: zero records means it never ran, not that the palette is
perfect. That polarity was reserved in `design_suite/engine/findings.py` for this
audit before the audit existed.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every declared pair meets its threshold |
| `1` | at least one pair is below its threshold |
| `2` | **refused** — see below |

It exits `2`, never `0`, when:

* there is no `.design-suite/contrast-pairs.json`, or it is unreadable, or it
  declares no pairs
* the adapter for this stack cannot read declared token values
* the token source could not be resolved (an uninstalled package, a moved file)
* a pair names a token the palette does not declare
* a declared colour value cannot be parsed, or is translucent

Every one of those is a place where a smaller, plausible-looking pass rate was
available and declined. A run that scored 24 of a declared 26 pairs and printed
"all passing" is indistinguishable from a clean palette.

## Declaring the pairs

```json
{
  "schemaVersion": 1,
  "pairs": [
    {
      "name": "body text on surface",
      "foreground": "colorTextPrimary",
      "background": "colorSurface",
      "minRatio": 4.5,
      "surface": "all screens"
    }
  ]
}
```

`minRatio` defaults to 4.5 (WCAG AA body text). Set 3.0 for large text and for
non-text UI boundaries, 7.0 for AAA. There is deliberately **no shipped default
pair list**: a default would score every project against combinations it never
declared and report a pass rate for assertions nobody agreed to.

Translucent tokens are refused rather than scored. A translucent colour has one
ratio per surface behind it; declare the composited opaque token you actually
paint.

## Why this runs here now

It used to not. This command shipped as `maturity: pointer`, and its entire body
said colour contrast is audited in the design-system repository, beside the
palette it scores. That reasoning does not survive being separated into its two
halves:

* the **pair list** is project data and stays with the project — this reads it
  from the consumer's own repo, never from a constant here
* the **scoring** is WCAG arithmetic, identical for a Flutter palette, a Tailwind
  theme or a CSS custom-property file, and there was never a reason it had to sit
  beside any one palette

And the pointer had stopped resolving for the audience that matters: the
repository it named is private, so for every team this suite is being prepared to
ship to, a listed command pointed at nothing they could open.

**Prior art, still valid where you can reach it.** The design system runs its own
matrix across every brand and mode:

```bash
python3 tooling/scripts/audit_contrast.py --matrix
```

in the org's design-system repo (`<design-system-repo>` — not shipped with this plugin),
scoring 26 curated pairs against 78 brand/mode cells. That is a *fleet* question
— is every brand we ship compliant — and this plugin has no standing to answer
it. This answers the per-project one, which nothing answered before.

## Maturity

`unverified`, not `proven`. The arithmetic is tested against values fixed by WCAG
(`bin/audit_contrast_test.py`) and every refusal path is tested beside the
positive case it must not swallow. What it has *not* had is a run against a real
consumer project's palette, resolving a real `tokens.source`, with a human
confirming the reported failures are failures. That is the bar for `proven`.
