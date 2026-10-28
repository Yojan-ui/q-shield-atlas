"""python -m atlas announce [--fast] [--json]

Terminal launch screen read from out/results.json, the ledger and pytest's JUnit report.
Without --fast the test suite is run first (QpiAI platform/QCloud submissions stay forbidden)
so the module status is current; --fast uses the last recorded test run.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .announce import REPO, collect, junit_counts, load_json, render


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["announce"])
    ap.add_argument("--fast", action="store_true", help="skip running pytest; use out/pytest-junit.xml from the last run")
    ap.add_argument("--json", action="store_true", help="print the collected data as JSON instead of the screen")
    ap.add_argument("--results", default=str(REPO / "out" / "results.json"))
    args = ap.parse_args(argv)

    junit_path = REPO / "out" / "pytest-junit.xml"
    if not args.fast:
        print("running the test suite for module status (use --fast to skip)...", file=sys.stderr, flush=True)
        env = {**os.environ, "QSHIELD_FORBID_PLATFORM": "1"}
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", f"--junitxml={junit_path}"],
                       cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    data = collect(load_json(Path(args.results)), junit_counts(junit_path))
    if args.json:
        print(json.dumps(data, indent=1, ensure_ascii=False))
        return 0
    from rich.console import Console

    render(data, Console())
    return 0


if __name__ == "__main__":
    sys.exit(main())
