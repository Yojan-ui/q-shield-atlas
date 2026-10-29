"""python -m atlas_web export: a static, read-only snapshot of the demo workspace in atlas_web/dist/ that
works over file:// (offline fallback). ES modules cannot load from file://, so every module is embedded
and loaded from Blob URLs; data comes from an embedded copy of the demo API payloads; routing uses the hash.
The tamper button replays a result recorded at export time, labelled "recorded".
"""

import json
import re
import shutil
import time
from pathlib import Path

from .config import REPO, STATIC
from .scene import build_scene
from .estimate import estimate
from .server import bench_payload, ledger_payload, load_results, tamper_demo
from .workspaces import demo

DIST = REPO / "atlas_web" / "dist"
THREE = REPO / "viz" / "vendor" / "three-0.170.0.module.min.js"

BOOT = r"""
(() => {
  const SRC = window.__ATLAS_SRC, urls = {};
  const resolve = (base, spec) => new URL(spec, "http://snapshot" + base).pathname;
  const RE = /(\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)(["'])([^"']+)\2/g;
  function url(path) {
    if (urls[path]) return urls[path];
    if (!(path in SRC)) throw new Error("module not in snapshot: " + path);
    let src = SRC[path];
    if (!path.startsWith("/vendor/")) src = src.replace(RE, (m, pre, q, spec) => pre + q + url(resolve(path, spec)) + q);
    return (urls[path] = URL.createObjectURL(new Blob([src], { type: "text/javascript" })));
  }
  window.__atlasImport = (p) => import(url(p));
  window.__atlasImport("/assets/js/main.js");
})();
"""


def _modules() -> dict:
    src = {f"/assets/{p.relative_to(STATIC).as_posix()}": p.read_text() for p in STATIC.rglob("*.js") if "vendor" not in p.parts}
    src["/viz/data.js"] = (REPO / "viz" / "data.js").read_text()
    src["/vendor/three-0.170.0.module.min.js"] = THREE.read_text()
    return src


def _data() -> dict:
    ws = demo()
    r = load_results(ws)
    data = {
        "/api/me": {"user": {"username": "snapshot", "role": "viewer", "expires": None}, "kiosk": True, "demo": True},
        "/api/workspaces": {"workspaces": [{**ws.public(), "name": "Demo snapshot (static export)"}], "templates": {}},
        "/api/workspaces/demo": ws.public(),
        "/api/workspaces/demo/results": {"workspace": "demo", "results": r, "status_text": None if r else "not yet run"},
        "/api/workspaces/demo/scene": build_scene("demo", r, ws.src),
        "/api/workspaces/demo/ledger": ledger_payload(ws),
        "/api/workspaces/demo/runs": {"runs": [], "active": None},
        "/api/workspaces/demo/bench": bench_payload(ws),
        "/api/workspaces/demo/estimate": {**estimate(r, None), "saved_threshold_weeks": None},
    }
    led = data["/api/workspaces/demo/ledger"]
    if led.get("available"):
        from ledger.log import canonical, read_entries
        from ledger.merkle import MerkleTree, verify_proof

        entries = read_entries(ws.root / r["ledger"]["ledger_ref"])
        items = [canonical(e) for e in entries]
        tree = MerkleTree(items)
        root = tree.root()
        import hashlib

        for i, e in enumerate(entries):
            proof = tree.inclusion_proof(i)
            data[f"/api/workspaces/demo/ledger/proof/{i}"] = {
                "index": i, "type": e["type"], "tree_size": len(items), "root": root, "proof": proof,
                "leaf_hash": hashlib.sha256(b"\x00" + items[i]).hexdigest(), "verified": verify_proof(items[i], i, len(items), proof, root)}
        t = tamper_demo(ws, min(2, len(entries) - 1))
        t["recorded"] = True
        t["note"] = (f"recorded at export time ({time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}): the server verified a "
                     "temporary copy; the real ledger and results.json were not touched. This static snapshot replays that result.")
        data["/api/workspaces/demo/tamper-demo"] = t
    return data


def export(dest: Path = DIST) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "assets").mkdir(parents=True)
    shutil.copyfile(STATIC / "favicon.svg", dest / "assets" / "favicon.svg")
    shutil.copytree(STATIC / "fonts", dest / "assets" / "fonts")  # vendored OFL fonts (licences + MANIFEST included)
    html = (STATIC / "index.html").read_text()
    html = re.sub(r'\s*<link rel="stylesheet"[^>]*>', "", html)
    html = re.sub(r'\s*<link rel="modulepreload"[^>]*>', "", html)
    html = html.replace('href="/assets/favicon.svg"', 'href="assets/favicon.svg"')
    payload = ("window.__ATLAS_STATIC = " + json.dumps(_data(), separators=(",", ":")) + ";\n"
               "window.__ATLAS_SRC = " + json.dumps(_modules(), separators=(",", ":")).replace("</", "<\\/") + ";\n")
    (dest / "assets" / "snapshot.js").write_text(payload)
    (dest / "assets" / "boot.js").write_text(BOOT)
    html = html.replace('<script type="module" src="/assets/js/main.js"></script>',
                        '<script src="assets/snapshot.js"></script>\n  <script src="assets/boot.js"></script>')
    html = html.replace("</head>", f"  <style>{_all_css().replace('url(\"/assets/fonts/', 'url(\"assets/fonts/')}</style>\n</head>")
    (dest / "index.html").write_text(html)
    return dest


def _all_css() -> str:
    files = [STATIC / "css" / "tokens.css", STATIC / "css" / "app.css"]
    files += sorted(p for p in (STATIC / "css").glob("*.css") if p not in files)
    return "\n".join(p.read_text() for p in files).replace("</style", "<\\/style")
