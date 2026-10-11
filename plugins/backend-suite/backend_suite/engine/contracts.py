"""Parsing a screen's CONTRACT header, without knowing the language.

The convention this reads — a banner comment with `INPUT:` and `OUTPUT:` naming
the fields a screen may touch — is a project's, not a language's. So the labels,
the marker and the receiver prefix all arrive as config; what stays here is the
shape of the thing: sections, continuation lines, and the arithmetic between what
a header claims and what a class declares.

Comment syntax and class structure are the language adapter's business
(`adapters/php.py`). This module never sees a `/*` or a `private $x;`.

## Two dialects, because two exist

Real headers in the originating project are written both ways, and a parser that
handled one silently mis-read the other:

    INPUT:    adapter.items, adapter.statusFilter
    OUTPUT:   adapter.onSelect(id), adapter.onStatusFilterChanged(status),
              adapter.onApprove(id, scheduleFor:)

    INPUT:
    - adapter.isLoading
    - adapter.staff

A third shorthand rides on the first: once the receiver has been named, further
entries may be written bare, as `.field`, and wrap onto the following lines.

## The terminator that mattered

A section ends at a blank line, the next label, **or a rule line** — because

    INPUT:    member
    ==============================================================================

has no blank between them. Treating the rule as a continuation yielded the token
`member ====…`, which matches no field, so a listed field was reported missing.
That is a false positive on a correct header, and those are what get an audit
turned off rather than fixed.
"""
from __future__ import annotations

import re

# A row of -, = or # used as a visual divider, not content.
RULE_RE = re.compile(r"^\s*[-=#_*]{4,}\s*$")
# `NAME:` at the start of a line — any all-caps label, so an unrelated section
# (PURPOSE, RULES) reliably terminates the one being read.
ANY_LABEL_RE = re.compile(r"^\s*[A-Z][A-Z /&-]*:")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
# Split on commas that are not inside a parenthesised argument list, so
# `onSave(id:, name:)` stays one token.
# Splits entries: a comma, or a slash WITH SPACES around it (`isLoading /
# errorMessage`). Never a bare slash — prose is full of `add/edit-medication`
# and `taken/untaken`, and splitting those invented members called `add`.
TOKEN_SPLIT_RE = re.compile(r"(?:,|\s/\s)(?![^()]*\))")
# An arrow or dash introducing a gloss: `errorMessage → skeleton / error state`.
ANNOTATION_RE = re.compile(r"\s(?:->|→|—|--|–|:)\s|\s{2,}")


def find_header(blocks, marker: str):
    """The first block comment that is a contract header, as (start_line, text).

    `blocks` is the adapter's `block_comments` output. Returns None when the file
    has no such header, which the caller must report rather than skip: a screen
    with no contract is invisible to every other check here, and invisible is
    indistinguishable from clean.
    """
    for start_line, text in blocks:
        if marker in text:
            return start_line, text
    return None


def _tokens(blob: str, prefix: str) -> list[str]:
    names = []
    for raw in TOKEN_SPLIT_RE.split(blob):
        token = raw.strip()
        if not token:
            continue
        # A call whose argument list is followed by more prose is prose. The
        # entry `context.push() to article/video detail routes` describes a
        # navigation, not a member, and dropping everything from `(` onwards
        # turned it into a field named `context` that no class declares — a
        # stale-header finding invented out of a sentence. An annotated member
        # (`onRefresh() — awaited by pull-to-refresh`) is kept, because what
        # follows its `)` is an annotation separator, not another word.
        call = re.match(r"[^()]*\([^()]*\)(.*)$", token)
        if call and call.group(1).strip() and not ANNOTATION_RE.match(call.group(1)):
            continue
        token = re.sub(r"\(.*", "", token).strip()   # drop the argument list
        # Drop a trailing gloss. Authors annotate entries — `errorMessage →
        # skeleton / error state`, `onRefresh() — awaited by pull-to-refresh` —
        # and the annotation is prose about the member, not another member.
        token = ANNOTATION_RE.split(token, maxsplit=1)[0].strip()
        if prefix and token.startswith(prefix):
            token = token[len(prefix):]
        # `.field` shorthand. An author who writes
        #     INPUT: adapter.journey, .riskFactors, .alerts,
        #            .adherenceSeries
        # is naming four members of the same receiver and not repeating the
        # prefix. Read literally, the shorthand entries are dropped (there is
        # nothing before the dot to keep), and the audit reported nine fields as
        # undocumented on the single most thoroughly documented header in the
        # project — a false positive on good documentation, which is the failure
        # that gets an audit switched off rather than fixed.
        elif prefix and token.startswith("."):
            token = token[1:]
        # A sub-path documents the field it starts from: a header line reading
        # `initial.hasMedicationAllergies` is documenting `initial`, in more
        # detail than a bare name would. Dropping it as prose reported the root
        # field as undocumented on nine screens whose headers describe it
        # thoroughly — a false positive on unusually good documentation.
        token = token.split(".", 1)[0].strip()
        # Anything still carrying punctuation is prose, not a field name.
        if re.fullmatch(r"[A-Za-z_]\w*", token):
            names.append(token)
    return names


def section(text: str, labels, prefix: str, header_start: int) -> dict:
    """`{name: absolute line}` for one header section, either dialect.

    `header_start` is where the comment begins in the file, so the returned lines
    are file lines: a finding has to be clickable at the place the edit goes.
    Returns {} for a section that is absent, which is a real state — a header may
    legitimately have no outputs — and is why this cannot signal "missing" by
    raising.
    """
    lines = text.splitlines()
    # A label may carry a parenthetical before its colon —
    # `OUTPUT (via LibraryAdapter callbacks):` is still an OUTPUT section, and
    # requiring a bare `OUTPUT:` made the most thoroughly documented header in
    # one project read as having no sections at all: 18 members reported
    # undocumented on a header that describes every one of them. Caught in a dry
    # run, one edit before it appended 18 duplicates to it.
    wanted = re.compile(
        rf"^(?:{'|'.join(re.escape(l) for l in labels)})\s*(?:\([^)]*\))?\s*:")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not wanted.match(stripped):
            continue
        rest = stripped.split(":", 1)[1].strip()
        collected: list[tuple[str, int]] = []
        if rest:
            collected.append((rest, index))
            for offset, following in enumerate(lines[index + 1:], start=index + 1):
                if (not following.strip()
                        or RULE_RE.match(following)
                        or ANY_LABEL_RE.match(following)):
                    break
                collected.append((following.strip(), offset))
        else:
            for offset, following in enumerate(lines[index + 1:], start=index + 1):
                bullet = BULLET_RE.match(following)
                if bullet:
                    collected.append((bullet.group(1), offset))
                    continue
                if not following.strip():
                    continue
                # A bulleted entry may wrap. An INDENTED non-bullet line
                # continues the bullet above it; a flush-left one is the prose
                # that ends the section. Treating a wrap as the end dropped six
                # members of one 11-name entry.
                if collected and following.startswith((" ", "\t")) \
                        and not RULE_RE.match(following) \
                        and not ANY_LABEL_RE.match(following.strip()):
                    collected.append((following.strip(), offset))
                    continue
                break
        # Tokenise the whole section at once, not blob by blob. A parenthetical
        # may span a line break — `pastCarePlans (each with id, name, tier,` /
        # `coachingSessionsCompleted/Total)` — and per-line splitting cannot see
        # that the commas inside it are enclosed, so it invented members named
        # `name`, `tier` and `createdAt`.
        # Joined with a comma, not a space: bullets are separate entries and must
        # stay separable, while an unclosed parenthesis from one line still meets
        # its closer on the next, so the paren-aware split can see it is enclosed.
        joined = ", ".join(blob for blob, _ in collected)
        names: dict[str, int] = {}
        for name in _tokens(joined, prefix):
            # First mention wins, so a finding points at where the name was
            # introduced rather than where it wrapped.
            line = next((header_start + off for blob, off in collected
                         if re.search(rf"\b{re.escape(name)}\b", blob)),
                        header_start + collected[0][1] if collected else header_start)
            names.setdefault(name, line)
        return names
    return {}


def label_line(text: str, labels, header_start: int, default: int) -> int:
    """Where a section's label sits, for anchoring an "add this" finding.

    Falls back to `default` (the header's first line) when the section is absent
    entirely — which is exactly when something needs adding and there is no label
    to point at.
    """
    wanted = re.compile(
        rf"^(?:{'|'.join(re.escape(l) for l in labels)})\s*(?:\([^)]*\))?\s*:")
    for index, line in enumerate(text.splitlines()):
        if wanted.match(line.strip()):
            return header_start + index
    return default
