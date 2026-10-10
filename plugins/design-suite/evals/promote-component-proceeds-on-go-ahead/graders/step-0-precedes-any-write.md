---
type: tool_order
before: Bash
after: Write
---

Step 0 runs before anything is built.

The command's body: "You never skip Step 0" and "Build a new design-system
component without running Step 0 first" is in its never-do list. The most
common correct outcome is finding the component already exists, which is only
reachable if the search precedes the building.
