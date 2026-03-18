#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
    echo "[ERROR] Virtual environment not found."
    echo "        Run: bash install.sh"
    exit 1
fi

MODEL_PATH=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c['llm']['model_path'])" 2>/dev/null || echo "")
if [[ -n "$MODEL_PATH" && ! -f "$SCRIPT_DIR/$MODEL_PATH" ]]; then
    echo "[ERROR] Model not found: $MODEL_PATH"
    echo "        Run: bash install.sh"
    exit 1
fi

PW=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c['web']['password'])" 2>/dev/null || echo "changeme")
if [[ "$PW" == "changeme" ]]; then
    echo ""
    echo "  [WARN] You are using the default password 'changeme'."
    echo "         Edit config.yaml to set a secure password."
    echo ""
fi

source "$VENV_DIR/bin/activate"

LOCAL_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "localhost")
PORT=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c['web']['port'])" 2>/dev/null || echo "7777")

echo ""
echo "  Starting Companion Core..."
echo "  Access at: http://${LOCAL_IP}:${PORT}"
echo ""

cd "$SCRIPT_DIR"
exec python3 main.py
