"""python -m contracts.assemble [--out-dir DIR]  ->  DIR/results.json from module sections in DIR (default out/).

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
    verify_path = out_dir / "ledger_verify.json"
    results["ledger_verification"] = json.loads(verify_path.read_text()) if verify_path.exists() else None
    if results["qaoa"] is not None:
        from qaoa.table import build_table

        ref = f"runs/{results['qaoa']['run_id']}/manifest.json"
        entries = (results["ledger"] or {}).get("entries", [])
        idx = next((e["index"] for e in entries if e["payload_ref"] == ref and e["type"] == "qaoa.run"), None)
        results["qaoa"]["ledger_index"] = idx
        results["qaoa"]["table"] = build_table(results["qaoa"], idx)
    validate("results", results)
    return results


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args(argv)
    results = assemble(args.out_dir)
    (args.out_dir / "results.json").write_text(json.dumps(results, indent=1))
    print(f"wrote {args.out_dir / 'results.json'}")


if __name__ == "__main__":
    main()
