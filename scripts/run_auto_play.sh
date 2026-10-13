#!/usr/bin/env bash
# Auto-play all exported certificates: P1=cert vs P2=pruned-random.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/build:${ROOT}/scripts:${PYTHONPATH:-}"
exec python3 "${ROOT}/scripts/auto_play.py" "$@"
