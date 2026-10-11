# Measurement — `web` adapter precision on public OSS, 2026-10-08

Issue #104 tracks per-audit false-positive rates. The `web` adapter
(`plugins/backend-suite/backend_suite/adapters/web.py`) shipped `unverified`, with
only planted fixtures behind it. This measures it on real code, tunes it, and
measures again.

**Bottom line.** Pooled over all five projects, wrong findings went from 31.0%
to 2.8%. The worst single project is still 8.3% wrong. The corpus that measured
the result is the same one the filters were tuned on. The adapter **stays
`unverified`**. It is not `proven`, because the next step is a re-measurement on
a held-out corpus.

---

## 1. Corpus

These are public open-source projects only, shallow-cloned into a `mktemp -d` under `/tmp`.
No client code was used.

| Project | Stack under test | URL | Commit | Scan dir |
|---|---|---|---|---|
| docusaurus | React + CSS Modules | https://github.com/facebook/docusaurus | `021ee05058b2df769306dd717246bd5967f4845a` | `packages/docusaurus-theme-classic/src` |
| excalidraw | React + SCSS | https://github.com/excalidraw/excalidraw | `4c00f31ddcc20086bac1020428819fe0b9a30bce` | `packages` |
| realworld | SvelteKit (Svelte SFC) | https://github.com/sveltejs/realworld | `df796708040f5200ec572b28ab7f88ecee5794dd` | `src` |
| taxonomy | Next.js + Tailwind | https://github.com/shadcn-ui/taxonomy | `298a8857c7128a0d121e7f699dfd729f23b3966d` | `.` |
| vitepress | Vue SFC + CSS | https://github.com/vuejs/vitepress | `8cc9e3432f8b96cab19f58961eaf842092008a65` | `src` |

On all five, `survey.py` proposed `candidateAdapter: web` (refined from `tsx`
because of `.css`, `.scss`, `.vue` or `.svelte` files), and `init.py --from-survey` seeded
`adapters.lang: web`. No other audit consumes `web`: reduced-motion,
focus-order, semantics and token-usage refuse with exit 2 for this adapter, as
they do for `tsx`. So `audit_tokens.py` is the only audit measured here.

```bash
python3 $SUITE/plugins/backend-suite/bin/survey.py --project-root .
python3 $SUITE/plugins/backend-suite/bin/init.py --dir . --from-survey
python3 $SUITE/plugins/backend-suite/bin/audit_tokens.py --dir <scan dir> --out <file>
```

## 2. Method

- **Sample.** For each project, `random.sample(findings, 60)` with a fixed seed,
  or every finding when there are fewer than 60. Each finding was judged by
  reading its source line and two lines of context.
- **Wrong (false positive)** means the matched literal is not a hardcoded
  UI-styling value at all. Examples: test fixture data, a token *definition*,
  SVG artwork, image metadata, a keyword, or text in a comment.
- **Low value, still counted correct**: offsets inside `calc()` around a
  token, syntax-highlighting theme colours, and values in projects that have no
  spacing scale to route through. These are real hardcoded design values. They
  are kept apart from "wrong", the same split #104 makes.
- **Before** was sampled with seed 104 against `main` @ `2cfe39a`. Tuning used
  seeds 104 and 2026. **After** was sampled with a fresh seed, 7, so the after
  sample does not repeat the rows the filters were tuned on. It is still the same
  *corpus* (see §6).

## 3. Results

| Project | Findings before → after | Sampled | Wrong before | Wrong after |
|---|---|---|---|---|
| docusaurus | 130 → 100 | 60 / 60 | 13 (21.7%) | 0 (0%) |
| excalidraw | 3177 → 1287 | 70 / 60 | 51 (72.9%) | 5 (8.3%) |
| realworld | 8 → 8 | 8 / 8 | 0 | 0 |
| taxonomy | 85 → 64 | 60 / 60 | 15 (25.0%) | 2 (3.3%) |
| vitepress | 731* → 701 | 60 / 60 | 1 (1.7%) | 0 (0%) |
| **pooled** | | **258 / 248** | **80 (31.0%)** | **7 (2.8%)** |

\* `main` printed **650** for vitepress, not 731. That gap is a real bug, below.

### A false-negative bug, found while measuring

`web.checks()` cached each SFC's `<style>`-region spans by `id(source)`. When a
file's text is freed, CPython reuses that id for a later string of the same
size. The later file then inherited the earlier file's spans, and its
`<style>` findings were silently dropped. On vitepress this lost **81 of 731
findings (11%)**. The fix is a one-slot cache compared by identity.
`test_region_cache_does_not_leak_between_files` fails on `main` and passes here.

`adapters/tsx.py` has the same `id(source)`-keyed pattern in `span_cache`, which
holds the CSS-in-JS template spans. It was not touched, because it is outside
this change's scope, but it is presumably exposed to the same reuse.

## 4. False-positive classes fixed (web.py only)

Every filter is a statement about what the literal *is*, never about how often
it appears. Each one is pinned in `bin/web_adapter_test.py` by a negative case
and a positive neighbour in the same source.

| Class | Seen in | Example | Rule |
|---|---|---|---|
| Test / story / minified files | excalidraw (≈1,800), docusaurus | `width: 100` in `*.test.tsx` | decided from content: top-level `describe('…'`, or `it`/`test` + `expect(`, or an import of vitest/jest/@testing-library/playwright/cypress, or Storybook `Meta`; or an average line length above 500 |
| Hairlines | all | `height: 1px`, `bottom: -1px`, `h-[1px]` | \|n\| ≤ 1px is not a spacing step. **Letter-spacing excluded**: `0.4px` tracking is a type value |
| Circle / pill radius | all CSS | `border-radius: 50%` | 50%, 100% and ≥ 999px are shapes, not radius tokens |
| Percent / viewport lengths | taxonomy | `max-w-[85%]` | a proportion, not a scale step |
| `var()` fallback | excalidraw | `width: var(--icon-size, 1rem)` | the declaration reads a token. `calc(var(--x) + 2rem)` **stays reported** |
| `1em` identity | vitepress | `width: 1em` on icons, `font-size: 1em` | "the size of the text" |
| Multi-line custom-property definition | excalidraw | `--shadow: …,\n 0 2px rgba(…)` | definition test looks back to the declaration start |
| JS custom-property definition | docusaurus | `style={{'--dark': '#000'}}` | a definition, not a use |
| SVG artwork colour | docusaurus, excalidraw | `fill="#fff"`, `stopColor=`, `setAttribute("fill", …)` | presentation attributes belong to the asset pipeline. CSS `fill: #fff` **stays reported** |
| Image metadata | taxonomy | `{ url, width: 1200, height: 630 }` | object literal with a `url`/`src` key |
| Tailwind keyword brackets | taxonomy | `rounded-[inherit]` | not a value |
| Multi-line comment text | vitepress | `… (#5399) */` | inside `/* … */` |

Not observed in this corpus, so not exercised as a measured class:
`@media` breakpoints (the length pattern cannot cross the `{` that ends them),
`@keyframes` percentages (they never match a length property), and
`transparent`/`currentColor`/`inherit` in CSS (they are not literals the
patterns match).

## 5. What is still wrong (after)

| Class | Count in sample | Why it is not fixed in web.py |
|---|---|---|
| Icon artwork dimensions, `createIcon(path, { width: 448, height: 512 })` | 3 (excalidraw) | Indistinguishable from a real `{width, height}` style object without project knowledge |
| Debug `console.log('%c', "color: #8B4000")` | 1 (excalidraw) | Rare. A rule for it would be overfitting |
| Test fixtures and helpers with no test-runner import (`tests/fixtures/*.ts`) | 1 (excalidraw), 17 in the full population | A check sees source text, not the path |
| OG `ImageResponse` options `{ width: 1200, height: 630, fonts }` | 2 (taxonomy) | No `url` key; same ambiguity as icon dims |

Two more classes fall outside the samples but were seen in the population.
**Palette definition files**, such as excalidraw's `packages/common/src/colors.ts`,
are token sources. **Vendored third-party CSS**, such as docusaurus's
`nprogress.css`, is another library's stylesheet. Both are what `exceptions.json` exists for: `color.themeFileToSkip`, or
`allowlistRegions` with a path glob such as `**/tests/**`.

**Engine gap, not fixable here.** `engine/scan.source_files` does not skip
`node_modules/` or `dist/`. With `--dir .`, a planted `node_modules/x/a.css`
and `dist/b.css` were both reported. The minified-bundle filter catches most
built output, but not a readable vendored stylesheet. Keep `source.root` on
authored source.

## 6. Verdict

- The bar in the `DISABLED` registry is **≤ 5% wrong**. Pooled, 2.8% clears it.
  Per project, excalidraw at 8.3% does not.
- The measurer tuned and judged on the same corpus. The after-sample rows are
  fresh, but the projects are not. This is a self-tested result
  (`Verification-Tier: self-tested`) and not an independent one.
- **Recommendation: keep `unverified`.** Do not mark it `proven`. It also should
  not become `experimental` or `disabled`: true-positive capacity is
  demonstrated on every stack (realworld 8/8, vitepress 60/60), and the
  remaining noise is narrow and config-addressable. Re-measure on 4 or more
  held-out projects, including a styled-components and an Angular or Lit
  codebase, before promoting it.

_Last updated: 2026-10-08_
