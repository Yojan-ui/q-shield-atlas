"""python -m viz [--no-browser] [--port N]

Serves the viz on 127.0.0.1 (free port by default) and opens the browser. Only viz/ files,
out/results.json and out/report.html are served: the rest of the repo (notably keys/) is never exposed, and paths
outside the allowlist get 404. results.json cannot be loaded over file:// (CORS), hence the server.
"""

import argparse
import posixpath
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"  # loopback only, never all interfaces
ALLOWED_FILES = {"/out/results.json", "/out/report.html"}
ALLOWED_PREFIX = "/viz/"
BLOCKED_SUFFIXES = (".py", ".pyc")


def allowed(url_path: str) -> bool:
    path = posixpath.normpath(unquote(urlsplit(url_path).path))
    if path in ALLOWED_FILES:
        return True
    return path.startswith(ALLOWED_PREFIX) and ".." not in path.split("/") and not path.endswith(BLOCKED_SUFFIXES)


class VizHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".json": "application/json"}

    def do_GET(self):
        if urlsplit(self.path).path in ("/", "/viz", "/viz/"):
            self.send_response(302)
            self.send_header("Location", "/viz/index.html")
            self.end_headers()
            return
        if not allowed(self.path):
            self.send_error(404, "not served")
            return
        super().do_GET()

    def do_HEAD(self):
        if not allowed(self.path):
            self.send_error(404, "not served")
            return
        super().do_HEAD()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def make_server(port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), partial(VizHandler, directory=str(REPO)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    if not (REPO / "out" / "results.json").exists():
        print("note: out/results.json not found; the viz will show 'not yet run' everywhere")
    server = make_server(args.port)
    url = f"http://{HOST}:{server.server_address[1]}/viz/index.html"
    print(f"serving Q-Shield Atlas viz at {url} (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
