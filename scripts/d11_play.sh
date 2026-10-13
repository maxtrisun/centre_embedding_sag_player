#!/usr/bin/env bash
# Wrapper: play with exported certificates.
#   ./d11_play.sh --n 6                    # batch JSON, P2=pruned-random
#   ./d11_play.sh --n 6 --interactive      # ASCII vs cert (or use d11_interact.sh)
#   ./d11_play.sh --list
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/build:${ROOT}/scripts:${PYTHONPATH:-}"
exec python3 "${ROOT}/scripts/play_game.py" "$@"
