"""tools/scan_banks.py: a polite TLS observation of public Indian bank endpoints (CC0 dataset, pinned).

    python tools/scan_banks.py targets      # build data/real_banks/targets.csv from the pinned dataset
    python tools/scan_banks.py scan         # one TLS handshake per target -> data/real_banks/scan_<date>.csv
    python tools/scan_banks.py workspace    # write the scan into a workspace src/ (one folder per endpoint)
    python tools/scan_banks.py publish      # create workspace real-banks via the atlas_web API, run the pipeline,
                                            # then sign the scan manifest into its Proof Chain (bank_scan.run)

Dataset: https://github.com/CCAgentOrg/bank-in-domains (CC0 1.0), commit 7b161ae, data/bank_domains_status.csv.
Selection (deterministic): https_works == True; host names whose tokens contain uat/dev/test/stg/staging/sit/
preprod/cug/internal/vpn/admin are excluded; only the apex, www. and netbanking. host of each bank (at most 3);
banks taken in SHA-256(bank name) order (a reproducible spread, not a ranking) until 60 hosts.
Probe: detect/live_probe.probe(host, 443) = one `openssl s_client` TLS handshake (offering X25519MLKEM768,
X25519, P-256), 8 s timeout, at most 4 at a time. No HTTP request, no other port, no retry, no scanning.
Classification of the negotiated key exchange: hybrid_pq / classical (quantum-vulnerable) / unreachable.
This is an observation of public endpoints, not an assessment of any bank's security.
"""

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
DATASET_URL = "https://github.com/CCAgentOrg/bank-in-domains"
COMMIT = "7b161ae37caa39703db0e9fd6b51ab8521a02da4"
CLONE = REPO / ".cache" / "repos" / "bank-in-domains"
OUT = REPO / "data" / "real_banks"
EXCLUDE = re.compile(r"(uat|dev|test|stg|staging|preprod|cug|internal|vpn|admin)")
EXCLUDE_EXACT = {"sit"}
MAX_HOSTS, PER_BANK, TIMEOUT_S, CONCURRENCY = 60, 3, 8, 4
TARGET_COLS = ["bank", "host", "endpoint", "port", "source_row_status_code", "dataset_commit"]
SCAN_COLS = ["bank", "host", "endpoint", "port", "observed_at_utc", "outcome", "tls_version", "negotiated_group",
             "cipher", "cert_key_algorithm", "cert_signature_algorithm", "cert_issuer", "cert_not_after",
             "kex_quantum_vulnerable", "auth_quantum_vulnerable", "transcript_sha256", "error"]


def git_show(path: str) -> bytes:
    if not (CLONE / ".git").exists():
        CLONE.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=CLONE, check=True)
        subprocess.run(["git", "remote", "add", "origin", DATASET_URL + ".git"], cwd=CLONE, check=True)
    if subprocess.run(["git", "cat-file", "-e", f"{COMMIT}^{{commit}}"], cwd=CLONE, capture_output=True).returncode:
        subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", COMMIT], cwd=CLONE, check=True, timeout=600)
    return subprocess.run(["git", "show", f"{COMMIT}:{path}"], cwd=CLONE, capture_output=True, check=True).stdout


def dataset_hashes() -> dict:
    names = subprocess.run(["git", "ls-tree", "-r", "--name-only", COMMIT, "data"], cwd=CLONE, capture_output=True, text=True, check=True).stdout.split()
    return {n: hashlib.sha256(git_show(n)).hexdigest() for n in names if n.endswith(".csv")}


def excluded(host: str) -> bool:
    tokens = re.split(r"[.\-_]", host.lower())
    return any(t in EXCLUDE_EXACT or EXCLUDE.search(t) for t in tokens)


def select_targets(rows: list[dict]) -> list[dict]:
    banks: dict[str, dict[str, dict]] = {}
    for r in rows:
        if r["https_works"] != "True" or excluded(r["domain"]):
            continue
        m = re.match(r"^(?:(www|netbanking)\.)?([a-z0-9-]+)\.bank\.in$", r["domain"].lower())
        if m:
            banks.setdefault(m.group(2), {})[m.group(1) or "apex"] = r
    out = []
    for bank in sorted(banks, key=lambda b: hashlib.sha256(b.encode()).hexdigest()):
        eps = banks[bank]
        picks = [k for k in ("www", "netbanking", "apex") if k in eps][:PER_BANK]
        if len(out) + len(picks) > MAX_HOSTS:
            picks = picks[: MAX_HOSTS - len(out)]
        for k in picks:
            out.append({"bank": bank, "host": eps[k]["domain"].lower(), "endpoint": k, "port": 443,
                        "source_row_status_code": eps[k]["status_code"], "dataset_commit": COMMIT})
        if len(out) >= MAX_HOSTS:
            break
    return out


def write_csv(path: Path, cols, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def leaf_cert(text: str):
    from cryptography import x509

    m = re.search(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", text, re.S)
    return (x509.load_pem_x509_certificate(m.group(0).encode()), m.group(0)) if m else (None, None)


def probe_one(t: dict, tdir: Path) -> dict:
    from cryptography.x509.oid import NameOID

    from detect.live_probe import probe

    label = t["host"].replace(".", "_")
    rec = probe(t["host"], 443, transcript_dir=tdir, label=label, timeout=TIMEOUT_S)
    text = (tdir / f"probe_{label}.txt").read_text(errors="replace")
    cert, pem = leaf_cert(text)
    row = {**{k: t[k] for k in ("bank", "host", "endpoint", "port")}, "observed_at_utc": rec["ts"],
           "transcript_sha256": rec["transcript_sha256"]}
    if not rec["handshake_ok"]:
        last = [ln for ln in text.splitlines() if ln.strip()][-1:] or ["no response"]
        return {**row, "outcome": "unreachable", "error": last[0][:160], "_pem": None}
    issuer = cert.issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME) or cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME) if cert else []
    return {**row, "outcome": "hybrid_pq" if rec["kex_family"] == "PQC" else "classical",
            "tls_version": rec["protocol"], "negotiated_group": rec["group"], "cipher": rec["cipher"],
            "cert_key_algorithm": rec["cert_algorithm"],
            "cert_signature_algorithm": cert.signature_algorithm_oid._name if cert else "",
            "cert_issuer": issuer[0].value if issuer else "",
            "cert_not_after": cert.not_valid_after_utc.strftime("%Y-%m-%d") if cert else "",
            "kex_quantum_vulnerable": str(rec["kex_quantum_vulnerable"]).lower(),
            "auth_quantum_vulnerable": str(rec["auth_quantum_vulnerable"]).lower(), "error": "", "_pem": pem}


def cmd_targets():
    raw = git_show("data/bank_domains_status.csv")
    targets = select_targets(list(csv.DictReader(io.StringIO(raw.decode()))))
    write_csv(OUT / "targets.csv", TARGET_COLS, targets)
    (OUT / "dataset.json").write_text(json.dumps({"url": DATASET_URL, "commit": COMMIT, "license": "CC0 1.0",
                                                  "csv_sha256": dataset_hashes(), "selection": __doc__.split("Selection")[1].split("Probe:")[0].strip()}, indent=1) + "\n")
    print(f"{len(targets)} targets from {len({t['bank'] for t in targets})} banks -> {OUT / 'targets.csv'}")


def cmd_scan():
    from contracts.manifest import new_run_id, sha256_json, utc_now

    targets = list(csv.DictReader((OUT / "targets.csv").open()))
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = new_run_id()
    run_dir = REPO / "runs" / "real_banks" / run_id  # git-ignored: transcripts and leaf certificates
    tdir = run_dir / "transcripts"
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        rows = list(pool.map(lambda t: probe_one(t, tdir), targets))
    certs = run_dir / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    for r in rows:
        if r.pop("_pem", None):
            (certs / f"{r['host']}.pem").write_text(leaf_cert((tdir / f"probe_{r['host'].replace('.', '_')}.txt").read_text())[1] + "\n")
    out = OUT / f"scan_{date}.csv"
    write_csv(out, SCAN_COLS, rows)
    counts = {k: sum(r["outcome"] == k for r in rows) for k in ("hybrid_pq", "classical", "unreachable")}
    manifest = {"type": "bank_scan.run", "run_id": run_id, "ts": utc_now(), "dataset": json.loads((OUT / "dataset.json").read_text()),
                "targets_sha256": hashlib.sha256((OUT / "targets.csv").read_bytes()).hexdigest(),
                "scan_csv": out.relative_to(REPO).as_posix(), "scan_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                "probe": {"port": 443, "timeout_s": TIMEOUT_S, "concurrency": CONCURRENCY, "handshakes_per_host": 1, "http_requests": 0},
                "counts": counts, "hosts": len(rows)}
    manifest["manifest_sha256"] = sha256_json(manifest)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (OUT / f"scan_{date}.manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{len(rows)} hosts: {counts} -> {out}; run {run_id}")


def cmd_workspace(ws_src: Path, scan: Path, run_dir: Path):
    """One folder per reachable endpoint: its real public leaf certificate (crypto evidence for the static scan) and
    an atlas-service.json whose kind/data_class are labelled assumptions (netbanking -> customer data)."""
    rows = list(csv.DictReader(scan.open()))
    n = 0
    for r in rows:
        if r["outcome"] == "unreachable":
            continue
        d = ws_src / r["bank"] / r["endpoint"]
        d.mkdir(parents=True, exist_ok=True)
        pem = run_dir / "certs" / f"{r['host']}.pem"
        if pem.exists():
            (d / "server-cert.pem").write_text(pem.read_text())
        (d / "atlas-service.json").write_text(json.dumps({
            "id": r["host"].replace(".", "-"), "name": f"{r['host']} ({r['bank']}, {r['endpoint']})", "kind": "tls_gateway",
            "data_class": "customer_pii" if r["endpoint"] == "netbanking" else "public_content", "depends_on": [],
            "basis": "declared by tools/scan_banks.py: kind from the endpoint name; data class is an assumption "
                     "(netbanking carries customer data). Observed key exchange: " + f"{r['negotiated_group']} ({r['outcome']}).",
            "observed": {k: r[k] for k in ("negotiated_group", "tls_version", "cert_key_algorithm", "outcome", "transcript_sha256")},
        }, indent=1))
        n += 1
    print(f"{n} endpoint folders in {ws_src}")


def cmd_publish():
    """Workspace "Real banks (public TLS, <date>)": src from the latest scan, full pipeline (local only), scan signed."""
    import os
    import secrets
    import threading

    sys.path.insert(0, str(REPO / "tests"))
    os.environ["QSHIELD_FORBID_PLATFORM"] = "1"
    from atlas_web_helpers import Client, sse_events

    from atlas_web.server import make_server
    from atlas_web import workspaces as wsmod

    scan = sorted(OUT.glob("scan_*.csv"))[-1]
    date = scan.stem.split("_", 1)[1]
    man = json.loads((OUT / f"scan_{date}.manifest.json").read_text())
    run_dir = REPO / "runs" / "real_banks" / man["run_id"]
    srv = make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    user, pw = f"banks-{secrets.token_hex(3)}", secrets.token_urlsafe(18)
    srv.app.store.create_user(user, pw, "operator")
    c = Client(srv.server_address[1])
    try:
        assert c.login(user, pw)[0] == 200
        st, body = c.post("/api/workspaces", {"id": "real-banks", "name": f"Real banks (public TLS, {date})", "template": "empty"})
        if st not in (201, 409):
            raise SystemExit(f"create failed: {body}")
        ws = wsmod.get(srv.app.store, "real-banks")
        cmd_workspace(ws.src, scan, run_dir)
        st, run = c.post("/api/workspaces/real-banks/runs", {})
        assert st == 202, run
        evs = sse_events(srv.server_address[1], f"/api/workspaces/real-banks/runs/{run['run_id']}/events", c.cookies, lambda e, d: e == "run_end", timeout=3600)
        end = evs[-1][1]
        print(f"pipeline: {end['status']} in {end.get('duration_s')} s")
        if end["status"] != "PASS":
            print("\n".join(end["tail"][-15:]))
            return 1
        led = ["--ledger", str(ws.out / "ledger.jsonl"), "--out-dir", str(ws.out), "--runs", str(ws.runs), "--root", str(ws.root), "--keys-dir", str(ws.keys)]
        payload = ws.runs / f"bank_scan_{man['run_id']}.json"
        payload.write_text(json.dumps(man, indent=1))
        for argv in (["append", str(payload), "--type", "bank_scan.run", *led], ["verify", *led]):
            subprocess.run([sys.executable, "-m", "ledger", *argv], check=True, cwd=REPO)
        r = json.loads(ws.results.read_text())
        print(f"workspace real-banks: {len(r['assets'])} assets, {len(r['waves'])} waves, ledger {r['ledger']['entry_count']} entries, verified {r['ledger_verification']['ok']}")
    finally:
        srv.app.store.delete_user(user)
        srv.shutdown()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["targets", "scan", "workspace", "publish"])
    ap.add_argument("--src", type=Path)
    ap.add_argument("--scan", type=Path)
    ap.add_argument("--run-dir", type=Path)
    a = ap.parse_args(argv)
    if a.command == "targets":
        cmd_targets()
    elif a.command == "scan":
        cmd_scan()
    elif a.command == "publish":
        return cmd_publish()
    else:
        cmd_workspace(a.src, a.scan, a.run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
