"""QpiAI usage log: one block per real QpiAI call (QpiAI Opt MILP, QpiAI SDK QSV-Local, QCloud login / jobs).

Each block goes to stderr (the server console; pipeline steps' output is echoed there by atlas_web/runner.py) and is
appended to logs/qpiai_usage.log (git-ignored; override with QSHIELD_QPIAI_LOG, "off" disables the file). Callers
pass values from the call results only. Never pass keys, tokens or account IDs. Under pytest nothing is appended.
"""

import os
import sys
import threading
import time
from pathlib import Path

SEP = "=" * 40
TAGS = ("[QPIAI OPT]", "[QPIAI QSV]", "[QCLOUD]")
_lock = threading.Lock()


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def origin() -> str:
    """Who asked: a web UI run (the runner sets QSHIELD_UI_WORKSPACE / QSHIELD_UI_RUN_ID) or the command line."""
    ws = os.environ.get("QSHIELD_UI_WORKSPACE")
    if ws:
        return f"Received dispatch request from UI (workspace={ws}, run_id={os.environ.get('QSHIELD_UI_RUN_ID', 'none')})"
    return "Started from the command line (no UI dispatch)"


def log_path() -> Path | None:
    v = os.environ.get("QSHIELD_QPIAI_LOG")
    if v == "off" or "PYTEST_CURRENT_TEST" in os.environ:
        return None
    return Path(v) if v else Path(__file__).resolve().parent / "logs" / "qpiai_usage.log"


def emit(lines: list[str]) -> None:
    text = "\n".join([SEP, *lines, SEP]) + "\n"
    with _lock:
        sys.stderr.write(text)
        sys.stderr.flush()
        p = log_path()
        if p is not None:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a") as f:
                    f.write(text)
            except OSError:
                pass  # logging must never change pipeline behaviour
