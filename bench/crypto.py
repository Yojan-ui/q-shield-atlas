"""python -m bench.crypto [--out-dir out] [--runs runs] [--n 15]  ->  out/bench_crypto.json

Classical vs post-quantum vs hybrid TLS 1.3, measured on this machine with OpenSSL 3.6.5 (lab services on 127.0.0.1).
"Quantum cryptography" here means post-quantum cryptography (new algorithms on ordinary computers), not QKD.

Per configuration (key exchange group + server certificate):
  handshake bytes   sum of TLS handshake message lengths from `s_client -msg` (client->server, server->client),
                    excluding record headers and AEAD tags
  handshake ms      median wall time of N full `openssl s_client` handshakes (includes process start, identical
                    for every row, so compare rows rather than read absolute values)
  key / signature   sizes measured from keys and a signature OpenSSL generates now (DER SubjectPublicKeyInfo for
                    public keys; raw signature bytes over a 32-byte message)
  primitive cost    `openssl speed -seconds 1` for the KEM / signature algorithm (operations per second)
  security level    reference values (NIST FIPS 203/204 categories; SP 800-57 classical bits): cited, not measured
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from capture.handshake import clean_env, parse_brief
from capture.services import HOST, free_port, stop
from contracts.manifest import new_run_id, sha256_json, utc_now
from detect.live_probe import openssl_binary, openssl_info

REPO = Path(__file__).resolve().parent.parent
LABEL = ("Measured on this machine with OpenSSL 3.6.5 lab services on 127.0.0.1. Post-quantum here means new "
         "algorithms on ordinary computers, not quantum key distribution (QKD).")
CONFIGS = [
    {"id": "classical-rsa", "family": "classical", "label": "Classical: X25519 + RSA-2048", "group": "X25519", "cert": "rsa:2048", "kem": "X25519", "sig": "RSA-2048"},
    {"id": "classical-ecdsa", "family": "classical", "label": "Classical: X25519 + ECDSA P-256", "group": "X25519", "cert": "ec:P-256", "kem": "X25519", "sig": "ECDSA P-256"},
    {"id": "hybrid", "family": "hybrid", "label": "Hybrid: X25519MLKEM768 + ECDSA P-256", "group": "X25519MLKEM768", "cert": "ec:P-256", "kem": "X25519MLKEM768", "sig": "ECDSA P-256"},
    {"id": "pq", "family": "post-quantum", "label": "Post-quantum: ML-KEM-768 + ML-DSA-65", "group": "MLKEM768", "cert": "ML-DSA-65", "kem": "ML-KEM-768", "sig": "ML-DSA-65"},
]
# cited reference values, not measurements
SECURITY = {
    "X25519": {"classical_bits": 128, "quantum": "broken by Shor's algorithm", "ref": "RFC 7748; SP 800-57"},
    "X25519MLKEM768": {"classical_bits": 128, "quantum": "NIST category 3 (ML-KEM-768 part)", "ref": "FIPS 203; draft-ietf-tls-ecdhe-mlkem"},
    "ML-KEM-768": {"classical_bits": None, "quantum": "NIST category 3", "ref": "FIPS 203"},
    "RSA-2048": {"classical_bits": 112, "quantum": "broken by Shor's algorithm", "ref": "SP 800-57"},
    "ECDSA P-256": {"classical_bits": 128, "quantum": "broken by Shor's algorithm", "ref": "SP 800-57"},
    "ML-DSA-65": {"classical_bits": None, "quantum": "NIST category 3", "ref": "FIPS 204"},
}
NEWKEY = {"rsa:2048": ["-newkey", "rsa:2048"], "ec:P-256": ["-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256"], "ML-DSA-65": ["-newkey", "ML-DSA-65"]}
GENPKEY = {"X25519": ["-algorithm", "X25519"], "ML-KEM-768": ["-algorithm", "ML-KEM-768"], "RSA-2048": ["-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
           "ECDSA P-256": ["-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256"], "ML-DSA-65": ["-algorithm", "ML-DSA-65"]}
SPEED = {"X25519": ["ecdhx25519"], "ML-KEM-768": ["-kem-algorithms", "ML-KEM-768"], "X25519MLKEM768": ["-kem-algorithms", "X25519MLKEM768"],
         "RSA-2048": ["rsa2048"], "ECDSA P-256": ["ecdsap256"], "ML-DSA-65": ["-signature-algorithms", "ML-DSA-65"]}
MSG = re.compile(r"^(>>>|<<<) TLS 1\.3, Handshake \[length ([0-9a-f]+)\], (\w+)", re.M)


def run(cmd, **kw):
    return subprocess.run([openssl_binary(), *cmd], capture_output=True, timeout=60, env=clean_env(), **kw)


def handshake_bytes(transcript: str) -> dict:
    out = {"client_to_server": 0, "server_to_client": 0, "messages": {}}
    for d, length, name in MSG.findall(transcript):
        n = int(length, 16)
        out["client_to_server" if d == ">>>" else "server_to_client"] += n
        out["messages"][name] = out["messages"].get(name, 0) + n
    out["total"] = out["client_to_server"] + out["server_to_client"]
    return out


def sizes(alg: str, tmp: Path) -> dict:
    key = tmp / f"{re.sub(r'[^A-Za-z0-9]', '_', alg)}.pem"
    run(["genpkey", *GENPKEY[alg], "-out", str(key)], check=True)
    pub = run(["pkey", "-in", str(key), "-pubout", "-outform", "DER"], check=True).stdout
    out = {"public_key_der_bytes": len(pub)}
    if alg not in ("X25519", "ML-KEM-768"):
        msg = tmp / "m.bin"
        msg.write_bytes(b"\x01" * 32)
        args = ["-rawin"] if alg == "ML-DSA-65" else ["-digest", "sha256", "-rawin"]
        sig = run(["pkeyutl", "-sign", "-inkey", str(key), "-in", str(msg), *args], check=True).stdout
        out["signature_bytes"] = len(sig)
    else:
        if alg == "ML-KEM-768":
            ct = run(["pkeyutl", "-encap", "-pubin", "-inkey", str(key), "-secret", str(tmp / "ss.bin")]).stdout  # ciphertext on stdout
            out["ciphertext_bytes"] = len(ct) if ct else None
    return out


def speed(alg: str) -> dict | None:
    """Operations per second from `openssl speed -seconds 1` (last header + row of its table)."""
    args = SPEED[alg]
    p = run(["speed", "-seconds", "1", *args])
    lines = [ln for ln in p.stdout.decode(errors="replace").splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    cols = [c for c in lines[-2].split() if c.endswith("/s")]
    vals = lines[-1].split()[-len(cols):] if cols else []
    try:
        return {"ops_per_s": {c: float(v) for c, v in zip(cols, vals)}, "command": "openssl speed -seconds 1 " + " ".join(args)}
    except ValueError:
        return None


def measure(cfg: dict, n: int, tmp: Path) -> dict:
    cert, key = tmp / f"{cfg['id']}.crt", tmp / f"{cfg['id']}.key"
    run(["req", "-x509", *NEWKEY[cfg["cert"]], "-nodes", "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", f"/CN={cfg['id']}.lab.test"], check=True)
    port = free_port()
    srv = subprocess.Popen([openssl_binary(), "s_server", "-accept", f"{HOST}:{port}", "-tls1_3", "-groups", cfg["group"],
                            "-cert", str(cert), "-key", str(key), "-www", "-quiet"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import socket

        for _ in range(100):
            try:
                socket.create_connection((HOST, port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.05)
        times, transcript, group = [], "", None
        for i in range(n):
            t0 = time.perf_counter()
            p = run(["s_client", "-connect", f"{HOST}:{port}", "-groups", cfg["group"], "-tls1_3", "-brief", "-msg"], stdin=subprocess.DEVNULL)
            times.append((time.perf_counter() - t0) * 1000)
            if i == 0:
                transcript = p.stdout.decode(errors="replace") + p.stderr.decode(errors="replace")
                group = parse_brief(transcript).get("negotiated_group")
        return {**cfg, "negotiated_group": group, "established": group == cfg["group"], "n": n,
                "handshake_ms_median": round(statistics.median(times), 2), "handshake_ms_p90": round(sorted(times)[int(0.9 * (n - 1))], 2),
                "handshake_bytes": handshake_bytes(transcript), "transcript_sha256": __import__("hashlib").sha256(transcript.encode()).hexdigest()}
    finally:
        stop(srv, 5)


def bench(n: int, run_root: Path) -> dict:
    run_id = new_run_id()
    with tempfile.TemporaryDirectory(prefix="qshield-cryptobench-") as d:
        tmp = Path(d)
        rows = [measure(c, n, tmp) for c in CONFIGS]
        algs = sorted({c["kem"] for c in CONFIGS if c["kem"] != "X25519MLKEM768"} | {c["sig"] for c in CONFIGS})
        prims = {a: {**sizes(a, tmp), "speed": speed(a), "security": SECURITY[a]} for a in algs}
    prims["X25519MLKEM768"] = {"speed": speed("X25519MLKEM768"), "security": SECURITY["X25519MLKEM768"]}
    section = {"label": LABEL, "run_id": run_id, "ts": utc_now(), "openssl": openssl_info(openssl_binary())["version"],
               "method": __doc__.split("Per configuration")[1].strip(), "handshakes": rows, "primitives": prims,
               "not_measured": [], "qkd": "not in scope: no quantum key distribution hardware or protocol is involved"}
    for r in rows:
        if not r["established"]:
            section["not_measured"].append(f"{r['label']}: handshake did not negotiate {r['group']} on this OpenSSL")
    section["inputs_sha256"] = sha256_json({"configs": CONFIGS, "n": n})
    d = run_root / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps(section, indent=1))
    return section


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=REPO / "out")
    ap.add_argument("--runs", type=Path, default=REPO / "runs")
    ap.add_argument("--n", type=int, default=15)
    a = ap.parse_args(argv)
    s = bench(a.n, a.runs)
    (a.out_dir / "bench_crypto.json").write_text(json.dumps(s, indent=1))
    for r in s["handshakes"]:
        print(f"{r['label']:42} group={r['negotiated_group']!s:15} {r['handshake_bytes']['total']:6} B  median {r['handshake_ms_median']} ms")
    for k, v in s["primitives"].items():
        print(f"  {k:15} {json.dumps({x: v.get(x) for x in ('public_key_der_bytes', 'signature_bytes', 'ciphertext_bytes')})}  speed: {(v.get('speed') or {}).get('ops_per_s')}")
    print(f"wrote {a.out_dir / 'bench_crypto.json'} (run {s['run_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
