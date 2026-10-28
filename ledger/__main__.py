"""python -m ledger keygen | ingest | verify | proof INDEX

keygen  create the ML-DSA-65 signing key in keys/ (0600) and write the public key + fingerprint;
        refuses to overwrite an existing key

ingest  append ML-DSA-65-signed run manifests to out/ledger.jsonl, write out/ledger.json and
        re-assemble out/results.json (ledger_root, entry_count, pubkey_fp anchored there)
verify  re-hash payloads, check chain, signatures and the root anchored in results.json
proof   print and check an RFC 6962 inclusion proof for one entry
"""

import argparse
import json
import sys
from pathlib import Path

from contracts.assemble import assemble
from contracts.manifest import utc_now

from .backend import detect
from .ingest import ingest
from .log import Ledger, canonical, read_entries
from .merkle import MerkleTree, verify_proof
from .verify import verify

REPO = Path(__file__).resolve().parent.parent
PRIVATE_KEY = REPO / "keys" / "ledger_mldsa65.key"
LOCAL_PUBLIC_KEY = REPO / "keys" / "ledger_mldsa65.pub.pem"  # written by keygen; git-ignored
PROJECT_PUBLIC_KEY = REPO / "ledger" / "pubkey" / "ledger_mldsa65.pub.pem"  # committed project key
LEDGER = REPO / "out" / "ledger.jsonl"


def default_public_key() -> Path:
    """The key generated on this machine if any, else the committed project key."""
    return LOCAL_PUBLIC_KEY if LOCAL_PUBLIC_KEY.exists() else PROJECT_PUBLIC_KEY


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["keygen", "ingest", "verify", "proof"])
    ap.add_argument("index", nargs="?", type=int)
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--public-key", type=Path, default=None, help="default: keys/ledger_mldsa65.pub.pem, else the committed key")
    ap.add_argument("--out-dir", type=Path, default=REPO / "out")
    args = ap.parse_args(argv)
    backend = detect()

    if args.command == "keygen":
        if PRIVATE_KEY.exists():
            sys.exit(f"{PRIVATE_KEY} already exists; not overwriting")
        # the public key goes next to the private key (git-ignored): committed files are never rewritten
        backend.generate(PRIVATE_KEY, LOCAL_PUBLIC_KEY)
        fp = backend.fingerprint(LOCAL_PUBLIC_KEY)
        LOCAL_PUBLIC_KEY.with_suffix(".sha256").write_text(fp + "\n")
        print(f"ML-DSA-65 key pair created in keys/ (git-ignored; private key 0600); pubkey_fp {fp}")
        return 0
    if args.public_key is None:
        args.public_key = default_public_key()

    if args.command == "ingest":
        if not PRIVATE_KEY.exists():
            sys.exit(f"no signing key at {PRIVATE_KEY.relative_to(REPO)}; generate one (see README) - keys are never committed")
        ledger = Ledger(args.ledger, backend, PRIVATE_KEY, args.public_key, REPO)
        appended, summary = ingest(ledger, args.out_dir, REPO / "runs")
        (args.out_dir / "ledger_verify.json").unlink(missing_ok=True)  # any earlier verification is stale now
        results = assemble(args.out_dir)
        (args.out_dir / "results.json").write_text(json.dumps(results, indent=1))
        print(f"backend {backend.label}, alg ML-DSA-65, pubkey_fp {summary['pubkey_fp']}")
        for e in appended:
            print(f"  appended #{e['index']:<3} {e['type']:20} {e['payload_ref']}  payload {e['payload_hash'][:16]}")
        print(f"entries {summary['entry_count']} (+{len(appended)}), root {summary['root']} -> results.json")
        return 0

    if args.command == "verify":
        results = json.loads((args.out_dir / "results.json").read_text())
        report = verify(args.ledger, args.public_key, backend, REPO, results.get("ledger"))
        status = {"ok": report["ok"], "ts": utc_now(), "entries_checked": report["entries_checked"],
                  "root": report.get("root"), "verifying_pubkey_fp": backend.fingerprint(args.public_key),
                  "first_failure": report["first_failure"]}
        (args.out_dir / "ledger_verify.json").write_text(json.dumps(status, indent=1))
        (args.out_dir / "results.json").write_text(json.dumps(assemble(args.out_dir), indent=1))
        if report["ok"]:
            print(f"OK: {report['entries_checked']} entries; chain, ML-DSA-65 signatures and payload hashes verified; "
                  f"root {report['root']} matches results.json")
            return 0
        f = report["first_failure"]
        print(f"FAIL at index {f['index']}: {f['reason']}")
        return 1

    entries = read_entries(args.ledger)
    items = [canonical(e) for e in entries]
    tree = MerkleTree(items)
    i = args.index if args.index is not None else len(entries) - 1
    proof = tree.inclusion_proof(i)
    ok = verify_proof(items[i], i, len(items), proof, tree.root())
    print(json.dumps({"index": i, "type": entries[i]["type"], "tree_size": len(items), "root": tree.root(),
                      "leaf_hash": __import__("hashlib").sha256(b"\x00" + items[i]).hexdigest(),
                      "proof": proof, "verified": ok}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
