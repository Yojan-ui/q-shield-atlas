"""tools/seed_real_workspaces.py: build the ready-made REAL REPO workspaces through the atlas_web HTTP API.

For each repo pinned in detect/real_repos.json: create a workspace, clone the pinned commit, write suggested
atlas-service.json manifests, and (only with --confirm) confirm them, then run the full pipeline with the
public reference endpoints. Uses a temporary operator account that is deleted afterwards. Platform jobs stay
forbidden (QSHIELD_FORBID_PLATFORM=1); QAOA uses the free QpiAI SDK local simulator.

    python tools/seed_real_workspaces.py [--confirm] [--only online-boutique]

--confirm means: the person running this accepts the suggested kind / data class / dependencies as the
operator review. The workspace records that decision; nothing is presented as reviewed otherwise.
"""

import argparse
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
WS_IDS = {"online-boutique": "online-boutique", "opentelemetry-demo": "otel-demo"}
NAMES = {"online-boutique": "Online Boutique (real repo)", "opentelemetry-demo": "OpenTelemetry Demo (real repo)"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="accept the suggested manifests as the operator review")
    ap.add_argument("--only", choices=list(WS_IDS))
    args = ap.parse_args(argv)
    os.environ["QSHIELD_FORBID_PLATFORM"] = "1"
    from atlas_web_helpers import Client, sse_events

    from atlas_web.server import make_server

    srv = make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    user, pw = f"seed-{secrets.token_hex(3)}", secrets.token_urlsafe(18)
    srv.app.store.create_user(user, pw, "operator")
    c = Client(srv.server_address[1])
    assert c.login(user, pw)[0] == 200
    report = []
    try:
        for r in json.loads((REPO / "detect" / "real_repos.json").read_text())["repos"]:
            if args.only and r["name"] != args.only:
                continue
            ws = WS_IDS[r["name"]]
            status, body = c.post("/api/workspaces", {"id": ws, "name": NAMES[r["name"]], "template": "empty"})
            if status not in (201, 409):
                raise SystemExit(f"{ws}: create failed {body}")
            t0 = time.monotonic()
            status, cl = c.post(f"/api/workspaces/{ws}/clone", {"url": r["url"], "commit": r["commit"]})
            if status != 200:
                raise SystemExit(f"{ws}: clone failed {cl}")
            print(f"{ws}: cloned {cl['commit'][:12]} (pinned), {cl['files']} files in {time.monotonic() - t0:.1f}s", flush=True)
            status, sg = c.post(f"/api/workspaces/{ws}/manifests/suggest", {})
            print(f"{ws}: {len(sg['written'])} manifests suggested from {sg['service_dirs']} service directories", flush=True)
            if not args.confirm:
                print(f"{ws}: suggestions left for operator review; run with --confirm to accept them and run the pipeline")
                continue
            status, cf = c.post(f"/api/workspaces/{ws}/manifests/confirm", {})
            assert status == 200, cf
            t0 = time.monotonic()
            status, run = c.post(f"/api/workspaces/{ws}/runs", {"presets": ["cloudflare-pq", "gnu-classical"]})
            assert status == 202, run
            evs = sse_events(srv.server_address[1], f"/api/workspaces/{ws}/runs/{run['run_id']}/events", c.cookies,
                             lambda e, d: e == "run_end", timeout=1800)
            end = evs[-1][1]
            res = (c.get(f"/api/workspaces/{ws}/results")[1] or {}).get("results") or {}
            det = res.get("detect") or {}
            row = {"workspace": ws, "status": end["status"], "run_s": round(time.monotonic() - t0, 1),
                   "files_scanned": det.get("files_scanned"), "findings": len(det.get("findings", [])),
                   "vulnerable_findings": (det.get("summary") or {}).get("vulnerable_findings"),
                   "assets": len(res.get("assets", [])), "waves": len(res.get("waves", [])),
                   "ledger_entries": (res.get("ledger") or {}).get("entry_count"), "manifests_confirmed": len(cf["confirmed"]),
                   "probes": [(p["service"], p["live"].get("group"), [d["kind"] for d in p["drift"]]) for p in det.get("probes", [])]}
            if end["status"] != "PASS":
                row["tail"] = end["tail"][-8:]
                row["hint"] = end.get("hint")
            report.append(row)
            print(json.dumps(row), flush=True)
    finally:
        srv.app.store.delete_user(user)
        srv.shutdown()
    return 0 if all(r["status"] == "PASS" for r in report) else 1


if __name__ == "__main__":
    sys.exit(main())
