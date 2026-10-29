#!/usr/bin/env bash
# Start the Q-Shield Atlas web app on http://127.0.0.1:8000/ (macOS / Linux).
cd "$(dirname "$0")"
eval "$(conda shell.bash hook)"
conda activate pqc
[ -f .env.sh ] && source .env.sh
python -m atlas_web --port 8000
