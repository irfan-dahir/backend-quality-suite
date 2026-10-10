# Measurement — `web` adapter, held-out corpus, 2026-10-08

Issue #104. The first measurement
([MEASUREMENT-2026-10-08-web-adapter.md](./MEASUREMENT-2026-10-08-web-adapter.md))
tuned `design_suite/adapters/web.py` and judged it on the same five projects.
This is the held-out re-measurement it asked for. **It is a test, not a tuning
pass: `web.py` is not changed by this branch.**

## 1. Protocol (fixed and committed to this file before any result was seen)

**Selection rule.** One project per styling style, each meeting all of:
public, permissive licence (MIT/Apache-2.0/BSD) *or* AGPL/GPL read-only use for
measurement; well known (≥ 10k GitHub stars); actively maintained; authors its
own styles in-repo. None of the five tuning projects (docusaurus, excalidraw,
sveltejs/realworld, shadcn taxonomy, vitepress), and no client code. Chosen
from memory of the ecosystem before cloning, not by inspecting findings:

| Style | Project |
|---|---|
| React + CSS Modules | mantinedev/mantine |
| Svelte + Tailwind | immich-app/immich (`web/`) |
| React + SCSS | mastodon/mastodon |
| Vue SFC (scoped CSS) | misskey-dev/misskey |
| Plain CSS + JS | pi-hole/web |
| Tailwind (React/Next) | calcom/cal.com |

**Run, exactly as a new user would**, in a shallow clone under `mktemp -d`:

```bash
python3 $SUITE/plugins/design-suite/bin/survey.py --project-root .
python3 $SUITE/plugins/design-suite/bin/init.py --dir . --from-survey
python3 $SUITE/plugins/design-suite/bin/audit_tokens.py      # no --dir: the profile's source.root
```

No `exceptions.json` edits, no `--dir` override. If init does not seed
`adapters.lang: web`, that is recorded as a result, and the run is repeated
with `web` named explicitly so the adapter is still measured.

**Sample.** `random.Random(20261008).sample(findings, 60)` per project (all
if fewer). Each finding judged from its source line plus context.

**Classification** (same definitions as the first measurement, so the numbers
are comparable): *FALSE* = the literal is not a hardcoded UI-styling value
(test data, token definition, SVG artwork, image metadata, keyword, comment
text, vendored third-party CSS, non-UI code). *TRUE* = a real hardcoded design
value, including low-value ones (offsets in `calc()`, syntax-theme colours).

**Recall.** Plant 5 violations per project under its scanned root — a colour,
a spacing length, a radius and a duration in one new stylesheet of the
project's own kind, plus a hardcoded colour in one new component file — rerun
`audit_tokens.py`, and count how many of the 5 planted lines are reported.

**Decision.** Apply the bar literally: ≤ 5% wrong *and* demonstrated
true-positive capacity, per project and pooled. A project over 5% is reported
as a failure, not averaged away.

---

*Everything below this line was written after the run.*

## 2. Corpus as run

Shallow clones under `mktemp -d /tmp/webheld.XXXX`; `main` @ `c6dc21b` of this
repo; `web.py` untouched.

| Project | Style | URL | Commit | Licence | `source.root` used |
|---|---|---|---|---|---|
| mantine | React + CSS Modules | https://github.com/mantinedev/mantine | `f7ab1ef52579366e2310fc12b1a12e88a821053a` | MIT | `packages/@mantine/core/src` |
| immich | Svelte + Tailwind | https://github.com/immich-app/immich | `02481deb145416ed1600bf2928c3562577a39600` | AGPL-3.0 | `src` (project root `web/`) |
| mastodon | React + SCSS | https://github.com/mastodon/mastodon | `aacb9fb0211c8245a04feebcf0979abb5e2230c4` | AGPL-3.0 | `app` |
| misskey | Vue SFC | https://github.com/misskey-dev/misskey | `5f501341d49d2bc3fa7e817ce7548a82174326eb` | AGPL-3.0 | `packages/frontend/src` |
| pi-hole/web | Plain CSS + JS | https://github.com/pi-hole/web | `b2a4078446519c58d84f199663ca9326d5d311f0` | EUPL-1.2 | `.` |
| cal.com | Tailwind (Next.js) | https://github.com/calcom/cal.com | `54343aa685ae8f33159d2f485ec4a57bad5c574a` | MIT (core) | `apps/web` |

Deviation from §1: pi-hole/web is EUPL-1.2, a copyleft licence that was not in
the pre-registered list. It was only read and nothing from it is redistributed,
the same as the AGPL projects. All six were chosen before cloning.

### What a new user actually hits (onboarding findings, not adapter precision)

The pre-registered run (`survey` → `init --from-survey` → `audit_tokens`, no
overrides) produced **zero findings on all six projects**. Every one exited 2
with a reason, so none of these is a silent pass:

- **5 of 6: `source.root` left as a `TODO`.** Survey found no candidate root
  for mantine and pi-hole. For misskey it ranked `packages/backend/src` first,
  and for cal.com `packages/app-store`, so neither guess was the UI. Only immich
  (`src`) got a usable root.
- **mastodon: `adapters.lang` left as a `TODO`.** The Gemfile plus the Ruby
  majority meant init did not seed `web`. Refused as INERT.
- **immich, cal.com: design-audit config drift.** The scaffolded
  `token_categories.color.names` still holds `TODO_TOKEN_NAME_*`, so
  `audit_tokens` refuses until it lists the discovered tokens (8 for immich,
  140 for cal.com). The error message names them, so the fix is mechanical.

To measure the adapter at all, I made the edits a user would make. I set
`source.root` as in the table, set `adapters.lang: web` on mastodon, and pasted
the token names that the refusal listed into `color.names`. Nothing else was
changed, and there were no `exceptions.json` entries and no `--dir` overrides.
pi-hole's `vendor/` was skipped by the engine on its own, and the audit said so.

## 3. Precision results

`random.Random(20261008).sample(findings, 60)` per project. Each finding was
judged from its line plus context. The per-finding table is in the
[appendix](./MEASUREMENT-2026-10-08-web-adapter-held-out-appendix.md).

| Project | Findings | Sampled | Wrong | Wrong % | ≤ 5%? |
|---|---|---|---|---|---|
| mantine | 1278 | 60 | 50 | **83.3%** | no |
| immich | 177 | 60 | 20 | **33.3%** | no |
| mastodon | 3198 | 60 | 0 | 0.0% | yes |
| misskey | 3950 | 60 | 3 | 5.0% | yes (at the limit) |
| pi-hole/web | 3109 | 60 | 0 | 0.0% | yes |
| cal.com | 453 | 60 | 5 | **8.3%** | no |
| **pooled** | 12165 | 360 | 78 | **21.7%** | no |

Pooling equal-sized samples weights every project the same. Pooling is not
how the bar is applied, and it is shown here only for comparison with the
first measurement's pooled 2.8%.

## 4. Recall (planted violations)

For each project I planted a stylesheet of the project's own kind under the
scanned root (`.module.css`, `.css`, `.scss`, `.scss`, `.css`, `.css`). It held a
hex colour, `padding: 13px`, `border-radius: 7px` and `transition: … 345ms`. I
also planted one component (`.tsx`, `.svelte`, `.tsx`, `.vue`, `.js`, `.tsx`)
with a hardcoded inline colour.

| Project | Found |
|---|---|
| mantine | 5 / 5 |
| immich | 5 / 5 |
| mastodon | 5 / 5 |
| misskey | 5 / 5 |
| pi-hole/web | 5 / 5 |
| cal.com | 5 / 5 |
| **total** | **30 / 30** |

True-positive capacity is also shown on real code: 282 of the 360 sampled
findings are true positives, and every project contributed some.

## 5. False-positive classes found (for a later fix — not fixed here)

| Class | Where | Count in sample | Population note |
|---|---|---|---|
| **Storybook stories without a `Meta` import** (`*.story.tsx`, `export default { title }`) | mantine | 46 | 958 of mantine's 1278 findings are in `.story.tsx`. The content-based test-file filter does not recognise this story shape |
| **Data objects with `width`/`height` keys** (video codec ladders, aspect-ratio options, image/crop model state) | immich | 18 | Same ambiguity as §5 of the first measurement ("icon dims", OG image options), now the dominant immich class |
| **HTML numeric entities read as hex colours** (`&#8595;`, `&#8203;`) | immich, cal.com | 2 | New class. `&#NNNN;` matches the 3/4-digit hex pattern; also `#face` in immich (an id reference) in the population |
| Palette / preset definitions in TS | mantine, misskey | 5 | `default-colors.ts`, theme-editor presets — `exceptions.json` territory, as the first measurement said |
| `mask-image` gradient alpha stops | immich, misskey | 3 | `rgba(0,0,0,a)` in a mask is opacity, not colour |
| Custom-property *definitions* in an embedded `<style>` in TSX, and Tailwind `[--x:#hex]` | cal.com | 2 | Definition filter covers CSS files and `style={{'--x'}}` but not these two shapes |
| `var(--token, #hex)` colour fallback | cal.com | 1 | The `var()` fallback filter covers lengths, not colours |
| `0ms` duration | mantine | 1 | Reset value, analogous to the hairline rule |
| Default value in app state (`organizationBrand.color`) | cal.com | 1 | Data, not styling |

Three of these, stories, data objects and HTML entities, account for 66 of the
78 wrong findings. None of the three is project-specific.

## 6. Decision

**The bar, quoted.** `docs/CONCEPTS.md` defines ✅ **proven** as "Recorded
evidence of a real end-to-end run". The numeric bar for this suite's
precision-measured components, from the `DISABLED` registry in
`design_suite/engine/audit_discovery.py` (issue #104), is "<=5% wrong AND
demonstrated non-zero true-positive capacity", re-measured "on two real
consumer projects".

**Applied literally:**

- **Per project, it fails.** mantine (83.3%), immich (33.3%) and cal.com
  (8.3%) are over 5%. mastodon (0%), pi-hole/web (0%) and misskey (5.0%, at
  the limit) are at or under it.
- **Pooled, it fails.** 21.7% wrong.
- **True-positive capacity is met.** Recall was 30/30, and every project
  produced real true positives.
- **"Real consumer projects."** None of these six projects adopted the suite.
  They are real codebases run end to end, but they are not *consumers*. Even a
  perfect result here would meet CONCEPTS.md's "real end-to-end run" only on a
  generous reading. It would not meet the registry's "real consumer projects"
  wording. I am not stretching that wording, and the precision failure makes the
  question moot this time.

**Verdict: the `web` adapter stays `unverified`.** It is not promoted, and
`web.py` and the catalog are unchanged. The held-out result is much worse than
the tuned one: 21.7% pooled against 2.8%, and 3 of 6 projects over the bar
against 1 of 5. That is the overfitting the held-out run was designed to
detect.

It should not be `disabled` either. Recall is complete, and the noise comes from
three generic, nameable classes rather than from a shape the checker cannot
judge.

**What remains before `proven`:**

1. Fix the three dominant classes in `web.py`/`tsx`: story files without
   `Meta`, `{width,height}` data objects, and HTML entities.
2. Re-measure on a *fresh* held-out set. This set is now spent as a tuning
   corpus, the same way the first one was.
3. Measure on at least two real consumer projects that have adopted the suite.

Verification tier for this document: `self-tested`. The measurer is the same
agent that ran it, and the classification has not been checked by an
independent party.

_Last updated: 2026-10-08_
