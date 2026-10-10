"""Shared "parse a stated date out of a document, compute days-since" logic.

Two consumers ask the same narrow question of a markdown document — "does it
state a date somewhere, and how many days old is that date?" — for different
purposes:

* `bin/audit_proposal_status.py` (issue #51): a proposal header's "dated
  YYYY-MM-DD" claim, aged against a configurable `stale_days` threshold, is
  what `stale_framing` checks.
* `bin/audit_doc_staleness.py` (issue #84): a doc's own `_Last updated:
  YYYY-MM-DD_`-style footer (or a `Date:`/`dated` header field), aged the same
  way, against its own threshold.

Both are the same two-step operation — find an ISO date token, compute
`(today - date).days` — so it is factored here rather than reimplemented a
second time, the same "factor, don't duplicate" call issue #60 already made
for the ✅/🔴-heading parser in `design_suite/engine/decisions.py`.

Stdlib only, no project literals — this lives in the universal engine layer.
"""
from __future__ import annotations

import datetime
import re

# A bare ISO date token, e.g. "2026-08-01". Deliberately not anchored to any
# particular label — callers pair it with their own label pattern (a
# `dated ...` header claim, a `Last updated:` footer, a `Date:` field) and
# hand this the matched span to pull the date out of.
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def parse_iso_date(text: str) -> datetime.date | None:
    """The first ISO `YYYY-MM-DD` token in `text`, parsed — or None.

    Returns None both when no date-shaped token exists and when one exists but
    is not a real calendar date (e.g. a typo'd `2026-13-40`). Callers must
    treat both as "no usable date found", never as an error that blocks
    everything else — that is the same "no staleness signal" outcome either
    way.
    """
    m = ISO_DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def days_since(dated: datetime.date, today: datetime.date) -> int:
    """How many days ago `dated` was, relative to `today`.

    A negative result (a future-dated document) is returned as-is rather than
    clamped — that is itself worth surfacing (a footer nobody meant to
    postdate), not a case to silently normalise away.
    """
    return (today - dated).days
