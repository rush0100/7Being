#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c "import sevenbeing" 2>/dev/null; then
  .venv/bin/pip install -e .
fi
# Device plugins (sibling repos) — install if present and missing.
if [[ -d "$ROOT/7being-emotiv-epocx" ]] && ! .venv/bin/python -c "import sevenbeing_epocx" 2>/dev/null; then
  .venv/bin/pip install -e "$ROOT/7being-emotiv-epocx"
fi
if [[ -d "$ROOT/7being-h1" ]] && ! .venv/bin/python -c "import sevenbeing_h1" 2>/dev/null; then
  .venv/bin/pip install -e "$ROOT/7being-h1"
fi
if [[ -d "$ROOT/7being-ads1299" ]] && ! .venv/bin/python -c "import sevenbeing_ads1299" 2>/dev/null; then
  .venv/bin/pip install -e "$ROOT/7being-ads1299"
fi
# Prefer gRPC device daemons when SEVENBEING_DEVICE_GRPC is set, e.g.
#   export SEVENBEING_DEVICE_GRPC=127.0.0.1:51051
exec .venv/bin/python -m sevenbeing
