"""tools/browser_flow.py: end-to-end runs in a real browser (Playwright, system Chrome, headless).

    python tools/browser_flow.py [--github URL] [--live online-boutique,real-banks] [--skip-github]

1. "Scan your own repo": paste a public GitHub URL on /settings/new-workspace -> workspace created -> cloned ->
   manifests suggested -> "Confirm all" on Detect -> Run pipeline -> the guided 3D run follows it live.
2. Live runs on throwaway copies of real workspaces (their signing key is copied into the throwaway dir so the run
   can append to the existing chain; it never leaves this machine's temp dir).
Each run must end PASS, light the 7 steps strictly left to right from its own events, and log
"chain verified (N entries) before append" (or "chain empty" for a new workspace). Exit 1 otherwise.
"""

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import ui_check as u  # noqa: E402


def follow_run(page, base, ws, timeout=900):
    """Start the pipeline from the Pipeline page and follow the guided view; returns (ok, notes)."""
    page.goto(f"{base}/w/{ws}/pipeline")
    page.wait_for_function("document.body.dataset.ready === '1'", timeout=30000)
    page.get_by_role("button", name="Run pipeline").click()
    page.locator("dialog[open] .btn.primary").click()
    page.wait_for_function("/Live run/.test((document.querySelector('.gd-mode') || {}).textContent || '')", timeout=30000)
    seen, order_ok, t0 = [], True, time.time()
    while time.time() - t0 < timeout:
        st = page.evaluate("[...document.querySelectorAll('.gd-steps li')].map(li => li.dataset.state || '')")
        if not seen or st != seen[-1]:
            seen.append(st)
            done = [s == "ok" for s in st]
            if any(done[j] and not done[i] for i in range(len(done)) for j in range(i + 1, len(done))):
                order_ok = False  # a later step done before an earlier one
        mode = page.evaluate("(document.querySelector('.gd-mode') || {}).textContent || ''")
        if "Replay of run" in mode or "not yet run" in mode:
            break
        page.wait_for_timeout(400)
    log = page.evaluate("[...document.querySelectorAll('.gd-log li')].map(l => l.textContent).join('\\n')")
    status = "PASS" if f"run " in log and " PASS" in log.split("\n")[-1] else ("FAIL" if " FAIL" in log else "unknown")
    chain = "chain verified" in log or "chain empty" in log
    return status == "PASS" and order_ok and chain, {"status": status, "steps_in_order": order_ok, "chain_checked_before_append": chain,
                                                      "states_seen": len(seen), "log_tail": log.split("\n")[-3:]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--github", default="https://github.com/GoogleCloudPlatform/microservices-demo")
    ap.add_argument("--live", default="online-boutique,real-banks")
    ap.add_argument("--skip-github", action="store_true")
    args = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright
    from cdp import chrome_binary

    live = [w for w in args.live.split(",") if w]
    data = Path(tempfile.mkdtemp(prefix="atlas-flow-"))
    srv = u.start_app(data, live)
    for wid in live:  # signing key for live runs on the copies (throwaway dir only)
        src = REPO / "atlas_web" / "data" / "workspaces" / wid / "keys"
        dst = data / "workspaces" / wid / "keys"
        for f in src.glob("*"):
            shutil.copy2(f, dst / f.name)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    results, ok = {}, True
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chrome_binary(), headless=True, args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, bypass_csp=True)
            ctx.add_cookies(u.login(srv.server_address[1]))
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            if not args.skip_github:
                t0 = time.time()
                page.goto(f"{base}/settings/new-workspace")
                page.wait_for_function("document.body.dataset.ready === '1'")
                page.fill("input[name=url]", "not a url")
                page.click("form .btn.primary")
                bad_url = page.locator(".field.invalid").count() > 0 or "https" in page.inner_text("form")
                page.fill("input[name=url]", args.github)
                page.click("form .btn.primary")
                page.wait_for_url("**/detect", timeout=600000)
                page.wait_for_function("document.body.dataset.ready === '1'")
                ws = page.url.split("/w/")[1].split("/")[0]
                btn = page.get_by_role("button", name="Confirm all")
                btn.first.click()
                page.wait_for_function("/confirmed|Confirmed/.test(document.body.innerText)", timeout=60000)
                okr, notes = follow_run(page, base, ws)
                notes["seconds"] = round(time.time() - t0)
                notes["bad_url_rejected"] = bad_url
                results[f"github {args.github} -> {ws}"] = notes
                ok &= okr and bad_url
            for wid in live:
                okr, notes = follow_run(page, base, wid)
                results[f"live {wid}"] = notes
                ok &= okr
            results["page_errors"] = errors
            ok &= not errors
            browser.close()
    finally:
        srv.shutdown()
        shutil.rmtree(data, ignore_errors=True)  # the copied signing keys go with it
    print(json.dumps(results, indent=1))
    print("FLOW OK" if ok else "FLOW FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
