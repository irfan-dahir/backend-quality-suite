"""Shared parser for the repo's ✅/🔴-marked decision-heading convention.

Two consumers ask the same question of a markdown document — "find a heading
marked ✅ (resolved) or 🔴 (open), and pull its title, date, and surrounding
prose" — for different purposes:

* `bin/audit_proposal_status.py` (issue #51): does *this* document's own header
  claim (an open-question count, a `Status:` field) still agree with what its
  body's decision headings say? A self-consistency check on one doc.
* `bin/query_decisions.py` (issue #60): what decisions exist, across however
  many decision documents a project has, open or resolved, matching a keyword?
  A read-time index over potentially many docs.

The convention itself — `docs/ROADMAP.md`'s own `## Decisions` section, e.g.
`### ✅ 1 — No, chains do not subsume verify.py` — is vetted by #51 already.
Factoring the regex and section-boundary logic here means both ask the same
question of the same parser instead of drifting apart the next time the
convention is extended (`➡️`-superseded, say).

Stdlib only, no project literals — this lives in the universal engine layer,
not the resolver, so it must not assume any project's directory layout.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

RESOLVED = "✅"
OPEN = "🔴"

# A heading naming a "Decisions" (or "Decision") section, any level 2-6.
DECISION_SECTION_HEADING_RE = re.compile(r"^#{2,6}\s*Decisions?\b.*$", re.I | re.M)

# A heading directly under such a section, carrying a ✅/🔴 marker and an
# optional ordinal, e.g. "### ✅ 1 — No, chains do not subsume verify.py".
ENTRY_HEADING_RE = re.compile(r"^(#{2,6})\s+(✅|🔴)\s*(\d+)?\.?\s*(?:—|-|:)?\s*(.*)$", re.M)

DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


@dataclass(frozen=True)
class DecisionEntry:
    """One ✅/🔴-marked heading under a Decisions section."""

    marker: str             # "✅" or "🔴"
    number: str | None      # the optional ordinal ROADMAP.md numbers entries with
    title: str              # heading text after the marker/number/separator
    line: int               # 1-based line number of the heading in the source text
    body: str               # prose between this heading and the next same-or-shallower one
    date: str | None        # first YYYY-MM-DD found on the heading line or in the body

    @property
    def resolved(self) -> bool:
        return self.marker == RESOLVED

    def matches(self, keyword: str) -> bool:
        """Case-insensitive substring match against title or body."""
        needle = keyword.lower()
        return needle in self.title.lower() or needle in self.body.lower()


@dataclass(frozen=True)
class DecisionSection:
    """A single `## Decisions` (or similarly-named) heading and its entries."""

    heading_line: int
    heading_text: str
    entries: list[DecisionEntry] = field(default_factory=list)

    @property
    def resolved_count(self) -> int:
        return sum(1 for e in self.entries if e.resolved)

    @property
    def open_count(self) -> int:
        return sum(1 for e in self.entries if not e.resolved)


def _parse_entries(section_text: str, full_text: str, offset: int) -> list[DecisionEntry]:
    matches = list(ENTRY_HEADING_RE.finditer(section_text))
    entries: list[DecisionEntry] = []
    for i, m in enumerate(matches):
        marker = m.group(2)
        number = m.group(3)
        title = m.group(4).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        body = section_text[start:end].strip()
        line_no = full_text.count("\n", 0, offset + m.start()) + 1
        date_m = DATE_RE.search(m.group(0)) or DATE_RE.search(body)
        entries.append(DecisionEntry(marker=marker, number=number, title=title,
                                      line=line_no, body=body,
                                      date=date_m.group(1) if date_m else None))
    return entries


def _section_at(text: str, heading_m: re.Match) -> DecisionSection:
    heading_line = text.count("\n", 0, heading_m.start()) + 1
    section_level = len(re.match(r"^#+", heading_m.group(0)).group(0))
    body_start = heading_m.end()

    # The section runs until the next heading of the same or shallower level.
    next_heading_re = re.compile(rf"^#{{1,{section_level}}}\s", re.M)
    next_m = next_heading_re.search(text, body_start)
    section_end = next_m.start() if next_m else len(text)
    section_text = text[body_start:section_end]

    entries = _parse_entries(section_text, text, body_start)
    return DecisionSection(heading_line=heading_line, heading_text=heading_m.group(0).strip(),
                            entries=entries)


def find_decision_section(text: str) -> DecisionSection | None:
    """Locate the *first* Decisions-shaped section and parse its ✅/🔴 entries.

    Returns None when no such section exists at all — a caller must not
    conflate that with "a Decisions section with zero entries"; those are
    different facts (see the suite's governing principle).
    """
    heading_m = DECISION_SECTION_HEADING_RE.search(text)
    if not heading_m:
        return None
    return _section_at(text, heading_m)


def find_all_decision_sections(text: str) -> list[DecisionSection]:
    """Every Decisions-shaped section in a document, not just the first.

    A proposal doc (#51's target) has exactly one, so it uses
    `find_decision_section`. A project's decision log (#60's target) may group
    entries under several thematic `## Decisions` headings, so the query tool
    needs all of them.
    """
    sections: list[DecisionSection] = []
    pos = 0
    while True:
        m = DECISION_SECTION_HEADING_RE.search(text, pos)
        if not m:
            break
        section = _section_at(text, m)
        sections.append(section)
        # Resume scanning after this section's body, not just after its heading,
        # so a second "## Decisions" heading inside the body text (unlikely, but
        # not impossible) isn't double-counted as a nested section.
        section_level = len(re.match(r"^#+", m.group(0)).group(0))
        next_heading_re = re.compile(rf"^#{{1,{section_level}}}\s", re.M)
        next_m = next_heading_re.search(text, m.end())
        pos = next_m.start() if next_m else len(text)
    return sections
