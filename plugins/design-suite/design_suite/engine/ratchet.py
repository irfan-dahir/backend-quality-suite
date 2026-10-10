"""The shared guard on every `--update-baseline` ratchet.

Why this exists at all: the ratchet audits each printed a hint —

    N baselined finding(s) no longer present — nice.
    Run --update-baseline to lock the improvement in.

— *before* the block that reports NEW violations, and `--update-baseline` then
wrote `sorted(current)`, which contains every new violation found in the same
run. So the one action the tool recommends, taken in the run that recommended
it, silently converted a regression into accepted debt, and the person who ran
it was never shown what they had just accepted. That is the governing
principle's own failure shape: a baseline that absorbed a regression and a
baseline that recorded a genuine improvement are indistinguishable afterwards.

The fix is a refusal at the write, not a reordering of the hint. A reordering
only protects someone who is reading this particular run's output; anyone
typing `--update-baseline` from memory, from a runbook, or from a chat log — the
common case for an agent — is unprotected. Refusing at the write protects both,
and it fails closed: the write does not happen, so nothing is recorded on the
strength of a decision nobody made.

Accepting a regression on purpose stays possible, but it has to be said out
loud with `--accept-new`, and the refusal prints the exact command. The point is
not to forbid it; it is that "I accept these 3 new violations" must be a
sentence someone wrote, never a side effect of "nice, lock the improvement in".
"""
from __future__ import annotations

ACCEPT_FLAG = "--accept-new"


def new_findings(current, baseline) -> list[str]:
    """Findings present now and not in the baseline — the ones a write would absorb."""
    return sorted(set(current) - set(baseline))


def refusal(audit: str, current, baseline, *, unit: str = "finding") -> str | None:
    """The message to print instead of writing the baseline, or None if it is safe.

    None means "no new findings, the write is a pure ratchet". A string means the
    write must not happen: the caller prints it to stderr and exits 2 ("I could
    not answer safely"), not 1 ("I looked and this is wrong") — refusing to write
    is not a finding about the code.
    """
    new = new_findings(current, baseline)
    if not new:
        return None
    lines = [
        f"{audit}: REFUSING TO UPDATE THE BASELINE — {len(new)} NEW {unit}(s) "
        f"would be absorbed:",
        "",
    ]
    lines += [f"  + {k}" for k in new]
    lines += [
        "",
        "These are not in the current baseline. Writing now would record them as "
        "accepted debt without anyone having decided that.",
        "",
        f"Fix them, or — if they really are accepted — re-run with {ACCEPT_FLAG} "
        f"to say so deliberately.",
    ]
    return "\n".join(lines)
