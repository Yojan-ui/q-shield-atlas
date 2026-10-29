"""tools/ui_check.py: real-browser UI check with Playwright (system Chrome, headless).

    python tools/ui_check.py [--sizes 1440x900,1280x720,390x844] [--workspaces demo,real-banks,online-boutique,otel-demo]

Starts the app in-process on a free 127.0.0.1 port with a throwaway data dir, copies the real workspaces'
out/ runs/ src/ config/ and their PUBLIC ledger key only (never the private key), signs in, and loads every page
at every size. Per page it fails on: console errors/warnings, page errors (incl. unhandled rejections), failed or
>= 400 requests, overlapping text (bounding boxes of every visible text run and SVG <text>), text clipped by an
overflow:hidden/clip container, text hidden under the fixed 56 px nav, elements wider than the viewport and numbers
wider than their card. Screenshots -> atlas_web/screenshots/final/<size>/ (PNGs are git-ignored). Exit 1 on problems.
"""

import argparse
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
PASSWORD = "ui-check-password-1"
ROUTES = ["pipeline", "detect", "inventory", "schedule", "handshakes", "ledger", "qaoa", "bench", "review", "migration"]
GLOBAL = ["/", "/glossary", "/settings/new-workspace"]

PROBE = r"""() => {
  const out = { overlap: [], clipped: [], undernav: [], overflow: [], numbers: [] };
  const vis = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0 || e.hidden || e.classList.contains('sr-only')) return false; } return true; };
  const navH = (document.querySelector('.strip') || { getBoundingClientRect: () => ({ bottom: 0 }) }).getBoundingClientRect().bottom;
  const runs = [];  // {r, el, t}
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement;
    if (!el || !n.textContent.trim() || el.closest('svg, script, style, #prov-tip, .tip, .toast, dialog:not([open])') || !vis(el)) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    for (const r of range.getClientRects()) if (r.width > 1 && r.height > 1) runs.push({ r, el, t: n.textContent.trim().slice(0, 40) });
  }
  for (const el of document.querySelectorAll('svg text')) {
    if (!el.textContent.trim() || !vis(el) || el.querySelector('tspan')) continue;
    const r = el.getBoundingClientRect(); if (r.width > 1) runs.push({ r, el, t: el.textContent.trim().slice(0, 40) });
  }
  for (const el of document.querySelectorAll('svg tspan')) { if (!vis(el)) continue; const r = el.getBoundingClientRect(); if (r.width > 1) runs.push({ r, el, t: el.textContent.trim().slice(0, 40) }); }
  const clipTo = (r, el) => {  // the part of r actually visible through overflow-hidden/auto ancestors
    let L = r.left, T = r.top, R = r.right, B = r.bottom;
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const cs = getComputedStyle(a); if (!/(hidden|clip|auto|scroll)/.test(cs.overflowX + cs.overflowY)) continue;
      if (!/(auto|scroll)/.test(cs.overflowX + cs.overflowY)) continue;  // hidden/clip: reported as clipped below
      const q = a.getBoundingClientRect(); L = Math.max(L, q.left); T = Math.max(T, q.top); R = Math.min(R, q.right); B = Math.min(B, q.bottom);
    }
    return R - L > 1 && B - T > 1 ? { left: L, top: T, right: R, bottom: B } : null;
  };
  const fixedOf = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) if (getComputedStyle(e).position === 'fixed') return e; return null; };
  for (const x of runs) { x.r = clipTo(x.r, x.el); x.fixed = fixedOf(x.el); }
  for (let k = runs.length - 1; k >= 0; k--) if (!runs[k].r) runs.splice(k, 1);
  const hit = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
  for (let i = 0; i < runs.length; i++) for (let j = i + 1; j < runs.length; j++) {
    const A = runs[i], B = runs[j];
    if (A.el === B.el || A.el.contains(B.el) || B.el.contains(A.el)) continue;
    if (A.fixed !== B.fixed) continue;  // fixed chrome (top strip, phone bottom rail) over scrolling content; under-nav is checked below
    if (hit(A.r, B.r)) { out.overlap.push(`"${A.t}" x "${B.t}"`); if (out.overlap.length > 8) break; }
  }
  for (const { r, el, t } of runs) {
    if (!el.closest('.strip') && r.top < navH - 1 && r.bottom > 0 && getComputedStyle(document.querySelector('.strip') || document.body).position === 'fixed' && scrollY === 0) out.undernav.push(t);
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (!/(hidden|clip)/.test(cs.overflowX + cs.overflowY) || cs.textOverflow === 'ellipsis' || getComputedStyle(el).textOverflow === 'ellipsis') continue;
      const ar = a.getBoundingClientRect();
      if (r.right > ar.right + 1.5 || r.left < ar.left - 1.5 || r.bottom > ar.bottom + 1.5 || r.top < ar.top - 1.5) { out.clipped.push(`${t} (in ${typeof a.className === "string" ? a.className : a.tagName})`); break; }
    }
  }
  if (document.documentElement.scrollWidth > innerWidth + 1) out.overflow.push(`page ${document.documentElement.scrollWidth} > ${innerWidth}`);
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('canvas, #world, .gr-labels, [style*="overflow"]') || !vis(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width > innerWidth + 1 && !el.closest('table, pre, .log, .gd-log')) { out.overflow.push(`${el.tagName}.${el.className} ${Math.round(r.width)}px`); if (out.overflow.length > 5) break; }
  }
  for (const el of document.querySelectorAll('.stat .value, .ld-num, .pg-stat .num, .ld-card .num')) {
    const c = el.closest('.pg-stat, .stat, .ld-stat, .ld-card'); if (c && el.getBoundingClientRect().right > c.getBoundingClientRect().right + 1.5) out.numbers.push(el.textContent.trim());
  }
  for (const k of Object.keys(out)) out[k] = [...new Set(out[k])].slice(0, 8);
  return out;
}"""


def start_app(data: Path, workspaces: list[str]):
    os.environ["ATLAS_WEB_DATA"] = str(data)
    from atlas_web import workspaces as wsmod
    from atlas_web.server import make_server

    srv = make_server("127.0.0.1", 0)
    srv.app.store.create_user("admin", PASSWORD, "admin")
    for wid in workspaces:
        if wid == "demo":
            continue
        src = REPO / "atlas_web" / "data" / "workspaces" / wid
        if not src.exists():
            continue
        ws = wsmod.create(srv.app.store, wid, f"{wid} (copy)", "mock_bank", "admin")
        for d in ("out", "runs", "src", "config"):
            if (src / d).exists():
                shutil.rmtree(ws.root / d, ignore_errors=True)
                shutil.copytree(src / d, ws.root / d)
        ws.keys.mkdir(parents=True, exist_ok=True)
        for pub in (src / "keys").glob("*.pub.*"):  # the public key only: enough to verify, never to sign
            shutil.copy2(pub, ws.keys / pub.name)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def login(port):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request("POST", "/api/auth/login", json.dumps({"username": "admin", "password": PASSWORD}), {"Content-Type": "application/json"})
    r = c.getresponse(); r.read()
    return [{"name": k, "value": m.value, "domain": "127.0.0.1", "path": "/"} for v in r.headers.get_all("Set-Cookie") for k, m in SimpleCookie(v).items()]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="1440x900,1280x720,390x844")
    ap.add_argument("--workspaces", default="demo,real-banks,online-boutique,otel-demo")
    ap.add_argument("--routes", default=",".join(ROUTES))
    args = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright
    from cdp import chrome_binary

    wss = args.workspaces.split(",")
    srv = start_app(Path(tempfile.mkdtemp(prefix="atlas-ui-check-")), wss)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    cookies = login(srv.server_address[1])
    paths = GLOBAL + [f"/w/{w}/{r}" for w in wss for r in args.routes.split(",")]
    shots = REPO / "atlas_web" / "screenshots" / "final"
    problems, n = {}, 0
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_binary(), headless=True, args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
        try:
            for size in args.sizes.split(","):
                w, hgt = map(int, size.split("x"))
                ctx = browser.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1, is_mobile=w < 600, has_touch=w < 600, bypass_csp=True)  # the probe is evaluated JS
                ctx.add_cookies(cookies)
                (shots / size).mkdir(parents=True, exist_ok=True)
                for path in paths:
                    page = ctx.new_page()
                    bad = []
                    page.on("console", lambda m: bad.append(f"console.{m.type}: {m.text[:160]}") if m.type in ("error", "warning") and "GL Driver Message" not in m.text else None)  # SwiftShader stalls during screenshots
                    page.on("pageerror", lambda e: bad.append(f"pageerror: {str(e)[:160]}"))
                    page.on("requestfailed", lambda r: bad.append(f"failed: {r.url.replace(base, '')} {r.failure}") if "/api/events" not in r.url and "/runs/" not in r.url else None)
                    page.on("response", lambda r: bad.append(f"HTTP {r.status} {r.url.replace(base, '')}") if r.status >= 400 else None)
                    try:
                        page.goto(base + path, wait_until="domcontentloaded")
                        page.wait_for_function("document.body && document.body.dataset.ready === '1' && !document.querySelector('.skel')", timeout=20000)
                        page.wait_for_timeout(1800)  # count-ups, reveals and the 3D first frames settle
                        res = page.evaluate(PROBE)
                        for k, v in res.items():
                            bad += [f"{k}: {x}" for x in v]
                        page.screenshot(path=str(shots / size / ((path.strip("/").replace("/", "_") or "landing") + ".png")))
                    except Exception as exc:  # noqa: BLE001 - a page that never becomes ready is a problem, not a crash
                        bad.append(f"not ready: {str(exc)[:160]}")
                    finally:
                        page.close()
                    n += 1
                    if bad:
                        problems[f"{size} {path}"] = bad
                ctx.close()
        finally:
            browser.close()
            srv.shutdown()
    for k, v in problems.items():
        print(k)
        for x in v:
            print("   ", x)
    print(json.dumps({"pages": n, "pages_with_problems": len(problems)}))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
