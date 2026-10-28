"""Local lab TLS 1.3 services run with `openssl s_server` (OpenSSL >= 3.5 for ML-KEM groups).

legacy: offers only X25519 (classical key exchange)
hybrid: offers only X25519MLKEM768 (hybrid post-quantum key exchange)
Each gets a fresh self-signed certificate in a temp dir. Services bind 127.0.0.1 only, on a
free port, and are always terminated (then killed if needed) when the context exits.
"""

import contextlib
import json
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from detect.live_probe import openssl_binary

REPO = Path(__file__).resolve().parent.parent
LAB_CONFIG = REPO / "config" / "lab.json"
HOST = "127.0.0.1"  # loopback only, never all interfaces


def load_lab(path=LAB_CONFIG) -> dict:
    return json.loads(Path(path).read_text())


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


@dataclass
class LabService:
    service_id: str
    host: str
    port: int
    groups: str
    process: subprocess.Popen

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


def _wait_ready(port: int, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"s_server exited early with code {proc.returncode}")
        with contextlib.suppress(OSError), socket.create_connection((HOST, port), timeout=0.2):
            return
        time.sleep(0.05)
    raise TimeoutError(f"s_server not ready on {HOST}:{port} after {timeout}s")


def stop(proc: subprocess.Popen, timeout: float) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)


@contextlib.contextmanager
def lab_service(service_id: str, groups: str, cert_key: str = "rsa:2048", lab: dict | None = None):
    lab = lab or load_lab()
    t = lab["timeouts_s"]
    binary = openssl_binary()
    with tempfile.TemporaryDirectory(prefix=f"qshield-{service_id}-") as tmp:
        cert, key = Path(tmp) / "cert.pem", Path(tmp) / "key.pem"
        subprocess.run(
            [binary, "req", "-x509", "-newkey", cert_key, "-nodes", "-keyout", key, "-out", cert,
             "-days", "1", "-subj", f"/CN={service_id}.lab.test"],
            check=True, capture_output=True, timeout=t["keygen"],
        )
        port = free_port()
        proc = subprocess.Popen(
            [binary, "s_server", "-accept", f"{HOST}:{port}", "-tls1_3", "-groups", groups,
             "-cert", cert, "-key", key, "-www", "-quiet"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            _wait_ready(port, proc, t["startup"])
            yield LabService(service_id, HOST, port, groups, proc)
        finally:
            stop(proc, t["shutdown"])


@contextlib.contextmanager
def lab_services(lab: dict | None = None):
    """Start every service in config/lab.json; yields {service_id: LabService}."""
    lab = lab or load_lab()
    with contextlib.ExitStack() as stack:
        yield {
            sid: stack.enter_context(lab_service(sid, spec["groups"], spec["cert_key"], lab))
            for sid, spec in lab["services"].items()
        }
