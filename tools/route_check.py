"""tools/route_check.py: load every atlas_web route in headless Chrome at 1440×900, 1280×720 and 390×844 as
admin, operator, viewer and signed out. Fails on any console error/warning, failed request, HTTP >= 400,
uncaught exception, unhandled rejection or error toast. Saves screenshots and a JSON report.

    python tools/route_check.py [--stage stage3] [--no-shots] [--only ROLE]

Runs against a throwaway data dir (users + an un-run `bank` workspace); the demo workspace reads the
repo's out/ snapshot read-only. Nothing in the repo is written except atlas_web/screenshots/<stage>/.
"""

import argparse
import http.client
import json
import os
import sys
import tempfile
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from cdp import Browser  # noqa: E402

SIZES = {"1440x900": (1440, 900, False), "1280x720": (1280, 720, False), "390x844": (390, 844, True)}
ROLES = ["admin", "operator", "viewer", "anon"]
PASSWORD = "route-check-password"
PUBLIC = ["/", "/signin", "/styleguide?dev", "/no/such/place"]
WS_ROUTES = ["pipeline", "detect", "schedule", "handshakes", "ledger", "qaoa"]
AUTH = [f"/w/demo/{r}" for r in WS_ROUTES] + ["/w/demo/schedule?scenario=Z2032", "/w/demo/asset/web-gw", "/w/demo/asset/no-such-asset",
                                              "/w/bank/pipeline", "/w/bank/detect", "/w/bank/schedule", "/w/bank/ledger", "/settings/users"]


def expected_route(role, path):
    p = path.split("?")[0]
    if p == "/styleguide":
        return "styleguide"
    if p == "/no/such/place":
        return "notfound"
    if p == "/":
        return "landing"
    if p == "/signin":
        return "signin" if role == "anon" else "pipeline"
    if role == "anon":
        return "signin"
    if p == "/settings/users":
        return "users" if role == "admin" else "forbidden"
    return "asset" if "/asset/" in p else p.rsplit("/", 1)[1]


def shot_name(path):
    s = path.strip("/").replace("/", "_").replace("?", "_q_").replace("=", "-") or "landing"
    return s


def start_app(data):
    os.environ["ATLAS_WEB_DATA"] = str(data)
    from atlas_web import workspaces
    from atlas_web.server import make_server

    srv = make_server("127.0.0.1", 0)
    store = srv.app.store
    for role in ("admin", "operator", "viewer"):
        store.create_user(role, PASSWORD, role)
    workspaces.create(store, "bank", "Bank (not yet run)", "mock_bank", "admin")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def login(port, role):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request("POST", "/api/auth/login", json.dumps({"username": role, "password": PASSWORD}), {"Content-Type": "application/json"})
    r = c.getresponse()
    r.read()
    assert r.status == 200, f"login {role}: {r.status}"
    jar = {}
    for v in r.headers.get_all("Set-Cookie"):
        for k, m in SimpleCookie(v).items():
            jar[k] = m.value
    return jar


def check_page(browser, ctx_id, base, role, path, size, cookies, shots_dir):
    w, h, mobile = SIZES[size]
    page = browser.new_page(ctx_id)
    problems = []
    try:
        for d in ("Runtime", "Log", "Network", "Page"):
            page.send(f"{d}.enable")
        page.send("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": mobile})
        if mobile:
            page.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
        for k, v in cookies.items():
            page.send("Network.setCookie", {"name": k, "value": v, "url": base, "httpOnly": k == "atlas_session", "sameSite": "Strict"})
        t0 = time.monotonic()
        page.send("Page.navigate", {"url": base + path})
        ok = page.wait_for("document.body && document.body.dataset.ready === '1' && !!document.body.dataset.route", 20)
        if not ok:
            problems.append("page never became ready")
        # settle: wait until no non-SSE request is in flight for 400 ms (max 6 s)
        idle_since, end = time.monotonic(), time.monotonic() + 6
        while time.monotonic() < end:
            inflight = {}
            for m, p in list(page.events):
                if m == "Network.requestWillBeSent" and p.get("type") != "EventSource":
                    inflight[p["requestId"]] = p["request"]["url"]
                elif m in ("Network.loadingFinished", "Network.loadingFailed"):
                    inflight.pop(p["requestId"], None)
            if inflight:
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since > 0.4:
                break
            time.sleep(0.05)
        load_s = time.monotonic() - t0
        route = page.eval("document.body.dataset.route")
        want = expected_route(role, path)
        if route != want:
            problems.append(f"route {route!r}, expected {want!r}")
        info = page.eval("""(() => ({title: document.title, h1: (document.querySelector('h1')||{}).textContent || null,
            focused: document.activeElement && document.activeElement.tagName, errors: window.__atlasErrors || [],
            overflowX: document.documentElement.scrollWidth > innerWidth + 1,
            fcp: (performance.getEntriesByName('first-contentful-paint')[0]||{}).startTime || null,
            readyAt: Number(document.body.dataset.readyAt || 0), path: location.pathname + location.search}))()""")
        if not info["h1"]:
            problems.append("no h1")
        if info["focused"] != "H1":
            problems.append(f"focus not on heading ({info['focused']})")
        if not info["title"].endswith("Q-Shield Atlas"):
            problems.append(f"title {info['title']!r}")
        if info["overflowX"]:
            problems.append("horizontal overflow")
        problems += [f"app error: {e}" for e in info["errors"]]
        reqs = {}
        for m, p in page.events:
            if m == "Runtime.consoleAPICalled" and p["type"] in ("error", "warning", "assert"):
                problems.append(f"console.{p['type']}: {' '.join(str(a.get('value', a.get('description', ''))) for a in p['args'])[:200]}")
            elif m == "Runtime.exceptionThrown":
                d = p["exceptionDetails"]
                problems.append(f"exception: {(d.get('exception') or {}).get('description', d.get('text'))[:200]}")
            elif m == "Log.entryAdded" and p["entry"]["level"] in ("error", "warning"):
                problems.append(f"log.{p['entry']['level']}: {p['entry'].get('text', '')[:200]} {p['entry'].get('url', '')}")
            elif m == "Network.requestWillBeSent":
                reqs[p["requestId"]] = p["request"]["url"]
            elif m == "Network.responseReceived" and p["response"]["status"] >= 400:
                problems.append(f"HTTP {p['response']['status']}: {p['response']['url']}")
            elif m == "Network.loadingFailed" and p.get("type") != "EventSource" and not p.get("canceled"):
                problems.append(f"request failed: {reqs.get(p['requestId'])} {p.get('errorText')}")
        api_calls = sorted({u.split(base)[-1] for u in reqs.values() if "/api/" in u})
        if shots_dir is not None:
            page.screenshot(shots_dir / size / f"{role}__{shot_name(path)}.png")
        return {"role": role, "path": path, "size": size, "route": route, "problems": problems, "load_s": round(load_s, 3),
                "fcp_ms": info["fcp"], "ready_ms": info["readyAt"], "api": api_calls, "title": info["title"]}
    finally:
        page.close()


def flows(browser, base, cookies):
    """Back/forward, rail keys, deep-link refresh, query state."""
    page = browser.new_page(browser.new_context())
    problems = []
    try:
        page.send("Runtime.enable")
        page.send("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        for k, v in cookies.items():
            page.send("Network.setCookie", {"name": k, "value": v, "url": base})
        page.send("Page.navigate", {"url": base + "/w/demo/pipeline"})
        page.wait_for("document.body.dataset.ready === '1'")
        r = lambda: page.eval("document.body.dataset.route")  # noqa: E731
        page.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "3", "text": "3"})
        page.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "3"})
        page.wait_for("document.body.dataset.route === 'schedule'", 5) or problems.append(f"key 3 -> {r()}")
        page.eval("document.querySelector('a[href=\"/w/demo/ledger\"]').click()")
        page.wait_for("document.body.dataset.route === 'ledger'", 5) or problems.append(f"rail click -> {r()}")
        page.eval("history.back()")
        page.wait_for("document.body.dataset.route === 'schedule'", 5) or problems.append(f"back -> {r()}")
        page.eval("history.back()")
        page.wait_for("document.body.dataset.route === 'pipeline'", 5) or problems.append(f"back x2 -> {r()}")
        page.eval("history.forward()")
        page.wait_for("document.body.dataset.route === 'schedule'", 5) or problems.append(f"forward -> {r()}")
        page.send("Page.navigate", {"url": base + "/w/demo/schedule?scenario=Z2035"})
        page.wait_for("document.body.dataset.ready === '1' && document.body.dataset.route === 'schedule'")
        page.wait_for("!!document.querySelector('[role=radio][aria-checked=true]')", 5)
        sel = page.eval("(document.querySelector('[role=radio][aria-checked=true]')||{}).textContent")
        if not sel or "Z2035" not in sel:
            problems.append(f"?scenario=Z2035 not restored ({sel})")
        page.eval("[...document.querySelectorAll('[role=radio]')].find(b => b.textContent.includes('Z2030')).click()")
        if "scenario=Z2030" not in page.eval("location.search"):
            problems.append("scenario change not written to the query")
        page.send("Page.reload")
        page.wait_for("document.body.dataset.ready === '1' && document.body.dataset.route === 'schedule'") or problems.append("refresh lost the route")
        return problems
    finally:
        page.close()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="stage3")
    ap.add_argument("--no-shots", action="store_true")
    ap.add_argument("--only", choices=ROLES)
    args = ap.parse_args(argv)
    data = Path(tempfile.mkdtemp(prefix="atlas-routecheck-"))
    srv = start_app(data)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    browser = Browser()
    shots = None if args.no_shots else REPO / "atlas_web" / "screenshots" / args.stage
    results = []
    try:
        jars = {r: ({} if r == "anon" else login(srv.server_address[1], r)) for r in ROLES}
        for role in [args.only] if args.only else ROLES:
            ctx = browser.new_context()
            paths = PUBLIC + AUTH
            for size in SIZES:
                for path in paths:
                    keep = shots is not None and (role == "admin" or (role == "anon" and path in PUBLIC + ["/w/demo/pipeline"])
                                                  or (role == "viewer" and path == "/settings/users"))
                    res = check_page(browser, ctx, base, role, path, size, jars[role], shots if keep else None)
                    results.append(res)
                    mark = "ok " if not res["problems"] else "ERR"
                    print(f"{mark} {role:8} {size:8} {path:40} -> {res['route']:10} {res['load_s']:.2f}s"
                          + ("" if not res["problems"] else "\n      " + "\n      ".join(res["problems"])), flush=True)
        flow_problems = flows(browser, base, jars["admin"])
    finally:
        browser.close()
        srv.shutdown()
    bad = [r for r in results if r["problems"]]
    landing = [r["fcp_ms"] for r in results if r["path"] == "/" and r["fcp_ms"]]
    summary = {"chrome": browser.version, "pages": len(results), "pages_with_problems": len(bad), "flow_problems": flow_problems,
               "landing_fcp_ms_max": max(landing) if landing else None, "ready_ms_max": max(r["ready_ms"] for r in results),
               "load_s_p95": sorted(r["load_s"] for r in results)[int(len(results) * 0.95) - 1]}
    out = REPO / "atlas_web" / "screenshots" / args.stage / "route_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": results}, indent=1))
    print(json.dumps(summary, indent=1))
    return 1 if bad or flow_problems else 0


if __name__ == "__main__":
    sys.exit(main())
