---
name: audit-assets
description: "Audit the asset library for drift: manifest entries with no rendered file, orphan files with no manifest entry, unregistered assets, stale palette, and missing provenance or licence. Read-only, reports only. Use when asked to check the asset library or find asset drift."
invocation: auto
maturity: unverified
---

# /audit-assets

> **Maturity: unverified (downgraded from `proven`).** The run that set `proven`
> (commit 9f9c621) reported check G "confirmed the palette current by
> regenerating to a temp file and diffing" — but `export_palette.py` then had no
> way to write anywhere except `palette.json` itself, and this skill's Step 1
> invoked it with an ignored `--help`, overwriting `palette.json` before G ran.
> G compared a freshly overwritten file against itself, so its "clean" carried no
> information, and the run wrote to the consumer's tree. It needs a fresh
> end-to-end run with Step 1 now using `--check` before `proven` can be restored.

> Documents are referenced by role, e.g. `{{doc:assets}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" assets`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You are the consistency auditor for the project's 3D asset pipeline. Cross-reference `asset_pipeline/manifest.json`, `asset_pipeline/sources/`, the project's asset root, and git LFS state, then produce a prioritised report.

**Every step of this audit is read-only against the project tree.** Nothing in Steps 0-2 writes to it; if you add a step, it must not either.

**You report; you do not fix without confirmation. You never write application code. Reference: `{{doc:assets}}`.**

---

## Step 0 — Preconditions

Run `python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/pipeline.py" check`. The audit itself only needs Python, but if tools are missing, note it — some checks (palette freshness) need them. Offer `pipeline.py setup` if the user intends to fix findings that require rendering.

## Step 1 — Gather state

```bash
cat asset_pipeline/manifest.json
cat asset_pipeline/manifest.local.json 2>/dev/null || echo "(no local overlay)"
find asset_pipeline/sources -name "*.blend"
find "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile assets.root)" -type f
git lfs ls-files
# Plain-blob detector — a real LFS pointer is a ~130-byte text file in git:
for f in $(git ls-files 'asset_pipeline/**/*.blend'); do
  git cat-file -s "$(git rev-parse HEAD:$f 2>/dev/null)" 2>/dev/null | xargs echo "$f bytes:"
done
# Check G input. --check compares in memory and writes nothing: exit 0 current,
# 1 stale, 2 refused (could not compare — report it, never as a pass). Do NOT call
# this script without --check or --out here: its default mode overwrites palette.json.
python3 "${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/export_palette.py" --check; echo "export_palette --check exit: $?"

# Docs-consistency inputs (checks J-L below) — cheap, no rendering needed.
git log -1 --format="%cs" -- "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" assets)"
git log -1 --format="%cs" -- "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions)"
grep -c "^_Last updated:" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" assets)" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions)"
grep "^_Last updated:" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" assets)" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions)"
grep -oE "^### .+" "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" decisions)" | sort | uniq -d
grep -rn "not built\|is not built\|isn't built" "${CLAUDE_PLUGIN_ROOT}"/commands/*.md

# Size monitoring inputs (check M) — per-file and total, no rendering needed.
find "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile assets.root)" -type f -name "*.webp" -exec du -k {} \; | sort -rn
du -sk "$(python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" --profile assets.root)" 2>/dev/null
```

**`manifest.local.json` (if present) is a gitignored WIP overlay — see `{{doc:assets}}` §6.** Its entries are explicitly OUT OF SCOPE for this audit's compliance checks (they're expected to have empty `slots` — that's the point of the overlay). Read it only to note its presence and asset count in your report (so "why isn't `prescription_v2` showing up" isn't a mystery), not to run checks A–H against its entries.

**Licensing/compliance is out of scope for this audit** — it's handled outside the asset pipeline entirely, not something this skill checks or gates on.

## Step 2 — Run every check

For each `manifest.json` asset (ignore ids prefixed `example_`, and ignore anything only present via `manifest.local.json`):

| # | Check | Severity if failed |
|---|---|---|
| A | Source `.blend` exists at `sources/<source or id>/<...>.blend` | 🔴 Critical |
| B | Every **committed** `.blend` is an LFS pointer (in `git lfs ls-files`; blob size < 1 KB) — a multi-MB git blob means LFS was bypassed | 🔴 Critical |
| C | Every slot: `dp × 3 ≤ render.masterPx` | 🟡 Should fix — upscaled 3x output |
| D | Every slot has synced files in the project's asset root (`assets.root`) (`<name>.webp` + `2.0x/` + `3.0x/`) | 🟡 Should fix — stale sync |
| E | Every file in the project's asset root (`assets.root`) (except `.gitkeep`) traces back to some manifest slot | 🔴 Critical — hand-placed or orphaned image |
| F | Slot names unique across all assets | 🔴 Critical — sync collision |
| G | `palette.json` matches a fresh export — the `export_palette.py --check` result from Step 1 (exit 1 = stale; exit 2 = could not compare, report G as not run, never clean) | 🟡 Should fix — stale palette; library may not match `AppTokens` |
| H | `renders/` or `outputs/` files tracked by git | 🟡 Should fix — gitignore bypassed |

**Docs-consistency checks (whole-doc, not per-asset)** — added after this audit itself found three stale claims and a footer stuck ~10 days behind real changes, all by luck rather than process:

| # | Check | Severity if failed |
|---|---|---|
| I | `{{doc:assets}}` and `{{doc:decisions}}` footer `_Last updated:` date is not older than that file's last real git commit date (`git log -1 --format=%cs -- <file>`) | 🟡 Should fix — stale footer, easy to miss by eye in a long file |
| J | No duplicate `### ` heading text within `{{doc:decisions}}` (`uniq -d` on the sorted heading list) — a real risk when appending a new dated entry near an existing one with a similar title | 🔴 Critical — usually means a bad append/merge, not just a doc nit |
| K | No skill file (the installed skill files) contains a stale "not built"/"is not built"/"isn't built" claim about a capability that has since shipped — cross-check each hit against what's actually implemented (e.g. grep the referenced script/field in `${CLAUDE_PLUGIN_ROOT}/design_suite/engine/assets/`) rather than assuming the claim is still true | 🟡 Should fix — a stale claim actively misleads whoever reads the skill next, unlike most doc drift which is just out of date |

**Icon/illustration consistency + size monitoring** — formalizes two things that were previously only checked per-asset, ad hoc (e.g. `/add-asset` Step 8's one-off "warn if 3x exceeds ~100KB"), into a standing repo-wide pass. (The orphan-file half of "orphan sweep" is already covered by check E above — every the project's asset root (`assets.root`) file must trace to a manifest slot; these two checks are the icon-consistency and size-monitoring half.)

| # | Check | Severity if failed |
|---|---|---|
| L | Cross-icon style/size consistency — for `generator.kind: "shapes"` assets in particular (multiple icons meant to read as one family), do the `render.masterPx` values and overall visual weight/scale match across the set? Flag an outlier that would look mismatched sitting next to its siblings in the UI | 🔵 FYI — a design judgment call, not a hard rule; describe the mismatch, don't assume which one is "wrong" |
| M | Repo-wide asset size report — total the project's asset root (`assets.root`) size, and any individual `.webp` (especially a `3.0x/` variant) that's unusually large relative to the rest of the set | 🟡 Should fix if a single file is a clear outlier (formalizes the existing "~100KB" per-asset warning into a standing check, not just something caught the one time an asset happens to get added) |

## Step 3 — Report

Use the `/review-docs` report format: 🔴 Critical / 🟡 Should Fix / 🔵 FYI sections (omit empty ones), one specific finding per bullet, then a summary count line. List anything mechanically fixable (e.g. re-running sync, regenerating the palette) under **Auto-fixable** and apply only on explicit confirmation.

---

## What you must never do

- Modify the manifest, sources, or the project's asset root (`assets.root`) without confirmation
- "Fix" a plain-blob `.blend` yourself — history rewriting is the user's call; report it loudly instead
