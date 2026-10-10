---
type: regex
target: files
pattern: '.'
match: not_contains
---

The run's created-files list is empty.

Backstop for the two `tool_used` graders: it catches a file brought into
existence by any route, including a shell redirect or `cp` through Bash,
which `tool_used: Write` would not see.
