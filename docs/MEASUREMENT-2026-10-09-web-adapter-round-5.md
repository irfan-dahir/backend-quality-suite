# Measurement: `web` adapter, round 5 held-out corpus, 2026-10-09

Issue #104. Round 4
([MEASUREMENT-2026-10-09-web-adapter-round-4.md](./MEASUREMENT-2026-10-09-web-adapter-round-4.md))
failed AdGuardHome (93.3%, vendored CSS) and grafana (15.0%, path-only mock
fixtures). Commit `7b28930` adds file-level classification for those classes.
The round-4 five (uptime-kuma, AdGuardHome, grafana, budibase, lobe-chat) are
now **spent**, along with every project used before them. Re-running them is
tuning, not validation.

## 1. Protocol (committed before any of these projects was cloned)

**Adapter under test:** `backend_suite/adapters/web.py` and the engine's
`scan_tree` file filter at `7b28930`. Neither is changed during the run. If a
defect is found, it is reported here and fixed on a later branch.

**Selection rule.** The projects must be public, well known (≥ 10k GitHub stars)
and actively maintained, and they must author their own UI styles in-repo.
Read-only use. Excluded (every project named in any earlier
`docs/MEASUREMENT-*web*` file): docusaurus, excalidraw, sveltejs/realworld,
shadcn taxonomy, vitepress, mantine, immich, mastodon, misskey, pi-hole/web,
cal.com, outline, gitea, open-webui, jellyfin-web, twenty, appwrite console,
hoppscotch, chatwoot, bulletproof-react, shadcn-admin, vitesse, uptime-kuma,
AdGuardHome, grafana, budibase, lobe-chat, and all client code. Chosen from
memory before cloning, one per styling style:

| Style | Project | Scan root (fixed now) |
|---|---|---|
| Vue SFC + Tailwind/CSS | koel/koel | `resources/assets/js` |
| React + SCSS / tss-react | jitsi/jitsi-meet | `react` |
| Svelte + SCSS | pocketbase/pocketbase | `ui/src` |
| Vue SFC + SCSS modules | n8n-io/n8n | `packages/frontend/editor-ui/src` |
| React + Tailwind | plausible/analytics | `assets/js` |

If a scan root does not exist at the cloned commit, the nearest directory that
holds the project's UI source is used, and the substitution is recorded as a
deviation. A project is never swapped out after its result is seen.

**Run.** Shallow clone (`--depth 1`) under `mktemp -d /tmp/...`. Findings are
computed the way `audit_tokens.py` computes them with an empty `exceptions.json`:
`scan_tree` over the adapter's `FILE_GLOBS` with `file_filter=web.non_product_file`,
the engine's default skip directories, minus `GENERATED_SUFFIXES`. The
file-level SKIPPED lines are recorded, and every vendored-classified file is
inspected by hand (a project's own file wrongly skipped is a recall defect).

**Sample.** `random.Random(20261009).sample(findings, 60)` per project, sorted
findings by (file, line), or every finding if there are fewer than 60.

**Classification.** Same definitions as earlier rounds. *FALSE*: the literal is
not a hardcoded UI-styling value (test data, a token definition, SVG or canvas
artwork, image or data metadata, a keyword, comment text, vendored code,
non-UI code). *TRUE*: a real hardcoded design value, including low-value ones.

**Recall.** Under each scan root, plant one new stylesheet of the project's own
kind with a hex colour, `padding: 13px`, `border-radius: 7px` and a `345ms`
transition, plus one new component with a hardcoded inline colour. Count how
many of the 5 planted lines are reported.

**Decision.** Apply the bar literally, per project: ≤ 5% wrong *and* non-zero
true-positive capacity. A project over 5% is a failure and is not averaged
away. None of these projects has adopted the suite, so the "real consumer
projects" clause cannot be met and maturity stays `unverified` whatever the result.

---

*Results are appended below this line after the run.*

## 2. Corpus as run

Shallow clones in `mktemp -d /tmp/webr5.XXXX`. The adapter is at `7b28930`, and
the protocol was committed at `53fbcc2`, before any clone. Every scan root
existed, so there was no substitution.

| Project | Commit | Licence | Scan root |
|---|---|---|---|
| koel/koel | `c9ec4fb1931f9de71bdaa6cb7aa65d0f18a9041c` | MIT | `resources/assets/js` |
| jitsi/jitsi-meet | `300bdaa8683b057e54b559d98318bda6e9c51b12` | Apache-2.0 | `react` |
| pocketbase/pocketbase | `6f370ea741f33adf889eef02e3c1b884a47aa522` | MIT | `ui/src` |
| n8n-io/n8n | `e64dc46055dd48f4c2685e6918aff4cf11abaa94` | Sustainable Use License (fair-code) | `packages/frontend/editor-ui/src` |
| plausible/analytics | `bc2c7b395caddf7bb4eec2548be7958824d07d4a` | AGPL-3.0 | `assets/js` |

**Deviations from §1:** n8n's licence is not OSI; it was only read, and nothing
from it is redistributed apart from file paths and line numbers. plausible has
44 findings, so all 44 were classified (the protocol's "fewer than 60" case).

**File-level skips (all inspected by hand, all correct):** koel 1 mock
(`composables/__mocks__/useContextMenu.ts`); n8n 7 mock/fixture (all under
`__tests__/…/fixtures/`) and 1 story (`ToolsConnectionModal.stories.ts`). No
file in the five was classified vendored, so the banner rule's precision on
fresh code is **untested here**; its only evidence is the tuning set (§3).

## 3. Tuning re-check on the spent round-4 five (tuning, not validation)

Same commits as round 4, fetched by SHA.

| Project | Findings before → after | Sampled FALSE still reported | Sampled TRUE lost |
|---|---|---|---|
| uptime-kuma | 657 → 655 | 0 / 2 | 0 / 58 |
| AdGuardHome | 3700 → 465 | 0 / 56 | 0 / 4 |
| grafana | 792 → 757 | 2 / 9 | 0 / 51 |
| budibase | 1866 → 1861 | 0 / 0 | 0 / 60 |
| lobe-chat | 5923 → 5675 | 0 / 2 | 0 / 58 |

67 of 69 sampled wrong findings are gone; none of the 231 sampled true findings
was lost. The two left are grafana's canvas `defaultSize: { width, height }`,
kept on purpose: no rule was found that separates a data default from a
component's own default size without naming grafana's key. Every vendored
skip on this set was checked by hand: AdGuardHome `Tabler.css` (Bootstrap 4
banner after a short header comment) and grafana `Mousetrap.ts` (a copied
library). Off-sample, the colour-map rule also drops all-colour maps that a
reviewer might call TRUE — e.g. AdGuardHome `StatsCard.tsx` `CHART_COLORS`
(4 series colours keyed by stat name) and lobe-chat's terminal theme. The rule
treats them as palette definitions, the same call already made for all-colour
arrays. Stated, not hidden.

## 4. Precision results (round 5 held-out)

| Project | Findings | Sampled | Wrong | Wrong % | ≤ 5%? |
|---|---|---|---|---|---|
| koel | 286 | 60 | 5 | **8.3%** | no |
| jitsi-meet | 748 | 60 | 0 | 0.0% | yes |
| pocketbase | 537 | 60 | 0 | 0.0% | yes |
| n8n | 1808 | 60 | 4 | **6.7%** | no |
| plausible | 44 | 44 | 2 | 4.5% | yes |
| pooled (comparison only) | 3423 | 284 | 11 | 3.9% | — |

**New wrong-finding classes (not fixed here):**

| Class | Where | Count |
|---|---|---|
| Theme preset records: `thumbnail_color` sitting next to the preset's own `--color-*` definitions in `config/themes.ts` | koel | 3 |
| Runtime custom-property definition: `style.setProperty('--color-highlight-fg', … '#ffffff')` | koel | 1 |
| Off-screen initial position (`left/top: -9999px`) where `position` comes from a Tailwind `fixed` class. The round-5 hide-hack rule only sees a `position:` declaration | koel | 1 |
| Seed-workflow data: sticky-note node `height/width` and a form node's `customCss` string, in `experiments/readyToRunWorkflows/workflows/*.ts`. Product-shipped data, not under a fixture path, and not styling | n8n | 4 |
| popper.js `preventOverflow` modifier `padding: 8` (a positioning-engine option) | plausible | 2 |

Judgement calls that went toward TRUE: third-party brand colours painted on
service tiles (koel `ServicesSettingGroup.vue`), agent-template card gradients
(n8n), SVG chart gradient stops and map colour scales (plausible), utility
classes such as `.m-l-20 { margin-left: 20px }` (pocketbase), a Prism theme
re-pointed at the project's own tokens (pocketbase `prism.css`), an ERD
component's `marginX: 90` prop default (pocketbase), and the inline styles of
a user-copyable embed snippet (plausible, after round 4's e-mail-template
precedent). If the koel brand colours were FALSE instead, koel would be at
13.3%; the verdict would not change.

## 5. Recall (planted violations)

| Project | Found |
|---|---|
| koel | 5 / 5 |
| jitsi-meet | 5 / 5 |
| pocketbase | 5 / 5 |
| n8n | 5 / 5 |
| plausible | 5 / 5 |
| **total** | **25 / 25** |

## 6. Decision

**The bar, quoted** from `backend_suite/engine/audit_discovery.py`:
"<=5% wrong AND demonstrated non-zero true-positive capacity, re-measured on two
real consumer projects".

**Applied literally, per project:** jitsi-meet, pocketbase and plausible pass
the precision half (plausible at 4.5%, with 2 wrong out of 44). **koel (8.3%)
and n8n (6.7%) fail it.** True-positive capacity is met (25/25). The
consumer-project clause is not met by this corpus.

**Verdict: the `web` adapter stays `unverified`.** The round-4 file-level
classes are fixed and none of them reappeared. The two failures are smaller and
of a different kind. Both are *definitions or data that the project ships*:
theme presets and runtime `setProperty('--x', …)` in koel, and seed workflows in
n8n. A path rule does not reach them. Candidates for the next round, each of
which would need a paired test: `setProperty('--…', …)` as a custom-property
definition (the JS twin of the existing `'--x':` key rule); an object that
carries `--*` keys is a theme record as a whole; a hide-hack rule that also
accepts `fixed`/`absolute` in a sibling `class`. Seed-workflow geometry has no
general rule yet, so a project would cover it through `exceptions.json`.
This corpus is now spent.

Verification tier: `self-tested`. The measurer and the fixer are the same agent.

_Last updated: 2026-10-09_
