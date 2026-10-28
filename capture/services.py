"""Local lab TLS services run with `openssl s_server` (OpenSSL >= 3.5 for ML-KEM groups).

A service's deployment mode (config/lab.json "modes": legacy | transition | strict) sets its
key-exchange groups and TLS versions. Each `ManagedService` keeps its settings in a JSON config
file on disk and is (re)started from that file, so a rollback can snapshot, restore and verify it.
Services bind 127.0.0.1 only, on a free port that is kept across restarts, and are always
terminated (then killed if needed) when closed.
"""

import contextlib
import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from contracts.manifest import sha256_hex
from detect.live_probe import openssl_binary

REPO = Path(__file__).resolve().parent.parent
LAB_CONFIG = REPO / "config" / "lab.json"
HOST = "127.0.0.1"  # loopback only, never all interfaces
SERVER_TLS_FLAGS = {"1.3": ["-tls1_3"], "1.2+": ["-no_ssl3", "-no_tls1", "-no_tls1_1"]}


def load_lab(path=LAB_CONFIG) -> dict:
    return json.loads(Path(path).read_text())


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def stop(proc: subprocess.Popen, timeout: float) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)


class ManagedService:
    """One s_server process driven by `<workdir>/service.json`."""

    def __init__(self, service_id: str, mode: str, lab: dict, workdir: Path, cert_key: str = "rsa:2048"):
        self.service_id, self.lab, self.workdir = service_id, lab, Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.workdir / "service.json"
        self.process: subprocess.Popen | None = None
        self.host, self.port = HOST, free_port()
        cert, key = self.workdir / "cert.pem", self.workdir / "key.pem"
        subprocess.run(
            [openssl_binary(), "req", "-x509", "-newkey", cert_key, "-nodes", "-keyout", key, "-out", cert,
             "-days", "1", "-subj", f"/CN={service_id}.lab.test"],
            check=True, capture_output=True, timeout=lab["timeouts_s"]["keygen"],
        )
        self.write_config(mode)

    # ---- config file ----
    def write_config(self, mode: str) -> None:
        spec = self.lab["modes"][mode]
        cfg = {"service_id": self.service_id, "mode": mode, "groups": spec["groups"], "tls": spec["tls"],
               "host": self.host, "port": self.port, "cert": "cert.pem", "key": "key.pem"}
        self.config_path.write_text(json.dumps(cfg, indent=1, sort_keys=True) + "\n")

    def read_config(self) -> dict:
        return json.loads(self.config_path.read_text())

    def config_sha256(self) -> str:
        return sha256_hex(self.config_path.read_bytes())

    @property
    def mode(self) -> str:
        return self.read_config()["mode"]

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    # ---- process ----
    def start(self) -> None:
        cfg = self.read_config()
        if cfg["host"] != HOST:
            raise ValueError(f"refusing to bind {cfg['host']}; lab services are loopback only")
        self.process = subprocess.Popen(
            [openssl_binary(), "s_server", "-accept", f"{HOST}:{cfg['port']}", *SERVER_TLS_FLAGS[cfg["tls"]],
             "-groups", cfg["groups"], "-cert", self.workdir / cfg["cert"], "-key", self.workdir / cfg["key"],
             "-www", "-quiet"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._wait_ready(self.lab["timeouts_s"]["startup"])

    def _wait_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"{self.service_id}: s_server exited early with code {self.process.returncode}")
            with contextlib.suppress(OSError), socket.create_connection((HOST, self.port), timeout=0.2):
                return
            time.sleep(0.05)
        raise TimeoutError(f"{self.service_id}: s_server not ready on {self.endpoint} after {timeout}s")

    def stop(self) -> None:
        if self.process is not None:
            stop(self.process, self.lab["timeouts_s"]["shutdown"])

    def restart(self) -> None:
        self.stop()
        self.start()

    def close(self) -> None:
        self.stop()


@contextlib.contextmanager
def managed_service(service_id: str, mode: str, lab: dict | None = None, cert_key: str = "rsa:2048", workdir: Path | None = None):
    lab = lab or load_lab()
    with contextlib.ExitStack() as stack:
        if workdir is None:
            workdir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=f"qshield-{service_id}-")))
        svc = ManagedService(service_id, mode, lab, workdir, cert_key)
        try:
            svc.start()
            yield svc
        finally:
            svc.close()


@contextlib.contextmanager
def lab_service(service_id: str, groups: str, cert_key: str = "rsa:2048", lab: dict | None = None):
    """Start a service by explicit group list (the mode whose groups match)."""
    lab = lab or load_lab()
    mode = next(m for m, spec in lab["modes"].items() if spec["groups"] == groups)
    with managed_service(service_id, mode, lab, cert_key) as svc:
        yield svc


@contextlib.contextmanager
def lab_services(lab: dict | None = None):
    """Start every service in config/lab.json "services"; yields {service_id: ManagedService}."""
    lab = lab or load_lab()
    with contextlib.ExitStack() as stack:
        yield {
            sid: stack.enter_context(managed_service(sid, spec["mode"], lab, spec["cert_key"]))
            for sid, spec in lab["services"].items()
        }
