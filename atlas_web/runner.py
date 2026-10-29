"""Pipeline runner: the run_demo.sh steps as subprocesses (sys.executable -m MODULE) with workspace path
flags. One run at a time (lab services share the machine); every step runs in its own process group,
which is killed when the step ends, so no lab `openssl s_server` survives. Output lines are streamed
as events (secrets redacted); a failure stops the run and keeps the last 40 lines."""

import importlib.metadata as md
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from contracts.stages import STEPS as STAGE_STEPS

from .auth import Store
from .config import PLATFORM_LOG, REPO, data_dir, limits, settings
from .workspaces import Workspace, WorkspaceError

STEPS = STAGE_STEPS  # contracts/stages.json: one stage list for runner, API and UI
SECRET_ENV = ("QPIAI_OPT_API_KEY", "QCLOUD_API_KEY")
SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
HOST_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,62})(\.[A-Za-z0-9]([A-Za-z0-9-]{0,62}))*$")
TAIL = 40


def env_file_values() -> dict:
    """`export NAME=value` lines from .env.sh (git-ignored), never echoed."""
    f = REPO / ".env.sh"
    out = {}
    if f.exists():
        for line in f.read_text().splitlines():
            m = re.match(r'\s*export\s+(\w+)=["\']?([^"\']*)["\']?\s*$', line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def step_env(platform: bool) -> dict:
    env = {**env_file_values(), **os.environ, "PYTHONUNBUFFERED": "1"}
    env.pop("SSLKEYLOGFILE", None)
    if platform:
        env.pop("QSHIELD_FORBID_PLATFORM", None)
    else:
        env["QSHIELD_FORBID_PLATFORM"] = "1"  # the guard refuses every paid submission
    return env


def redactor(env: dict):
    secrets_ = [env[k] for k in SECRET_ENV if len(env.get(k) or "") >= 8]
    def redact(line: str) -> str:
        for s in secrets_:
            line = line.replace(s, "[redacted]")
        return line
    return redact


# ---------------- preflight (ported from run_demo.sh) ----------------

def preflight(ws: Workspace | None = None) -> dict:
    checks = []
    def add(cid, ok, detail, fix):
        checks.append({"id": cid, "ok": bool(ok), "detail": detail, "fix": None if ok else fix})

    ver = "%d.%d" % sys.version_info[:2]
    add("python", ver == "3.12", f"Python {ver} ({sys.executable})",
        "conda activate pqc, or create a 3.12 venv and pip install -r requirements.txt")
    bad = []
    for line in (REPO / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        name, want = line.split("==")
        try:
            have = md.version(name)
            if have != want:
                bad.append(f"{name} {have} != pinned {want}")
        except md.PackageNotFoundError:
            bad.append(f"{name} (missing)")
    add("packages", not bad, "pinned packages present" if not bad else "; ".join(bad), "pip install -r requirements.txt")
    try:
        from detect.live_probe import openssl_binary, openssl_info

        b = openssl_binary()
        add("openssl", True, f"{b} | {openssl_info(b)['version']}", "")
    except Exception as exc:  # noqa: BLE001
        add("openssl", False, f"no OpenSSL >= 3.5 with X25519MLKEM768 and ML-DSA-65 ({str(exc)[:160]})",
            "conda install -n pqc -c conda-forge openssl=3.6.5, or export QSHIELD_OPENSSL=/path/to/openssl")
    try:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.close()
        add("port", True, "a free port on 127.0.0.1 can be bound", "")
    except OSError as exc:
        add("port", False, f"cannot bind a free port on 127.0.0.1 ({exc})", "check local firewall / sandbox settings")
    env = step_env(False)
    add("opt_key", bool(env.get("QPIAI_OPT_API_KEY")),
        "QPIAI_OPT_API_KEY is set (value never shown)" if env.get("QPIAI_OPT_API_KEY") else "QPIAI_OPT_API_KEY not set (local QpiAI Opt solves verify the key online)",
        "export QPIAI_OPT_API_KEY=... (free key at https://opt.qpiai.tech/) or put it in .env.sh (git-ignored)")
    if ws is not None:
        mfs = list(ws.src.rglob("atlas-service.json")) if ws.src.exists() else []
        n = len(mfs)
        add("manifests", n > 0, f"{n} service manifests (atlas-service.json) in the workspace source",
            "upload a .zip or clone a repository, then add atlas-service.json manifests in Detect")
        pending = [m for m in mfs if '"suggested"' in m.read_text(errors="replace")]
        add("manifests_confirmed", not pending, "every manifest confirmed by an operator" if not pending else
            f"{len(pending)} manifests are suggestions, not facts", "review the suggested manifests in Detect and confirm them")
        try:
            json.loads(ws.assumptions.read_text())
            add("assumptions", True, "workspace assumptions.json readable", "")
        except (OSError, ValueError) as exc:
            add("assumptions", False, f"workspace assumptions.json unreadable ({exc})", "restore it in Schedule → Assumptions")
        key = ws.keys / "ledger_mldsa65.key"
        add("signing_key", True, "ledger signing key present" if key.exists() else
            "no ledger signing key yet: one is generated before the run (python -m ledger keygen, never overwrites)", "")
    s = settings()["platform"]
    platform = {"opt": {"enabled": s["opt_enabled"], "status_text": None if s["opt_enabled"] else s["opt_blocked_reason"]},
                "qcloud": {"enabled": s["qcloud_enabled"], "status_text": None if s["qcloud_enabled"] else s["qcloud_blocked_reason"]}}
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "platform": platform}


# ---------------- steps ----------------

def parse_probes(items: list, authorised: bool) -> list[str]:
    out = []
    for item in items or []:
        text = str(item).strip()
        sid, _, endpoint = text.partition("=")
        host, _, port = endpoint.rpartition(":")
        host = host.strip("[]")
        if not SERVICE_RE.match(sid) or not (HOST_RE.match(host) or _is_ip(host)) or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise WorkspaceError("bad_probe", f"probe {text!r}: use SERVICE=HOST:PORT, e.g. web-gw=example.com:443")
        out.append(f"{sid}={host}:{int(port)}")
    if out and not authorised:
        raise WorkspaceError("not_authorised", "confirm that you own or are authorised to test these endpoints", 422)
    return out


def reference_presets(ids: list) -> list[dict]:
    """Public reference endpoints from config/atlas_web.json (one standard TLS handshake each, no scanning).
    Only ids listed there are accepted, so a preset can never carry a user-chosen host."""
    known = {e["id"]: e for e in settings()["reference_endpoints"]["endpoints"]}
    bad = [str(i) for i in ids if i not in known]
    if bad:
        raise WorkspaceError("bad_preset", f"unknown reference endpoint preset: {', '.join(bad)}")
    return [known[i] for i in dict.fromkeys(ids)]


def _is_ip(host: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def pipeline_steps(ws: Workspace, probes: list[str], platform: bool = False, qcloud: bool = False,
                   calibration_payload: Path | None = None) -> list[tuple[str, list[str]]]:
    py = [sys.executable, "-m"]
    out, runs = str(ws.out), str(ws.runs)
    led = ["--ledger", str(ws.out / "ledger.jsonl"), "--out-dir", out, "--runs", runs, "--root", str(ws.root), "--keys-dir", str(ws.keys)]
    detect = [*py, "detect", "--root", str(ws.src), "--out-dir", out, "--runs", runs, "--probe-timeout", str(limits()["probe_timeout_s"])]
    for lp in ws.settings.get("lab_probes", []):
        detect += ["--lab-probe", lp]
    for p in probes:
        detect += ["--probe", p]
    steps = [
        ("detect", detect),
        ("ledger_open", [*py, "ledger", "ingest", "--only", "detect.run", *led]),  # Proof Chain: sign the Detect evidence first
        ("schedule", [*py, "schedule", "--inventory", str(ws.out / "inventory.json"), "--assumptions", str(ws.assumptions),
                      "--out", str(ws.out / "schedule.json"), "--runs", runs, "--platform-log", str(PLATFORM_LOG),
                      *(["--platform"] if platform else [])]),
        ("capture", [*py, "capture", "--out-dir", out, "--runs", runs]),
        ("gates", [*py, "gates", "--schedule", str(ws.out / "schedule.json"), "--out-dir", out, "--runs", runs]),
        ("qaoa", [*py, "qaoa", "--qpiai-local", "--schedule", str(ws.out / "schedule.json"), "--out-dir", out, "--runs", runs,
                  "--platform-log", str(PLATFORM_LOG), *(["--qcloud"] if qcloud else [])]),
        ("ledger_ingest", [*py, "ledger", "ingest", *led]),
        ("ledger_verify", [*py, "ledger", "verify", *led]),
        ("assemble", [*py, "contracts.assemble", "--out-dir", out]),
        ("validate", [*py, "contracts", "validate", "results", str(ws.results)]),
        ("report", [*py, "atlas", "report", "--out-dir", out, "--runs", runs, "--root", str(ws.root), "--keys-dir", str(ws.keys)]),
        ("validate_final", [*py, "contracts", "validate", "results", str(ws.results)]),
    ]
    if calibration_payload is not None:  # signed right after the runs it caused, before verification
        i = [n for n, _ in steps].index("ledger_ingest") + 1
        steps.insert(i, ("calibration_sign", [*py, "ledger", "append", str(calibration_payload), "--type", "calibration.apply", *led]))
    assert [n for n, _ in steps if n != "calibration_sign"] == list(STEPS), "pipeline_steps out of order with contracts/stages.json"
    return steps


def bench_steps(ws: Workspace) -> list[tuple[str, list[str]]]:
    """python -m bench on this workspace's schedule, then sign it (bench.run) and verify the whole chain."""
    py = [sys.executable, "-m"]
    out, runs = str(ws.out), str(ws.runs)
    led = ["--ledger", str(ws.out / "ledger.jsonl"), "--out-dir", out, "--runs", runs, "--root", str(ws.root), "--keys-dir", str(ws.keys)]
    return [("bench", [*py, "bench", "--schedule", str(ws.out / "schedule.json"), "--out-dir", out, "--runs", runs]),
            ("bench_crypto", [*py, "bench.crypto", "--out-dir", out, "--runs", runs]),
            ("ledger_ingest", [*py, "ledger", "ingest", *led]), ("ledger_verify", [*py, "ledger", "verify", *led])]


# ---------------- runs ----------------

class Run:
    def __init__(self, run_id: str, ws_id: str, user: str, kind: str, detail: dict):
        self.id, self.ws_id, self.user, self.kind, self.detail = run_id, ws_id, user, kind, detail
        self.events: list[dict] = []
        self.cond = threading.Condition()
        self.status = "running"
        self.started = time.time()
        self.log_path = data_dir() / "runlogs" / f"{run_id}.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, type_: str, **fields) -> None:
        with self.cond:
            ev = {"seq": len(self.events), "type": type_, "ts": time.time(), **fields}
            self.events.append(ev)
            with self.log_path.open("a") as fh:
                fh.write(json.dumps(ev) + "\n")
            self.cond.notify_all()

    def wait(self, after: int, timeout: float) -> list[dict]:
        with self.cond:
            if len(self.events) <= after and self.status == "running":
                self.cond.wait(timeout)
            return self.events[after:]


def capacity_hint(tail: list[str]) -> dict | None:
    """Designed explanations for known failures: an asset that exceeds one week of capacity (which and how to fix
    it via assumptions), or the QpiAI Opt key check being rate-limited (retry later; nothing is wrong with the data)."""
    for line in tail:
        if "rate-limited this solve" in line:
            return {"code": "opt_rate_limited", "title": "QpiAI Opt rate-limited the solve",
                    "message": "Local QpiAI Opt solves verify the API key online, and the authentication service rate-limited this one "
                               "(\"The authentication service rate-limited this solve; retry later\"). The data and the plan are not at fault.",
                    "fix": "Wait a few minutes and run again. No platform job or credit was involved."}
        m = re.search(r"(\S+) effort ([\d.]+) d exceeds weekly capacity ([\d.]+) d", line)
        if m:
            return {"code": "capacity_infeasible", "title": "Schedule cannot fit an asset into one week", "asset": m.group(1), "effort_days": float(m.group(2)), "capacity_days": float(m.group(3)),
                    "message": f"Asset {m.group(1)} needs {m.group(2)} engineer-days but one week has capacity for {m.group(3)}; "
                               "each asset must fit in one week.",
                    "fix": "In Schedule → Assumptions, raise capacity_days_per_week or lower effort_days_by_kind for this asset's kind "
                           "(both are assumptions), or split the service into smaller manifests in Detect."}
    return None


def kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(0.2)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def kill_orphaned_lab_servers(since: float) -> int:
    """Lab services run from temp dirs named qshield-*; kill any started during this run that survived."""
    import psutil

    n = 0
    for p in psutil.process_iter(["pid", "cmdline", "create_time"]):
        cmd = p.info["cmdline"] or []
        if cmd and cmd[0].endswith("openssl") and "s_server" in cmd and any("qshield-" in c for c in cmd) \
                and (p.info["create_time"] or 0) >= since - 1:
            try:
                p.kill()
                n += 1
            except psutil.Error:
                pass
    return n


def _active_file() -> Path:
    return data_dir() / "active_step.json"


class RunManager:
    def __init__(self, store: Store):
        self.store = store
        self.lock = threading.Lock()
        self.active: Run | None = None
        self.runs: dict[str, Run] = {}
        self.recover()

    def recover(self) -> list[str]:
        """After a crash or kill: stop the step that was running (its process group), kill orphaned lab
        services, and close every run still marked running as INTERRUPTED with a final run_end event."""
        f = _active_file()
        if f.exists():
            try:
                kill_group(int(json.loads(f.read_text())["pgid"]))
            except (ValueError, KeyError, OSError):
                pass
            f.unlink(missing_ok=True)
        with self.store.db() as c:
            stale = c.execute("SELECT id, started, detail FROM runs WHERE status='running'").fetchall()
        if stale:
            kill_orphaned_lab_servers(min(r["started"] for r in stale))
        for r in stale:
            tail = ["interrupted: the atlas_web server stopped during this run; nothing after the last completed step was recorded"]
            log = data_dir() / "runlogs" / f"{r['id']}.jsonl"
            seq = sum(1 for _ in log.open()) if log.exists() else 0
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a") as fh:
                fh.write(json.dumps({"seq": seq, "type": "run_end", "ts": time.time(), "status": "INTERRUPTED", "summary": [], "tail": tail,
                                     "orphans_killed": 0, "duration_s": None}) + "\n")
            with self.store.db() as c:
                c.execute("UPDATE runs SET finished=?, status='INTERRUPTED', detail=? WHERE id=?",
                          (time.time(), json.dumps({**json.loads(r["detail"]), "tail": tail}), r["id"]))
        return [r["id"] for r in stale]

    def shutdown(self) -> None:
        """Graceful stop (Ctrl+C): kill the running step's process group; recover() closes the run on next start."""
        f = _active_file()
        if f.exists():
            try:
                kill_group(int(json.loads(f.read_text())["pgid"]))
            except (ValueError, KeyError, OSError):
                pass

    def start(self, ws: Workspace, user: str, steps: list, kind: str, detail: dict, platform: bool,
              needs_keygen: bool) -> Run:
        with self.lock:
            if self.active is not None and self.active.status == "running":
                same = self.active.ws_id == ws.id
                raise WorkspaceError("run_in_progress", "a run is already in progress in this workspace" if same else
                                     f"a run is in progress in workspace {self.active.ws_id}; lab services are shared, one run at a time", 409)
            run = Run(secrets.token_hex(8), ws.id, user, kind, detail)
            self.active = run
            self.runs[run.id] = run
        with self.store.db() as c:
            c.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                      (run.id, ws.id, user, kind, run.started, None, "running", json.dumps(detail)))
        threading.Thread(target=self._execute, args=(run, ws, steps, platform, needs_keygen), daemon=True).start()
        return run

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def _execute(self, run: Run, ws: Workspace, steps: list, platform: bool, needs_keygen: bool) -> None:
        env = step_env(platform)
        redact = redactor(env)
        timeout = limits()["step_timeout_s"]
        summary, status, tail = [], "PASS", []
        run.emit("run_start", steps=[n for n, _ in steps], workspace=ws.id, kind=run.kind)
        try:
            if needs_keygen:
                code, _, lines = self._step(run, "keygen", [sys.executable, "-m", "ledger", "keygen", "--keys-dir", str(ws.keys)],
                                            env, redact, timeout, station=False)
                if code != 0:
                    status, tail = "FAIL", lines[-TAIL:]
            if status == "PASS":
                for name, argv in steps:
                    code, dur, lines = self._step(run, name, argv, env, redact, timeout)
                    summary.append({"step": name, "exit_code": code, "duration_s": round(dur, 2)})
                    if code != 0:
                        status, tail = "FAIL", lines[-TAIL:]
                        break
        except Exception as exc:  # noqa: BLE001 - reported as a run failure, never a traceback to the client
            status, tail = "FAIL", [f"runner error: {type(exc).__name__}: {exc}"[:300]]
        finally:
            killed = kill_orphaned_lab_servers(run.started)
            run.status = status
            hint = capacity_hint(tail) if status != "PASS" else None
            run.emit("run_end", status=status, summary=summary, tail=tail, orphans_killed=killed, hint=hint,
                     duration_s=round(time.time() - run.started, 2))
            with self.store.db() as c:
                c.execute("UPDATE runs SET finished=?, status=?, detail=? WHERE id=?",
                          (time.time(), status, json.dumps({**run.detail, "summary": summary, "tail": tail, "hint": hint}), run.id))
            with run.cond:
                run.cond.notify_all()
            with self.lock:
                if self.active is run:
                    self.active = None

    def _step(self, run, name, argv, env, redact, timeout, station=True):
        run.emit("step_start", step=name, station=station, argv=[a if not a.startswith(str(REPO)) else a.replace(str(REPO), ".") for a in argv[1:]])
        t0 = time.monotonic()
        lines: list[str] = []
        proc = subprocess.Popen(argv, cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
        _active_file().write_text(json.dumps({"run_id": run.id, "pgid": proc.pid, "step": name}))
        timer = threading.Timer(timeout, kill_group, args=(proc.pid,))
        timer.start()
        try:
            for raw in proc.stdout:
                line = redact(raw.rstrip("\n"))[:2000]
                lines.append(line)
                run.emit("line", step=name, text=line)
            code = proc.wait()
        finally:
            timer.cancel()
            kill_group(proc.pid)  # anything the step left behind in its process group (e.g. s_server)
            _active_file().unlink(missing_ok=True)
        if code < 0 or (time.monotonic() - t0) >= timeout:
            lines.append(f"step {name} stopped (timeout {timeout} s or signal {-code if code < 0 else ''})")
            code = code or 124
        dur = time.monotonic() - t0
        run.emit("step_end", step=name, station=station, exit_code=code, duration_s=round(dur, 2))
        return code, dur, lines
