"""Live TLS handshake probe using the OpenSSL CLI (needs OpenSSL >= 3.5 for ML-KEM groups).

The probe offers a modern client's group list (hybrid X25519MLKEM768 first, then classical
X25519 / P-256) and records what the server actually negotiates plus its certificate key.
The raw s_client transcript is kept (hash + optional file) as evidence.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from cryptography import x509

from contracts.manifest import sha256_hex, utc_now

from .static_scan import describe_public_key

CLIENT_GROUPS = "X25519MLKEM768:X25519:prime256v1"
PQC_GROUPS = {"X25519MLKEM768", "SecP256r1MLKEM768", "SecP384r1MLKEM1024", "MLKEM512", "MLKEM768", "MLKEM1024"}
CERT = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)


def openssl_binary() -> str:
    """Prefer the OpenSSL next to this interpreter (conda env `pqc` ships 3.6.x)."""
    local = Path(sys.executable).parent / "openssl"
    found = str(local) if local.exists() else shutil.which("openssl")
    if not found:
        raise RuntimeError("openssl CLI not found")
    return found


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


def probe(host: str, port: int, groups: str = CLIENT_GROUPS, transcript_dir: Path | None = None, label: str = "") -> dict:
    binary = openssl_binary()
    info = openssl_info(binary)
    if not info["ml_kem"]:
        groups = ":".join(g for g in groups.split(":") if g not in PQC_GROUPS)
    cmd = [binary, "s_client", "-connect", f"{host}:{port}", "-groups", groups, "-showcerts"]
    proc = subprocess.run(cmd, input="", capture_output=True, text=True, timeout=20)
    text = proc.stdout + proc.stderr
    record = {
        "endpoint": f"{host}:{port}",
        "ts": utc_now(),
        "client_groups_offered": groups,
        "openssl": info["version"],
        "handshake_ok": proc.returncode == 0 and "Cipher is" in text and "(NONE)" not in text,
        "transcript_sha256": sha256_hex(text.encode()),
        **parse_transcript(text),
    }
    if transcript_dir is not None:
        transcript_dir.mkdir(parents=True, exist_ok=True)
        name = (label or f"{host}_{port}").replace("/", "_")
        (transcript_dir / f"probe_{name}.txt").write_text(text)
    return record
