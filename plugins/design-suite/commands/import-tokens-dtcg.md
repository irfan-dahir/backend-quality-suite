---
name: import-tokens-dtcg
description: "Report drift between a W3C DTCG (2025.10) token file — a Figma variables, Tokens Studio or Style Dictionary export — and the tokens this project's code declares: missing in code, missing in the file, value mismatches, and tokens that cannot be compared. Read-only by default; writes one JSON report only with --write-report. Use when asked whether the code's tokens still match Figma or a DTCG/tokens.json file."
invocation: auto
maturity: unverified
---

# /import-tokens-dtcg

Reads a DTCG file and compares it with the code's declared tokens.

**Format:** [Design Tokens Format Module 2025.10](https://www.designtokens.org/tr/2025.10/format/)
— Final Community Group Report (stable; not a W3C Recommendation).

`invocation: auto` because the default run is report-only. `maturity:
unverified` — synthetic token sets only so far.

## Run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/import_tokens_dtcg.py"                       # file from tokens.dtcg.path
python3 "${CLAUDE_PLUGIN_ROOT}/bin/import_tokens_dtcg.py" --file design.tokens.json --json
python3 "${CLAUDE_PLUGIN_ROOT}/bin/import_tokens_dtcg.py" --accept-draft-forms  # legacy Tokens Studio / pre-2025.10 files
python3 "${CLAUDE_PLUGIN_ROOT}/bin/import_tokens_dtcg.py" --write-report        # the only write
```

The default file comes from the profile:

```json
"tokens": { "source": { ... }, "accessor": "...", "dtcg": { "path": "design/figma.tokens.json" } }
```

## What it writes

Nothing by default. `--write-report [PATH]` writes one JSON report, default
`.design-suite/dtcg-drift.json`. It never writes to source code or to the DTCG
file.

## What it reports

| Kind | Meaning |
|---|---|
| `missing_in_code` | in the file, no matching token in code |
| `missing_in_file` | declared in code, not in the file |
| `value_mismatch` | both, different resolved value or type |
| `uncomparable` | a code token with no faithful DTCG form — **not** counted as matching |
| `ambiguous` | two names on one side share a comparison key |

Names match on a stack-neutral key (lower-case alphanumerics, `$root` dropped),
so `color.primary`, `--color-primary` and `colorPrimary` are one token. Aliases
are resolved on both sides before comparing. `0.15s` equals `150ms`; `1rem`
never equals `16px` (no root font size is assumed).

## Refusals — exit 2, named

Not JSON; not an object; a cycle or dangling alias; an alias to a group
(`{color.accent}` instead of `{color.accent.$root}`); a token missing `$type`
after inheritance; an unknown `$type`; a value of the wrong shape; a reserved
character in a name; JSON Pointer `$ref` or `$extends` (in 2025.10, not
implemented here — refused rather than ignored); a draft-era value without
`--accept-draft-forms`; no file configured; a code token source it cannot read.

Typography, border, transition, strokeStyle and gradient are accepted but
compared as opaque JSON, not interpreted.

## Not done: DTCG as audit_tokens' token source

This does **not** make `/audit-tokens` read the DTCG file as the project's
token source. That audit's token list is keyed by code names, and mapping DTCG
paths back to code names is the lossy step this drift check reports on rather
than assumes. Use the drift report to bring code and file into agreement.

## Exit codes

`0` no drift · `1` drift or uncomparable tokens listed · `2` refused.
