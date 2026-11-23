#!/usr/bin/env bash
set -euo pipefail
AXON_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${AXON_PYTHON:-}" ]]; then
  for candidate in "$AXON_ROOT/.venv/bin/python" python3.12 python3.13 python3; do
    if command -v "$candidate" >/dev/null; then AXON_PYTHON="$(command -v "$candidate")"; break; fi
  done
fi
if [[ -z "${AXON_NODE:-}" ]]; then AXON_NODE="$(command -v node || true)"; fi
export AXON_ROOT AXON_PYTHON AXON_NODE
export PYTHONPATH="$AXON_ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
