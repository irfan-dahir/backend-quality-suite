---
name: scaffold-screen
description: "Generate a new screen pre-wired with the three standard states — loading, error, content — using the components the project has already standardized on. Use when asked to build or scaffold a screen."
argument-hint: "<screen name>"
invocation: auto
maturity: unverified
---

# /scaffold-screen

> Documents are referenced by role, e.g. `{{doc:instructions}}` — resolve with
> `python3 "${CLAUDE_PLUGIN_ROOT}/bin/resolve.py" instructions`. See `${CLAUDE_PLUGIN_ROOT}/docs/DOC-ROLES.md`.
>
> **Exit 4 — declined:** the project has recorded that it has no such document,
> and `resolve.py` prints the reason on stdout. Skip the check that needed it and
> name the role, that reason, and the decline in your report. Declined is not
> passed.
>
> **Exit 5 — stub:** the path is printed, but the document is registered and
> unwritten. Name it and report what needed it as outstanding work — never read a
> stub's empty content as nothing to flag.

You generate a new screen file pre-wired with the three standard states (loading, error, content) using the components this repo has already standardized on — instead of the loading/error/empty handling being invented fresh (and inconsistently) for every new screen. This is the single most repetitive part of building a new screen; this skill exists to remove that repetition, not to replace the design/product thinking about what the screen actually shows.

**You scaffold structure; you never invent the screen's actual content/business logic.** Reference: `{{doc:instructions}}` §3 (Adapter Pattern) and §"Screen Contract Header", `{{doc:contributing}}` (component lookup table).

---

## Step 0 — Preconditions

Ask (if not already given):
- Screen name (e.g. `SupplementHistoryScreen`) and its feature directory (`<source.root>/<feature>/presentation/pages/`).
- What data it needs (its adapter's `// INPUTS`) and what events it emits (`// OUTPUTS`) — at minimum `isLoading` and `errorMessage` inputs, since every screen needs the loading/error states this skill wires up.
- Which skeleton shape fits the content best — read the skeleton primitives in `<source.sharedComponentDir>` for the existing set (`SkeletonProviderCard`, `SkeletonProfileRowCard`, `SkeletonChipRow`/`SkeletonChipWrap`, `SkeletonField`, `SkeletonProgressBar`, `SkeletonChart`, `SkeletonRing`, etc.) — reuse one of these rather than inventing a new skeleton shape unless nothing fits.

## Step 1 — Generate the adapter

Following `{{doc:instructions}}` §3's Adapter Pattern exactly: a plain, `const`-constructable Dart class with `// INPUTS` and `// OUTPUTS` sections, at minimum:

```dart
class <ScreenName>Adapter {
  // INPUTS
  final bool isLoading;
  final String? errorMessage;
  // ...screen-specific fields...

  // OUTPUTS
  final VoidCallback onRefresh;
  // ...screen-specific callbacks...

  const <ScreenName>Adapter({
    required this.isLoading,
    required this.onRefresh,
    this.errorMessage,
    // ...
  });
}
```

## Step 2 — Generate the screen with all three states wired

Use the exact reusable pieces already in the codebase — do not reinvent loading/error handling:

- **Loading ↔ content transition:** `MinDurationLoadingSwitcher` (from `<source.sharedComponentDir>`) — `isLoading: adapter.isLoading`, `skeleton: <the chosen skeleton primitive>`, `child: <the real content or the error view>`.
- **Error state:** a private `_ErrorView` matching the established pattern (see `health_hub_screen.dart`'s `_ErrorView` for the canonical shape — centered icon + title + message, `AppTokens.colorError`/`space*` tokens, no hardcoded values).
- **Empty state:** ask what "no data yet" should say for this specific screen — don't invent generic copy; if the feature has a brand-voice doc available (`{{doc:brand-voice}}`, on branches where the copy skills have landed), draft it consistent with that voice, otherwise keep it plain and match the tone of nearby screens.

Structure:

```dart
/*
==============================================================================
<SCREEN NAME> CONTRACT
==============================================================================

PURPOSE:
[one sentence — ask the user if not obvious from context]

RULES:
1. Do not fetch data.
2. Do not call repositories.
3. Do not call APIs.
4. Do not access Bloc directly.
5. Do not modify the adapter interface.
6. UI changes are allowed.

INPUT:
- adapter.isLoading
- adapter.errorMessage
[- ...screen-specific...]

OUTPUT:
- adapter.onRefresh()
[- ...screen-specific...]

==============================================================================
*/

class <ScreenName> extends StatelessWidget {
  final <ScreenName>Adapter adapter;
  const <ScreenName>({super.key, required this.adapter});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: MinDurationLoadingSwitcher(
          isLoading: adapter.isLoading,
          skeleton: const <ChosenSkeletonPrimitive>(),
          child: adapter.errorMessage != null
              ? _ErrorView(message: adapter.errorMessage!)
              : <the real content, or an empty-state widget if no data>,
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  const _ErrorView({required this.message});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppTokens.space32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 48, color: AppTokens.colorError),
            const SizedBox(height: AppTokens.space16),
            Text('Something went wrong', style: theme.textTheme.titleMedium),
            const SizedBox(height: AppTokens.space8),
            Text(
              message,
              style: theme.textTheme.bodyMedium?.copyWith(color: AppTokens.colorOnSurfaceVariant),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
```

## Step 3 — Queue doc updates, register, and hand off

- Do **not** wire the route yourself unless asked — flag that `app_router.dart`/the feature's route file needs a new entry, and let the user decide the route path.
- Do **not** add this to `{{doc:design}}`'s Screen Inventory yourself — that's `/sync-docs`'s job, and the screen isn't real until its actual content is filled in. Instead, **draft the row** (status `🚧 Placeholder` — it isn't real content yet) and, if the screen introduces a new flow/route, a one-line `{{doc:flows}}` note — present both to the user to apply via `/sync-docs` when they're ready, rather than leaving "update the docs" as an unstated afterthought they have to remember themselves.
- Run `flutter analyze` on the new file before handing it back.

### Portable core vs. this project's instantiation

The reusable idea here — three explicit states (loading/error/content-or-empty), adapter/screen separation, a contract header documenting inputs/outputs — is framework-agnostic; it's the same shape a React or SwiftUI screen scaffold would want. What's Flutter-specific is the concrete widgets this skill wires up (`MinDurationLoadingSwitcher`, the `_ErrorView` shape, `AppTokens`). A future non-Flutter project reusing this skill's *pattern* would swap in its own equivalent primitives at Step 2 — the three-state structure and the "ask, don't invent, the actual content" discipline in Step 0/1 carry over unchanged.

---

## What you must never do

- Invent the screen's actual business content, copy, or data shape — scaffold structure, ask for the rest
- Skip the `MinDurationLoadingSwitcher`/`_ErrorView` pattern in favor of a bespoke one-off — consistency is the entire point
- Hardcode colors, spacing, or radii — every literal must be an `AppTokens.*` reference
- Wire the route or update the Screen Inventory without being asked
- Fetch data, call a repository, or touch BLoC directly from the generated screen file
