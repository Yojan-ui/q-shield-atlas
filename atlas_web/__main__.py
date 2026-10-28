"""python -m atlas_web [serve] [--host H] [--port N] [--no-browser] [--demo] [--kiosk]
python -m atlas_web create-user [--username NAME] --role viewer|operator|admin   (password via getpass)
python -m atlas_web list-users
python -m atlas_web delete-user NAME
python -m atlas_web export                 (static read-only snapshot of the demo in atlas_web/dist/, works over file://)

Binds 127.0.0.1 by default. There is no default user: create an admin first.
"""

import argparse
import getpass
import sys
import threading
import webbrowser

from .auth import ROLES, Store
from .config import data_dir, limits


def _store() -> Store:
    lim = limits()
    return Store(data_dir() / "atlas.db", lim["session_hours"], lim["login_failures"], lim["login_window_s"])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0].startswith("-"):
        argv = ["serve", *argv]
    ap = argparse.ArgumentParser(prog="python -m atlas_web", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--demo", action="store_true", help="open the landing page on the demo workspace")
    s.add_argument("--kiosk", action="store_true", help="hide sign-out (venue kiosk)")
    c = sub.add_parser("create-user")
    c.add_argument("--username")
    c.add_argument("--role", required=True, choices=ROLES)
    sub.add_parser("list-users")
    d = sub.add_parser("delete-user")
    d.add_argument("username")
    sub.add_parser("export")
    args = ap.parse_args(argv)

    if args.command == "create-user":
        store = _store()
        username = args.username or input("username: ").strip()
        pw = getpass.getpass("password (min 10 characters): ")
        if pw != getpass.getpass("repeat password: "):
            sys.exit("passwords do not match")
        try:
            store.create_user(username, pw, args.role)
        except ValueError as e:
            sys.exit(str(e))
        print(f"created {args.role} {username.strip().lower()!r}")
        return 0
    if args.command == "list-users":
        users = _store().list_users()
        for u in users:
            print(f"{u['username']:24} {u['role']}")
        if not users:
            print("no users yet: python -m atlas_web create-user --role admin")
        return 0
    if args.command == "export":
        from .export import export

        out = export()
        print(f"static snapshot written to {out}/index.html (open it directly; no server needed)")
        return 0
    if args.command == "delete-user":
        if not _store().delete_user(args.username):
            sys.exit(f"no user {args.username!r}")
        print(f"deleted {args.username!r} and their sessions")
        return 0

    from .server import make_server

    if args.host != "127.0.0.1":
        print(f"WARNING: binding {args.host}: the app is reachable from other machines on this network. "
              "Traffic is plain HTTP (no TLS) and lab TLS services still bind 127.0.0.1 only.", file=sys.stderr)
    srv = make_server(args.host, args.port, kiosk=args.kiosk, demo=args.demo)
    host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{host}:{srv.server_address[1]}/"
    if not srv.app.store.list_users():
        print("no users yet: create one with  python -m atlas_web create-user --role admin", flush=True)
    print(f"Q-Shield Atlas web at {url} (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.app.runs.shutdown()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
