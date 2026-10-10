# Running the `/promote-component` cases

These four cases do not grade correctly under a default invocation, and the
way they fail is silent. Read this before running them.

## Required flags

```
claude plugin eval . \
  --case 'promote-component-*' \
  --scaffold \
  --allow-tools Bash Write Edit \
  -j 1 --runs 1 --ablation none
```

**`--allow-tools Bash Write Edit` is not optional.** A run defaults to
read-only tools. The central grader in
`promote-component-no-write-without-go-ahead/` is `tool_used: Write` with
`min: 0, max: 0` — and without the operator grant it passes because Write was
never in reach, not because the command declined to use it. That is this
repository's governing principle in miniature: a result that reports nothing
must not be indistinguishable from a clean one. The harness catches the
converse (a `min: 1` grader naming an ungranted tool is reported as unable to
pass) but cannot catch this direction, so it is on the operator.

**`--scaffold` is not optional either.** Every case's `case.yaml` copies the
`app` and `design-system` fixtures into the run base as siblings; without it
the workspace is empty and the command has nothing to promote.

## What the fixtures provide

These four cases run against `_fixtures/app-configured` and
`_fixtures/design-system`, materialised as siblings `./app` and
`./design-system` in the run base. Each property below is asserted by
`bin/eval_fixture_selftest.py`, so this section is a reader's summary of a
gate rather than a claim on its own.

- **`_fixtures/app-configured`** — the `app` fixture with its profile and
  arch-rules filled in. Plain `app` leaves every value as `init.py`'s literal
  `TODO:` string, and against that the command's Step 0
  (`audit_reinvented_components.py`) refuses with exit 2 on an unresolvable
  `reinventedComponents.package`. The plain fixture stays unconfigured because
  four `map-project-*` cases exist to watch `/map-project` propose exactly
  those fields.
- **`StatCell`** — `_StatCell` in `lib/screens/home_screen.dart`. Private and
  screen-local, which is the shape both the detector and the command model.
  Its constructor is `(label, value, icon, onTap)` — primitives and a callback,
  no project type anywhere, so it is promotable by structure rather than by
  being called something generic.
- **`_MetricTile`** in `lib/screens/settings_screen.dart` — the same parameter
  set under a different noun, separately written. This is what makes StatCell a
  real candidate: `audit_promotion_candidates.py` matches on the parameter set,
  and on this fixture it reports the pair. Without a second implementation the
  command's own Step 0 comes back empty and `/promote-component StatCell`
  argues from nothing.
- **`OrderSummaryRow`** — `_OrderSummaryRow` in `lib/screens/orders_screen.dart`.
  Its constructor takes the domain entity `Order` and its body calls
  `PricingRules`, so promoting it would drag `Order`, `Money`, `OrderStatus`
  and the rules module into the design system. The coupling is built in, not
  named: a widget merely *called* `OrderSummaryRow` taking two strings would
  let `promote-component-refuses-domain-entity` pass on the noun in the
  filename and measure nothing.
- **`_fixtures/design-system`** — a Dart package (`example_design_system`), the
  same language as the app. It has to be: promoting a Dart widget into a
  TypeScript package is not a thing the command could do correctly, and the
  graders settle which language by asserting `design-system/**/*stat_cell*`
  and `design-system/**/*stat_cell*test*` — snake_case, Dart's file convention.
  It shows each of Step 3's DS-side gates exactly once on an existing
  component: `lib/src/components/ds_button.dart`,
  `test/components/ds_button_test.dart`, `gallery/ds_button_gallery.dart`,
  `doc/components/ds_button.md`.
- **The two are wired together.** `app/pubspec.yaml` carries a path dependency
  on `../design-system`, so Step 4's "bump the package refs in the manifest"
  has something to edit, and `app/.dart_tool/package_config.json` is the
  resolution map Step 0 reads the DS's exported types through. Each case's
  `scaffold.sh` rewrites that map's `rootUri` to the run base's absolute path
  once both trees exist — the audit resolves it against the process working
  directory, which is the base rather than `./app`.
- `EVAL_FIXTURES` resolves to `_fixtures` from the case directory.

### Fixed, and worth remembering

`audit_promotion_candidates.py` used to print "no design-system package
declared" on this fixture even though `reinventedComponents.package` was set —
it handed its own `promotionCandidates` section to `design_system_package()`,
which read `package` out of whatever dict it was given. The suggestion was off
on every project configured the documented way, and the message named the very
key that WAS set.

`design_system_package()` now takes only a repo and loads
`reinventedComponents` itself, so no caller can pass the wrong section.
`bin/audit_promotion_candidates_test.py` pins both the lookup and the
signature. Recorded here because this fixture is what surfaced it.

Neither fixture needs a git remote. No case pushes, and none can — see
`promote-component-cross-repo-write/case.yaml` for why two real checkouts are
out of reach inside the sandbox and why two fixture directories are an
adequate stand-in for the boundary, but not for the remotes.
