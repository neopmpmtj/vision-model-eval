#!/usr/bin/env bash
set -Eeuo pipefail

RUN_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RUN_SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
    printf '%s\n' "Virtual environment not found. Run the setup installer again." >&2
    exit 1
fi

exec .venv/bin/streamlit run app.py
