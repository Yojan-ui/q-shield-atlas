"""viz/: data layer (run under node), provenance of every displayed number, fallbacks, offline assets, server."""

import copy
import hashlib
import json
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
VIZ = REPO / "viz"
SAMPLE = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed; JS data layer not exercised")


def model_for(results, tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps(results))
    out = subprocess.run([NODE, str(VIZ / "export_model.js"), str(p)], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


def numbers_in(obj, acc=None):
    acc = set() if acc is None else acc
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        acc.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            numbers_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            numbers_in(v, acc)
    return acc


def texts(model):
    out = []
    def walk(x):
        if isinstance(x, dict):
            if x.get("kind") in ("missing", "status"):
                out.append(x["text"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(model)
    return out


# ---------- every displayed number comes from results.json, with a source ----------

@needs_node
@pytest.mark.parametrize("which", ["sample", "live"])
def test_every_number_is_a_value_in_results_with_a_source(which, tmp_path):
    results = SAMPLE if which == "sample" else None
    if which == "live":
        live = REPO / "out" / "results.json"
        if not live.exists():
            pytest.skip("out/results.json not generated")
        results = json.loads(live.read_text())
    d = model_for(results, tmp_path)
    present = numbers_in(results)
    assert d["number_cells"], "no numbers rendered"
    for cell in d["number_cells"]:
        assert float(cell["value"]) in present, cell
        assert set(cell["source"]) >= {"run_id", "solver", "job_id", "ts"}, cell


@needs_node
def test_failed_and_skipped_qcloud_rows_render_status_text_not_numbers(tmp_path):
    m = model_for(SAMPLE, tmp_path)["model"]
    cloud = [r for r in m["qaoa"]["rows"] if r["source_kind"] == "qcloud"]
    assert cloud and all("cells" not in r for r in cloud)
    assert [r["status_cell"]["text"] for r in cloud] == [
        "failed: no QCloud subscription (attempt logged, ledger #7)",
        "skipped: no QCloud subscription (attempt logged, ledger #7)",
        "skipped: no QCloud subscription (attempt logged, ledger #7)",
    ]


@needs_node
def test_later_qcloud_success_shows_numbers_without_code_changes(tmp_path):
    r = copy.deepcopy(SAMPLE)
    for row in r["qaoa"]["table"]:
        if row["source"] == "qcloud":
            local = next(x for x in r["qaoa"]["table"] if x["source"] == "local" and x["p"] == row["p"])
            row.update(status="ok", status_text=None, metrics=local["metrics"], shots=local["shots"],
                       job_ids=[f"qcloud-job-{row['p']}"], backend="QpiAI-QSV-Simulator")
    m = model_for(r, tmp_path)["model"]
    cloud = [x for x in m["qaoa"]["rows"] if x["source_kind"] == "qcloud"]
    assert all("cells" in x and x["cells"]["feasible_fraction"]["kind"] == "number" for x in cloud)
    assert [x["source"]["job_id"] for x in cloud] == ["qcloud-job-1", "qcloud-job-2", "qcloud-job-3"]


@needs_node
def test_missing_sections_render_not_yet_run_never_zero(tmp_path):
    minimal = {"schema_version": "1.0", "generated_at": SAMPLE["generated_at"]}
    d = model_for(minimal, tmp_path)
    m = d["model"]
    assert d["number_cells"] == []
    assert m["chart"] == {"available": False, "text": "not yet run"}
    for key in ("ledger", "handshake", "qaoa", "tower"):
        assert m[key]["available"] is False and m[key]["text"] == "not yet run"
    assert m["avoided"] is None and m["waves"] == []


@needs_node
def test_null_metric_field_renders_not_yet_run(tmp_path):
    r = copy.deepcopy(SAMPLE)
    local = next(x for x in r["qaoa"]["table"] if x["source"] == "local")
    local["metrics"]["approximation_ratio"] = None
    m = model_for(r, tmp_path)["model"]
    row = next(x for x in m["qaoa"]["rows"] if x["source_kind"] == "local")
    assert row["cells"]["approximation_ratio"] == {"kind": "missing", "text": "not yet run"}


@needs_node
def test_ledger_verified_only_for_the_anchored_root(tmp_path):
    assert model_for(SAMPLE, tmp_path)["model"]["ledger"]["verified"]["symbol"] == "✔"
    stale = copy.deepcopy(SAMPLE)
    stale["ledger_verification"]["root"] = "0" * 64
    assert model_for(stale, tmp_path)["model"]["ledger"]["verified"]["symbol"] == ""
    none = copy.deepcopy(SAMPLE)
    none["ledger_verification"] = None
    assert model_for(none, tmp_path)["model"]["ledger"]["verified"]["text"] == "not verified since last ingest"
    failed = copy.deepcopy(SAMPLE)
    failed["ledger_verification"].update(ok=False, first_failure={"index": 3, "reason": "payload hash mismatch"})
    assert model_for(failed, tmp_path)["model"]["ledger"]["verified"]["symbol"] == "✖"


@needs_node
def test_hndl_beams_follow_pq_handshake_gates(tmp_path):
    m = model_for(SAMPLE, tmp_path)["model"]
    beams = {b["id"]: b["off_from_week"] for b in m["tower"]["beams"]}
    gates = {g["service_id"]: g["result"] for g in SAMPLE["gates"]["pq_handshake"]}
    for sid, result in gates.items():
        assert (beams[f"svc:{sid}"] is None) == (result != "PASS")
    flipped = copy.deepcopy(SAMPLE)
    for g in flipped["gates"]["pq_handshake"]:
        g["result"] = "PASS"
    m2 = model_for(flipped, tmp_path)["model"]
    assert all(b["off_from_week"] == 0 for b in m2["tower"]["beams"] if b["id"].startswith("svc:"))


@needs_node
def test_honesty_labels_present(tmp_path):
    m = model_for(SAMPLE, tmp_path)["model"]
    assert m["banner"] == ("Lab demo · local test ledger · simulator-scale QAOA · risk, effort and shelf-life "
                           "values are assumptions (config/assumptions.json)")
    assert m["qaoa"]["label"] == "measured cross-check, no quantum advantage"
    assert "No quantum advantage claimed" in m["qaoa"]["full_label"]


# ---------- offline assets ----------

def test_vendored_files_match_recorded_sha256():
    manifest = json.loads((VIZ / "vendor" / "MANIFEST.json").read_text())
    on_disk = {p.name for p in (VIZ / "vendor").iterdir() if p.name != "MANIFEST.json"}
    assert on_disk == set(manifest["files"])
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((VIZ / "vendor" / name).read_bytes()).hexdigest() == digest, name
    assert manifest["three"]["version"] == "0.170.0"


def test_no_cdn_or_remote_urls_in_viz_sources():
    for p in list(VIZ.glob("*.js")) + list(VIZ.glob("*.html")) + list(VIZ.glob("*.css")):
        assert not re.search(r"(src|href|import[^\n]*from)\s*=?\s*[\"']https?://", p.read_text()), p
    assert 'from "./vendor/three-0.170.0.module.min.js"' in (VIZ / "render3d.js").read_text()


# ---------- server ----------

@pytest.fixture
def server():
    from viz.__main__ import make_server

    srv = make_server(0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _status(srv, path):
    url = f"http://127.0.0.1:{srv.server_address[1]}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_server_binds_loopback_only(server):
    assert server.server_address[0] == "127.0.0.1"


@pytest.mark.parametrize("path, code", [
    ("/viz/index.html", 200), ("/viz/data.js", 200), ("/viz/vendor/three-0.170.0.module.min.js", 200),
    ("/keys/ledger_mldsa65.key", 404), ("/viz/../keys/ledger_mldsa65.key", 404), ("/viz/%2e%2e/keys/ledger_mldsa65.key", 404),
    ("/out/ledger.jsonl", 404), ("/viz/__main__.py", 404), ("/CLAUDE.md", 404), ("/.env.sh", 404),
])
def test_server_serves_only_viz_and_results(server, path, code):
    assert _status(server, path) == code


def test_server_serves_results_json_when_present(server):
    if not (REPO / "out" / "results.json").exists():
        pytest.skip("out/results.json not generated")
    assert _status(server, "/out/results.json") == 200
