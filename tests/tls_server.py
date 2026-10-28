"""Run a real local `openssl s_server` for probe tests (RSA cert, chosen groups)."""

import contextlib
import socket
import subprocess
import time

from detect.live_probe import openssl_binary


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def tls_server(tmp_path, groups: str, key: str = "rsa:2048"):
    binary = openssl_binary()
    cert, keyfile = tmp_path / "srv.crt", tmp_path / "srv.key"
    subprocess.run(
        [binary, "req", "-x509", "-newkey", key, "-nodes", "-keyout", keyfile, "-out", cert,
         "-days", "1", "-subj", "/CN=localhost"],
        check=True, capture_output=True,
    )
    port = free_port()
    proc = subprocess.Popen(
        [binary, "s_server", "-accept", str(port), "-cert", cert, "-key", keyfile, "-groups", groups, "-www", "-quiet"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
            time.sleep(0.05)
        yield "127.0.0.1", port
    finally:
        proc.terminate()
        proc.wait(timeout=5)
