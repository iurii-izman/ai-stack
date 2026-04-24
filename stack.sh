#!/usr/bin/env bash
set -euo pipefail

if ! command -v python >/dev/null 2>&1; then
  echo "python not found. Install Python 3.11+ to use ./stack.sh." >&2
  exit 1
fi

exec python "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ops/ai_stack.py" "$@"
