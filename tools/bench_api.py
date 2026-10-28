"""tools/bench_api.py: latency of the read API on localhost (keep-alive connection, signed in as a viewer).

    python tools/bench_api.py [-n 300]

Reports p50/p95/max per endpoint; fails (exit 1) if any p95 >= 50 ms. Uses a throwaway data dir; the demo
workspace reads the repo's out/ snapshot read-only.
"""

import argparse
import http.client
import json
import os
import statistics
import sys
import tempfile
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
BUDGET_MS = 50.0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=300)
    args = ap.parse_args(argv)
    os.environ["ATLAS_WEB_DATA"] = tempfile.mkdtemp(prefix="atlas-bench-")
    from atlas_web.server import make_server

    srv = make_server("127.0.0.1", 0)
    srv.app.store.create_user("bench", "bench-password-1", "viewer")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request("POST", "/api/auth/login", json.dumps({"username": "bench", "password": "bench-password-1"}), {"Content-Type": "application/json"})
    r = c.getresponse()
    r.read()
    cookie = "; ".join(f"{k}={m.value}" for v in r.headers.get_all("Set-Cookie") for k, m in SimpleCookie(v).items())
    c.request("GET", "/api/workspaces/demo/scene", headers={"Cookie": cookie})
    r = c.getresponse()
    r.read()
    etag = r.headers.get("ETag")
    endpoints = [("/api/health", {}), ("/api/me", {}), ("/api/workspaces", {}), ("/api/workspaces/demo/results", {}),
                 ("/api/workspaces/demo/scene", {}), ("/api/workspaces/demo/scene (304)", {"If-None-Match": etag}),
                 ("/api/workspaces/demo/ledger", {}), ("/api/workspaces/demo/manifests", {}), ("/api/workspaces/demo/assumptions", {}),
                 ("/", {})]
    rows, ok = [], True
    for label, extra in endpoints:
        path = label.split(" ")[0]
        times = []
        for i in range(args.n + 10):
            t0 = time.perf_counter()
            c.request("GET", path, headers={"Cookie": cookie, **extra})
            r = c.getresponse()
            body = r.read()
            dt = (time.perf_counter() - t0) * 1000
            if r.status not in (200, 304):
                raise SystemExit(f"{label}: HTTP {r.status} {body[:200]!r}")
            if i >= 10:  # warm-up excluded (first ledger read verifies the ML-DSA signatures once, then caches)
                times.append(dt)
        times.sort()
        p95 = times[int(len(times) * 0.95) - 1]
        ok &= p95 < BUDGET_MS
        rows.append({"endpoint": label, "p50_ms": round(statistics.median(times), 2), "p95_ms": round(p95, 2), "max_ms": round(times[-1], 2),
                     "bytes": len(body)})
    srv.shutdown()
    for row in rows:
        print(f"{row['endpoint']:42} p50 {row['p50_ms']:6.2f} ms  p95 {row['p95_ms']:6.2f} ms  max {row['max_ms']:6.2f} ms  {row['bytes']:>7} B")
    print(json.dumps({"n": args.n, "budget_p95_ms": BUDGET_MS, "worst_p95_ms": max(r["p95_ms"] for r in rows), "pass": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
