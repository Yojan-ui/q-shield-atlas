"""Build out/report.html, sign it into the ledger, re-anchor and verify (python -m atlas report)."""

import json
import shutil
from pathlib import Path

from contracts.assemble import assemble
from contracts.manifest import new_run_id, sha256_hex, utc_now

from .report import REPO, build_html, finalize, self_hash_ok


def build_and_sign(out_dir: Path = REPO / "out", runs_dir: Path = REPO / "runs", repo: Path = REPO,
                   private_key: Path | None = None, public_key: Path | None = None) -> dict:
    results_path = out_dir / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else None
    html_text, content_hash = finalize(build_html(results, runs_dir))
    assert self_hash_ok(html_text)
    run_id = new_run_id()
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    signed_copy = run_dir / "report.html"  # immutable payload for the ledger; out/report.html is the latest copy
    signed_copy.write_text(html_text, encoding="utf-8")
    file_hash = sha256_hex(signed_copy.read_bytes())
    manifest = {"run_id": run_id, "ts": utc_now(), "report": f"runs/{run_id}/report.html", "file_sha256": file_hash,
                "content_sha256_zeroed_footer": content_hash,
                "results_generated_at": results.get("generated_at") if results else None,
                "results_ledger_root": (results.get("ledger") or {}).get("root") if results else None}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(signed_copy, out_dir / "report.html")

    from ledger.__main__ import PRIVATE_KEY, default_public_key
    from ledger.backend import detect
    from ledger.ingest import ledger_summary
    from ledger.log import Ledger
    from ledger.verify import status_record, verify

    private_key = private_key or PRIVATE_KEY
    public_key = public_key or default_public_key()
    signed = verified = None
    if results and results.get("ledger") and Path(private_key).exists():
        backend = detect()
        ledger = Ledger(repo / results["ledger"]["ledger_ref"], backend, private_key, public_key, repo)
        signed = ledger.append("report.html", signed_copy)
        (out_dir / "ledger.json").write_text(json.dumps(ledger_summary(ledger, repo), indent=1))
        (out_dir / "ledger_verify.json").unlink(missing_ok=True)
        anchored = assemble(out_dir)
        verified = verify(ledger.path, public_key, backend, repo, anchored["ledger"])
        (out_dir / "ledger_verify.json").write_text(json.dumps(status_record(verified, backend.fingerprint(public_key)), indent=1))
        results_path.write_text(json.dumps(assemble(out_dir), indent=1))
        print(f"ledger verify: {'OK' if verified['ok'] else 'FAIL'} ({verified['entries_checked']} entries)"
              + ("" if verified["ok"] else f" at index {verified['first_failure']['index']}: {verified['first_failure']['reason']}"))
    return {"run_id": run_id, "report": out_dir / "report.html", "file_sha256": file_hash, "content_sha256": content_hash,
            "ledger_entry": signed["index"] if signed else None, "verify_rc": None if verified is None else (0 if verified["ok"] else 1)}
