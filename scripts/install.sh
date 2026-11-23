#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/runtime.sh"
umask 077
cd "$AXON_ROOT"
if [[ -z "${AXON_PYTHON:-}" ]] || ! "$AXON_PYTHON" -c 'import sys; sys.exit(sys.version_info[:2] not in {(3, 12), (3, 13)})'; then
  echo 'Instala Python 3.12 o 3.13. Usa AXON_PYTHON para elegir el ejecutable.' >&2
  exit 1
fi
if [[ -z "$AXON_NODE" ]] || ! "$AXON_NODE" -e 'const [major,minor]=process.versions.node.split(".").map(Number);process.exit(major>=24 || major===22&&minor>=13 ? 0:1)'; then
  echo 'Instala Node.js 22.13+ o 24.' >&2
  exit 1
fi
export PATH="$(dirname "$AXON_NODE"):$PATH"
if ! command -v pnpm >/dev/null; then
  echo 'Instala pnpm 11 o añade su ejecutable a PATH.' >&2
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then "$AXON_PYTHON" -m venv .venv; fi
.venv/bin/python -m pip install -r backend/requirements.lock
(
  cd frontend
  pnpm install --frozen-lockfile
  pnpm run build
)
.venv/bin/python -m app.cli init
printf '%s\n' 'AXON instalado. Si es la primera vez, ejecuta ./scripts/setup-admin.sh. Abre AXON con ./scripts/start.sh.'
