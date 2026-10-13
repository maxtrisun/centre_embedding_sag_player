#!/usr/bin/env bash
# Interactive ASCII play vs exported DAG / merge certificate.
#   ./d11_interact.sh --n 6
#   ./d11_interact.sh --n 18
#   ./d11_interact.sh --n 6 --side p1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/build:${ROOT}/scripts:${PYTHONPATH:-}"
exec python3 "${ROOT}/scripts/play_game.py" --interactive "$@"
