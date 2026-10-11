# Measurement: `web` adapter, fresh held-out corpus, 2026-10-09

Issue #104. The held-out run
([MEASUREMENT-2026-10-08-web-adapter-held-out.md](./MEASUREMENT-2026-10-08-web-adapter-held-out.md))
found the adapter 21.7% wrong pooled. Commit `aedf620` fixed the classes it
named. Those six projects are now **spent**: they were used to tune the fix, so
re-running on them is tuning, not validation. This document measures the fixed
adapter on projects that have never been used.

## 1. Protocol (committed before any of these projects was cloned)

**Adapter under test:** `backend_suite/adapters/web.py` at the commit that
precedes this file's results section. It is not changed during the run. If a
defect is found, it is reported here and fixed on a later branch.

**Selection rule.** The projects must be public, well known (≥ 10k GitHub stars),
and actively maintained, and they must author their own UI styles in-repo. Read-only
use for measurement is allowed under any OSI licence. Excluded: every project used
before (docusaurus, excalidraw, sveltejs/realworld, shadcn taxonomy, vitepress,
mantine, immich, mastodon, misskey, pi-hole/web, cal.com) and all client code.
The projects were chosen from memory, one per styling style, before cloning:

| Style | Project | Scan root (fixed now) |
|---|---|---|
| React + styled-components | outline/outline | `app` |
| Vue SFC + plain CSS | go-gitea/gitea | `web_src` |
| Svelte + Tailwind | open-webui/open-webui | `src` |
| Plain JS + SCSS | jellyfin/jellyfin-web | `src` |
| React + Linaria/emotion | twentyhq/twenty | `packages/twenty-front/src` |

**Run.** Shallow clone (`--depth 1`) under `mktemp -d /tmp/...`. Findings are
computed the way `audit_tokens.py` computes them with an empty `exceptions.json`:
`scan_tree` over the adapter's `FILE_GLOBS`, with the engine's default skip
directories, minus `GENERATED_SUFFIXES`. Onboarding (survey/init) is not under
test here; the previous document measured it.

**Sample.** `random.Random(20261009).sample(findings, 60)` per project, or every
finding if there are fewer than 60. Each finding is judged from its line plus its
context.

**Classification.** The definitions are the same as in both earlier measurements. *FALSE* means the
literal is not a hardcoded UI-styling value: test data, a token definition, SVG
artwork, image or data metadata, a keyword, comment text, vendored CSS, or non-UI
code. *TRUE* means a real hardcoded design value, including low-value ones.

**Recall.** Under each scan root, plant one new stylesheet of the project's own
kind. It holds a hex colour, `padding: 13px`, `border-radius: 7px` and a `345ms`
transition. Also plant one new component with a hardcoded inline colour. Count
how many of the 5 planted lines are reported.

**Decision.** Apply the bar literally, per project: ≤ 5% wrong *and* non-zero
true-positive capacity. A project over 5% counts as a failure and is not
averaged away. Maturity is decided by the bar's own wording, quoted in §6.

---

*Results are appended below this line after the run.*

## 2. Corpus as run

Shallow clones in `mktemp -d /tmp/webfix.XXXX`. The adapter is at `aedf620`, and
the protocol was committed at `3d9b5b6`, before any clone.

| Project | Commit | Licence | Scan root |
|---|---|---|---|
| outline/outline | `f6f27d51296978b3f5d7305c556c2bd4f81a666f` | BSL 1.1 | `app` |
| go-gitea/gitea | `76aabbff9f0644743b30882b5910d9e1d818ec2e` | MIT | `web_src` |
| open-webui/open-webui | `8bd8b4fac5e059578ac0c74b3c18d11139f88b7d` | Open WebUI License (BSD-3 derived, branding clause) | `src` |
| jellyfin/jellyfin-web | `d93e8b419058ab337e2d32651d873ca76c84e296` | GPL-2.0 | `src` |
| twentyhq/twenty | `d951b09880b4ec2dae7d30d5c7bd8e83810d374a` | AGPL-3.0 (mostly) | `packages/twenty-front/src` |

**Deviation from §1:** outline (BSL 1.1) and open-webui (a custom licence) are
not OSI licences. They were only read, and nothing from them is redistributed
apart from file paths and line numbers in the appendix. All five were chosen
before cloning, and none was swapped out after a result was seen.

## 3. Tuning re-check on the spent six (tuning, not validation)

Commit `aedf620` was re-run on the held-out set that motivated it. That set
was used to design the fixes, so this section only confirms that the classes
are gone. It says nothing about how the adapter generalises.

| Project | Findings before → after | Sampled FALSE still reported | Sampled TRUE lost |
|---|---|---|---|
| mantine | 1278 → 179 | 0 / 50 | 0 / 10 |
| immich | 177 → 117 | 1 / 20 (`this.cropImageSize = {width, height}`, a bare assignment, deliberately left reported) | 0 / 40 |
| mastodon | 3198 → 3194 | 0 / 0 | 0 / 60 |
| misskey | 3950 → 3838 | 1 / 3 (theme-editor preset rows of objects, not an all-colour array) | 0 / 57 |
| pi-hole/web | 3109 → 3089 | 0 / 0 | 0 / 60 |
| cal.com | 453 → 394 | 1 / 5 (default brand colour in app state) | 0 / 55 |

Of the 78 sampled wrong findings, 75 are gone, and none of the 282 sampled true findings was lost.
While building the fix, one draft lost a true finding: misskey's
`withDefaults(…, { width: 400 })` modal size. Another draft hid a colour after a
closed `var()` on pi-hole. Both were fixed before `aedf620`, and each has a test.

## 4. Precision results (fresh held-out)

| Project | Findings | Sampled | Wrong | Wrong % | ≤ 5%? |
|---|---|---|---|---|---|
| outline | 772 | 60 | 0 | 0.0% | yes |
| gitea | 1690 | 60 | 0 | 0.0% | yes |
| open-webui | 1659 | 60 | 2 | 3.3% | yes |
| jellyfin-web | 1309 | 60 | 4 | **6.7%** | no |
| twenty | 691 | 60 | 4 | **6.7%** | no |
| pooled (comparison only) | 6121 | 300 | 10 | 3.3% | — |

The per-finding judgements are in the
[appendix](./MEASUREMENT-2026-10-09-web-adapter-fresh-held-out-appendix.md).

**Wrong-finding classes still open (new, not fixed here):**

| Class | Where | Count |
|---|---|---|
| Theme palette definitions in TS object form (`primary: { main: '#00a4dc' }`) | jellyfin-web | 2 |
| Width/height that is data rather than style: an image-request param (`getScaledImageUrl(id, { width: 80 })`), dagre graph-node sizes | jellyfin-web, twenty | 3 |
| Custom-property definition inside a styled-components template (`--x-max-width: 768px`). The `tsx` `css_spacing` path has a `\b` anchor that matches after `-`, so **`tsx` shares this defect** | twenty | 1 |
| `1s` unit multiplier on a token (`calc(${token} * 1s)`) | twenty | 1 |
| Canvas fills in a document-preview renderer | open-webui | 2 |
| Default value of a user setting | jellyfin-web | 1 |

Judgement calls that went toward TRUE and are recorded so they can be checked:
gitea's 256-colour ANSI terminal classes (`.term-fgxNNN`) were judged TRUE,
consistent with "syntax-theme colours". So were data-grid column widths and
skeleton-bar widths. Snippets labelled `css_spacing` that are actually
`border-radius` lines (outline #4, #5) are mislabelled by kind, but they are
real values, so they count as TRUE.

## 5. Recall (planted violations)

| Project | Found |
|---|---|
| outline | 5 / 5 |
| gitea | 5 / 5 |
| open-webui | 5 / 5 |
| jellyfin-web | 5 / 5 |
| twenty | 5 / 5 |
| **total** | **25 / 25** |

## 6. Decision

**The bar, quoted** from `backend_suite/engine/audit_discovery.py` (issue #104):
"<=5% wrong AND demonstrated non-zero true-positive capacity, re-measured on two
real consumer projects".

**Applied literally, per project:**

- outline, gitea and open-webui pass the precision half.
- **jellyfin-web (6.7%) and twenty (6.7%) fail it.** With 60 samples, 6.7% is 4
  wrong where the bar allows 3, so this is a narrow miss. It is still a miss,
  and it is not averaged away by the pooled 3.3%.
- True-positive capacity is met: 25/25 planted, and every project produced real
  true positives.
- "Real consumer projects": none of these five adopted the suite, so even a
  clean sweep could not meet that clause.

**Verdict: the `web` adapter stays `unverified`.** It does not meet the
precision bar on 2 of 5 fresh projects, and the consumer-project clause is not
met by this corpus in any case. The fix did shrink the error: the worst
project went from 83.3% before the fix to 6.7% on unseen code. The adapter
should not be `disabled`.

**What remains:** fix the open classes above (on a new branch), re-measure on
yet another fresh set, since this one is now spent, and measure on two real
consumer projects.

Verification tier: `self-tested`. The measurer and the fixer are the same agent,
and no independent party has checked the classification.

_Last updated: 2026-10-09_
