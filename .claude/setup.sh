#!/usr/bin/env bash
set -euo pipefail

echo
echo "========================================"
echo "  Clef -- AI Composition Dependencies"
echo "========================================"
echo

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found. Install Python 3.10+ from https://python.org"
    exit 1
fi
echo "  Python: $(python3 --version)"

# Create venv
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating isolated environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate and install
echo "  Installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install -r "$SCRIPT_DIR/requirements.txt" --quiet

# Verify
echo "  Verifying..."
python3 "$SCRIPT_DIR/skills/clef-compose/scripts/check_dependencies.py"

echo
echo "  Done! The venv is at: $VENV_DIR"
echo "  To activate manually: source $VENV_DIR/bin/activate"
echo