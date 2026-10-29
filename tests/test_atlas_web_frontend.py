"""atlas_web frontend: node --check on every JS file, node unit tests (router, data layer, motion, WCAG contrast),
own-asset size budget, no CDN / web fonts, scene.json content and ETag."""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .atlas_web_helpers import PASSWORD, Client, start_server

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "atlas_web" / "static"
NODE = shutil.which("node")
BUDGET = 440 * 1024  # user decisions 2026-10-29: 250 -> 300 KB (Benchmark/Review/Migration), -> 400 KB (page template, glossary, sidebar, new pages), -> 440 KB (3D on every page, guided run)
FIRST_LOAD_BUDGET = 120 * 1024  # index.html + every stylesheet + main.js and its static imports (views load lazily)
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def own_assets():
    return [p for p in STATIC.rglob("*") if p.is_file() and p.suffix in (".js", ".css", ".glsl", ".html", ".svg") and "vendor" not in p.parts]


@needs_node
def test_node_check_every_js_file():
    files = [p for p in REPO.joinpath("atlas_web").rglob("*.js") if "data" not in p.parts] + list(REPO.joinpath("atlas_web", "jstests").glob("*.mjs"))
    assert files
    for f in files:
        r = subprocess.run([NODE, "--check", str(f)], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, f"{f}: {r.stderr}"


@needs_node
def test_node_unit_tests():
    tests = sorted(str(p) for p in (REPO / "atlas_web" / "jstests").glob("*.test.mjs"))
    r = subprocess.run([NODE, "--test", *tests], capture_output=True, text=True, timeout=120, cwd=REPO)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    assert re.search(r"ℹ fail 0", r.stdout)


def test_own_assets_within_budget():
    total = sum(p.stat().st_size for p in own_assets())
    assert total <= BUDGET, f"own JS+CSS+shaders+HTML {total} B > {BUDGET} B"


def test_first_load_within_budget():
    seen = set()

    def walk(p):
        if p in seen or not p.exists():
            return
        seen.add(p)
        for m in re.findall(r'^\s*(?:import|export)[^;]*?from\s+"(\.[^"]+)"', p.read_text(), re.M):
            walk((p.parent / m).resolve())

    walk((STATIC / "js" / "main.js").resolve())
    # first load = the stylesheets index.html links (page-only sheets in css/views/ load with their lazy view)
    html = (STATIC / "index.html").read_text()
    linked = [STATIC / h.removeprefix("/assets/") for h in re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)]
    assert set(linked) == set((STATIC / "css").glob("*.css")), "every top-level stylesheet is linked from index.html"
    assert not any("/views/" in str(p) for p in linked)
    total = sum(f.stat().st_size for f in seen) + sum(f.stat().st_size for f in linked) + (STATIC / "index.html").stat().st_size
    assert total <= FIRST_LOAD_BUDGET, f"first load {total} B > {FIRST_LOAD_BUDGET} B"


def test_no_cdn_no_web_fonts_no_inline_script():
    for p in own_assets():
        text = p.read_text()
        # no resource is loaded from another origin (example URLs in form placeholders are allowed)
        assert not re.search(r"""(\bfrom\s*|\bimport\s*\(\s*|\bsrc\s*[=:]\s*|\bhref\s*[=:]\s*|url\(\s*|fetch\(\s*|EventSource\(\s*)["'`]?https?://""", text), \
            f"external resource in {p}"
        assert "fonts.googleapis" not in text and "fonts.gstatic" not in text, p
        for src in re.findall(r"@font-face\s*{[^}]*?src:\s*([^;]+);", text):  # only vendored local files or local() fallbacks
            assert all(u.startswith("/assets/fonts/") for u in re.findall(r'url\("([^"]+)"\)', src)), (p, src)
    html = (STATIC / "index.html").read_text()
    assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html) is None  # CSP script-src 'self': no inline scripts


@pytest.fixture
def server(monkeypatch, tmp_path):
    srv = start_server(monkeypatch, tmp_path)
    srv.app.store.create_user("vic", PASSWORD, "viewer")
    yield srv
    srv.shutdown()
    srv.server_close()


def test_scene_matches_results_and_scheduler(server, tmp_path):
    results = json.loads((REPO / "tests" / "fixtures" / "results_sample.json").read_text())
    ops = Client(server.server_address[1])
    server.app.store.create_user("ops", PASSWORD, "operator")
    ops.login("ops")
    ops.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})
    out = Path(server.app.store.path).parent / "workspaces" / "bank" / "out"
    assert ops.get("/api/workspaces/bank/scene")[1] == {"workspace": "bank", "available": False, "status_text": "not yet run"}
    (out / "results.json").write_text(json.dumps(results))
    r, body = ops.request("GET", "/api/workspaces/bank/scene", raw=True)
    scene = json.loads(body)
    etag = r.headers["ETag"]
    assert etag == '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    r2, body2 = ops.request("GET", "/api/workspaces/bank/scene", headers={"If-None-Match": etag}, raw=True)
    assert r2.status == 304 and body2 == b""
    from schedule.problem import exposure_years, problem_from_dicts

    problem = problem_from_dicts(results["assumptions"], {"assets": results["assets"]})
    by_id = problem.by_id()
    for n in scene["nodes"]:
        if not n["vulnerable"]:
            assert n["exposure_years"] is None
            continue
        a = next(x for x in results["assets"] if x["id"] == n["id"])
        assert n["status"] == a["status"] and n["week"] == results["exposure"]["completion_week"][a["id"]]
        for s in problem.scenarios:
            assert n["exposure_years"][s.name] == exposure_years(problem, by_id[a["id"]], n["week"], s)
    for k, plan in (("optimized", results["exposure"]), ("fcfs", results["baselines"]["fcfs"]), ("greedy", results["baselines"]["greedy"])):
        for s in plan["remaining_by_week"]:
            assert scene["tower"][k][s["scenario"]] == [p["exposure_years"] for p in s["points"]]
    ids = {n["id"] for n in scene["nodes"]}
    assert all(e["from"] in ids and e["to"] in ids for e in scene["edges"])
    assert scene["provenance"]["positions"] == "presentation layout, not data"
    # a results change invalidates the cached scene (new ETag)
    results["generated_at"] = "2099-01-01T00:00:00Z"
    (out / "results.json").write_text(json.dumps(results))
    r3, _ = ops.request("GET", "/api/workspaces/bank/scene", headers={"If-None-Match": etag}, raw=True)
    assert r3.status == 200 and r3.headers["ETag"] != etag


def test_viz_data_layer_served_only_exact_files(server):
    c = Client(server.server_address[1])
    r, body = c.request("GET", "/viz/data.js", raw=True)
    assert r.status == 200 and body == (REPO / "viz" / "data.js").read_bytes()
    for p in ("/viz/__main__.py", "/viz/index.html", "/viz/vendor/MANIFEST.json", "/viz/app.js"):
        assert c.request("GET", p, raw=True)[0].status == 404, p


def test_vendored_fonts_match_manifest_and_are_served(server):
    """Inter Tight + JetBrains Mono (OFL) are vendored locally with SHA-256s and licences; no web-font service."""
    fonts = STATIC / "fonts"
    mf = json.loads((fonts / "MANIFEST.json").read_text())
    assert {"OFL-inter-tight.txt", "OFL-jetbrains-mono.txt"} <= set(mf["files"])
    for name, digest in mf["files"].items():
        assert hashlib.sha256((fonts / name).read_bytes()).hexdigest() == digest, name
    assert all(p["license"] == "OFL-1.1" for p in mf["packages"].values())
    r, body = Client(server.server_address[1]).request("GET", "/assets/fonts/jetbrains-mono-latin-400-normal.woff2", raw=True)
    assert r.status == 200 and r.headers["Content-Type"] == "font/woff2" and body[:4] == b"wOF2"
    css = (STATIC / "css" / "tokens.css").read_text()
    assert "font-display: swap" in css and "size-adjust" in css and "googleapis" not in css
