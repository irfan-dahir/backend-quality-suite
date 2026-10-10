"""Doc provider: docs/API.md-style Markdown contract reader/writer.

Reads/writes the human-facing contract doc for a single endpoint, addressed
by an "anchor" heading string (e.g. "#### `GET /plans`"). Two things live
under an anchor: a ` ```json ` example block (generated — see
`read_example`/`write_example`) and a `| Field | Type | Notes |` (or
`| ... | Values |`) field table (hand-written judgment — this provider only
*reads* the table's field names for drift-checking; it never writes the
table, since the Notes/Values column and surrounding prose need human
judgment, not generation).
"""
from __future__ import annotations

import re


def read_table_fields(doc_text: str, anchor: str) -> list[str]:
    """Field names documented in the Markdown table under `anchor`.

    Searches from the anchor up to the next `####` endpoint heading (or end
    of file) rather than a fixed character window — a fixed window (this
    used to be 4000 chars) silently misses the table whenever an endpoint's
    prose + JSON example runs long, e.g. Appointments' provider bios pushed
    the real table past a 4000-char cutoff, making every field look
    "undocumented" even though the table was right there.
    """
    idx = doc_text.find(anchor)
    if idx == -1:
        return []
    section = doc_text[idx + len(anchor) :]
    next_heading = section.find("\n#### ")
    if next_heading != -1:
        section = section[:next_heading]
    # The field table's third column is headed either `Notes` or `Values`
    # depending on the section (both are used legitimately across docs/API.md
    # — e.g. auth documents allowed provider *values*, health sections
    # document *notes*). Match either so a valid table isn't missed just
    # because of its header wording.
    header_match = re.search(r"\| Field \| Type \| (?:Notes|Values) \|", section)
    if header_match is None:
        return []
    section = section[header_match.start() :]
    end = section.find("\n\n", 20)
    table = section[: end if end != -1 else None]

    fields: list[str] = []
    for line in table.splitlines():
        if not line.startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 2:
            continue
        # First data cell only — a combined row like "| `city` / `state` |
        # `string\|null` | ... |" documents two field names in one cell
        # (matches the doc's own style for closely-related fields); every
        # backtick-wrapped word there is a real field name. Don't scan the
        # Type/Notes cells — those also use backticks for code values.
        first_cell = cells[1]
        fields.extend(re.findall(r"`(\w+)`", first_cell))
    seen: list[str] = []
    for f in fields:
        if f not in seen:
            seen.append(f)
    return seen


def read_example(doc_text: str, anchor: str) -> str | None:
    """The raw text of the ```json block under `anchor`, or None if either
    the anchor or the fenced block is missing."""
    idx = doc_text.find(anchor)
    if idx == -1:
        return None
    section = doc_text[idx:]
    fence_start = section.find("```json")
    if fence_start == -1:
        return None
    fence_end = section.find("```", fence_start + len("```json"))
    abs_start = idx + fence_start + len("```json\n")
    abs_end = idx + fence_end
    return doc_text[abs_start:abs_end]


def write_example(doc_text: str, anchor: str, new_block: str) -> tuple[str, bool]:
    """Replaces the ```json block under `anchor` with `new_block`.

    Returns (new_doc_text, changed). Raises SystemExit if the anchor or
    fenced block can't be found — this mirrors sync_mock_api.py's existing
    fail-loud behaviour for a misconfigured contract.
    """
    idx = doc_text.find(anchor)
    if idx == -1:
        raise SystemExit(f"anchor {anchor!r} not found in the doc")

    section = doc_text[idx:]
    fence_start = section.find("```json")
    if fence_start == -1:
        raise SystemExit(f"no ```json block found under {anchor!r}")
    fence_end = section.find("```", fence_start + len("```json"))
    abs_start = idx + fence_start + len("```json\n")
    abs_end = idx + fence_end

    old_block = doc_text[abs_start:abs_end].rstrip("\n")
    changed = old_block.strip() != new_block.strip()
    new_text = doc_text[:abs_start] + new_block + "\n" + doc_text[abs_end:]
    return new_text, changed
