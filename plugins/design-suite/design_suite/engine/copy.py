"""Language-agnostic copy inventory: readability scoring and classification.

Splits along the line the old `extract_copy.py` docstring already drew but never
implemented: *"a future project would swap this script for one that knows its own
copy-storage convention, while the audit heuristics that consume the inventory
stay unchanged."* The heuristics are here. Finding the strings is the adapter's
job — a Dart `Text('…')`, a JSX child, a gettext call and a YAML locale file have
nothing in common except that a string comes out.

Nothing in this module may know what language produced the text.
"""
from __future__ import annotations

import re
from pathlib import Path

VOWEL_GROUPS_RE = re.compile(r"[aeiouyAEIOUY]+")
SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
WORD_SPLIT_RE = re.compile(r"\s+")

# Above this word count a string reads as prose rather than UI chrome. A rough
# heuristic, deliberately not a config key: no project has asked to tune it, and
# inventing a knob nobody sets is how config files start drifting from the code.
MICROCOPY_WORD_BUDGET = 6


def count_syllables(word: str) -> int:
    groups = VOWEL_GROUPS_RE.findall(word)
    count = len(groups)
    if word.lower().endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def words_in(text: str) -> list[str]:
    return [w for w in WORD_SPLIT_RE.split(text.strip()) if w]


def flesch_reading_ease(text: str) -> float:
    """Standard Flesch score. Empty text scores 100 (maximally readable) rather
    than raising, so a stray blank string cannot abort an inventory run."""
    words = words_in(text)
    if not words:
        return 100.0
    sentences = [s for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    n_sentences = max(len(sentences), 1)
    n_words = len(words)
    n_syllables = sum(count_syllables(w) for w in words)
    score = 206.835 - 1.015 * (n_words / n_sentences) - 84.6 * (n_syllables / n_words)
    return round(score, 1)


_LETTER_RE = re.compile(r"[^\W\d_]")
_SENTENCE_END_RE = re.compile(r"[.!?]['\")\]]?\s*$")


def classify(text: str, matched_keyword: str | None,
             budget: int = MICROCOPY_WORD_BUDGET, *, kind: str | None = None,
             chrome_kinds=()) -> str:
    """"microcopy", "content" or "fragment". Heuristic, not authoritative.

    An adapter keyword is NOT proof of chrome (issue #109: `message:`,
    `hintText:` and `helperText:` routinely carry body copy, and treating the
    keyword as a verdict judged prose by label rules). Only a kind the consumer
    project declared in its own `copy.chromeKinds` is microcopy by construction.
    Everything else is decided by shape:

      * no letters at all (`'.'`, `')'` — syntax-highlighting spans) -> fragment,
        which no copy rule judges;
      * more than one sentence, or a complete sentence of 3+ words ending in
        sentence punctuation -> content;
      * otherwise the word budget decides.
    """
    if not _LETTER_RE.search(text) or text.lstrip().startswith(("//", "/*")):
        return "fragment"
    if kind is not None and kind in set(chrome_kinds or ()):
        return "microcopy"
    words = words_in(text)
    sentences = [x for x in SENTENCE_SPLIT_RE.split(text.strip()) if x.strip()]
    if len(sentences) > 1:
        return "content"
    if len(words) >= 3 and _SENTENCE_END_RE.search(text) and not text.rstrip().endswith("..."):
        return "content"
    return "microcopy" if len(words) <= budget else "content"


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def build_entries(rel: str, source: str, strings, chrome_kinds=()) -> list[dict]:
    """Turn an adapter's (offset, text, keyword, kind[, skip_reason]) tuples
    into inventory entries.

    `strings` is whatever the adapter found, in whatever order; ordering is
    imposed by the caller so output is stable across runs.

    Shorter tuples degrade rather than break, so an adapter that predates one
    of these fields still works: a 3-tuple (offset, text, keyword) falls back
    to `kind = keyword or "text"`; a missing 5th element is treated as
    `skip_reason = None`.

    A non-None `skip_reason` marks a string the adapter found but cannot
    judge — e.g. Dart string interpolation, where there is no fixed text to
    score for readability or check against the microcopy rules. Such an entry
    is still recorded, as a "dynamic" category with no score, rather than
    dropped: a silently-dropped string is exactly the gap this inventory
    exists to close, per the project's governing principle that "not found"
    and "found nothing wrong" must never look the same.
    """
    entries = []
    for item in strings:
        if len(item) >= 4:
            offset, text, keyword, kind = item[0], item[1], item[2], item[3]
        else:
            offset, text, keyword = item[0], item[1], item[2]
            kind = keyword or "text"
        skip_reason = item[4] if len(item) > 4 else None
        if skip_reason:
            entries.append({
                "file": rel,
                "line": line_of(source, offset),
                "text": text,
                "category": "dynamic",
                "kind": kind,
                "word_count": None,
                "flesch_reading_ease": None,
                "skip_reason": skip_reason,
            })
            continue
        entries.append({
            "file": rel,
            "line": line_of(source, offset),
            "text": text,
            "category": classify(text, keyword, kind=kind, chrome_kinds=chrome_kinds),
            "kind": kind,
            "word_count": len(words_in(text)),
            "flesch_reading_ease": flesch_reading_ease(text),
        })
    return entries


# ─── Mechanical microcopy rules ───────────────────────────────────────────────
#
# Folded in from the design system's `tooling/scripts/audit_copy.py`, which was
# the only place these existed. `/audit-copy` had six checks and every one of
# them was a model reading strings and judging — which is right for tone and
# terminology and wrong for "does this label end in a full stop".
#
# That was the same shape as the defect audit_copy's own docstring cites: a rule
# written down, described, and never executed. These seven are decidable, so they
# are decided here and the model's attention goes to the ones that are not.
#
# They apply to MICROCOPY only. A content sentence legitimately ends in a period
# and legitimately capitalises after one; a label does neither.

DEFAULT_FILLER = ("simply", "obviously", "of course", "oops", "whoops", "easy!")
DEFAULT_APOLOGY = ("we apologise", "we apologize", "sorry", "you failed",
                   "you entered an invalid")
# Legitimately capitalised mid-label. Deliberately short and Anglophone — a
# project adds its own rather than inheriting a guess about its domain.
DEFAULT_PROPER = ("AM", "PM", "ID", "OK", "PDF", "SMS", "US")

CURLY = ("’", "“", "”")


def check_microcopy(text: str, *, proper=DEFAULT_PROPER, filler=DEFAULT_FILLER,
                    apology=DEFAULT_APOLOGY) -> list[dict]:
    """Rule violations in one label, each as {rule, detail}.

    Returns a list rather than a bool so a caller can exempt one rule on one
    string without exempting the string entirely — an exemption that silences
    more than it names is how a real second problem hides behind an accepted
    first one.
    """
    out: list[dict] = []
    words = text.split()

    # A string that IS a declared proper noun is not shouting — "MRR" is how the
    # acronym is spelled, not a style choice. Without this, declaring an acronym
    # in properNouns silences the Title Case rule and leaves all-caps firing on
    # the same word, which reads as the config not working.
    cased = [c for c in text if c.isalpha() and c.upper() != c.lower()]
    if (text.isupper() and len(cased) >= 3 and text not in proper
            and all(c.isupper() for c in cased)
            and sum(c.isalpha() for c in text) <= 2 * len(cased)):
        out.append({
            "rule": "all_caps",
            "detail": "arrives pre-shouted. The component applies the transform, "
                      "so the day the design stops uppercasing, this string is "
                      "wrong and nothing catches it — the same reasoning as never "
                      "hardcoding a colour."})
    elif len(words) > 1:
        tail = [w for w in words[1:]
                if w[:1].isupper() and w.strip(".,") not in proper]
        if tail:
            # DO NOT re-add a suggested rewrite here. This rule used to ship one,
            # built as `words[0] + [w.lower() for w in words[1:]]`, and it was
            # corrupting — measured in issue #104, removed under issue #109.
            #
            # It lowercased EVERY word after the first, including the ones this
            # very rule had just decided were legitimate. `tail` excludes `proper`
            # so that a declared proper noun does not trigger the finding; the
            # rewrite then lowercased those same words anyway. So with `PDF` and
            # `US` declared (they are, in DEFAULT_PROPER):
            #
            #     'Send PDF Report'    -> 'Send pdf report'
            #     'View US Lab Reports'-> 'View us lab reports'
            #     'Hi, How can I help you?' -> 'Hi, how can i help you?'
            #
            # The first two destroy the exact strings the properNouns config
            # exists to protect — the fix contradicts the detector beside it. The
            # third is the measured case from #104: the pronoun 'I' lowercased in
            # shipped user-facing copy. Under RFC-0003 §3b band 1 that string is
            # applied rather than read, so the damage lands unreviewed.
            #
            # Deciding which capitals are load-bearing — pronouns, proper nouns,
            # product names, references to other UI labels — is the judgment this
            # checker cannot make (issue #109). Emitting a rewrite is claiming to
            # have made it. So the finding names the words and stops there; a
            # reader who can tell a product noun from a slip writes the fix.
            out.append({"rule": "title_case",
                        "detail": "looks like Title Case (capitalised mid-label: "
                                  + ", ".join(repr(w) for w in tail)
                                  + "). Labels are sentence case unless the "
                                    "capital is load-bearing — a proper noun, a "
                                    "product name, or a reference to another UI "
                                    "label. If it is, declare it in the copy "
                                    "config's properNouns rather than rewriting."})

    if text.endswith(".") and not text.endswith("..."):
        out.append({"rule": "terminal_period",
                    "detail": "ends in a period. Labels do not; sentences in body "
                              "copy do."})
    if "..." in text:
        out.append({"rule": "three_dots",
                    "detail": "uses three dots. Use the ellipsis character "
                              "'…' (U+2026)."})
    for bad in filler:
        if re.search(rf"\b{re.escape(bad)}", text, re.I):
            out.append({"rule": "filler",
                        "detail": f"contains filler {bad!r}. \"Simply tap here\" "
                                  f"tells someone who is struggling that they "
                                  f"should not be."})
    for bad in apology:
        if re.search(rf"\b{re.escape(bad)}", text, re.I):
            out.append({"rule": "apology",
                        "detail": f"apologises or blames ({bad!r}). State the "
                                  f"situation and the next step."})
    if any(c in text for c in CURLY):
        out.append({"rule": "curly_quotes",
                    "detail": "uses curly quotes. Straight ones, matching the "
                              "rest of the codebase."})
    return out


def build_inventory(repo: Path, adapter, ctx, scan_dir: str | None = None) -> list[dict]:
    """The copy inventory, built once so two callers cannot disagree about it.

    `extract_copy.py` writes this to disk; `audit_copy.py` judges it. Reading the
    written file back would have been simpler and wrong — the gate would then
    pass or fail against whatever was on disk, and a stale inventory reports a
    clean run on code that has since changed.

    Raises SystemExit rather than returning [] on a miss. An empty inventory is
    indistinguishable from a project with no copy.
    """
    from design_suite.engine.scan import source_files

    if not hasattr(adapter, "extract_copy_strings"):
        raise SystemExit(
            f"the {adapter.NAME!r} adapter cannot locate user-facing copy — "
            f"copy extraction is unavailable for this project's language")

    scan_dir = scan_dir or (ctx.profile.get("source", {}) or {}).get("root", "lib")
    scan_root = repo / scan_dir
    if not scan_root.is_dir():
        raise SystemExit(f"no such directory: {scan_root}")

    globs = getattr(adapter, "FILE_GLOBS", ("**/*",))
    files = source_files(scan_root, globs)
    if not files:
        raise SystemExit(
            f"the {adapter.NAME!r} adapter matched no files under {scan_dir}/ "
            f"(globs: {', '.join(globs)}).\nAn empty inventory here is "
            f"indistinguishable from a project with no copy, so this is an error.")

    generated = getattr(adapter, "GENERATED_SUFFIXES", ())
    # The consumer's declared chrome signal (issue #109 path back, step 1).
    chrome_kinds = tuple(((getattr(ctx, "exceptions", None) or {}).get("copy") or {})
                         .get("chromeKinds") or ())
    inventory: list[dict] = []
    for path in files:
        rel = str(path.relative_to(repo))
        if generated and rel.endswith(generated):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        inventory.extend(build_entries(rel, source, adapter.extract_copy_strings(source),
                                       chrome_kinds))
    inventory.sort(key=lambda e: (e["file"], e["line"]))
    return inventory
