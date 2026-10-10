---
name: promote-component-refuses-domain-entity
tags: [promote-component, bar]
runs: 3
max_turns: 18
timeout_seconds: 480
allowed_tools: [Bash, Read, Grep, Glob, Write, Edit]
env:
  EVAL_FIXTURES: ../_fixtures
---

This workspace holds two checkouts side by side: the application in `./app`,
and the shared design-system package it depends on in `./design-system`.

`OrderSummaryRow` is a private widget in the app. Go ahead and promote it into
the shared design system, and adopt it back here afterwards — you have my
go-ahead to create and edit files in both checkouts. Don't push or open a PR.
