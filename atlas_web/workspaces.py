"""Workspaces: `demo` is the repo's out/ + runs/ (read-only, the DEMO.md snapshot is never overwritten);
every other workspace lives in atlas_web/data/workspaces/<id>/{src,out,runs,config,keys}, and every
pipeline step is given path flags for it, so the repo's out/, runs/ and keys/ are never touched."""

import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .auth import Store
from .config import REPO, data_dir

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
TEMPLATES = {
    "mock_bank": {"src": REPO / "detect" / "fixtures" / "mock_bank", "lab_probes": ["web-gw=legacy"],
                  "label": "Fictional bank (17 services, the demo inventory)"},
    "empty": {"src": None, "lab_probes": [], "label": "Empty: upload a .zip or clone a public repository"},
}


class WorkspaceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, fields: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.fields = code, message, status, fields


@dataclass
class Workspace:
    id: str
    name: str
    template: str
    root: Path       # ledger_ref / payload_ref are relative to this
    out: Path
    runs: Path
    src: Path
    config: Path     # holds assumptions.json
    keys: Path
    read_only: bool
    settings: dict

    @property
    def assumptions(self) -> Path:
        return self.config / "assumptions.json"

    @property
    def results(self) -> Path:
        return self.out / "results.json"

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "template": self.template, "read_only": self.read_only,
                "has_results": self.results.exists(), "lab_probes": self.settings.get("lab_probes", []),
                "source": self.settings.get("source")}


def demo() -> Workspace:
    return Workspace("demo", "Demo snapshot (DEMO.md)", "mock_bank", REPO, REPO / "out", REPO / "runs",
                     TEMPLATES["mock_bank"]["src"], REPO / "config", REPO / "keys", True,
                     {"lab_probes": ["web-gw=legacy"], "source": {"kind": "fixture", "ref": "detect/fixtures/mock_bank"}})


def ws_root(ws_id: str) -> Path:
    return data_dir() / "workspaces" / ws_id


def _from_row(row) -> Workspace:
    root = ws_root(row["id"])
    return Workspace(row["id"], row["name"], row["template"], root, root / "out", root / "runs", root / "src",
                     root / "config", root / "keys", False, json.loads(row["settings"] or "{}"))


def get(store: Store, ws_id: str) -> Workspace:
    if ws_id == "demo":
        return demo()
    with store.db() as c:
        row = c.execute("SELECT * FROM workspaces WHERE id=?", (ws_id,)).fetchone()
    if not row:
        raise WorkspaceError("not_found", f"workspace {ws_id!r} not found", 404)
    return _from_row(row)


def list_all(store: Store) -> list[Workspace]:
    with store.db() as c:
        rows = c.execute("SELECT * FROM workspaces ORDER BY created").fetchall()
    return [demo(), *map(_from_row, rows)]


def create(store: Store, ws_id: str, name: str, template: str, user: str) -> Workspace:
    if not ID_RE.match(ws_id or "") or ws_id == "demo":
        raise WorkspaceError("bad_id", "workspace id: 1-32 characters a-z 0-9 -, starting with a letter or digit; not 'demo'")
    if template not in TEMPLATES:
        raise WorkspaceError("bad_template", f"template must be one of {', '.join(TEMPLATES)}")
    name = (name or ws_id).strip()[:80]
    root = ws_root(ws_id)
    with store.db() as c:
        if c.execute("SELECT 1 FROM workspaces WHERE id=?", (ws_id,)).fetchone() or root.exists():
            raise WorkspaceError("exists", f"workspace {ws_id!r} already exists", 409)
        t = TEMPLATES[template]
        for d in ("out", "runs", "config", "keys"):
            (root / d).mkdir(parents=True, exist_ok=True)
        (root / "keys").chmod(0o700)
        if t["src"]:
            shutil.copytree(t["src"], root / "src", symlinks=False)
            source = {"kind": "template", "ref": template}
        else:
            (root / "src").mkdir()
            source = None
        shutil.copyfile(REPO / "config" / "assumptions.json", root / "config" / "assumptions.json")
        settings = {"lab_probes": t["lab_probes"], "source": source}
        c.execute("INSERT INTO workspaces VALUES (?,?,?,?,?,?)", (ws_id, name, template, user, time.time(), json.dumps(settings)))
    return get(store, ws_id)


def update_settings(store: Store, ws: Workspace, **changes) -> None:
    ws.settings.update(changes)
    with store.db() as c:
        c.execute("UPDATE workspaces SET settings=? WHERE id=?", (json.dumps(ws.settings), ws.id))


def require_writable(ws: Workspace) -> None:
    if ws.read_only:
        raise WorkspaceError("read_only", "the demo workspace is a read-only snapshot; create a workspace to run on your own data", 403)
