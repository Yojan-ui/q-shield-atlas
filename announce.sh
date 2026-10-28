#!/usr/bin/env bash
# Q-Shield Atlas launch screen: ./announce.sh [--fast] [--json]
set -euo pipefail
cd "$(dirname "$0")"
exec "${PYTHON:-python}" -m atlas announce "$@"
