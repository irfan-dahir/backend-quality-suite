---
type: regex
target: files
pattern: 'design-system/'
match: not_contains
---

Nothing is created in the design-system repository.

The component fails the command's own Step 1 bar, so the go-ahead in the prompt
does not make the move correct. Asserted on the created-files list rather than
on the report's prose, because the report claiming it declined while a file sits
in the other repository is exactly the disagreement worth catching.
