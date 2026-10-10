---
type: file_exists
path: 'design-system/**/*stat_cell*test*'
---

The design system's own contribution gates are met, not just the component
file.

Step 3 of the command's body lists what the DS repo requires alongside the
component: a unit test, a gallery use case, and a docs entry. The test is the
cheapest of those to assert mechanically and the one whose absence most
clearly means the gates were skipped rather than followed.
