#!/usr/bin/env bash
set -euo pipefail
workspace=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
repo="$HOME/projects/LIBERO-LOHO"
mkdir -p "$HOME/projects" "$workspace/setup_logs"
if [[ ! -d "$repo/.git" ]]; then
    git clone --depth 1 https://github.com/markli1hoshipu/LIBERO-LOHO.git "$repo"
fi
printf 'Repository revision: '
git -C "$repo" rev-parse HEAD
if [[ ! -x "$HOME/.local/bin/uv" ]]; then
    curl -LsSf https://astral.sh/uv/install.sh -o "$workspace/setup_logs/install_uv.sh"
    bash "$workspace/setup_logs/install_uv.sh"
fi
uv="$HOME/.local/bin/uv"
"$uv" python install 3.8
if [[ ! -x "$repo/.venv/bin/python" ]]; then
    "$uv" venv --python 3.8 "$repo/.venv"
fi
printf 'Isolated runtime: '
"$repo/.venv/bin/python" --version
bash "$workspace/scripts/install_wsl_dependencies.sh"
