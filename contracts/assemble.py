"""python -m contracts.assemble  ->  out/results.json from module sections in out/.

Sections from modules that have not run yet are null. The output must validate against
contracts/results.schema.json before it is written.
"""

import json
from pathlib import Path

from . import validate
from .manifest import utc_now

OUT = Path(__file__).resolve().parent.parent / "out"
LATER_SECTIONS = ("detect", "handshake_evidence", "gates", "qaoa")


def assemble(out_dir: Path = OUT) -> dict:
    results = {"schema_version": "1.0", "generated_at": utc_now()}
    results.update(json.loads((out_dir / "schedule.json").read_text()))
    for name in LATER_SECTIONS:
        path = out_dir / f"{name}.json"
        results[name] = json.loads(path.read_text()) if path.exists() else None
    waves_path = out_dir / "wave_status.json"
    if waves_path.exists():  # wave runner verdicts replace the planned statuses
        run = json.loads(waves_path.read_text())
        by_week = {w["week"]: w for w in run["waves"]}
        if sorted(by_week) != sorted(w["week"] for w in results["waves"]):
            raise ValueError("wave_status.json does not match the scheduled waves; rerun python -m gates")
        results["waves"] = [{**w, **{k: by_week[w["week"]][k] for k in ("status", "asset_status", "evidence")}} for w in results["waves"]]
        for a in results["assets"]:
            a["status"] = run["asset_status"].get(a["id"], "planned")
    ledger = out_dir / "ledger.json"
    results["ledger"] = json.loads(ledger.read_text()) if ledger.exists() else None
    results["ledger_root"] = results["ledger"]["root"] if results["ledger"] else None
    validate("results", results)
    return results


def main():
    results = assemble()
    (OUT / "results.json").write_text(json.dumps(results, indent=1))
    print(f"wrote {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
