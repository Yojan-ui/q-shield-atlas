"""Real-data intake: safe .zip extraction, shallow git clone of a public https URL, and
atlas-service.json manifests. Uploaded or cloned code is only ever read by the static scanner,
never executed."""

import ipaddress
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from detect.inventory import MANIFEST

from .workspaces import Workspace, WorkspaceError

CLONE_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:\d{1,5})?/[A-Za-z0-9._~/-]+$")
SERVICE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _replace_src(ws: Workspace, new_src: Path) -> None:
    old = ws.src.with_name("src.old")
    shutil.rmtree(old, ignore_errors=True)
    if ws.src.exists():
        ws.src.rename(old)
    new_src.rename(ws.src)
    shutil.rmtree(old, ignore_errors=True)


def check_zip(zf: zipfile.ZipFile, limits: dict) -> list[zipfile.ZipInfo]:
    infos = zf.infolist()
    if len(infos) > limits["unzipped_max_files"]:
        raise WorkspaceError("zip_too_many_files", f"archive has {len(infos)} entries (limit {limits['unzipped_max_files']})")
    total = 0
    for i in infos:
        name = i.filename
        p = PurePosixPath(name)
        if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name) or "\\" in name:
            raise WorkspaceError("zip_absolute_path", f"absolute or non-POSIX path in archive: {name!r}")
        if ".." in p.parts:
            raise WorkspaceError("zip_traversal", f"path traversal in archive: {name!r}")
        mode = i.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise WorkspaceError("zip_symlink", f"symbolic link in archive: {name!r}")
        if i.flag_bits & 0x1:
            raise WorkspaceError("zip_encrypted", f"encrypted entry: {name!r}")
        total += i.file_size
        if i.file_size and i.compress_size and i.file_size / i.compress_size > limits["max_compression_ratio"]:
            raise WorkspaceError("zip_bomb", f"compression ratio of {name!r} exceeds {limits['max_compression_ratio']}:1")
        if total > limits["unzipped_max_bytes"]:
            raise WorkspaceError("zip_bomb", f"archive expands beyond {limits['unzipped_max_bytes']} bytes")
    return infos


def extract_zip(ws: Workspace, zip_path: Path, limits: dict) -> dict:
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise WorkspaceError("zip_invalid", "the upload is not a valid .zip archive") from None
    with zf, tempfile.TemporaryDirectory(dir=ws.root) as tmp:
        infos = check_zip(zf, limits)
        dest = Path(tmp) / "src"
        dest.mkdir()
        written = 0
        for i in infos:
            target = (dest / i.filename).resolve()
            if not str(target).startswith(str(dest.resolve()) + os.sep) and target != dest.resolve():
                raise WorkspaceError("zip_traversal", f"path escapes the workspace: {i.filename!r}")
            if i.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(i) as src, open(target, "wb") as out:  # streamed with a hard byte cap
                while chunk := src.read(1 << 16):
                    written += len(chunk)
                    if written > limits["unzipped_max_bytes"]:
                        raise WorkspaceError("zip_bomb", f"archive expands beyond {limits['unzipped_max_bytes']} bytes")
                    out.write(chunk)
            target.chmod(0o644)  # never executable
        root = _single_top_dir(dest)
        _replace_src(ws, root)
    files = sum(1 for p in ws.src.rglob("*") if p.is_file())
    return {"files": files, "bytes": written, "manifests": len(list(ws.src.rglob(MANIFEST)))}


def _single_top_dir(dest: Path) -> Path:
    """`repo-main/…` archives unwrap to their single top-level directory."""
    kids = [k for k in dest.iterdir() if k.name not in ("__MACOSX", ".DS_Store")]
    return kids[0] if len(kids) == 1 and kids[0].is_dir() else dest


def _public_host(host: str) -> bool:
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)}
    except socket.gaierror:
        return False
    return bool(addrs) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)


def validate_clone_url(url: str) -> str:
    url = (url or "").strip()
    if not CLONE_RE.match(url) or "@" in url or ".." in url:
        raise WorkspaceError("bad_url", "use a public https:// repository URL, e.g. https://github.com/owner/repo")
    host = urlsplit(url).hostname or ""
    if not _public_host(host):
        raise WorkspaceError("bad_url", f"{host} does not resolve to a public address; only public repositories can be cloned")
    return url


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def clone(ws: Workspace, url: str, timeout: float, commit: str | None = None) -> dict:
    """Shallow clone of a public https repository; with `commit`, exactly that commit (fetched by id, verified)."""
    url = validate_clone_url(url)
    if commit is not None and not COMMIT_RE.match(commit):
        raise WorkspaceError("bad_commit", "commit must be a full 40-character hexadecimal id")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(ws.root), "GIT_TERMINAL_PROMPT": "0",
           "GIT_LFS_SKIP_SMUDGE": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    with tempfile.TemporaryDirectory(dir=ws.root) as tmp:
        dest = Path(tmp) / "src"
        safe = ["git", "-c", "core.symlinks=false", "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never",
                "-c", "protocol.https.allow=always"]
        if commit is None:
            steps = [[*safe, "clone", "--depth", "1", "--no-tags", "--single-branch", "--", url, str(dest)]]
        else:
            dest.mkdir()
            g = [*safe, "-C", str(dest)]
            steps = [[*g, "init", "-q"], [*g, "remote", "add", "origin", url], [*g, "fetch", "-q", "--depth", "1", "--no-tags", "origin", commit],
                     [*g, "-c", "advice.detachedHead=false", "checkout", "-q", "--force", commit]]
        deadline = time.monotonic() + timeout
        for cmd in steps:
            try:
                proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=max(1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise WorkspaceError("clone_timeout", f"git clone did not finish within {timeout:g} s", 504) from None
            if proc.returncode != 0:
                msg = (proc.stderr.strip().splitlines() or ["git clone failed"])[-1][:300]
                raise WorkspaceError("clone_failed", msg, 502)
        head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], env=env, capture_output=True, text=True).stdout.strip()
        if commit is not None and head != commit:
            raise WorkspaceError("clone_failed", f"checked out {head}, expected the pinned commit {commit}", 502)
        shutil.rmtree(dest / ".git")
        for p in dest.rglob("*"):
            if p.is_symlink():
                p.unlink()
        _replace_src(ws, dest)
    files = sum(1 for p in ws.src.rglob("*") if p.is_file())
    return {"url": url, "commit": head, "pinned": commit is not None, "files": files, "manifests": len(list(ws.src.rglob(MANIFEST)))}


# ---------------- manifests ----------------

def _candidate_dirs(src: Path, max_depth: int = 3) -> list[str]:
    out = []
    for p in sorted(src.rglob("*")):
        if p.is_dir() and not p.is_symlink() and len(p.relative_to(src).parts) <= max_depth \
                and not any(part.startswith(".") or part in ("node_modules", "vendor", "__pycache__") for part in p.relative_to(src).parts):
            out.append(p.relative_to(src).as_posix())
    return out[:2000]


def list_manifests(ws: Workspace, assumptions: dict) -> dict:
    services = []
    if ws.src.exists():
        for m in sorted(ws.src.rglob(MANIFEST)):
            try:
                data = json.loads(m.read_text())
                err = None
            except (OSError, ValueError) as exc:
                data, err = None, f"unreadable: {exc}"[:200]
            services.append({"dir": m.parent.relative_to(ws.src).as_posix(), "manifest": data, "error": err})
    return {"services": services, "candidate_dirs": _candidate_dirs(ws.src) if ws.src.exists() else [],
            "kinds": sorted(assumptions["effort_days_by_kind"]), "data_classes": sorted(assumptions["data_classes"]),
            "label": "Ownership facts the scanner cannot infer; kind and data class map to assumptions in config/assumptions.json."}


def save_manifest(ws: Workspace, rel_dir: str, manifest: dict, assumptions: dict) -> dict:
    rel = PurePosixPath(rel_dir or "")
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise WorkspaceError("bad_dir", "dir must be a relative directory inside the workspace source")
    target = (ws.src / rel).resolve()
    if not str(target).startswith(str(ws.src.resolve()) + os.sep) or not target.is_dir() or target.is_symlink():
        raise WorkspaceError("bad_dir", f"{rel_dir!r} is not a directory in the workspace source")
    errors = {}
    m = {k: manifest.get(k) for k in ("id", "name", "kind", "data_class", "depends_on")}
    if not isinstance(m["id"], str) or not SERVICE_ID_RE.match(m["id"]):
        errors["id"] = "1-64 characters a-z 0-9 -"
    if not isinstance(m["name"], str) or not m["name"].strip() or len(m["name"]) > 120:
        errors["name"] = "required, at most 120 characters"
    if m["kind"] not in assumptions["effort_days_by_kind"]:
        errors["kind"] = f"one of {', '.join(sorted(assumptions['effort_days_by_kind']))}"
    if m["data_class"] not in assumptions["data_classes"]:
        errors["data_class"] = f"one of {', '.join(sorted(assumptions['data_classes']))}"
    deps = m["depends_on"] if m["depends_on"] is not None else []
    others = {}
    for s in list_manifests(ws, assumptions)["services"]:
        if s["manifest"] and s["dir"] != rel.as_posix():
            others[s["manifest"].get("id")] = s["dir"]
    if m.get("id") in others:
        errors["id"] = f"already used by {others[m['id']]}"
    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
        errors["depends_on"] = "a list of service ids"
    else:
        unknown = [d for d in deps if d not in others]
        if unknown:
            errors["depends_on"] = f"unknown service ids: {', '.join(unknown)}"
        if m.get("id") in deps:
            errors["depends_on"] = "a service cannot depend on itself"
    if errors:
        raise WorkspaceError("invalid_manifest", "the manifest has invalid fields", 422, errors)
    m["name"], m["depends_on"] = m["name"].strip(), deps
    (target / MANIFEST).write_text(json.dumps(m, indent=1) + "\n")
    return m


# ---------------- suggested manifests (operator must confirm) ----------------

SUGGEST_BY = "atlas_web suggest-manifests"
KIND_RULES = [  # (kind, basis) checked in order; first match wins
    ("message_bus", lambda n, f, r: re.search(r"kafka|rabbit|nats|pulsar|queue|amqp", n), "service name suggests a message bus"),
    ("database_tls", lambda n, f, r: re.search(r"postgres|mysql|mariadb|mongo|redis|valkey|cassandra|opensearch|elastic|(^|-)db$", n)
     or any(re.search(r"postgres|mysql|mongo|redis", x) for x in r), "database service or database TLS finding"),
    ("tls_gateway", lambda n, f, r: any(re.match(r"(nginx|tls-(ciphers|groups)|envoy|haproxy)", x) for x in r)
     or any(x in f for x in ("nginx.conf", "envoy.yaml", "envoy.tmpl.yaml", "haproxy.cfg")) or re.search(r"proxy|gateway|ingress", n),
     "TLS termination config (nginx/envoy) or a proxy/gateway service"),
    ("service_mtls", lambda n, f, r: any(x.endswith(".proto") for x in f) or "go.mod" in f and "grpc" in " ".join(f), "gRPC service (.proto)"),
]


def _service_dirs(src: Path) -> list[Path]:
    """Directories that look like deployable services: they hold a Dockerfile (depth <= 3), not the repo root."""
    out = []
    for d in sorted({p.parent for p in src.rglob("Dockerfile*") if p.is_file() and not p.is_symlink()}):
        rel = d.relative_to(src)
        if 1 <= len(rel.parts) <= 3 and not any(part.startswith(".") or part in ("test", "tests", "docs") for part in rel.parts):
            out.append(d)
    return [d for d in out if not any(o != d and o in d.parents for o in out)]  # outermost service dir only


def _slug(name: str) -> str:
    s_ = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return s_[:64] or "service"


def _deploy_refs(src: Path, ids: set[str]) -> dict[str, dict]:
    """Dependencies from deployment files: compose `depends_on` and k8s env values of the form <service>:<port>."""
    deps: dict[str, dict] = {}
    for f in sorted(list(src.glob("*compose*.y*ml")) + list(src.glob("docker-compose*.y*ml"))):
        text = f.read_text(errors="replace")
        body = text.split("\nservices:", 1)[1] if "\nservices:" in text else ""
        for block in re.split(r"\n(?=  [A-Za-z0-9_.-]+:\s*\n)", body):
            m = re.match(r"\s*([A-Za-z0-9_.-]+):", block)
            if not m or _slug(m.group(1)) not in ids:
                continue
            sid = _slug(m.group(1))
            dep = re.search(r"\n\s{4}depends_on:\s*\n((?:\s{6,}.*\n?)+)", block)
            names = re.findall(r"^\s{6}-?\s*([A-Za-z0-9_.-]+):?", dep.group(1), re.M) if dep else []
            for n in names:
                if _slug(n) in ids and _slug(n) != sid:
                    deps.setdefault(sid, {}).setdefault(_slug(n), f"{f.name}: depends_on")
    for f in sorted(src.glob("kubernetes-manifests/*.y*ml")):
        for doc in f.read_text(errors="replace").split("\n---"):
            if not re.search(r"^kind:\s*Deployment", doc, re.M):
                continue
            m = re.search(r"^metadata:\s*\n\s+name:\s*([A-Za-z0-9_.-]+)", doc, re.M)
            if not m or _slug(m.group(1)) not in ids:
                continue
            sid = _slug(m.group(1))
            for target in re.findall(r"value:\s*\"?([a-z][a-z0-9-]+):\d{2,5}\"?", doc):
                if target in ids and target != sid:
                    deps.setdefault(sid, {}).setdefault(target, f"{f.relative_to(src).as_posix()}: env {target}:<port>")
    return deps


def suggest_manifests(ws: Workspace, assumptions: dict) -> dict:
    """Write atlas-service.json suggestions for service directories without one. Every field is a suggestion
    (marked `suggested`, with the basis) until an operator confirms it; existing manifests are never touched."""
    from detect.static_scan import scan

    findings = scan(ws.src)["findings"]
    dirs = _service_dirs(ws.src)
    existing = {m.parent for m in ws.src.rglob(MANIFEST)}
    ids, by_dir = set(), {}
    for d in dirs:
        sid = _slug(d.name)
        while sid in ids:
            sid = _slug(f"{d.parent.name}-{sid}")
        ids.add(sid)
        by_dir[d] = sid
    deps = _deploy_refs(ws.src, ids)
    written, skipped = [], []
    default_kind = "service_mtls" if "service_mtls" in assumptions["effort_days_by_kind"] else sorted(assumptions["effort_days_by_kind"])[0]
    default_class = "internal_ops" if "internal_ops" in assumptions["data_classes"] else sorted(assumptions["data_classes"])[0]
    for d, sid in by_dir.items():
        rel = d.relative_to(ws.src).as_posix()
        if d in existing:
            skipped.append(rel)
            continue
        files = [p.name for p in d.rglob("*") if p.is_file()][:5000]
        rules = [f["rule"] for f in findings if f["file"].startswith(rel + "/")]
        kind, kbasis = default_kind, "no specific evidence: default service_mtls"
        for k, test, basis in KIND_RULES:
            if k in assumptions["effort_days_by_kind"] and test(sid, files, rules):
                kind, kbasis = k, basis
                break
        dmap = deps.get(sid, {})
        manifest = {"id": sid, "name": d.name, "kind": kind, "data_class": default_class, "depends_on": sorted(dmap),
                    "suggested": {"by": SUGGEST_BY, "status": "suggested — review", "fields": ["id", "name", "kind", "data_class", "depends_on"],
                                  "basis": {"kind": kbasis, "data_class": f"default {default_class} (no data classification in the code)",
                                            "depends_on": [f"{t} ({why})" for t, why in sorted(dmap.items())] or ["no references found in compose/k8s files"],
                                            "findings_in_dir": len(rules)}}}
        (d / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n")
        written.append(rel)
    return {"written": written, "skipped_existing": skipped, "service_dirs": len(dirs)}


def confirm_manifests(ws: Workspace, dirs: list[str] | None, assumptions: dict) -> dict:
    """Operator confirmation: re-save each suggested manifest through the validating editor path, which drops
    the `suggested` marker. `dirs` None = every suggested manifest."""
    pending = [s_ for s_ in list_manifests(ws, assumptions)["services"] if s_["manifest"] and s_["manifest"].get("suggested")]
    chosen = [s_ for s_ in pending if dirs is None or s_["dir"] in dirs]
    done = []
    for s_ in chosen:
        save_manifest(ws, s_["dir"], s_["manifest"], assumptions)
        done.append(s_["dir"])
    return {"confirmed": done, "still_suggested": len(pending) - len(done)}
