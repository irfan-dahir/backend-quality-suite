---
type: regex
target: trace
pattern: '"file_path"\s*:\s*"/(Users|home)/'
match: not_contains
---

NEGATIVE CONTROL for this case.

Every path the run writes is relative to the run base. A command that has been
told "the design system is the sibling checkout" and goes looking for a real
one on the host — `~/…/<design-system-repo>`, or any absolute path under a home
directory — is doing the thing this case exists to bound, and the sandbox
blocking it is not a reason to leave it unasserted.

This grader is also the honest limit of the case: it proves the command wrote
across a *directory* boundary without proving it would behave on two real
checkouts with two real remotes. See case.yaml.

## Why the bare `path` key is NOT matched

The pattern used to read `"(file_path|path)"`. That alternative made this
grader **unpassable in the with-plugin arm and free in the without-plugin
arm**, which is the reverse of what a negative control is for.

The harness's own `system`/`init` trace event — the first line of every
`trace.jsonl`, written before the model takes a turn — carries the plugin under
test as `plugins[].path`, an absolute path to wherever the suite was invoked
from:

    {"type":"system","subtype":"init", … "plugins":[{…,"path":
     "/Users/<user>/…/ai-design-suite/plugins/design-suite"}] … }

In the without-plugin arm `plugins` is `[]`, so no such path exists.

Measured on the 2026-09-18T03-06-49-269Z run: all three with-plugin runs
reported `pattern found (expected absent)` and all three without-plugin runs
reported `pattern absent as expected`. Grepping the surviving traces from that
run confirms the init record was the **only** match in the whole trace — there
were zero `file_path` matches, i.e. the model never once reached for a host
path. The grader was scoring "was a plugin loaded", not "did the run stay
inside its base", and it did so **conditionally on where the suite was invoked
from**: traces from a run launched out of `/private/tmp/…` carry no
home-directory path and would have passed.

`file_path` is the input key of `Read`, `Write`, `Edit` and `NotebookEdit`, and
appears nowhere in harness metadata, so it discriminates the thing this control
is actually about.

**Residual gap, stated rather than papered over:** `Glob` and `Grep` address
their scope with the bare `path` key and `Bash` with `command`, so a run that
*listed* or *shelled at* a real host checkout without reading or writing a file
there is no longer caught here. Narrowing the control to something it can
actually fail on is worth that, but it is a narrowing.
