---
type: tool_used
tool: Edit
input_match: 'app/'
min: 1
---

Step 4 happens: the application actually adopts the component it just
extracted.

The command's body is emphatic that this is where the job is usually left
undone — "Extraction and adoption are two jobs and only the first one feels
finished", and "Leave Step 4 undone and call the promotion finished" is in the
never-do list. Adoption is deletion of the private widget and rewriting of an
import: modifications to files that already exist, so this is asserted on the
Edit call rather than on the created-files list, which cannot see an in-place
change.
