"""One spelling of "I could not look" for every audit.

Exit-code contract (DOC-ROLES.md): 0 looked and found nothing, 1 looked and
found something, 2 could not look. `raise SystemExit("message")` exits **1** —
Python's rule, not ours — so every cannot-determine path written that way was
read by hooks and `repo_health.py` as *findings*. `Refused` keeps the
one-line `raise` ergonomics and exits 2 with a named, INERT reason.

It subclasses SystemExit so existing callers that catch SystemExit keep
working; `.code` is 2 and `.reason` carries the message.
"""
from __future__ import annotations

import sys

REFUSED = 2


class Refused(SystemExit):
    def __init__(self, reason: str, audit: str | None = None):
        self.reason = str(reason)
        label = f"{audit}: " if audit else ""
        print(f"{label}REFUSED (exit 2, INERT — could not check, not clean): "
              f"{self.reason}", file=sys.stderr)
        super().__init__(REFUSED)

    def __str__(self) -> str:  # keeps str(exc) meaningful for callers/tests
        return self.reason
