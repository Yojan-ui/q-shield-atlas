"""atlas_web real-data intake: zip safety (absolute paths, '..', symlinks, bombs), clone URL rules, upload limits."""

import io
import os
import stat
import zipfile
from pathlib import Path

import pytest

from atlas_web import intake
from atlas_web.config import limits
from atlas_web.workspaces import WorkspaceError

from .atlas_web_helpers import PASSWORD, Client, start_server


def make_zip(entries) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for e in entries:
            if isinstance(e, zipfile.ZipInfo):
                z.writestr(e, b"target")
            else:
                name, data = e
                z.writestr(name, data)
    return buf.getvalue()


def symlink_entry(name):
    zi = zipfile.ZipInfo(name)
    zi.create_system = 3
    zi.external_attr = (stat.S_IFLNK | 0o777) << 16
    return zi


@pytest.fixture
def server(monkeypatch, tmp_path):
    srv = start_server(monkeypatch, tmp_path)
    srv.app.store.create_user("ops", PASSWORD, "operator")
    c = Client(srv.server_address[1])
    c.login("ops")
    assert c.post("/api/workspaces", {"id": "w", "template": "empty"})[0] == 201
    srv.client = c
    srv.ws_root = tmp_path / "data" / "workspaces" / "w"
    yield srv
    srv.shutdown()
    srv.server_close()


def upload(srv, data: bytes, ctype="application/zip"):
    return srv.client.request("POST", "/api/workspaces/w/upload", data, headers={"Content-Type": ctype})


def test_valid_zip_unwraps_and_is_never_executable(server):
    manifest = b'{"id":"api","name":"API","kind":"service_mtls","data_class":"payments","depends_on":[]}'
    data = make_zip([("repo-main/services/api/atlas-service.json", manifest),
                     ("repo-main/services/api/run.sh", b"#!/bin/sh\necho hi\n"), ("repo-main/README", b"x")])
    status, body = upload(server, data)
    assert status == 200 and body["files"] == 3 and body["manifests"] == 1 and len(body["sha256"]) == 64
    src = server.ws_root / "src"
    assert (src / "services" / "api" / "atlas-service.json").exists()  # top-level dir unwrapped
    assert not os.access(src / "services" / "api" / "run.sh", os.X_OK)
    status, ws = server.client.get("/api/workspaces/w")
    assert ws["source"]["kind"] == "zip" and ws["source"]["sha256"] == body["sha256"]


@pytest.mark.parametrize("entries,code", [
    ([("../evil.txt", b"x")], "zip_traversal"),
    ([("a/../../evil.txt", b"x")], "zip_traversal"),
    ([("/etc/evil.txt", b"x")], "zip_absolute_path"),
    ([("C:/evil.txt", b"x")], "zip_absolute_path"),
    ([("a\\..\\evil.txt", b"x")], "zip_absolute_path"),
    ([symlink_entry("link")], "zip_symlink"),
    ([("bomb.bin", b"\0" * (20 << 20))], "zip_bomb"),
])
def test_unsafe_zips_rejected_and_src_untouched(server, entries, code):
    upload(server, make_zip([("keep/file.txt", b"keep")]))
    status, body = upload(server, make_zip(entries))
    assert status == 400 and body["error"]["code"] == code
    assert (server.ws_root / "src" / "file.txt").read_text() == "keep" or (server.ws_root / "src" / "keep" / "file.txt").exists()
    assert not (server.ws_root.parent / "evil.txt").exists() and not Path("/etc/evil.txt").exists()


def test_too_many_files_and_total_size(tmp_path):
    lim = {**limits(), "unzipped_max_files": 3}
    with zipfile.ZipFile(io.BytesIO(make_zip([(f"f{i}", b"x") for i in range(5)]))) as z, pytest.raises(WorkspaceError) as e:
        intake.check_zip(z, lim)
    assert e.value.code == "zip_too_many_files"
    lim = {**limits(), "unzipped_max_bytes": 10}
    with zipfile.ZipFile(io.BytesIO(make_zip([("a", b"y" * 11)]))) as z, pytest.raises(WorkspaceError) as e:
        intake.check_zip(z, lim)
    assert e.value.code == "zip_bomb"


def test_not_a_zip_and_wrong_type(server):
    status, body = upload(server, b"definitely not a zip")
    assert status == 400 and body["error"]["code"] == "zip_invalid"
    status, body = upload(server, make_zip([("a", b"x")]), ctype="application/octet-stream")
    assert status == 415


def test_upload_size_limit(server, monkeypatch):
    import atlas_web.server as s

    monkeypatch.setattr(s, "limits", lambda: {**limits(), "upload_max_bytes": 100})
    status, body = upload(server, make_zip([("a", os.urandom(500))]))
    assert status == 413 and body["error"]["code"] == "too_large"


@pytest.mark.parametrize("url", ["http://github.com/a/b", "file:///etc", "ssh://github.com/a/b", "git@github.com:a/b.git",
                                 "https://user:pw@github.com/a/b", "https://localhost/a/b", "https://127.0.0.1/a/b",
                                 "https://10.0.0.1/a/b", "https://github.com/a/b;rm -rf", "https://github.com/../x",
                                 "--upload-pack=x", "", "https://no-such-host.invalid/a/b"])
def test_clone_url_rules(url):
    with pytest.raises(WorkspaceError) as e:
        intake.validate_clone_url(url)
    assert e.value.code == "bad_url"


@pytest.mark.skipif(os.environ.get("ATLAS_WEB_NET_TESTS") != "1", reason="network test: set ATLAS_WEB_NET_TESTS=1")
def test_live_shallow_clone(server):
    status, body = server.client.post("/api/workspaces/w/clone", {"url": "https://github.com/octocat/Hello-World"})
    assert status == 200 and len(body["commit"]) == 40 and body["files"] >= 1
    assert not (server.ws_root / "src" / ".git").exists()
