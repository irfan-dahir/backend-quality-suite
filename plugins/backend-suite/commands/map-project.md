---
name: map-project
description: "Propose the mappings a survey cannot: which document is really the API doc, which project kind this is (service or library), which candidate document source is the true one — each with the reasoning it was argued from. Every value it proposes is written with provenance `inferred` and nothing else, so no downstream check trusts it until a human ratifies. Proposes and argues; never decides."
invocation: explicit
maturity: unverified
---

# /map-project

> Documents are referenced by role, e.g. `{{doc:api}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" api`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

The judgement half of discovery (RFC-0002 §3b-ii). `bin/survey.py` is the
mechanical half: it reads the disk and states facts. This skill reads the survey
*and the candidate documents themselves* and **argues** for a mapping — "four
files could be `{{doc:api}}`; this one, because it carries the endpoint
inventory the other three reference."

A regex over filenames scored 4 confident of 20 on a real zero-state repository.
The remaining ambiguity is semantic, and semantics is what a skill is for. But a
skill's output is **argument, not proof**, so:

**Everything this skill proposes is written with provenance `inferred`. Always,
without exception.** Not `declared`, not `approved` — those two states mean a
human decided, and you are not a human. `doctor.py` exists to report `inferred`
fields as UNTRUSTED precisely so that your guesses land somewhere that already
refuses to trust them. A skill that writes `approved` defeats the entire
provenance design, and the profile then looks reviewed when nobody reviewed it.

You propose. A human ratifies. Those are different jobs and this skill only does
the first one.

---

## Step 0 — Preconditions, and the refusals

0. **A project must already be scaffolded.** If there is no `.backend-suite/`
   directory, stop. Every `bin/*.py` exits 2 here — `project_root()` prints
   "Refusing to guess" — and that refusal is correct, not an obstacle to route
   around. You are being asked to map a project nobody has onboarded yet, and
   mapping is not onboarding.

   ```bash
   test -d .backend-suite || echo "no .backend-suite/ — this is onboarding, not mapping"
   ```

   Refuse; say plainly that nothing was written and nothing could be; name
   `bin/init.py` (or `/onboard-new-client`) as the step that has to happen
   first. **Do not create `.backend-suite/profile.json` yourself** just to have
   somewhere to write. A profile this skill invented is not a scaffolded
   project, and it converts a visible gap into a file that reads like one.

1. **A survey must exist and be current.** If `.backend-suite/survey.json` is
   absent, run `/survey` first — do not map from your own reading of the tree.
   The survey is the reproducible half and it is what your proposals are
   accountable to.

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/survey.py"
   ```

2. **If the survey's `sourceStamp.commit` is not the commit you are on, re-run
   it.** Mapping a stale inventory proposes roles for files that may have moved.

3. **Confirm you are on a feature branch.** This skill edits
   `.backend-suite/profile.json`.

4. **Read `couldNotDetermine` before anything else.** Every entry in it is a
   question the script refused to answer. Some you can answer with reasoning and
   evidence; some you cannot, and those stay refusals — see Step 5.

## Step 1 — Read the survey as a brief, not as answers

Three of its fields are deliberately hedged, and you inherit the hedge:

- **`stack.fileCensus` never votes.** A committed documentation build makes a
  census read a Dart repository as JavaScript. If the manifests did not decide
  the stack, the census does not get to.
- **`candidateTokenSources` is ranked and plural** — and on both real consumer
  projects measured for RFC-0002 the true token source **is not in the repository
  at all**; it arrives as a package dependency. "Not present on disk" is a live
  possibility here, not an edge case.
- **`documents[].proposedRole` is already `inferred` and confidence-scored.** A
  filename match is a prior, not a conclusion. Your job is to confirm, overturn,
  or refuse it — with a reason either way, including when you agree.

## Step 2 — Argue each mapping from the documents' contents

For every role the archetype expects, and for every document the survey left
unmapped, **open the candidates and read them.** The argument must rest on what
a document contains, not on what it is called.

Evidence that counts, roughly in order of strength:

1. **What the document is the source of truth for.** The `design` doc is the one
   other documents cite for tokens and the screen inventory, not the one with
   "design" in its name.
2. **Inbound references.** A document three others link to as authoritative is
   doing the role's job; a document nothing references may be a historical copy.
3. **Structure.** A route table, a component catalogue, a dated append-only list
   — roles have shapes.
4. **Recency and churn.** Of two plausible candidates, the one nobody has
   touched in two years is likely superseded. Weak on its own; decisive as a
   tiebreak between two otherwise-equal candidates.
5. **The filename.** Last, and never alone.

Write the argument down as you go: it becomes the `evidence` string on the
provenance entry, and it is the thing a human actually reviews when ratifying.
An entry whose evidence reads "filename matches" has proposed nothing a script
could not have proposed, and should usually have been a refusal instead.

Check the vocabulary before proposing a role that may not exist:

```bash
python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from backend_suite.engine import archetypes; print(', '.join(sorted(archetypes.roles())))"
```

A document that maps to **no** role is reported as unmapped, never dropped. RFC-0002
§3d measured one missing role (`components`) accounting for 83% of the mapping gap
on a real repository: "no role fits" is frequently a finding about the vocabulary,
not about the document. Propose the new role to the suite; do not quietly file the
document under a role that nearly fits.

## Step 3 — `projectKind` is the highest-stakes proposal you make

A wrong archetype misroutes every downstream audit, and guessing `app` for a
package is what makes a scaffolder emit an empty flows document — the exact
"clean vs. couldn't look" ambiguity the governing principle forbids.

```bash
python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from backend_suite.engine import archetypes; print(', '.join(archetypes.kinds()))"
```

Propose one **of that list only**, with your reasoning, as `inferred`. If the
evidence is genuinely split — a repository that publishes a package *and* ships
an app — say so and propose nothing; that is a `workspace`, an orthogonal axis,
and the human decides how to describe it. **An unknown or unsupported kind is a
refusal, never a default to `app`.**

Until a human ratifies `projectKind`, say plainly in your report that nothing
archetype-scoped should be run: the kind selects which roles are expected and
which audits apply at all, so running on an unratified kind is running on a guess.

## Step 4 — Write the proposals, with `bin/map_project.py`

**This step writes to disk, and you do not write it by hand.** Proposing in chat
and stopping is not this step: the `inferred` states must actually land in
`.backend-suite/profile.json`, because that file is where `doctor.py` reads them
and reports them UNTRUSTED, and an unwritten proposal is outside the provenance
chain entirely. This was measured — the skill fired, argued well, and wrote
nothing, because the write was described in this document and this document was
the whole mechanism.

So the persistence is a script and the rules below are enforced by it, not by
your compliance with them:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/map_project.py" \
  --field docs.roles.design \
  --value docs/DESIGN.md \
  --evidence "Four candidates. This one is the only file the other three cite for the token tables, and it carries the screen inventory they reference by section number."
```

Several at once — which is the normal case, and is all-or-nothing, so a refused
proposal never leaves a half-written mapping behind:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/map_project.py" --proposals /tmp/proposals.json
```

where the file is a list of `{"field", "value", "evidence"}` objects, each
optionally carrying `"candidates"` — every value that was genuinely in
contention. Useful flags: `--dry-run` runs every refusal and prints what would
be written without writing it, `--list` shows what has already been proposed,
`--candidate` names a contender on the single-field form, and `--dir` /
`--profile` point at a project or a profile other than the detected ones.

The field is a **dotted path** (`source.root`, `tokens.source.path`,
`project.projectKind`, `docs.roles.design`) — the same paths `doctor.py`
enumerates as profile leaves. The script writes the value at that leaf and one
entry under `provenance.fields` keyed by the same path:

```json
"provenance": {
  "fields": {
    "docs.roles.design": {
      "state": "inferred",
      "evidence": "Four candidates. This one is the only file the other three cite for the token tables, and it carries the screen inventory they reference by section number."
    }
  }
}
```

`state: "inferred"` and `evidence` are the whole of the entry — it is built from
a whitelist and the serialised file is re-checked before it is written.

**What the script refuses, so that it is not left to prose:**

| It refuses | Because |
|---|---|
| `state`, `by`, `on` or `verifiedAgainst` on a proposal | Each asserts a human decided. Refused, not stripped — a key silently ignored reads as a key accepted |
| A `value` key on the entry | `value` is the human's: it is what lets `doctor.py` compute CONTRADICTED when a ratified value is edited later. Pre-filling it from a guess lets the guess masquerade as a ratification that has drifted |
| Missing evidence, or bare filename matching | An entry whose evidence reads "filename matches" proposed nothing a script could not have, and should usually have been a refusal instead |
| A field already `declared` or `approved` | Someone decided that already. Exit 2, nothing written. Report the disagreement and your evidence; do not downgrade a human's decision to your own inference |
| Two candidates still in contention | A plausible default is worse than a gap. Refuse and say what evidence would settle it |
| No proposals at all | Exit 2, never 0. "Nothing could be mapped" and "everything mapped cleanly" must never print the same verdict |
| A field under a top-level section the profile does not have | A field invented here is one `doctor.py` reports as real |

Exit 0 every proposal landed, 1 findings, 2 refused, 3 the answer lives in
another repository, 4 the role is declined, 5 the role is a registered stub. A
non-zero exit is the script doing its job; read the refusal, fix the proposal or
move the field to your Step 5 refusal list, and do not route around it by
editing the profile yourself.

## Step 5 — Where you cannot tell, say so and stop

This is the governing principle, and it outranks being useful. An unresolvable
mapping is a `CapabilityError`-shaped outcome: **refuse, name what you needed,
and leave the field absent.** A plausible default is worse than a gap, because a
gap is visible and a plausible default reads as a decision.

Refuse — do not propose — when:

- two candidates are genuinely equal on evidence and only the filename separates them;
- the role's true owner looks like another repository (that is a `docs.manifest.json`
  `external` entry and exit 3, not a path here);
- the survey put the field in `couldNotDetermine` and you found nothing it did not;
- the true value appears not to be in this repository at all (the token-source case);
- no role in the vocabulary fits, and the honest answer is that the vocabulary is short one.

Collect every refusal in one list in your report, each with **what evidence would
settle it** — "which of these two is authoritative?" is a question a human answers
in ten seconds and a model cannot answer at all.

An empty refusal list on a real unknown project is itself suspicious. A survey
that determined everything and a survey that never ran produce the same short
file; the same is true of this skill.

## Step 6 — Prove nothing you wrote is trusted

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/doctor.py"
```

Every field you proposed must appear in the **UNTRUSTED** list, and the
ratified-of-total count must be unchanged from before you ran. If a field you
wrote is absent from that list, you wrote a trusted state — fix it before
reporting anything else. Paste the provenance section of the output into your
report verbatim; do not summarise it.

`doctor.py` exits non-zero on contradictions, not on untrusted fields — untrusted
is the expected state of your output, not a failure of it.

## Step 7 — Hand over the ratification

State explicitly, in your report, what changes when the human accepts — because
it is not a formality and it is not something you can do for them:

- `state` moves from `inferred` to **`approved`** (or `declared`, if they replace
  your value with their own rather than accepting it);
- `by` and `on` record **who** decided and when, so the decision can be
  re-examined later rather than inherited forever;
- `verifiedAgainst.commit` is stamped with the tree it was confirmed against —
  staleness is then measured in diffs ("verified against a tree 339 commits ago"),
  never in days;
- optionally `value` is recorded, which is what lets `doctor.py` later compute
  **CONTRADICTED** if the field is edited after ratification.

Present the proposals **one at a time, each with its argument**, and take a
per-field answer. A single "looks good" over twenty fields is not twenty
ratifications; it is one skim wearing twenty decisions' clothes.

Nothing archetype-scoped runs until `projectKind` is ratified. Say so last, so it
is the line the reader leaves with.

---

## What you must never do

- Write `approved` or `declared` for anything, under any circumstance, including
  when the user says "yes, that's right" in chat — a ratification is a recorded
  decision with an author and a commit stamp, and recording it is theirs.
- Fill in `by`, `on`, `value`, or `verifiedAgainst` on a field you proposed.
- Hand-edit `.backend-suite/profile.json` to record a proposal, or route around
  a `map_project.py` refusal by writing the entry yourself. The script is the
  mechanism precisely because this document was not one.
- Emit a plausible default for something you could not determine, or narrow a
  ranked candidate list to a single value because one field wants one value.
- Overwrite or downgrade a field that already carries a human's `declared` or
  `approved` state.
- Write your conclusions into `survey.json` — it is a derived collateral and the
  write-back direction is the one rule it has.
- Present an argument as a finding. "This is the design doc" is wrong; "this is
  the strongest candidate, because …, and it is not ratified" is right.
- Claim this skill has been verified against a real unknown project until it has.

## The adjacent seeder: `init.py --from-survey`

`bin/init.py --from-survey` exists — RFC-0002 §3b's **generate** step, the
scaffolder named there. It seeds `.backend-suite/profile.json` from
`bin/survey.py`'s findings instead of leaving those particular fields as TODOs,
and it writes the `provenance` block for them:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/init.py" --from-survey [--survey path/to/survey.json]
```

`--survey` implies `--from-survey` and defaults to `.backend-suite/survey.json`,
generating it if absent.

It is **not** a substitute for Step 4 and does not overlap it: it seeds the
fields a *survey* settled mechanically, before this skill runs, whereas Step 4
records the mappings only reading the documents could settle. Run it first if the
profile is still full of TODOs; then map. It holds the same two rules
`map_project.py` does:

- **Every seeded field is written `inferred`** — never `declared`, never
  `approved`. A survey found it; no human decided it.
- **A field the survey could not determine stays an explicit TODO.** No
  plausible default. (`tokens.source` is deliberately outside the seed table for
  that reason — it is the worst-measured signal in the suite.)

The `inferred`-only rule is the same on both sides of that boundary. What does
**not** change hands:
review is `doctor.py`, which reports every seeded field as untrusted and prints
the ratified-of-total count; **commit is the human's**; drift is `survey.py
--check` and doctor's contradiction check. Seeded is not ratified — say so, and
never present a generated profile as a set of decisions.
