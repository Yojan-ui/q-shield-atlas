"""python -m contracts.assemble  ->  out/results.json from module sections in out/.

Sections from modules that have not run yet are null. The output must validate against
contracts/results.schema.json before it is written.
"""

import json
from pathlib import Path

from . import validate
from .manifest import utc_now

OUT = Path(__file__).resolve().parent.parent / "out"
LATER_SECTIONS = ("detect", "attack", "gates", "qaoa")


def assemble(out_dir: Path = OUT) -> dict:
    results = {"schema_version": "1.0", "generated_at": utc_now()}
    results.update(json.loads((out_dir / "schedule.json").read_text()))
    for name in LATER_SECTIONS:
        path = out_dir / f"{name}.json"
        results[name] = json.loads(path.read_text()) if path.exists() else None
    ledger = out_dir / "ledger_root.txt"
    results["ledger_root"] = ledger.read_text().strip() if ledger.exists() else None
    validate("results", results)
    return results


def main():
    results = assemble()
    (OUT / "results.json").write_text(json.dumps(results, indent=1))
    print(f"wrote {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
