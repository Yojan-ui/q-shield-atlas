"""site/ + python -m atlas site. Freeze rule: only TEMP COPIES of results.json and the ledger are used here."""

import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from atlas.site_server import make_server
from tests.test_viz import numbers_in

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
SAMPLE = REPO / "tests" / "fixtures" / "results_sample.json"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed; site data layer not exercised")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def world(tmp_path):
    """A temp results.json + a temp ML-DSA-signed ledger whose root is anchored in it."""
    from ledger.backend import detect
    from ledger.ingest import ledger_summary
    from ledger.log import Ledger

    backend = detect()
    backend.generate(tmp_path / "k" / "sk.pem", tmp_path / "k" / "pk.pem")
    (tmp_path / "runs" / "r0").mkdir(parents=True)
    (tmp_path / "runs" / "r0" / "manifest.json").write_text('{"run": 0}')
    ledger = Ledger(tmp_path / "out" / "ledger.jsonl", backend, tmp_path / "k" / "sk.pem", tmp_path / "k" / "pk.pem", tmp_path)
    ledger.append("test.run", tmp_path / "runs" / "r0" / "manifest.json")
    results = json.loads(SAMPLE.read_text())
    results["ledger"] = ledger_summary(ledger, tmp_path)
    results["ledger_verification"] = None
    (tmp_path / "out" / "results.json").write_text(json.dumps(results))
    srv = make_server(tmp_path / "out" / "results.json", ledger_path=ledger.path, public_key=tmp_path / "k" / "pk.pem", repo=tmp_path)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"srv": srv, "base": f"http://127.0.0.1:{srv.server_address[1]}", "tmp": tmp_path, "results": tmp_path / "out" / "results.json", "ledger": ledger.path}
    srv.shutdown()
    srv.server_close()


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


# ---------- server: allowlist, loopback, read-only ----------

def test_binds_loopback_only(world):
    assert world["srv"].server_address[0] == "127.0.0.1"


@pytest.mark.parametrize("path", ["/", "/js/app.js", "/js/data.js", "/js/scenes.js", "/css/site.css",
                                  "/vendor/three-0.170.0.module.min.js", "/api/results", "/api/ledger", "/api/handshakes", "/viz/"])
def test_serves_site_and_apis(world, path):
    assert get(world["base"], path)[0] == 200


@pytest.mark.parametrize("path", ["/keys/ledger_mldsa65.key", "/.env.sh", "/runs/", "/runs/r0/manifest.json", "/out/ledger.jsonl",
                                  "/CLAUDE.md", "/atlas/site_server.py", "/js/../../keys/ledger_mldsa65.key", "/%2e%2e/.env.sh",
                                  "/vendor/MANIFEST.json", "/viz/__main__.py", "/site/js/app.js"])
def test_never_serves_secrets_or_repo_files(world, path):
    assert get(world["base"], path)[0] == 404


def test_apis_are_read_only(world):
    before = {p: sha(p) for p in (world["results"], world["ledger"])}
    for p in ("/api/results", "/api/ledger", "/api/handshakes", "/api/ledger"):
        assert get(world["base"], p)[0] == 200
    assert {p: sha(p) for p in before} == before
    assert not (world["tmp"] / "out" / "ledger_verify.json").exists()  # live verify is never recorded


def test_ledger_api_reports_live_verification(world):
    led = json.loads(get(world["base"], "/api/ledger")[1])
    assert led["entry_count"] == 1 and len(led["entries"]) == 1
    assert led["live_verification"]["ok"] is True and led["recorded_verification"] is None


def test_sse_pushes_when_results_change(world):
    req = urllib.request.urlopen(world["base"] + "/api/events", timeout=10)
    assert b"event: hello" in req.readline() + req.readline()
    time.sleep(0.4)
    data = json.loads(world["results"].read_text())
    world["results"].write_text(json.dumps(data, indent=1))  # same content, new mtime/size
    deadline, got = time.time() + 5, b""
    while time.time() < deadline and not re.search(rb"event: update\ndata: [^\n]+\n", got):
        got += req.readline()
    req.close()
    assert b"event: update" in got and b"results" in got


# ---------- data layer (node, real data.js) ----------

def model_for(world_or_none, tmp_path):
    if world_or_none:
        payloads = {n: get(world_or_none["base"], f"/api/{n}")[1] for n in ("results", "ledger", "handshakes")}
    else:
        payloads = {n: b"null" for n in ("results", "ledger", "handshakes")}
    paths = []
    for n, body in payloads.items():
        p = tmp_path / f"api_{n}.json"
        p.write_bytes(body)
        paths.append(str(p))
    out = subprocess.run([NODE, str(SITE / "js" / "export_model.js"), *paths], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout), json.loads(payloads["results"])


@needs_node
def test_every_number_the_site_renders_exists_in_api_results(world, tmp_path):
    d, results = model_for(world, tmp_path)
    present = numbers_in(results)
    assert len(d["number_cells"]) > 50
    for c in d["number_cells"]:
        assert float(c["value"]) in present, c
        assert set(c["source"]) >= {"run_id", "solver", "job_id", "ts"}


@needs_node
def test_chapter_models_match_results(world, tmp_path):
    d, r = model_for(world, tmp_path)
    m = d["model"]
    assert m["harvest"]["scenarios"] == [s["name"] for s in r["scenarios"]]
    assert m["detect"]["filesScanned"]["value"] == r["detect"]["files_scanned"]
    assert sum(len(f["findings"]) for f in m["detect"]["files"]) == len(r["detect"]["findings"])
    assert m["schedule"]["weeks"] == [p["week"] for p in r["exposure"]["remaining_by_week"][0]["points"]]
    ids = {s["id"]: s for s in m["handshake"]["services"]}
    assert ids["legacy"]["strands"] == ["X25519"] and ids["hybrid"]["strands"] == ["X25519", "ML-KEM-768"]
    assert ids["pq-auth"]["authGate"] == "PASS" and ids["legacy"]["kexGate"] == "FAIL"


@needs_node
def test_missing_data_renders_not_yet_run(tmp_path):
    d, _ = model_for(None, tmp_path)
    m = d["model"]
    assert d["number_cells"] == []
    for key in ("harvest", "detect", "schedule", "handshake", "ledger"):
        assert m[key]["available"] is False


# ---------- assets: offline, budget ----------

def own_assets():
    return [p for p in SITE.rglob("*") if p.is_file() and p.suffix in {".js", ".css", ".html"} and "dist" not in p.parts]


def test_own_assets_within_budget():
    total = sum(p.stat().st_size for p in own_assets())
    assert total <= 150 * 1024, f"{total} bytes"


def test_no_external_urls_cdn_or_web_fonts():
    for p in own_assets():
        text = p.read_text()
        assert not re.search(r"(src|href|from|import\()\s*=?\s*[\"']https?://", text), p
        assert "@font-face" not in text and "fonts.googleapis" not in text, p
    assert '"/vendor/three-0.170.0.module.min.js"' in (SITE / "js" / "scenes.js").read_text()
