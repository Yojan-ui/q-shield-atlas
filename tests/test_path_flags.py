"""Every pipeline CLI can be pointed at a separate workspace (atlas_web): outputs, runs, ledger root
and keys go where the flags say, the defaults are unchanged, and the repo's out/, runs/ and keys/
are never touched."""

import hashlib
import json
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "tests" / "fixtures" / "results_sample.json"
LATER = ("schema_version", "generated_at", "detect", "handshake_evidence", "gates", "qaoa", "ledger", "ledger_root",
         "ledger_verification")


def tree_digest(*dirs: Path) -> dict:
    """SHA-256 of every file under the given repo dirs (missing dirs count as empty)."""
    out = {}
    for d in dirs:
        if d.exists():
            for p in sorted(d.rglob("*")):
                if p.is_file():
                    out[str(p.relative_to(REPO))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture
def repo_untouched():
    before = tree_digest(REPO / "out", REPO / "keys", REPO / "ledger" / "pubkey")
    runs_before = sorted(p.name for p in (REPO / "runs").iterdir()) if (REPO / "runs").exists() else []
    yield
    assert tree_digest(REPO / "out", REPO / "keys", REPO / "ledger" / "pubkey") == before
    assert (sorted(p.name for p in (REPO / "runs").iterdir()) if (REPO / "runs").exists() else []) == runs_before


def cli(*args, cwd=REPO, check=True):
    proc = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, timeout=180)
    if check and proc.returncode != 0:
        raise AssertionError(f"{args} exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return proc


@pytest.fixture
def workspace(tmp_path):
    """A workspace outside the repo with a schedule section and its solver-run manifests."""
    ws = tmp_path / "ws"
    out, runs = ws / "out", ws / "runs"
    out.mkdir(parents=True)
    sample = json.loads(SAMPLE.read_text())
    schedule = {k: v for k, v in sample.items() if k not in LATER}
    schedule["waves"] = [{k: w[k] for k in w if k not in ("evidence", "asset_status")} | {"status": "planned"}
                         for w in schedule["waves"]]
    for a in schedule["assets"]:
        a["status"] = "planned"
    (out / "schedule.json").write_text(json.dumps(schedule))
    for r in schedule["solver_runs"]:
        d = runs / r["run_id"]
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"run_id": r["run_id"], "note": "test payload"}))
    return ws


def test_assemble_out_dir(workspace, repo_untouched):
    cli("-m", "contracts.assemble", "--out-dir", str(workspace / "out"))
    results = json.loads((workspace / "out" / "results.json").read_text())
    from contracts import validate

    validate("results", results)
    assert results["ledger"] is None and results["detect"] is None


def test_assemble_default_is_still_repo_out():
    from contracts import assemble

    assert assemble.OUT == REPO / "out"
    import inspect

    assert inspect.signature(assemble.assemble).parameters["out_dir"].default == REPO / "out"


def test_keygen_keys_dir_never_overwrites(tmp_path, repo_untouched):
    keys = tmp_path / "keys"
    cli("-m", "ledger", "keygen", "--keys-dir", str(keys))
    assert (keys / "ledger_mldsa65.key").exists() and (keys / "ledger_mldsa65.pub.pem").exists()
    assert (keys / "ledger_mldsa65.key").stat().st_mode & 0o777 == 0o600
    sk = (keys / "ledger_mldsa65.key").read_bytes()
    again = cli("-m", "ledger", "keygen", "--keys-dir", str(keys), check=False)
    assert again.returncode != 0 and "not overwriting" in again.stderr
    assert (keys / "ledger_mldsa65.key").read_bytes() == sk


def test_ledger_and_report_in_workspace(workspace, repo_untouched):
    ws, out, runs, keys = workspace, workspace / "out", workspace / "runs", workspace / "keys"
    flags = ["--out-dir", str(out), "--runs", str(runs), "--root", str(ws), "--keys-dir", str(keys)]
    cli("-m", "ledger", "keygen", "--keys-dir", str(keys))
    cli("-m", "ledger", "ingest", "--ledger", str(out / "ledger.jsonl"), *flags)
    results = json.loads((out / "results.json").read_text())
    assert results["ledger"]["ledger_ref"] == "out/ledger.jsonl"
    assert all(e["payload_ref"].startswith("runs/") for e in results["ledger"]["entries"])
    fp = (keys / "ledger_mldsa65.pub.sha256").read_text().strip()
    assert results["ledger"]["pubkey_fp"] == fp  # signed with the workspace key, not the repo's

    v = cli("-m", "ledger", "verify", "--ledger", str(out / "ledger.jsonl"), *flags)
    assert v.stdout.startswith("OK:")
    assert json.loads((out / "ledger_verify.json").read_text())["ok"] is True  # anchored ledger: recorded

    # the report resolves ledger_ref against the workspace root, signs into the workspace ledger and verifies it
    rep = cli("-m", "atlas", "report", *flags)
    assert "ledger verify: OK" in rep.stdout, rep.stdout
    results = json.loads((out / "results.json").read_text())
    assert results["ledger"]["entries"][-1]["type"] == "report.html"
    assert (out / "report.html").exists()
    from atlas.report import checks

    name = "ledger file recomputes to the anchored Merkle root"
    assert dict(checks(results, runs, ws))[name] is True
    assert dict(checks(results, runs, REPO))[name] is False  # resolving against the repo would be wrong

    p = cli("-m", "ledger", "proof", "0", "--ledger", str(out / "ledger.jsonl"), *flags)
    assert json.loads(p.stdout)["verified"] is True


def test_verify_of_a_workspace_copy_is_not_recorded(workspace, repo_untouched, tmp_path):
    ws, out, runs, keys = workspace, workspace / "out", workspace / "runs", workspace / "keys"
    flags = ["--out-dir", str(out), "--runs", str(runs), "--root", str(ws), "--keys-dir", str(keys)]
    cli("-m", "ledger", "keygen", "--keys-dir", str(keys))
    cli("-m", "ledger", "ingest", "--ledger", str(out / "ledger.jsonl"), *flags)
    before = (out / "results.json").read_bytes()
    copy = tmp_path / "copy.jsonl"
    shutil.copyfile(out / "ledger.jsonl", copy)
    v = cli("-m", "ledger", "verify", "--ledger", str(copy), *flags)
    assert "not the anchored ledger" in v.stdout
    assert (out / "results.json").read_bytes() == before and not (out / "ledger_verify.json").exists()


def _silent_server():
    """Accepts TCP connections and never answers: a TLS probe must time out."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    conns = []
    stop = threading.Event()

    def loop():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conns.append(srv.accept()[0])
            except OSError:
                pass

    threading.Thread(target=loop, daemon=True).start()
    return srv, stop, conns


def test_detect_probe_timeout_is_recorded_as_probe_failed(tmp_path, repo_untouched):
    from detect.live_probe import openssl_binary

    try:
        openssl_binary()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no OpenSSL >= 3.5: {exc}")
    srv, stop, conns = _silent_server()
    try:
        port = srv.getsockname()[1]
        cli("-m", "detect", "--probe", f"web-gw=127.0.0.1:{port}", "--probe-timeout", "1",
            "--out-dir", str(tmp_path / "out"), "--runs", str(tmp_path / "runs"))
    finally:
        stop.set()
        for c in conns:
            c.close()
        srv.close()
    det = json.loads((tmp_path / "out" / "detect.json").read_text())
    probe = det["probes"][0]
    assert probe["live"]["handshake_ok"] is False
    assert [d["kind"] for d in probe["drift"]] == ["probe_failed"]
    assert (tmp_path / "out" / "inventory.json").exists()


@pytest.mark.parametrize("module", ["schedule", "qaoa"])
def test_platform_log_flag_sets_the_shared_cap_log(module, tmp_path, monkeypatch):
    """--platform-log points the daily cap at one shared file; the guard refuses before anything is sent."""
    import importlib

    from schedule.platform_guard import PlatformBudget, PlatformRefused

    mod = importlib.import_module(f"{module}.__main__")
    seen = []

    class Recorder(PlatformBudget):
        def check(self, n):
            seen.append(self.log_path)
            raise PlatformRefused("test: refused before submission")

    monkeypatch.setattr(mod, "PlatformBudget", Recorder)
    shared = tmp_path / "shared" / "platform_jobs.log"
    flag = "--platform" if module == "schedule" else "--qcloud"
    extra = ["--inventory", str(REPO / "schedule" / "data" / "mock_bank_assets.json")] if module == "schedule" else \
        ["--schedule", str(SAMPLE)]
    with pytest.raises(PlatformRefused):
        mod.main([flag, "--runs", str(tmp_path / "runs"), "--platform-log", str(shared), *extra])
    assert seen == [shared]
    seen.clear()
    with pytest.raises(PlatformRefused):
        mod.main([flag, "--runs", str(tmp_path / "runs"), *extra])
    assert seen == [tmp_path / "runs" / "platform_jobs.log"]  # default unchanged


def test_ledger_append_signs_a_workspace_payload(workspace, repo_untouched):
    ws, out, runs, keys = workspace, workspace / "out", workspace / "runs", workspace / "keys"
    flags = ["--ledger", str(out / "ledger.jsonl"), "--out-dir", str(out), "--runs", str(runs), "--root", str(ws),
             "--keys-dir", str(keys)]
    cli("-m", "ledger", "keygen", "--keys-dir", str(keys))
    cli("-m", "ledger", "ingest", *flags)
    payload = runs / "calib" / "manifest.json"
    payload.parent.mkdir()
    payload.write_text(json.dumps({"change": "test"}))
    cli("-m", "ledger", "append", str(payload), "--type", "calibration.apply", *flags)
    results = json.loads((out / "results.json").read_text())
    last = results["ledger"]["entries"][-1]
    assert (last["type"], last["payload_ref"]) == ("calibration.apply", "runs/calib/manifest.json")
    assert cli("-m", "ledger", "verify", *flags).stdout.startswith("OK:")
    assert cli("-m", "ledger", "append", str(payload), *flags, check=False).returncode != 0  # --type required
