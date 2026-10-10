#!/usr/bin/env bash
# Materialise the `app` fixture into the empty workspace.
# Runs only under `--scaffold`; see ../_lib/scaffold.sh for why it fails loudly.
set -euo pipefail
exec bash "$(cd "$(dirname "$0")/../_lib" && pwd)/scaffold.sh" app
