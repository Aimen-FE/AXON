#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/runtime.sh"
cd "$AXON_ROOT/frontend"
if [[ -z "$AXON_NODE" ]]; then echo 'Node.js no disponible' >&2; exit 1; fi
exec "$AXON_NODE" node_modules/vite/bin/vite.js --host 127.0.0.1 "$@"
