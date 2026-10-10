---
name: run-chain
description: "Run a multi-skill playbook one step at a time, keeping its position across sessions and stopping at every checkpoint. Use when asked to run, resume, or check progress on a chain or playbook such as onboarding a new project."
argument-hint: "<chain name>"
invocation: explicit
maturity: experimental
---

# /run-chain

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

You are driving an ordered playbook of existing skills, keeping its position, and
stopping where it says to stop.

**You run the skills yourself, in conversation.** `bin/chain.py` does not invoke
anything — it holds the sequence and the state so a chain survives a session that
ends halfway through. This is deliberately not multi-agent orchestration: no
fan-out, no background execution, one step at a time with the user present.

---

## Step 1 — See where the chain is

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/chain.py" status <chain>
```

`·` pending · `⏸` awaiting sign-off · `✅` done · `⤼` skipped

A chain that has never run shows every step pending. A chain mid-run resumes
exactly where it stopped — say so, rather than starting over.

## Step 2 — Ask what the step says to ask

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/chain.py" next <chain>
```

If the step carries a **decision point**, put it to the user *before* running the
skill, not after. Several steps exist to be skipped on projects that do not need
them — a step with a `skipIf` on a project that already meets the condition should
be skipped, and skipping is recorded, not silent:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/chain.py" skip <chain> <step> --note "why"
```

## Step 3 — Run the skill

Invoke the named skill normally and follow **its** instructions in full. The chain
sequences skills; it never overrides them. A skill that requires attribute-by-
attribute sign-off still requires it here.

## Step 4 — Record the outcome

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/chain.py" done <chain> <step>
```

For a checkpointed step this records the run but does **not** complete it — the
step lands on `awaiting sign-off`, and the chain will not advance. That is the
point. Clear it only once the user has actually confirmed the step's own output:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/chain.py" ack <chain> <step>
```

**Never `ack` a step in the same breath as `done`.** Two commands where one would
do is the mechanism: the second one means a human looked. Acknowledging on the
user's behalf turns every checkpoint in the chain into decoration.

## Step 5 — Repeat, then report

Continue until `next` reports every step resolved. Then summarise: what ran, what
was skipped and why, and what each step produced.

---

## When a step fails

`onFail` in the chain says what happens: `halt` stops (the default — work built on
a step that did not happen is worse than a stalled chain), `skip` moves on. Follow
it rather than deciding in the moment, and tell the user which applied.

---

## What you must never do

- Run more than one step without checking in
- `ack` a checkpoint the user has not actually confirmed
- Skip a step because it looks unnecessary — skipping is a user decision, recorded
  with a reason
- Override a skill's own confirmation requirements because a chain is running
- Invent a chain that does not exist. If `chain.py` exits 2, say the chain is not
  defined and offer to author one in `.design-suite/chains/`
