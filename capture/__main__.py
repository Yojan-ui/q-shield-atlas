"""python -m capture  ->  out/capture.json, out/handshake_evidence.json, out/gates.json, runs/<run_id>/

Starts the local lab TLS 1.3 services, records one handshake per service with a modern client
(hybrid + classical groups offered) and one with a classical-only client, then evaluates the PQ
handshake gate from capture.json. Handshake metadata only: nothing is decrypted.
"""

import argparse
import json
from pathlib import Path

from contracts import validate
from contracts.manifest import new_run_id, sha256_json, utc_now
from detect.live_probe import openssl_binary, openssl_info
from gates.pq_handshake import evaluate

from .handshake import record
from .services import REPO, lab_services, load_lab


def capture_all(lab: dict, run_dir: Path) -> dict:
    run_id = new_run_id()
    info = openssl_info(openssl_binary())
    if not info["ml_kem"]:
        raise RuntimeError(f"{info['version']} has no ML-KEM; lab needs OpenSSL >= 3.5 (conda env pqc)")
    sessions, refused = [], []
    timeout = lab["timeouts_s"]["handshake"]
    with lab_services(lab) as services:
        for sid, svc in services.items():
            for kind, groups in (("client", lab["client_groups"]), ("classical-only", lab["classical_only_client_groups"])):
                rec = record(sid, svc.host, svc.port, groups, run_dir / run_id, f"{sid}_{kind}", timeout)
                if rec.pop("established"):
                    sessions.append(rec)
                else:
                    refused.append({**rec, "established": False})
    capture = {
        "schema_version": "2.0",
        "run_id": run_id,
        "generated_at": utc_now(),
        "openssl_version": info["version"],
        "sessions": sessions,
        "refused_attempts": refused,
    }
    validate("capture", capture)
    return capture


def handshake_evidence(capture: dict, gates: dict) -> dict:
    return {
        "run_id": capture["run_id"],
        "ts": capture["generated_at"],
        "capture_sha256": sha256_json(capture),
        "openssl_version": capture["openssl_version"],
        "note": "Real TLS 1.3 handshakes with local lab services; metadata only. No decryption is performed or claimed.",
        "sessions": [
            {k: g[k] for k in ("service_id", "negotiated_group", "kex_class", "hndl_exposed", "label", "transcript_sha256")}
            for g in gates["pq_handshake"]
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=REPO / "out")
    ap.add_argument("--runs", type=Path, default=REPO / "runs")
    args = ap.parse_args(argv)

    lab = load_lab()
    capture = capture_all(lab, args.runs)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    capture_path = args.out_dir / "capture.json"
    capture_path.write_text(json.dumps(capture, indent=1))

    gates = evaluate(json.loads(capture_path.read_text()), lab)  # gates read the contract file only
    evidence = handshake_evidence(capture, gates)
    (args.out_dir / "gates.json").write_text(json.dumps(gates, indent=1))
    (args.out_dir / "handshake_evidence.json").write_text(json.dumps(evidence, indent=1))
    run_dir = args.runs / capture["run_id"]
    (run_dir / "manifest.json").write_text(json.dumps(
        {"run_id": capture["run_id"], "ts": capture["generated_at"], "capture_sha256": evidence["capture_sha256"],
         "openssl_version": capture["openssl_version"], "gates": gates}, indent=1))

    print(f"capture run {capture['run_id']} ({capture['openssl_version']}) -> {capture_path}")
    for s in capture["sessions"]:
        print(f"  session  {s['service_id']:7} offered={s['client_groups_offered']:24} negotiated={s['negotiated_group']:15} "
              f"{s['protocol']} {s['cipher']} cert={s['cert_alg']} transcript={s['transcript_sha256'][:16]}")
    for a in capture["refused_attempts"]:
        print(f"  refused  {a['service_id']:7} offered={a['client_groups_offered']:24} error={a['error']}")
    for g in gates["pq_handshake"]:
        print(f"  gate pq_handshake  {g['service_id']:7} {g['result']}  {g['reason']}" + (f"  [{g['label']}]" if g["label"] else ""))
    for g in gates["downgrade"]:
        print(f"  gate downgrade     {g['service_id']:7} {g['result']}  {g['reason']}")


if __name__ == "__main__":
    main()
