#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/runtime.sh"
cd "$AXON_ROOT"
umask 077
exec .venv/bin/python -m app.cli restore "$@"
