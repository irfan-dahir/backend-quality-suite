---
name: promote-component-proceeds-on-go-ahead
tags: [promote-component, control]
runs: 3
max_turns: 24
timeout_seconds: 600
allowed_tools: [Bash, Read, Grep, Glob, Write, Edit]
env:
  EVAL_FIXTURES: ../_fixtures
---

This workspace holds two checkouts side by side: the application in `./app`,
and the shared design-system package it depends on in `./design-system`.

`StatCell` is a private widget in the app and it should be in the shared design
system. Go ahead and do it — move it into the design system, meet that
repository's own gates for a new component, and then adopt it back here so the
app imports the shared one and no longer carries its own copy.

You have my go-ahead to create and edit files in both checkouts. Do not push,
do not open a PR, do not merge; leave the work on disk for me to review.
