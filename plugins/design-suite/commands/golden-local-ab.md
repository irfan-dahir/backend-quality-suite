---
name: golden-local-ab
description: "Prove a refactor changed no pixels by rendering the golden corpus on this machine before and after and comparing the two byte-for-byte. Use before and after any large mechanical change whose claim is that it changed no rendering — an extraction, an import rewrite, a token migration."
invocation: explicit
maturity: proven
---

# /golden-local-ab

You run a before/after comparison the committed corpus cannot give you, because the committed images were rendered on whatever platform CI uses and you are not on it.

**This is a two-call skill and the first call must happen before the change.** If the user asks for it *after* already making the change, say so plainly — there is no baseline to compare against and no way to reconstruct one from a dirty tree. Offer to stash the change, snapshot, and unstash.

---

## Step 0 — Preconditions

`${CLAUDE_PLUGIN_ROOT}/bin/golden_local_ab.py` is stdlib-only Python, but it *runs the project's own test command*, so the toolchain has to be working. A project that configures no corpus does not have this tool available, which is correct rather than a gap.

## Step 1 — Before touching anything

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/golden_local_ab.py" snapshot
```

Confirm the image count it reports looks right. A baseline of 0 images is a misconfigured corpus, not a small one.

## Step 2 — Make the change

Whatever the refactor is. The corpus is not touched by this skill in between — the committed images are stashed and restored around every run, including when a render fails, so the working tree never ends up holding locally-rendered goldens.

## Step 3 — After

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/golden_local_ab.py" check
```

**0 differing, 0 added, 0 removed is the only passing result for a pure refactor.** A byte match is a stronger claim than a tolerance match, and it is available here precisely because both sides were rendered on one machine.

## Step 4 — Report

State the number of images compared and the result. If anything differs:

- Name every differing image. Do not summarise as a count — the reader needs to know *which* screens moved
- Do not regenerate the committed corpus to make the difference go away. A differing image on a refactor that claimed to change nothing is the finding, and burying it defeats the entire exercise
- Added or removed images mean the corpus itself changed shape, which a refactor should not do

---

## What you must never do

- Run `check` without a `snapshot` from before the change and present the result as meaningful
- Update the committed goldens as a way of resolving a difference
- Report a passing byte-comparison as proof the change is correct — it proves only that rendering did not move, which is exactly and only what it claims
