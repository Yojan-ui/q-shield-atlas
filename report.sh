#!/usr/bin/env bash
# Build out/report.html (self-contained, offline), sign it into the ledger, verify, and open it.
set -euo pipefail
cd "$(dirname "$0")"
"${PYTHON:-python}" -m atlas report "$@"
if [ -f out/report.html ]; then
  if command -v open >/dev/null 2>&1; then open out/report.html
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open out/report.html
  else echo "open out/report.html in a browser"; fi
fi
