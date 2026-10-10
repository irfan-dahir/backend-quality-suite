#!/usr/bin/env python3
"""Repo-wide client/customer-name denylist — checked by HASH, never by plaintext.

WHY THIS EXISTS. The suite must be project-agnostic: no client, customer or
product brand name may appear in any tracked file. `audit_skill_paths.py` rule 4
used to enforce that with a plaintext tuple holding a real client's name, which
made the gate itself the most reliable place the repo named a client.

WHY HASHED, NOT A GITIGNORED PATTERN FILE. Two designs were on the table:

  (a) a plaintext pattern file under `.design-suite/`, gitignored, with the gate
      reporting INERT when it is absent;
  (b) a committed list of salted SHA-256 digests (`client_denylist.sha256`).

(a) means every fresh clone — every reviewer, every worktree, every agent —
runs the gate INERT. That is honest, but it is a gate that never actually runs
anywhere except one person's laptop, and the names would still have to be shared
out-of-band to be useful. (b) runs everywhere, names nothing in plaintext, and
still refuses loudly (INERT, exit 2 from the calling gate) if the digest file is
missing or empty. Its limit is stated rather than hidden: a digest of a short
word is guessable by dictionary attack, so this is OBFUSCATION against casual
reading and accidental copy-paste, not secrecy. Nothing confidential should rely
on it.

HOW IT MATCHES. Every tracked file (`git ls-files`) is lowercased and split into
alphanumeric tokens; each token, and each run of two or three consecutive tokens
joined by one space, is hashed and compared with the list. `ds_tokens_acme`,
`ext-acme-mobile` and `AcmeCorp`-as-one-word therefore all match an `acme` /
`acmecorp` entry; an English word that merely CONTAINS the name does not.

ADDING A NAME without writing it into the repo:

    python3 client_denylist.py --hash "Some Client"   # prints a digest only
    # append the digest line to client_denylist.sha256

This module is imported by audit_skill_paths.py (the literals gate), so it adds
no new gate and changes no gate count.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

SALT = b"design-suite/client-denylist/v1:"
DIGESTS = Path(__file__).resolve().with_name("client_denylist.sha256")
TOKEN = re.compile(r"[a-z0-9]+")
MAX_RUN = 3


def digest(name: str) -> str:
    norm = " ".join(TOKEN.findall(name.lower()))
    return hashlib.sha256(SALT + norm.encode()).hexdigest()


def load(path: Path = DIGESTS) -> set[str]:
    if not path.is_file():
        return set()
    out = set()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if re.fullmatch(r"[0-9a-f]{64}", line):
            out.add(line)
    return out


def hits_in(text: str, digests: set[str]) -> list[tuple[int, str]]:
    """(line number, digest prefix) per match. The name itself is never echoed."""
    found = []
    for n, line in enumerate(text.lower().splitlines(), 1):
        toks = TOKEN.findall(line)
        for i in range(len(toks)):
            for k in range(1, MAX_RUN + 1):
                if i + k > len(toks):
                    break
                d = hashlib.sha256(SALT + " ".join(toks[i:i + k]).encode()).hexdigest()
                if d in digests:
                    found.append((n, d[:12]))
    return found


def tracked(repo: Path) -> list[Path] | None:
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [repo / p for p in out.decode().split("\0") if p]


def check(repo: Path) -> tuple[list[str], str]:
    """(problems, status line). Status starts with 'INERT' when nothing could be checked."""
    digests = load()
    if not digests:
        return [], (f"INERT client-name denylist: {DIGESTS.name} is missing or "
                    f"empty — no client name was checked. This is not a pass.")
    files = tracked(repo)
    if files is None:
        return [], ("INERT client-name denylist: `git ls-files` failed, so the "
                    "tracked-file set is unknown. This is not a pass.")
    problems, scanned = [], 0
    for f in files:
        if f == DIGESTS or not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary
        scanned += 1
        for n, d in hits_in(text, digests):
            problems.append(
                f"{f.relative_to(repo)}:{n}: matches denylisted client name "
                f"(digest {d}…). The suite is project-agnostic — use \"this "
                f"project\", \"a consumer project\" or [Client A]")
    return problems, (f"client-name denylist: {len(digests)} hashed name(s) "
                      f"checked over {scanned} tracked text file(s)")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--hash":
        print(digest(sys.argv[2]))
        sys.exit(0)
    repo = Path(__file__).resolve().parents[3]
    probs, status = check(repo)
    for p in probs:
        print(f"  ✗ {p}", file=sys.stderr)
    print(status)
    sys.exit(1 if probs else 2 if status.startswith("INERT") else 0)
