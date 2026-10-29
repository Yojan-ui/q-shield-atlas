"""tools/present_check.py: presentation readiness at 1440x900 in headless Chrome (stdlib CDP, tools/cdp.py).

Every page as admin: no console errors, no failed requests; the Detect 3D graph layer renders; on QAOA the
live quantum run returns a result that names its backend. Screenshots -> atlas_web/screenshots/present/
(git-ignored PNGs). Uses a temporary data dir; the repo's out/, runs/ and keys/ are only read.
"""

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO))
import route_check as rc  # noqa: E402

PAGES = ["/", "/w/demo/pipeline", "/w/demo/detect", "/w/demo/ledger", "/w/demo/schedule", "/w/demo/handshakes",
         "/w/demo/qaoa", "/w/demo/bench", "/w/demo/review", "/w/demo/migration?week=4"]


def main():
    shots = REPO / "atlas_web" / "screenshots" / "present"
    srv = rc.start_app(Path(tempfile.mkdtemp(prefix="atlas-present-")))
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    br = rc.Browser()
    bad = 0
    try:
        jar = rc.login(srv.server_address[1], "admin")
        ctx = br.new_context()
        for path in PAGES:
            r = rc.check_page(br, ctx, base, "admin", path, "1440x900", jar, shots)
            extra = f" 3D layer={r['layer']} fps={r['fps']}" if "detect" in path else ""
            print(f"{'ok ' if not r['problems'] else 'ERR'} {path:28} {r['load_s']:.2f}s{extra} {r['problems'] or ''}", flush=True)
            bad += bool(r["problems"]) or ("detect" in path and r["layer"] != "detect")
        page = br.new_page(ctx)
        try:
            page.send("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
            for k, v in jar.items():
                page.send("Network.setCookie", {"name": k, "value": v, "url": base})
            page.send("Page.navigate", {"url": base + "/w/demo/qaoa"})
            page.wait_for("document.body.dataset.ready === '1'")
            page.wait_for("!!document.querySelector('.qp button:not([disabled])')", 30)
            page.eval("document.querySelector('.qp button').click()")
            ok = page.wait_for("/Backend|Local simulator|QpiAI Cloud/.test((document.querySelector('.qp-out')||{}).innerText||'') && !document.querySelector('.qp-out .skel')", 120)
            text = page.eval("(document.querySelector('.qp-out')||{}).innerText || ''")
            page.eval("document.querySelector('.qp').scrollIntoView({block: 'center'})")
            (shots / "1440x900").mkdir(parents=True, exist_ok=True)
            page.screenshot(shots / "1440x900" / "admin__quantum_run.png")
            print(f"{'ok ' if ok and 'failed' not in text else 'ERR'} quantum run: {text.splitlines()[0] if text else '(no result)'}")
            bad += not ok or "failed" in text
        finally:
            page.close()
    finally:
        br.close()
        srv.shutdown()
    print(f"{'READY' if not bad else 'NOT READY'}: screenshots in {shots.relative_to(REPO)}/1440x900/")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
