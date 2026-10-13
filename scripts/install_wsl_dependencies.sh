#!/usr/bin/env bash
set -euo pipefail
workspace=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
repo="$HOME/projects/LIBERO-LOHO"
uv="$HOME/.local/bin/uv"
"$uv" pip install --python "$repo/.venv/bin/python" \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --index-strategy unsafe-best-match -r "$workspace/requirements-sim.txt"
"$uv" pip install --python "$repo/.venv/bin/python" -e "$repo"
"$uv" pip check --python "$repo/.venv/bin/python"
"$uv" pip freeze --python "$repo/.venv/bin/python" > "$workspace/setup_logs/wsl-freeze.txt"

