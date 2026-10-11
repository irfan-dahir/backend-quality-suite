---
name: audit-toolchain-gates
description: "Report-only audit for the project's own test toolchain — required scripts absent from the manifest, scripts pointing at undeclared runner suites, and suites whose directory no longer exists (running zero tests while exiting green). Use when asked whether the test command actually runs tests, after renaming a testsuite or moving a test directory."
invocation: auto
maturity: unverified
---

# /audit-toolchain-gates

> Needs a `toolchainGates` section in the architecture rules
> (`manifestGlob`, `runnerGlob`, `requiredScripts`, `testsuiteFlag`).
> Manifest and runner are parsed as JSON and XML — a refusal to parse is
> a refusal to guess.

## What it does

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/audit_toolchain_gates.py"
```

The project's test command and its runner configuration are two documents
that must agree. The quietest failure in any toolchain is a suite pointing
at a directory that no longer exists: the runner executes zero tests and
exits green, and the CI badge stays honest-looking forever.

## Reading the output

- `missing_required_script` — the manifest declares no `test` (or
  whatever `requiredScripts` names). Tests exist but the toolchain never
  says how to run them; the knowledge lives in prose, which drifts.
- `script_testsuite_undefined` — a script references a suite the runner
  does not declare: the command is broken as written.
- `testsuite_directory_missing` — critical: the suite runs zero tests and
  exits green. Point it at the real directory or remove the suite.

## What you must never do

- Add a `test` script that shells out to something unverified just to
  clear the finding; the script must run the suite it names
