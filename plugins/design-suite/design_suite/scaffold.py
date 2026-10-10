"""Recognising scaffold text that was never filled in.

One definition, read by both bin/doctor.py and hooks/audit_on_edit.py. They used
to carry the same regex and the same field walk separately; the moment the two
disagreed, doctor would call a hooks map configured while the hook treated it as
scaffold (or the reverse) — one check saying "fine" about a hook doing nothing.
"""
from __future__ import annotations

import re

# `hooks.map.json.template` used to ship one TODO-shaped entry, and `init.py`
# substitutes only {{PROJECT_NAME}} / TODO_PROJECT_NAME — so every other TODO in
# a scaffolded config survives into the project verbatim, and a TODO glob
# matches no file that was ever saved.
PLACEHOLDER = re.compile(r"TODO|\{\{[A-Z_]+\}\}")


def entry_is_placeholder(entry: dict) -> bool:
    """Whether a hooks.map.json entry is scaffold text rather than a configured trigger.

    Checked across the fields that decide whether the entry can ever fire — its
    name, its trigger, and its command — rather than the whole entry, so a
    genuine entry whose `reason` or `fixHint` prose happens to contain the word
    TODO is not mistaken for an unconfigured one.
    """
    watched = [entry.get("name"), entry.get("glob"), entry.get("commandPattern"),
               entry.get("command")]
    flat: list[str] = []
    for value in watched:
        if isinstance(value, str):
            flat.append(value)
        elif isinstance(value, list):
            flat += [v for v in value if isinstance(v, str)]
    return any(PLACEHOLDER.search(v) for v in flat)
