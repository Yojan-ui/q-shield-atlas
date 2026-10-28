"""Guardrails for paid QpiAI Opt platform submissions.

- Platform mode is opt-in (`python -m schedule --platform`); the default is local.
- QSHIELD_FORBID_PLATFORM=1 (set by pytest and run_demo.sh) refuses every submission.
- Every submission is announced ("Submitting N QpiAI jobs"), written to the stage's run
  directory, and appended to runs/platform_jobs.log before it is sent.
- At most DAILY_LIMIT submissions per UTC day unless allow_more=True (--allow-more).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from contracts.manifest import utc_now

from .problem import REPO

DAILY_LIMIT = 10
DEFAULT_LOG = REPO / "runs" / "platform_jobs.log"
FORBID_ENV = "QSHIELD_FORBID_PLATFORM"


class PlatformRefused(RuntimeError):
    pass


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class PlatformBudget:
    def __init__(self, log_path: Path = DEFAULT_LOG, allow_more: bool = False, daily_limit: int = DAILY_LIMIT):
        self.log_path = Path(log_path)
        self.allow_more = allow_more
        self.daily_limit = daily_limit

    def _events(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text().splitlines() if line.strip()]

    def used_today(self) -> int:
        today = _today()
        return sum(e["n"] for e in self._events() if e["event"] == "submit" and e["date"] == today)

    def check(self, n: int) -> None:
        """Refuse before anything is sent if `n` more submissions are not allowed."""
        if os.environ.get(FORBID_ENV) == "1":
            raise PlatformRefused(f"{FORBID_ENV}=1: platform submissions are disabled here")
        used = self.used_today()
        if used + n > self.daily_limit and not self.allow_more:
            raise PlatformRefused(
                f"{used} QpiAI platform jobs already submitted today (UTC); {n} more would exceed "
                f"the daily limit of {self.daily_limit}. Pass --allow-more to override."
            )

    def _append(self, event: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a") as fh:
            fh.write(json.dumps(event) + "\n")

    def reserve(self, n: int, run_id: str, stage: str, run_dir: Path) -> None:
        self.check(n)
        message = f"Submitting {n} QpiAI jobs (run_id={run_id}, stage={stage})"
        print(message, flush=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / "platform_submit.log").open("a") as fh:
            fh.write(f"{utc_now()} {message}\n")
        self._append({"event": "submit", "ts": utc_now(), "date": _today(), "run_id": run_id, "stage": stage, "n": n})

    def record(self, run_id: str, **fields) -> None:
        self._append({"event": "result", "ts": utc_now(), "date": _today(), "run_id": run_id, **fields})
