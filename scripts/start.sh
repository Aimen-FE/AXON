#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/runtime.sh"
umask 077
cd "$AXON_ROOT"
if [[ ! -x .venv/bin/python || ! -f frontend/dist/index.html ]]; then
 echo 'Ejecuta primero ./scripts/install.sh' >&2; exit 1
fi
exec .venv/bin/python -m app.cli serve "$@"
