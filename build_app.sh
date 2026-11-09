#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
.venv/bin/pip install -q pyinstaller
.venv/bin/pyinstaller --noconfirm --clean sevenbeing.spec
echo "Built: dist/7Being/"
