#!/usr/bin/env bash
set -euo pipefail
workspace=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
repo="${LOHO_REPO:-$HOME/projects/LIBERO-LOHO}"
export LOHO_REPO="$repo"
export MUJOCO_GL="${MUJOCO_GL:-osmesa}"
if [[ "$MUJOCO_GL" == osmesa ]]; then export PYOPENGL_PLATFORM=osmesa; fi
exec "$repo/.venv/bin/python" -u "$workspace/src/loho_frontier_eval.py" "$@"

