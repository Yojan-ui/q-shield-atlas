"""The pipeline stages (contracts/stages.json): one list for the runner, run_demo.sh, the API and the UI.

    python -m contracts.stages              print the step names, one per line (run_demo.sh order)
    python -m contracts.stages --write-js   regenerate atlas_web/static/js/stages.js
    python -m contracts.stages --check-js   exit 1 if stages.js is out of date
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JS = HERE.parent / "atlas_web" / "static" / "js" / "stages.js"
DOC = json.loads((HERE / "stages.json").read_text())
STAGES = DOC["stages"]
STEPS = tuple(s for st in STAGES for s in st["steps"])
STAGE_OF = {s: st["id"] for st in STAGES for s in st["steps"]}


def js_source() -> str:
    body = json.dumps(STAGES, indent=1)
    return ("// Generated from contracts/stages.json by python -m contracts.stages --write-js. Do not edit.\n"
            f"export const STAGES = {body};\n"
            "export const STEPS = STAGES.flatMap((s) => s.steps);\n"
            "export const STAGE_OF = Object.fromEntries(STAGES.flatMap((s) => s.steps.map((step) => [step, s])));\n")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--write-js" in argv:
        JS.write_text(js_source())
        print(f"wrote {JS}")
    elif "--check-js" in argv:
        if not JS.exists() or JS.read_text() != js_source():
            print(f"{JS} is out of date: python -m contracts.stages --write-js", file=sys.stderr)
            return 1
    else:
        print("\n".join(STEPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
