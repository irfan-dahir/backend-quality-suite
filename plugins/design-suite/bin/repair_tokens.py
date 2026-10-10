#!/usr/bin/env python3
"""Generate a unified diff replacing raw literals with the tokens that equal them.

RFC-0003 §3b/§3c. The suite has 18 audits and, before this, zero fix paths. This
is the narrowest possible first one: the finding `EdgeInsets.all(16)` becomes the
patch `AppTokens.space16`, and only when exactly one declared spacing token is
exactly 16.

**It emits a diff and stops.** It does not write to the working tree, stage,
or commit — see RFC-0003 §3c and the tier table in CLAUDE.md. Review the diff,
then `git apply` it yourself if you agree with it. Precedent for the shape:
`design_suite/engine/mockapi/sync_mock_api.py`, which generates rather than
reports and carries a `--check` mode.

    python3 "${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens.py"            # diff to stdout
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens.py" --out t.patch
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens.py" --report   # bands only, no diff
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens.py" --check    # exit 1 if repairs exist
    python3 "${CLAUDE_PLUGIN_ROOT}/bin/repair_tokens.py" --files a.dart b.dart

## Why --files exists, and why it is the mode that actually pays

Run across a whole already-migrated codebase this repaired **0 of 33** findings:
everything deterministic had already been migrated, and what was left was band 2
and band 3 by construction. That is not a defect in the repairer — it is RFC-0003
§3a's argument arriving as a measurement. A repair is worth generating on the
lines a developer is touching *right now*, where the literal is new and the
author is still holding the context; on cold code the survivors are precisely the
ones no band-1 rule may touch. `--files` is how the pre-commit runner
(`run_precommit_audits.py`) asks for exactly that narrow sweep. Do not read the
0-of-33 number as "band 1 does not work" and widen this back to whole-repo
batches — widening is what produced the 0.

`--bands-json` writes one `{file, line, kind, band}` record per finding, keyed
the same way `engine/scan.py` keys an audit finding, so a caller can say which of
*its* findings got an offer and which did not. A finding with no offered fix must
never be presentable as a fixed one.

## What it refuses to do, and why that is the feature

RFC-0003 §2c: `dart.checks()` falls back to `ctx.token_accessor or "AppTokens"`,
so a token audit run against a project with no declared token source *appears to
work* — it reports raw literals as though it knew a token existed for them. It
does not. Band 1 means "exactly one declared token matches", and with no
declared, resolving token source there is nothing to match against.

So this refuses (exit 2) rather than guessing when:

  - `tokens.accessor` is not declared in the profile
  - `tokens.source` is not declared, or does not resolve (an uninstalled
    package, a moved file)
  - the adapter cannot enumerate token values at all
  - `unusedTokens.categories` in arch-rules names no naming prefixes, so
    "a token of the right category" has no meaning here

A repairer that guesses in any of those cases is not producing a weaker fix —
it is producing a wrong one, into source, under a heading that says it was
deterministic.

## Exit codes

    0   ran; a diff was emitted, or there was nothing in band 1
    1   --check only: band-1 repairs are available
    2   refusal — could not establish what a token is on this project
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import project_root  # noqa: E402  (also puts the plugin on sys.path)

REPO = project_root()

from design_suite.adapters import for_project                    # noqa: E402
from design_suite.engine import arch, token_repair as R          # noqa: E402
from design_suite.engine import exceptions as X                  # noqa: E402
from design_suite.engine.scan import line_of, source_files       # noqa: E402

REFUSED = 2


def refuse(message: str) -> int:
    print(f"REFUSING: {message}\n\nThis is a refusal, not a finding of zero "
          "repairable values. Band 1 requires a declared, resolving token "
          "source — see RFC-0003 §2c.", file=sys.stderr)
    return REFUSED


def _categories(args) -> dict:
    """{category: name prefix}, from the project's own architecture rules.

    Reuses `unusedTokens.categories` rather than inventing a second place to
    declare the same naming convention — that audit already needs "which
    declared names mean spacing", and two copies of one convention is one copy
    that drifts.

    `--categories-file` exists for previewing on a project that has not declared
    the section yet. It is a preview, not a source of truth, and it says so in
    the report so a band split produced with it cannot be quoted as the
    project's own.
    """
    if args.categories_file:
        return json.loads(Path(args.categories_file).read_text())
    try:
        return arch.load(REPO, "unusedTokens").get("categories") or {}
    except SystemExit:
        return {}


def _declared_tokens(adapter, ctx, categories: dict):
    """{category: {name: value}}, or (None, why) if any category cannot be read."""
    if not hasattr(adapter, "token_declarations"):
        return None, (f"the {getattr(adapter, 'NAME', '?')!r} adapter cannot read "
                      "declared token values (no token_declarations capability)")
    tokens = {}
    for category, prefix in sorted(categories.items()):
        if not prefix:
            return None, f"unusedTokens.categories.{category} declares no name prefix"
        declared = adapter.token_declarations(ctx, prefix)
        if declared is None:
            return None, (f"tokens.source does not resolve, so category {category!r} "
                          f"(prefix {prefix!r}) is undeterminable. If it names a "
                          "package, install dependencies first")
        tokens[category] = declared
    if not any(tokens.values()):
        return None, ("the declared categories resolved but matched no tokens at all — "
                      "refusing to report every literal as band 3 on an empty token set")
    return tokens, None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=None, help="defaults to the profile's source.root")
    p.add_argument("--out", default=None, help="write the diff here instead of stdout")
    p.add_argument("--report", action="store_true",
                   help="band counts only; emit no diff")
    p.add_argument("--check", action="store_true",
                   help="write nothing; exit 1 if any band-1 repair is available")
    p.add_argument("--files", nargs="+", default=None,
                   help="repo-relative paths to sweep instead of the whole tree — "
                        "diff-time delivery (RFC-0003 §3a)")
    p.add_argument("--bands-json", default=None,
                   help="write one {file, line, kind, band} record per finding here, "
                        "so a caller can tell an offered fix from an absent one")
    p.add_argument("--suggestions-json", default=None,
                   help="write band-2 (ambiguous) findings here as "
                        "{file, line, kind, snippet, candidates} records — plausible "
                        "matches for a human to confirm, never a diff and never "
                        "folded into --out's findings envelope (RFC-0003 phase 2, S1)")
    p.add_argument("--categories-file",
                   help="preview category→prefix map, for a project that has not "
                        "declared unusedTokens.categories yet")
    args = p.parse_args()

    adapter, ctx, checks = for_project(REPO)

    accessor = (ctx.profile.get("tokens", {}) or {}).get("accessor")
    if not accessor:
        return refuse("the profile does not declare tokens.accessor, so nothing "
                      "can be written as a token reference")

    categories = _categories(args)
    if not categories:
        return refuse("no token categories are declared (arch-rules "
                      "unusedTokens.categories), so \"exactly one token of the right "
                      "category\" has no meaning on this project")

    tokens, why = _declared_tokens(adapter, ctx, categories)
    if tokens is None:
        return refuse(why)

    if omitted := getattr(checks, "omitted", []):
        for note in omitted:
            print(f"note: check omitted — {note}", file=sys.stderr)

    scan_dir = args.dir or (ctx.profile.get("source", {}) or {}).get("root", "lib")
    scan_root = REPO / scan_dir
    if not scan_root.is_dir():
        print(f"no such directory: {scan_root}", file=sys.stderr)
        return 1

    globs = getattr(adapter, "FILE_GLOBS", ("**/*",))
    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    exceptions = ctx.exceptions
    skip = {theme} if (theme := exceptions.get("themeFileToSkip")) else set()
    # Same reading of the same file as audit_tokens, from one implementation.
    # These two disagreeing is worse than either being wrong alone: this one
    # rewrites source, so a literal the project exempted and the audit stopped
    # reporting would still be edited out from under it.
    exempt = X.exemptions(exceptions)
    protected = X.report_anyway(exceptions)

    files = source_files(scan_root, globs)
    if not files:
        print(f"the {adapter.NAME!r} adapter matched no files under {scan_dir}/ — "
              "refusing to report zero repairable findings on an empty sweep",
              file=sys.stderr)
        return 1

    if args.files is not None:
        requested = {Path(f).as_posix() for f in args.files}
        files = [p for p in files if str(p.relative_to(REPO)) in requested]
        # Named but not swept is not the same as named and clean: a caller that
        # hands us a path the adapter does not scan must hear about it, or an
        # empty diff reads as "nothing to repair here".
        unswept = sorted(requested - {str(p.relative_to(REPO)) for p in files})
        for path in unswept:
            print(f"note: {path} is not a source file this adapter sweeps — "
                  "no repair was even attempted for it", file=sys.stderr)
        if not files:
            print("none of the given --files are sweepable source — emitting no "
                  "diff, which means 'not looked at', not 'nothing to fix'",
                  file=sys.stderr)
            if args.bands_json:
                empty = Path(args.bands_json)
                empty = empty if empty.is_absolute() else REPO / empty
                empty.parent.mkdir(parents=True, exist_ok=True)
                empty.write_text(json.dumps({"bands": []}))
            if args.suggestions_json:
                empty = Path(args.suggestions_json)
                empty = empty if empty.is_absolute() else REPO / empty
                empty.parent.mkdir(parents=True, exist_ok=True)
                empty.write_text(json.dumps({"suggestions": []}))
            return 0

    bands = {R.BAND_DETERMINISTIC: [], R.BAND_AMBIGUOUS: [], R.BAND_ABSENT: [],
             R.UNSUPPORTED: [], R.UNDETERMINABLE: []}
    diff: list[str] = []
    suggestions: list[dict] = []

    for path in files:
        rel = str(path.relative_to(REPO))
        if generated and rel.endswith(generated):
            continue
        if rel in skip:
            continue
        source = path.read_text()
        repairable = []

        for check in checks:
            if X.covering_entry(rel, check.category, exempt, protected):
                continue
            if not check.applies_to(rel):
                continue
            for match in check.pattern.finditer(source):
                if not check.fires(match, source):
                    continue
                sites = R.sites_for(check.kind, match, adapter, tokens, accessor)
                record = {"file": rel, "line": line_of(source, match.start()),
                          "kind": check.kind, "snippet": match.group(0)}
                if isinstance(sites, str):
                    bands[sites].append(record)
                    continue
                if not sites:
                    bands[R.UNSUPPORTED].append(record)
                    continue
                band = R.band_of(sites)
                record["candidates"] = sorted(
                    {c for s in sites for c in s.candidates})
                if band == R.BAND_DETERMINISTIC:
                    # V1 (RFC-0003 phase 2): never offer a diff without first
                    # proving it clears the finding it claims to fix. See
                    # token_repair.revalidates for why (issue #109).
                    if R.revalidates(check, match, source, sites):
                        bands[band].append(record)
                        repairable.extend(sites)
                    else:
                        bands[R.UNDETERMINABLE].append(record)
                else:
                    bands[band].append(record)
                    if band == R.BAND_AMBIGUOUS:
                        # S1: band 2 gets its own channel (--suggestions-json),
                        # never merged into the diff or into --out's envelope
                        # as though it were a confirmed band-1 fix.
                        suggestions.append(record)

        if repairable:
            diff.extend(R.unified(rel, source, R.rewrite(source, repairable)))

    if args.bands_json:
        bands_out = Path(args.bands_json)
        bands_out = bands_out if bands_out.is_absolute() else REPO / bands_out
        bands_out.parent.mkdir(parents=True, exist_ok=True)
        bands_out.write_text(json.dumps({"bands": [
            dict(record, band=band) for band, records in bands.items()
            for record in records]}, indent=2))

    if args.suggestions_json:
        # S1: a real channel for band-2 candidates, keyed identically to the
        # bands-json record so a caller can correlate a suggestion back to its
        # finding. Never a diff, never merged into --out.
        sug_out = Path(args.suggestions_json)
        sug_out = sug_out if sug_out.is_absolute() else REPO / sug_out
        sug_out.parent.mkdir(parents=True, exist_ok=True)
        sug_out.write_text(json.dumps({"suggestions": suggestions}, indent=2))

    total = sum(len(v) for v in bands.values())
    counts = {k: len(v) for k, v in bands.items()}
    print(f"{total} token finding(s) across {len(files)} file(s)", file=sys.stderr)
    print(f"  band 1  deterministic   {counts[R.BAND_DETERMINISTIC]:4d}  "
          "exactly one declared token matches — rewritten in the diff",
          file=sys.stderr)
    print(f"  band 2  ambiguous       {counts[R.BAND_AMBIGUOUS]:4d}  "
          "several candidates — proposed, never rewritten", file=sys.stderr)
    print(f"  band 3  absent          {counts[R.BAND_ABSENT]:4d}  "
          "no token has this value — authoring one is a human decision",
          file=sys.stderr)
    print(f"  unsupported             {counts[R.UNSUPPORTED]:4d}  "
          "no literal to replace (a token used in the wrong place)", file=sys.stderr)
    print(f"  undeterminable          {counts[R.UNDETERMINABLE]:4d}  "
          "this project declares no naming prefix for that category",
          file=sys.stderr)
    if args.categories_file:
        print("  (categories came from --categories-file: a preview, not this "
              "project's declared convention)", file=sys.stderr)

    for record in bands[R.BAND_AMBIGUOUS]:
        print(f"  band 2  {record['file']}:{record['line']}  {record['snippet']}"
              f"  -> {', '.join(record['candidates']) or '(near match)'}",
              file=sys.stderr)

    if args.check:
        return 1 if counts[R.BAND_DETERMINISTIC] else 0
    if args.report:
        return 0

    text = "".join(diff)
    if args.out:
        out = Path(args.out)
        out = out if out.is_absolute() else REPO / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(f"diff written to {out} — review it, then `git apply` it yourself. "
              "Nothing in the working tree was changed.", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
