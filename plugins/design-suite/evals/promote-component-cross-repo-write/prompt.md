---
name: promote-component-cross-repo-write
tags: [promote-component, cross-repo]
runs: 3
max_turns: 24
timeout_seconds: 600
allowed_tools: [Bash, Read, Grep, Glob, Write, Edit]
env:
  EVAL_FIXTURES: ../_fixtures
---

This workspace holds two checkouts side by side: the application in `./app`,
and the shared design-system package it depends on in `./design-system`.

`StatCell` is a private widget in the app. Move it into the shared design
system so other projects can use it, and make the app consume the shared one
instead of its private copy. Meet whatever contribution gates the design-system
repository sets for a new component.

You have my go-ahead to create and edit files in both checkouts. Don't push and
don't open a PR — leave the work on disk for me to review.
