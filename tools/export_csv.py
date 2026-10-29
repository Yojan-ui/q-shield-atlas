"""tools/export_csv.py: write the project's data as clean CSV, real and synthetic kept in separate, labelled files.

    python tools/export_csv.py [--probes DETECT_JSON ...]

data/real_crypto_observations.csv     REAL. Two record types, one table:
    static_finding   crypto found by the static scan in public repos at pinned commits (out/real_repos/*.json,
                     from python -m detect.real_repos): file, line, rule, algorithm family
    live_handshake   TLS 1.3 handshakes with public endpoints (detect --probe), from the given detect.json files
                     (default: the real-repo workspaces' out/detect.json, which probe the reference endpoints)
data/SYNTHETIC_mock_bank_assets.csv   SYNTHETIC. The fictional 16-asset mock-bank inventory used by the demo
                                      (schedule/data/mock_bank_assets.json). Not real data.
data/sources.json                     SHA-256 of every input file, so each row traces back to a logged run.

The column meanings, units and sources are in data/DATA_DICTIONARY.md. Lab handshakes (local services on
127.0.0.1 with lab certificates) are regenerated on every run and are not exported as a dataset.
"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
DATA = REPO / "data"
REAL_CSV = DATA / "real_crypto_observations.csv"
SYNTH_CSV = DATA / "SYNTHETIC_mock_bank_assets.csv"
DEFAULT_PROBES = [REPO / "atlas_web" / "data" / "workspaces" / w / "out" / "detect.json" for w in ("otel-demo", "online-boutique")]
VULNERABLE = {"RSA", "ECC", "DH", "DSA"}  # detect/inventory.py

REAL_COLUMNS = ["record_type", "source_name", "source_url", "source_commit", "observed_at_utc", "run_id",
                "file", "line", "rule", "crypto_family", "use", "confidence", "quantum_vulnerable",
                "endpoint", "tls_protocol", "key_exchange_group", "cipher", "cert_algorithm", "handshake_transcript_sha256"]
SYNTH_COLUMNS = ["asset_id", "name", "kind", "data_class", "algorithm", "depends_on", "synthetic"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def vuln(family: str) -> str:
    return "true" if family in VULNERABLE else "false" if family == "PQC" else "unknown"


def real_rows(repo_scans: list[Path], probe_files: list[Path]) -> list[dict]:
    rows = []
    for p in sorted(repo_scans):
        d = json.loads(p.read_text())
        for f in sorted(d["findings"], key=lambda f: (f["file"], f["line"], f["rule"])):
            rows.append({"record_type": "static_finding", "source_name": d["root"], "source_url": d["url"],
                         "source_commit": d["commit"], "observed_at_utc": d["ts"], "run_id": d["run_id"],
                         "file": f["file"], "line": f["line"], "rule": f["rule"], "crypto_family": f["family"],
                         "use": f["use"], "confidence": f["confidence"], "quantum_vulnerable": vuln(f["family"])})
    seen = set()
    for p in probe_files:
        d = json.loads(p.read_text())
        for pr in d.get("probes", []):
            lv = pr.get("live") or {}
            if not lv.get("handshake_ok") or pr["endpoint"].startswith("127.") or lv["transcript_sha256"] in seen:
                continue  # public endpoints only; lab services are not a dataset
            seen.add(lv["transcript_sha256"])
            rows.append({"record_type": "live_handshake", "source_name": pr["service"], "source_url": f"https://{pr['endpoint'].rsplit(':', 1)[0]}/",
                         "observed_at_utc": lv["ts"], "run_id": d["run_id"], "crypto_family": lv["kex_family"],
                         "use": "kex", "quantum_vulnerable": "true" if lv["kex_quantum_vulnerable"] else "false",
                         "endpoint": pr["endpoint"], "tls_protocol": lv["protocol"], "key_exchange_group": lv["group"],
                         "cipher": lv["cipher"], "cert_algorithm": lv["cert_algorithm"],
                         "handshake_transcript_sha256": lv["transcript_sha256"]})
    return rows


def synthetic_rows(path: Path) -> list[dict]:
    d = json.loads(path.read_text())
    return [{"asset_id": a["id"], "name": a["name"], "kind": a["kind"], "data_class": a["data_class"],
             "algorithm": a["algorithm"], "depends_on": ";".join(a["depends_on"]), "synthetic": "true"} for a in d["assets"]]


def write(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probes", nargs="*", type=Path, default=None, help="detect.json files with public-endpoint probes")
    args = ap.parse_args(argv)
    scans = sorted((REPO / "out" / "real_repos").glob("*.json"))
    probes = [p for p in (args.probes if args.probes is not None else DEFAULT_PROBES) if p.exists()]
    if not scans:
        sys.exit("no out/real_repos/*.json: run python -m detect.real_repos first")
    synth_src = REPO / "schedule" / "data" / "mock_bank_assets.json"
    DATA.mkdir(exist_ok=True)
    real = real_rows(scans, probes)
    write(REAL_CSV, REAL_COLUMNS, real)
    write(SYNTH_CSV, SYNTH_COLUMNS, synthetic_rows(synth_src))
    sources = {"real": [{"path": p.relative_to(REPO).as_posix(), "sha256": sha(p)} for p in scans + probes],
               "synthetic": [{"path": synth_src.relative_to(REPO).as_posix(), "sha256": sha(synth_src)}],
               "outputs": [{"path": p.relative_to(REPO).as_posix(), "sha256": sha(p)} for p in (REAL_CSV, SYNTH_CSV)]}
    (DATA / "sources.json").write_text(json.dumps(sources, indent=1) + "\n")
    kinds = {k: sum(r["record_type"] == k for r in real) for k in ("static_finding", "live_handshake")}
    print(f"wrote {REAL_CSV.relative_to(REPO)}: {len(real)} rows {kinds}; {SYNTH_CSV.relative_to(REPO)} (synthetic)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
