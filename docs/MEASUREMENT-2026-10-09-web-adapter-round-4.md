# Measurement: `web` adapter, round 4 held-out corpus, 2026-10-09

Issue #104. The fresh held-out run
([MEASUREMENT-2026-10-09-web-adapter-fresh-held-out.md](./MEASUREMENT-2026-10-09-web-adapter-fresh-held-out.md))
left the adapter 3.3% wrong pooled, with jellyfin-web and twenty at 6.7%.
Commit `2c8e260` fixed the six classes it named. The five projects from that run
(outline, gitea, open-webui, jellyfin-web, twenty) are now **spent**, along with
every project used before them. Re-running them is tuning, not validation.

## 1. Protocol (committed before any of these projects was cloned)

**Adapter under test:** `backend_suite/adapters/web.py` at `2c8e260`. It is not
changed during the run. If a defect is found, it is reported here and fixed on
a later branch.

**Selection rule.** The projects must be public, well known (≥ 10k GitHub stars)
and actively maintained, and they must author their own UI styles in-repo.
Read-only use. Excluded: docusaurus, excalidraw, sveltejs/realworld, shadcn
taxonomy, vitepress, mantine, immich, mastodon, misskey, pi-hole/web, cal.com,
outline, gitea, open-webui, jellyfin-web, twenty, appwrite console, hoppscotch,
chatwoot, bulletproof-react, shadcn-admin, vitesse, and all client code. The
projects were chosen from memory before cloning, one per styling style:

| Style | Project | Scan root (fixed now) |
|---|---|---|
| Vue SFC + SCSS | louislam/uptime-kuma | `src` |
| React + plain CSS | AdguardTeam/AdGuardHome | `client/src` |
| React + emotion (object CSS-in-JS) | grafana/grafana | `public/app` |
| Svelte + CSS | Budibase/budibase | `packages/builder/src` |
| React + antd-style CSS-in-JS | lobehub/lobe-chat | `src` |

If a scan root does not exist at the cloned commit, the nearest directory that
holds the project's UI source is used, and the substitution is recorded as a
deviation. A project is never swapped out after its result is seen.

**Run.** Shallow clone (`--depth 1`) under `mktemp -d /tmp/...`. Findings are
computed the way `audit_tokens.py` computes them with an empty `exceptions.json`:
`scan_tree` over the adapter's `FILE_GLOBS`, the engine's default skip
directories, minus `GENERATED_SUFFIXES`. The clones are deleted afterwards.

**Sample.** `random.Random(20261009).sample(findings, 60)` per project, or
every finding if there are fewer than 60. Each finding is judged from its line
plus its context.

**Classification.** Same definitions as the earlier measurements. *FALSE*: the
literal is not a hardcoded UI-styling value (test data, a token definition, SVG
or canvas artwork, image or data metadata, a keyword, comment text, vendored
CSS, non-UI code). *TRUE*: a real hardcoded design value, including low-value ones.

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

Shallow clones in `mktemp -d /tmp/webr4.XXXX`. The adapter is at `2c8e260`, and
the protocol was committed at `790d5cd`, before any clone. Every scan root
existed, so there was no substitution.

| Project | Commit | Licence | Scan root |
|---|---|---|---|
| louislam/uptime-kuma | `91e193729ed78ed3aa13c03f76344a08e645e616` | MIT | `src` |
| AdguardTeam/AdGuardHome | `8dedd3278542b45ea21994e24422f5cc53e14b8f` | GPL-3.0 | `client/src` |
| grafana/grafana | `7d14232feee3523f09b95caf51353cdfca2f2194` | AGPL-3.0 | `public/app` |
| Budibase/budibase | `dfd8926046f86e14cf7de6ecda59302e798d5a4b` | GPL-3.0 (builder package) | `packages/builder/src` |
| lobehub/lobe-chat | `7ac04afbceee4deb3f76025d7824b1f52e721cff` | LobeHub Community License | `src` |

**Deviation from §1:** lobe-chat's licence is not OSI. It was only read, and
nothing from it is redistributed apart from file paths and line numbers.

## 3. Tuning re-check on the spent five (tuning, not validation)

| Project | Findings before → after | Sampled FALSE still reported | Sampled TRUE lost |
|---|---|---|---|
| outline | 772 → 771 | 0 / 0 | 0 / 60 |
| gitea | 1690 → 1690 | 0 / 0 | 0 / 60 |
| open-webui | 1659 → 1648 | 0 / 2 | 0 / 58 |
| jellyfin-web | 1309 → 1254 | 0 / 4 | 0 / 56 |
| twenty | 691 → 672 | 0 / 4 | 0 / 56 |

All 10 sampled wrong findings are gone, and none of the 290 sampled true
findings was lost. (These counts exclude the planted recall files.) One draft
lost `scroll-margin-*` and `scrollbar-width` on twenty, which the old `\b`
only reached by accident. They are now named in the `tsx` pattern and covered
by a test.

## 4. Precision results (round 4 held-out)

| Project | Findings | Sampled | Wrong | Wrong % | ≤ 5%? |
|---|---|---|---|---|---|
| uptime-kuma | 657 | 60 | 2 | 3.3% | yes |
| AdGuardHome | 3700 | 60 | 56 | **93.3%** | no |
| grafana | 792 | 60 | 9 | **15.0%** | no |
| budibase | 1866 | 60 | 0 | 0.0% | yes |
| lobe-chat | 5923 | 60 | 2 | 3.3% | yes |
| pooled (comparison only) | 12938 | 300 | 69 | 23.0% | — |

**New wrong-finding classes (not fixed here):**

| Class | Where | Count |
|---|---|---|
| Vendored framework CSS: `components/ui/Tabler.css`, a 16,646-line copy of Bootstrap 4 + Tabler with its `/*! … Licensed under MIT */` banner. It accounts for 3227 of 3700 findings. This is the known gap stated in the adapter docstring ("a vendored copy of a library's CSS is still scanned"). Under the protocol's empty `exceptions.json`, it is reported in full. | AdGuardHome | 56 |
| A colour inside an HTML string in a `*.mock.ts` fixture that has no test-runner import. This is the docstring's other stated gap: fixtures are decided by content, not path | grafana | 6 |
| Canvas-editor element `defaultSize: { width, height }` (user-content geometry) | grafana | 2 |
| Data-colour lookup (`colors.indexOf('#E24D42')`) | grafana | 1 |
| Language-to-colour data map (`'lua': '#000080'`) | lobe-chat | 2 |
| Off-screen hide hack (`left: -999999px`) | uptime-kuma | 2 |

Judgement calls that went toward TRUE: chart.js `layout.padding`, table
column-width schemas (budibase), `tinycolor.mostReadable(…, ['#fff','#000'])`
label candidates, and inline styles in an HTML email template.

## 5. Recall (planted violations)

| Project | Found |
|---|---|
| uptime-kuma | 5 / 5 |
| AdGuardHome | 5 / 5 |
| grafana | 5 / 5 |
| budibase | 5 / 5 |
| lobe-chat | 5 / 5 |
| **total** | **25 / 25** |

## 6. Decision

**The bar, quoted** from `backend_suite/engine/audit_discovery.py`:
"<=5% wrong AND demonstrated non-zero true-positive capacity, re-measured on two
real consumer projects".

**Applied literally, per project:** uptime-kuma, budibase and lobe-chat pass the
precision half. **AdGuardHome (93.3%) and grafana (15.0%) fail it.** True-positive
capacity is met (25/25). The consumer-project clause is not met by this corpus.

**Verdict: the `web` adapter stays `unverified`.** The six round-3 classes are
fixed. On fresh code, though, the two largest failures are the adapter's two
*documented* blind spots: vendored CSS and path-only fixtures. Both are files
that a check reading content one match at a time cannot classify. The
`exceptions.json` escape hatch that the docstring points to is correct, but in
practice it is not discoverable. The next fix should be file-level: detect a
vendored stylesheet from its licence banner (`/*!` + `Copyright`/`Licensed`),
and treat `*.mock.*` / `__mocks__/` / `fixtures/` as non-product paths, the way
story files already are. Each needs a paired test, and then a re-measure on yet
another fresh set, because this one is now spent.

Verification tier: `self-tested`. The measurer and the fixer are the same agent.

_Last updated: 2026-10-09_
