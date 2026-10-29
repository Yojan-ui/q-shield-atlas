#!/usr/bin/env bash
# Start the Q-Shield Atlas web app on http://127.0.0.1:8000/ (conda env pqc and .env.sh are used when present).
set -euo pipefail
cd "$(dirname "$0")"
if command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | grep -qE '^pqc\s'; then
  eval "$(conda shell.bash hook)"
  conda activate pqc
fi
if [ -f .env.sh ]; then
  # shellcheck disable=SC1091
  source .env.sh
fi
echo "Q-Shield Atlas: http://127.0.0.1:8000/ (Ctrl+C to stop)"
exec python -m atlas_web --port 8000 --no-browser
