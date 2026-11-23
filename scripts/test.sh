#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/runtime.sh"
cd "$AXON_ROOT"
.venv/bin/python -m pytest backend/tests "$@"
if [[ -n "$AXON_NODE" && -d frontend/node_modules ]]; then
 cd frontend
 "$AXON_NODE" node_modules/typescript/bin/tsc -b
 "$AXON_NODE" node_modules/vite/bin/vite.js build
fi
