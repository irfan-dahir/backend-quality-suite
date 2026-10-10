---
name: repair-tokens
description: "Use when asked to fix, repair, or auto-tokenise the findings /audit-tokens reported. Emits a reviewable unified diff swapping hardcoded values for exactly-equal tokens. Never modifies source, stages, or commits; writes only the report paths you name (--out, --bands-json, --suggestions-json)."
invocation: explicit
maturity: unverified
---

# /repair-tokens

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

The first fix path in a suite of 18 report-only audits (RFC-0003 §2a). It takes
the findings `/audit-tokens` produces and answers a narrower question about each:
**is there exactly one declared token that is exactly this value?**

**You generate a diff. You do not apply it.** Nothing here writes to source,
stages, or commits — RFC-0003 §3c. Show the patch, let the human decide, and let
them run `git apply` themselves.

`invocation: explicit` because this is content-generating: the tier table in
`CLAUDE.md` puts read-only and report-only on `auto` and everything that produces
content on `explicit`, decided by blast radius rather than difficulty.

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens.py` is stdlib-only Python — nothing to
install. It needs the project to have declared, in its own config:

- `tokens.accessor` and a `tokens.source` that **resolves** (for a package
  source, that means dependencies are installed)
- `unusedTokens.categories` in the architecture rules — which name prefixes mean
  spacing, radius, colour, duration, curve

If any of that is missing it exits **2 and refuses**. Do not work around the
refusal. See "Why it refuses" below; that refusal is the most carefully
considered behaviour in this component.

## Step 1 — Generate

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens.py" --report     # bands only
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens.py"              # diff to stdout
```

The band summary goes to stderr, the diff to stdout, so the two never mix.

## Step 2 — Read the three bands back to the user, all three

| Band | Meaning | What the tool did |
|---|---|---|
| **1 — deterministic** | The literal exactly equals **exactly one** declared token of the right category | Rewrote it, in the diff |
| **2 — ambiguous** | Several tokens share that value, or the value is close to one but not equal | Listed the candidates. Nothing rewritten |
| **3 — absent** | No declared token has this value | Nothing. Reported it |

Two more outcomes are reported separately and are **not** bands:

- **unsupported** — the finding flags a token used in the wrong place, not a
  literal (an `entrance_curve`). There is nothing to substitute.
- **undeterminable** — the project declares no naming prefix for that category,
  so the lookup never happened.

Report band 3 as *"no token has this value — someone has to decide whether one
should exist"*, never as *"here is a token you could add"*. **Creating a token
is a convention decision and is reserved permanently for humans** (RFC-0003
§3b). A tool that invents `colorNeutral450` because it found an unmatched grey
has started authoring the design system.

Band 2 is a question for the user, not a recommendation. Two tokens with the
same value usually mean the two *roles* differ — picking one by coin flip
records a meaning the code never had.

## Step 3 — Hand the diff over

Show it. Offer to save it (`--out <path>`), and say plainly that applying it is
theirs to do.

`--out`, `--bands-json` and `--suggestions-json` are the only paths this script
writes, and a relative one resolves against the repo root, not your shell's cwd —
so name them deliberately, and keep them out of source directories. No source
file is touched, and no `git` command is ever run:

```bash
git apply <path>
```

If they ask you to apply it, that is a separate, explicit instruction — and
before claiming the rewrite changed nothing on screen, capture the oracle:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/golden_local_ab.py" snapshot   # before
# apply the patch, then:
python3 "${CLAUDE_PLUGIN_ROOT}/bin/golden_local_ab.py" check      # after
```

A mechanical substitution of a literal for a token of the same value *should* be
pixel-identical, which is exactly the claim `/golden-local-ab` exists to test
rather than assume.

## Why it refuses (RFC-0003 §2c)

`dart.checks()` falls back to `ctx.token_accessor or "AppTokens"`. A token audit
run against a project with no declared token source therefore **appears to
work** — it reports raw literals as though it knew a token existed for each of
them. It does not.

Band 1 means "exactly one declared token matches". With no declared, resolving
token source there is nothing to match against, so the honest output is a
refusal and not a guess. A repairer that guesses here does not produce a weaker
fix; it produces a wrong one, in source, under a heading claiming it was
deterministic.

## Pre-commit / CI

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens.py" --check
```

Writes nothing and exits 1 when a band-1 repair is available — same shape as
`sync_mock_api.py --check`. This is the delivery point RFC-0003 §3a argues for:
a finding that arrives on the change that caused it, while the fix is still
cheap.

## Maturity

`unverified`: the band logic is covered by `bin/repair_tokens_test.py` against a
fixture whose token values are controlled, and the emitted diff is asserted to
apply cleanly with `git apply`. No generated diff has yet been applied to a real
project and re-rendered through the golden corpus, which is what `proven` would
require.
