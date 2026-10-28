"""Live TLS handshake probe using the OpenSSL CLI (needs OpenSSL >= 3.5 for ML-KEM groups).

The probe offers a modern client's group list (hybrid X25519MLKEM768 first, then classical
X25519 / P-256) and records what the server actually negotiates plus its certificate key.
The raw s_client transcript is kept (hash + optional file) as evidence.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from cryptography import x509

from contracts.manifest import sha256_hex, utc_now

from .static_scan import describe_public_key

CLIENT_GROUPS = "X25519MLKEM768:X25519:prime256v1"
PQC_GROUPS = {"X25519MLKEM768", "SecP256r1MLKEM768", "SecP384r1MLKEM1024", "MLKEM512", "MLKEM768", "MLKEM1024"}
CERT = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)


LAB_CONFIG = Path(__file__).resolve().parent.parent / "config" / "lab.json"


def _supports_pqc(binary: str) -> bool:
    try:
        groups = subprocess.run([binary, "list", "-tls-groups"], capture_output=True, text=True, timeout=10).stdout
        sigs = subprocess.run([binary, "list", "-signature-algorithms"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "X25519MLKEM768" in groups and "ML-DSA-65" in sigs


def openssl_candidates() -> list[str]:
    """Lookup order: $QSHIELD_OPENSSL, config/lab.json openssl.path, next to this interpreter, PATH."""
    out = [os.environ.get("QSHIELD_OPENSSL")]
    try:
        out.append(json.loads(LAB_CONFIG.read_text()).get("openssl", {}).get("path"))
    except (OSError, ValueError):
        pass
    out += [str(Path(sys.executable).parent / "openssl"), shutil.which("openssl")]
    seen = []
    for c in out:
        if c and Path(c).exists() and c not in seen:
            seen.append(c)
    return seen


@lru_cache(maxsize=1)
def openssl_binary() -> str:
    """First candidate that lists X25519MLKEM768 and ML-DSA-65 (OpenSSL >= 3.5)."""
    candidates = openssl_candidates()
    for c in candidates:
        if _supports_pqc(c):
            return c
    raise RuntimeError(
        f"no OpenSSL with X25519MLKEM768 and ML-DSA-65 found (checked {candidates or 'nothing'}). "
        "Install OpenSSL >= 3.5 (e.g. `conda install -c conda-forge openssl=3.6.5`) and set QSHIELD_OPENSSL=/path/to/openssl."
    )


def openssl_info(binary: str) -> dict:
    version = subprocess.run([binary, "version"], capture_output=True, text=True, timeout=10).stdout.strip()
    kems = subprocess.run([binary, "list", "-kem-algorithms"], capture_output=True, text=True, timeout=10).stdout
    return {"binary": binary, "version": version, "ml_kem": "MLKEM768" in kems or "ML-KEM-768" in kems}


def parse_transcript(text: str) -> dict:
    def grab(pattern):
        m = re.search(pattern, text, re.M)
        return m.group(1).strip() if m else None

    group = grab(r"^Negotiated TLS1\.3 group:\s*(\S+)") or grab(r"^(?:Peer|Server) Temp Key:\s*([^,\s]+)")
    protocol = grab(r"^\s*Protocol\s*:\s*(\S+)") or grab(r"^New, (TLSv[\d.]+)")
    cipher = grab(r"Cipher is (\S+)")
    cert_algo = cert_family = None
    if m := CERT.search(text):
        cert_family, cert_algo = describe_public_key(x509.load_pem_x509_certificate(m.group(0).encode()).public_key())
    if group is None:
        kex_family = "RSA" if cipher and not cipher.startswith(("TLS_", "ECDHE", "DHE")) else None
    elif group in PQC_GROUPS:
        kex_family = "PQC"
    elif group.startswith("ffdhe") or group == "DH":
        kex_family = "DH"
    else:
        kex_family = "ECC"
    return {
        "protocol": protocol,
        "cipher": cipher,
        "group": group,
        "kex_family": kex_family,
        "cert_algorithm": cert_algo,
        "cert_family": cert_family,
        "peer_signature_type": grab(r"^Peer signature type:\s*(\S+)"),
        "kex_quantum_vulnerable": kex_family in {"RSA", "ECC", "DH"},
        "auth_quantum_vulnerable": cert_family in {"RSA", "ECC", "DSA"},
    }


def probe(host: str, port: int, groups: str = CLIENT_GROUPS, transcript_dir: Path | None = None, label: str = "",
          timeout: float = 20) -> dict:
    binary = openssl_binary()
    info = openssl_info(binary)
    if not info["ml_kem"]:
        groups = ":".join(g for g in groups.split(":") if g not in PQC_GROUPS)
    cmd = [binary, "s_client", "-connect", f"{host}:{port}", "-groups", groups, "-showcerts"]
    try:
        proc = subprocess.run(cmd, input="", capture_output=True, text=True, timeout=timeout)
        text, ok = proc.stdout + proc.stderr, proc.returncode == 0
    except subprocess.TimeoutExpired:  # recorded as a failed probe (drift: probe_failed), never as a result
        text, ok = f"probe timed out after {timeout:g} s\n", False
    record = {
        "endpoint": f"{host}:{port}",
        "ts": utc_now(),
        "client_groups_offered": groups,
        "openssl": info["version"],
        "handshake_ok": ok and "Cipher is" in text and "(NONE)" not in text,
        "transcript_sha256": sha256_hex(text.encode()),
        **parse_transcript(text),
    }
    if transcript_dir is not None:
        transcript_dir.mkdir(parents=True, exist_ok=True)
        name = (label or f"{host}_{port}").replace("/", "_")
        (transcript_dir / f"probe_{name}.txt").write_text(text)
    return record
