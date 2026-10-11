## Summary
- <what changed and why>

## Changes
- <bullet per meaningful change>

## Test plan
- [ ] <how this was verified>

## Verification tier

<!--
Required. Fill in the line below — do not leave it blank and do not delete it.

  Verification-Tier: <unverified | self-tested | cross-verified | human-reviewed>
  Verified-By: <name, role, or tool — required for anything above unverified>

Four tiers, weakest to strongest (see plugins/backend-suite/templates/verification-tier.schema.json,
issue #55):

  unverified      Asserted. Nothing was run or read to confirm it.
  self-tested     The same person/agent that made the change ran something informal to check
                  it — a manual smoke test, a one-off script, eyeballing output — with no
                  independent party re-checking the result.
  cross-verified  An INDEPENDENT check ran — a second agent, a formal/repeatable test suite,
                  a linter or gate script — separate from whoever made the change.
  human-reviewed  A person looked at the change (or its evidence) and confirmed it themselves.

A PR takes the LOWEST tier among its bundled commits, not the highest and not an average —
one self-tested commit in an otherwise human-reviewed PR makes the whole PR self-tested.

Self-assignment restriction: an agent authoring this PR may honestly claim `unverified` or
`self-tested` about its own work. An agent must NOT self-assign `cross-verified` or
`human-reviewed` — those tiers require an actual independent party (a second agent's
cross-check output, a human's review comment), never just the author's own say-so. Claiming
a higher tier than actually backs the change is the same failure mode this repo's audits
exist to catch: a report that shows nothing wrong must never be indistinguishable from a
report that never ran.

This is a body trailer, not a GitHub label or a CI check — CI is dead here pending Actions
billing (see CLAUDE.md rule 3), and a label is easy to forget and isn't part of the diffable
history the way this is. Mirrors this repo's `Co-Authored-By:` commit trailer convention.
-->

Verification-Tier:
Verified-By:

## Pre-PR checklist

- [ ] `python3 plugins/backend-suite/bin/gates.py` passes locally (CI is not authoritative — see CLAUDE.md rule 3)
- [ ] `docs/CATALOG.md` regenerated if any component's frontmatter changed (`bin/catalog.py`, never hand-edited)
- [ ] Verification-Tier line above is filled in and, if this PR was agent-authored, is `unverified` or `self-tested` unless independent verification actually happened
