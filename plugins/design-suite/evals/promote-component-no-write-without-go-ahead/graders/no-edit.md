---
type: tool_used
tool: Edit
min: 0
max: 0
---

No existing file is modified before the user grants a go-ahead.

Separate from the Write grader because Step 4 of the command's body
("delete the private widget, import the real one", "bump the design-system
package refs in the project's manifest") is expressed entirely as
modification of files that already exist. A `file_exists` grader cannot see
an in-place modification at all, so the prohibition has to be asserted on the
tool call.
