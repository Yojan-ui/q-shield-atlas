"""ML-DSA-65 signing backend: OpenSSL >= 3.5 CLI (`genpkey`, `pkeyutl -sign/-verify -rawin`).

Detection order chosen by the user: (a) OpenSSL CLI, (b) `cryptography`, (c) liboqs-python. All
three passed a sign/verify/tamper round trip on 2026-10-28; (a) is used. There is deliberately no
fallback to RSA, ECDSA or Ed25519: if the ML-DSA-65 self-test fails, `detect()` raises.
Private keys are only ever written to files with mode 0600 and are never printed or logged.
"""

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from detect.live_probe import openssl_binary

ALG = "ML-DSA-65"


class BackendUnavailable(RuntimeError):
    pass


class OpenSSLMLDSA:
    name = "openssl-cli"

    def __init__(self, binary: str | None = None):
        self.binary = binary or openssl_binary()
        self.version = subprocess.run([self.binary, "version"], capture_output=True, text=True, timeout=10).stdout.strip()

    @property
    def label(self) -> str:
        return f"{self.name} ({self.version})"

    def _run(self, *args, check=True, timeout=30) -> subprocess.CompletedProcess:
        return subprocess.run([self.binary, *map(str, args)], capture_output=True, timeout=timeout, check=check)

    def generate(self, private_path: Path, public_path: Path) -> None:
        private_path, public_path = Path(private_path), Path(public_path)
        private_path.parent.mkdir(parents=True, exist_ok=True)
        public_path.parent.mkdir(parents=True, exist_ok=True)
        old = os.umask(0o077)
        try:
            self._run("genpkey", "-algorithm", ALG, "-out", private_path)
        finally:
            os.umask(old)
        os.chmod(private_path, 0o600)
        self._run("pkey", "-in", private_path, "-pubout", "-out", public_path)

    def sign(self, private_path: Path, data: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as d:
            msg, sig = Path(d) / "msg", Path(d) / "sig"
            msg.write_bytes(data)
            self._run("pkeyutl", "-sign", "-rawin", "-inkey", private_path, "-in", msg, "-out", sig)
            return sig.read_bytes()

    def verify(self, public_path: Path, data: bytes, signature: bytes) -> bool:
        with tempfile.TemporaryDirectory() as d:
            msg, sig = Path(d) / "msg", Path(d) / "sig"
            msg.write_bytes(data)
            sig.write_bytes(signature)
            return self._run("pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", public_path,
                             "-in", msg, "-sigfile", sig, check=False).returncode == 0

    def public_key_der(self, public_path: Path) -> bytes:
        return self._run("pkey", "-pubin", "-in", public_path, "-outform", "DER").stdout

    def key_alg(self, public_path: Path) -> str:
        text = self._run("pkey", "-pubin", "-in", public_path, "-noout", "-text").stdout.decode()
        return text.splitlines()[0].replace(" Public-Key:", "").strip()

    def fingerprint(self, public_path: Path) -> str:
        """SHA-256 of the DER SubjectPublicKeyInfo."""
        return hashlib.sha256(self.public_key_der(public_path)).hexdigest()

    def self_test(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sk, pk = Path(d) / "sk.pem", Path(d) / "pk.pem"
            self.generate(sk, pk)
            if self.key_alg(pk) != ALG:
                raise BackendUnavailable(f"generated key is {self.key_alg(pk)!r}, not {ALG}")
            msg = b"q-shield ledger self-test"
            sig = self.sign(sk, msg)
            tampered = bytes([sig[0] ^ 1]) + sig[1:]
            if not self.verify(pk, msg, sig):
                raise BackendUnavailable("valid signature did not verify")
            if self.verify(pk, b"Q" + msg[1:], sig) or self.verify(pk, msg, tampered):
                raise BackendUnavailable("tampered message or signature verified")


def detect() -> OpenSSLMLDSA:
    try:
        backend = OpenSSLMLDSA()
        backend.self_test()
        return backend
    except (subprocess.SubprocessError, OSError, RuntimeError) as exc:
        raise BackendUnavailable(
            f"OpenSSL ML-DSA-65 backend failed its self-test ({exc}). No fallback to classical "
            "signatures is allowed; install OpenSSL >= 3.5 in the pqc env."
        ) from exc
