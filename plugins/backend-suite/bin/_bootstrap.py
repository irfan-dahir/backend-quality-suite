"""Locate the two roots these tools need, which stopped being the same directory.

Inside the app repo every script could say `parents[2]` and mean both "where the
suite lives" and "the project being audited". Installed as a plugin those are
different places — the code sits in the plugin cache, the project sits wherever
the user is working — so conflating them silently pointed the audits at the plugin
directory instead of the project.

  PLUGIN_ROOT   where this plugin's own code and data live
  project_root() the repository being audited

`project_root()` prefers `CLAUDE_PROJECT_DIR` (exported by Claude Code), then
walks up from the working directory looking for a `.backend-suite/` profile. The
marker matters: a plain `cwd` would silently audit a subdirectory as if it were the
whole project, which reports fewer findings and looks like an improvement.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MARKER = ".backend-suite"

# So `import backend_suite` resolves to this plugin's copy.
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from backend_suite.project import project_root  # noqa: E402,F401
