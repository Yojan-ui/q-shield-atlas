"""Review page API: items from the latest results, roles, read-only demo, validation (signing is covered in
test_atlas_web_pipeline, which records real decisions in a temp workspace)."""

from .atlas_web_helpers import PASSWORD, Client, start_server


def test_demo_lists_items_but_cannot_decide(monkeypatch, tmp_path):
    srv = start_server(monkeypatch, tmp_path)
    try:
        for name, role in (("ops", "operator"), ("vic", "viewer")):
            srv.app.store.create_user(name, PASSWORD, role)
        ops, vic = Client(srv.server_address[1]), Client(srv.server_address[1])
        assert ops.login("ops")[0] == 200 and vic.login("vic")[0] == 200
        status, rv = ops.get("/api/workspaces/demo/reviews")
        assert status == 200 and rv["read_only"] and not rv["can_decide"]
        kinds = {i["kind"] for i in rv["items"]}
        assert {"plan", "wave", "qaoa"} <= kinds and all(i["status"] in ("pending", "approved", "rejected") for i in rv["items"])
        item = rv["items"][0]["id"]
        assert ops.post("/api/workspaces/demo/reviews", {"item": item, "decision": "approve", "reason": "fine"})[0] == 403
        assert vic.post("/api/workspaces/demo/reviews", {"item": item, "decision": "approve", "reason": "fine"})[0] == 403
        assert ops.post("/api/workspaces", {"id": "r1", "name": "r1", "template": "mock_bank"})[0] == 201
        assert ops.get("/api/workspaces/r1/reviews")[1]["items"] == []  # nothing until a run exists
        status, body = ops.post("/api/workspaces/r1/reviews", {"item": "plan:x", "decision": "maybe", "reason": "fine"})
        assert status == 422 and body["error"]["code"] == "bad_decision"
        assert ops.post("/api/workspaces/r1/reviews", {"item": "plan:x", "decision": "approve", "reason": "fine"})[1]["error"]["code"] == "unknown_item"
    finally:
        srv.shutdown()
