"""Access matrix: only the demo snapshot views (results, ledger incl. proofs, report, scene), /api/me and
/api/health answer without a session; everything else is 401 signed out and 403 for the wrong role."""

import pytest

from .atlas_web_helpers import PASSWORD, Client, start_server

PUBLIC = [("GET", "/api/me"), ("GET", "/api/health"), ("GET", "/api/workspaces/demo/results"),
          ("GET", "/api/workspaces/demo/ledger"), ("GET", "/api/workspaces/demo/report"),
          ("GET", "/api/workspaces/demo/scene")]

SIGNED_IN = [  # (method, path, minimum role)
    ("GET", "/api/workspaces", "viewer"), ("POST", "/api/workspaces", "operator"),
    ("GET", "/api/workspaces/demo", "viewer"), ("GET", "/api/workspaces/demo/manifests", "viewer"),
    ("GET", "/api/workspaces/demo/assumptions", "viewer"), ("GET", "/api/workspaces/demo/calibration", "viewer"),
    ("GET", "/api/workspaces/demo/runs", "viewer"), ("POST", "/api/workspaces/demo/tamper-demo", "viewer"),
    ("GET", "/api/events?ws=demo", "viewer"), ("GET", "/api/events?ws=bank", "viewer"),
    ("GET", "/api/preflight", "operator"), ("GET", "/api/preflight?ws=bank", "operator"),
    ("GET", "/api/users", "admin"), ("POST", "/api/users", "admin"), ("DELETE", "/api/users/vic", "admin"),
    *[("GET", f"/api/workspaces/bank{p}", "viewer") for p in
      ("", "/results", "/ledger", "/ledger/proof/0", "/report", "/scene", "/manifests", "/assumptions", "/calibration",
       "/runs", "/runs/0123456789abcdef", "/runs/0123456789abcdef/events")],
    ("POST", "/api/workspaces/bank/tamper-demo", "viewer"),
    ("POST", "/api/workspaces/bank/runs", "operator"), ("POST", "/api/workspaces/bank/upload", "operator"),
    ("POST", "/api/workspaces/bank/clone", "operator"), ("POST", "/api/workspaces/bank/manifests", "operator"),
    ("PUT", "/api/workspaces/bank/assumptions", "operator"), ("POST", "/api/workspaces/bank/calibration", "operator"),
    ("POST", "/api/workspaces/bank/calibration/apply", "operator"),
]
BELOW = {"viewer": [], "operator": ["vic"], "admin": ["vic", "ops"]}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    srv = start_server(mp, tmp_path_factory.mktemp("acc"))
    for name, role in (("ada", "admin"), ("ops", "operator"), ("vic", "viewer")):
        srv.app.store.create_user(name, PASSWORD, role)
    c = Client(srv.server_address[1])
    c.login("ops")
    assert c.post("/api/workspaces", {"id": "bank", "template": "mock_bank"})[0] == 201
    srv.clients = {}
    for name in ("ada", "ops", "vic"):
        srv.clients[name] = Client(srv.server_address[1])
        srv.clients[name].login(name)
    yield srv
    srv.shutdown()
    srv.server_close()
    mp.undo()


def send(c, method, path):
    body = None if method in ("GET", "DELETE") else {}
    return c.request(method, path, body)


@pytest.mark.parametrize("method,path", PUBLIC)
def test_public_endpoints(server, method, path):
    status, body = send(Client(server.server_address[1]), method, path)
    assert status in (200, 404), (path, status)  # 404 only when the demo has no report/ledger yet
    if status == 404:
        assert body["error"]["code"] in ("not_yet_run", "no_ledger")


@pytest.mark.parametrize("method,path,role", SIGNED_IN)
def test_signed_out_is_401(server, method, path, role):
    status, body = send(Client(server.server_address[1]), method, path)
    assert status == 401 and body["error"]["code"] == "unauthenticated", (method, path, status, body)


@pytest.mark.parametrize("method,path,role", [x for x in SIGNED_IN if BELOW[x[2]]])
def test_wrong_role_is_403(server, method, path, role):
    for name in BELOW[role]:
        status, body = send(server.clients[name], method, path)
        assert status == 403 and body["error"]["code"] == "forbidden", (name, method, path, status, body)


def test_unknown_workspace_is_401_signed_out_not_404(server):
    assert send(Client(server.server_address[1]), "GET", "/api/workspaces/secret-ws/results")[0] == 401
