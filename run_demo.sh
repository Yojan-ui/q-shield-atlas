#!/usr/bin/env bash
# Q-Shield Atlas: regenerate everything (detect -> proof chain -> schedule -> capture -> gates -> qaoa -> seal ->
# results.json) and open the viz. Local only by default: no QpiAI Opt or QCloud jobs are submitted
# unless --platform / --qcloud are given (both go through the guarded commands). If data/real_ibm_qaoa/ exists,
# the recorded IBM ibm_fez run is attached after QAOA (no IBM access, no jobs; --no-ibm skips it).
#
#   ./run_demo.sh [--no-open] [--report-open] [--platform] [--qcloud] [--allow-more] [--no-ibm]
#
# Env: PYTHON (default: python), QSHIELD_OPENSSL (OpenSSL >= 3.5 binary), QPIAI_OPT_API_KEY,
# QCLOUD_API_KEY (read from .env.sh if present and not already set). Bash 3.2 compatible.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python}"
OPEN=1
REPORT_OPEN=()
PLATFORM_ARGS=()
QCLOUD_ARGS=()
ALLOW_MORE=()
IBM_DIR="data/real_ibm_qaoa"
for arg in "$@"; do
  case "$arg" in
    --no-open) OPEN=0 ;;
    --report-open) REPORT_OPEN=(--open) ;;
    --platform) PLATFORM_ARGS=(--platform) ;;
    --qcloud) QCLOUD_ARGS=(--qcloud) ;;
    --allow-more) ALLOW_MORE=(--allow-more) ;;
    --no-ibm) IBM_DIR="" ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

cleanup() {
  # Lab services are started from temp dirs named qshield-*; kill any that survived (normally none).
  pkill -f "s_server.*qshield-" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'echo; echo "interrupted"; exit 130' INT TERM

LOG_DIR="out/demo_logs"
mkdir -p "$LOG_DIR"
now() { "$PY" -c 'import time; print(f"{time.time():.3f}")'; }
elapsed() { "$PY" -c "import sys; print(f'{float(sys.argv[2]) - float(sys.argv[1]):6.1f}s')" "$1" "$2"; }
fail() { echo "PREFLIGHT FAIL: $1" >&2; echo "  fix: $2" >&2; exit 1; }

T_START=$(now)
echo "== Q-Shield Atlas demo =="
echo "Lab demo · local test ledger · simulator-scale QAOA · assumptions in config/assumptions.json"

# ---------------- preflight ----------------
command -v "$PY" >/dev/null 2>&1 || fail "'$PY' not found" "activate the env (conda activate pqc) or set PYTHON=/path/to/python3.12"
PYVER=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
[ "$PYVER" = "3.12" ] || fail "Python $PYVER found, 3.12 required" "conda activate pqc, or create a 3.12 venv and pip install -r requirements.txt"
"$PY" - <<'EOF' || fail "required Python packages missing or at the wrong version" "pip install -r requirements.txt"
import importlib.metadata as m, re, sys
bad = []
for line in open("requirements.txt"):
    line = line.split("#")[0].strip()
    if not line:
        continue
    name, want = re.split(r"==", line)
    try:
        have = m.version(name)
    except m.PackageNotFoundError:
        bad.append(f"{name} (missing)")
        continue
    if have != want:
        bad.append(f"{name} {have} != pinned {want}")
if bad:
    print("  packages: " + "; ".join(bad), file=sys.stderr)
    sys.exit(1)
EOF
OPENSSL_LINE=$("$PY" -c 'from detect.live_probe import openssl_binary, openssl_info; b = openssl_binary(); print(b, "|", openssl_info(b)["version"])' 2>/dev/null) \
  || fail "no OpenSSL >= 3.5 with X25519MLKEM768 and ML-DSA-65" "conda install -n pqc -c conda-forge openssl=3.6.5, or export QSHIELD_OPENSSL=/path/to/openssl"
"$PY" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); s.close()' \
  || fail "cannot bind a free port on 127.0.0.1" "check local firewall / sandbox settings"
if [ -z "${QPIAI_OPT_API_KEY:-}" ] && [ -f .env.sh ]; then
  # shellcheck disable=SC1091
  source .env.sh
fi
[ -n "${QPIAI_OPT_API_KEY:-}" ] || fail "QPIAI_OPT_API_KEY not set (local QpiAI Opt solves verify the key online)" \
  "export QPIAI_OPT_API_KEY=... (free key at https://opt.qpiai.tech/) or put it in .env.sh (git-ignored)"
if [ ${#QCLOUD_ARGS[@]} -gt 0 ] && [ -z "${QCLOUD_API_KEY:-}" ]; then
  fail "--qcloud given but QCLOUD_API_KEY not set" "export QCLOUD_API_KEY=... or drop --qcloud"
fi
if [ ${#PLATFORM_ARGS[@]} -eq 0 ] && [ ${#QCLOUD_ARGS[@]} -eq 0 ]; then
  export QSHIELD_FORBID_PLATFORM=1   # default run: the guard refuses every paid submission
  MODE_NOTE="local only (no QpiAI Opt or QCloud jobs)"
else
  MODE_NOTE="opt-in: ${PLATFORM_ARGS[*]:-} ${QCLOUD_ARGS[*]:-} (guarded, logged, daily cap)"
fi
echo "preflight OK: Python $PYVER, OpenSSL ${OPENSSL_LINE}, mode: ${MODE_NOTE}"

if [ ! -f keys/ledger_mldsa65.key ]; then
  echo "no ledger signing key found: generating an ML-DSA-65 key pair (keys/ is git-ignored)"
  "$PY" -m ledger keygen
fi

# ---------------- pipeline ----------------
NAMES=""
TIMES=""
STATUS="PASS"
step() {
  local name="$1"; shift
  local t0 t1 log="$LOG_DIR/${name}.log"
  echo
  echo "-- ${name}: $*"
  t0=$(now)
  if "$@" 2>&1 | tee "$log"; then
    t1=$(now)
    NAMES="${NAMES}${name}|"; TIMES="${TIMES}$(elapsed "$t0" "$t1") ok|"
  else
    t1=$(now)
    NAMES="${NAMES}${name}|"; TIMES="${TIMES}$(elapsed "$t0" "$t1") FAILED (see ${log})|"
    STATUS="FAIL"
    summary
    exit 1
  fi
}
summary() {
  echo
  echo "== summary =="
  local IFS='|' i=0 n t
  set -f
  local names=($NAMES) times=($TIMES)
  set +f
  for n in "${names[@]}"; do
    t="${times[$i]}"
    printf "  %-16s %s\n" "$n" "$t"
    i=$((i + 1))
  done
  echo "  total            $(elapsed "$T_START" "$(now)")"
  echo "RESULT: ${STATUS}"
}

# stage order: contracts/stages.json (Detect -> Proof Chain -> Plan -> Handshakes -> Gates -> QAOA -> Seal -> Report)
step detect          "$PY" -m detect --lab-probe web-gw=legacy
step ledger_open     "$PY" -m ledger ingest --only detect.run
step schedule        "$PY" -m schedule --inventory out/inventory.json ${PLATFORM_ARGS[@]+"${PLATFORM_ARGS[@]}"} ${ALLOW_MORE[@]+"${ALLOW_MORE[@]}"}
step capture         "$PY" -m capture
step gates           "$PY" -m gates
step qaoa            "$PY" -m qaoa --qpiai-local ${QCLOUD_ARGS[@]+"${QCLOUD_ARGS[@]}"} ${ALLOW_MORE[@]+"${ALLOW_MORE[@]}"}
if [ -n "$IBM_DIR" ] && [ -f "$IBM_DIR/manifest.json" ]; then
  # part of the QAOA stage: attach the recorded ibm_fez rows (hashes and metrics re-checked; refuses if the
  # week-1 problem differs from the packaged one; rerun with --no-ibm to skip)
  step ibm_import    "$PY" -m qaoa --ibm-import "$IBM_DIR"
fi
step ledger_ingest   "$PY" -m ledger ingest
step ledger_verify   "$PY" -m ledger verify
step assemble        "$PY" -m contracts.assemble
step validate        "$PY" -m contracts validate results out/results.json
step report          "$PY" -m atlas report ${REPORT_OPEN[@]+"${REPORT_OPEN[@]}"}
step validate_final  "$PY" -m contracts validate results out/results.json
summary

if [ "$OPEN" -eq 1 ]; then
  echo
  echo "opening the viz (Ctrl+C to stop)"
  "$PY" -m viz
fi
