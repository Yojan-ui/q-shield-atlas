"""Record TLS handshake evidence with `openssl s_client -brief -msg`.

Only handshake metadata is kept (group, cipher, protocol, certificate key family) plus the raw
s_client transcript and its SHA-256. `-msg` adds the hex of each handshake message (including the
ClientHello/ServerHello randoms), so every session's transcript and hash are unique. Key material
is never logged or derived: no -keylogfile, and SSLKEYLOGFILE is removed from the environment.
No application data, no decryption.
"""

import os
import re
import subprocess
from pathlib import Path

from contracts.manifest import sha256_hex, utc_now
from detect.live_probe import openssl_binary

SIG_FAMILY = (
    ("rsa", "RSA"),
    ("ecdsa", "ECDSA"),
    ("ed25519", "Ed25519"),
    ("ed448", "Ed448"),
    ("mldsa", "ML-DSA"),
    ("slhdsa", "SLH-DSA"),
)


def cert_alg_from_signature(sig_type: str | None) -> str | None:
    if not sig_type:
        return None
    low = sig_type.lower().replace("-", "")
    return next((fam for prefix, fam in SIG_FAMILY if low.startswith(prefix)), sig_type)


def parse_brief(text: str) -> dict:
    def grab(pattern):
        m = re.search(pattern, text, re.M)
        return m.group(1).strip() if m else None

    sig = grab(r"^Signature type:\s*(\S+)")
    return {
        "established": "CONNECTION ESTABLISHED" in text,
        "negotiated_group": grab(r"^Negotiated TLS1\.3 group:\s*(\S+)") or grab(r"^Peer Temp Key:\s*([^,\s]+)"),
        "cipher": grab(r"^Ciphersuite:\s*(\S+)"),
        "protocol": grab(r"^Protocol version:\s*(\S+)"),
        "signature_type": sig,
        "cert_alg": cert_alg_from_signature(sig),
        "error": grab(r"(SSL alert number \d+|alert [a-z ]+)"),
    }


TLS_FLAGS = {None: [], "auto": [], "1.2": ["-tls1_2"], "1.3": ["-tls1_3"]}


def clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if k != "SSLKEYLOGFILE"}


def handshake(host: str, port: int, groups: str, timeout: float = 15.0, tls: str | None = None) -> tuple[dict, str]:
    """Return (parsed fields, raw transcript). Never raises on a refused handshake."""
    cmd = [openssl_binary(), "s_client", "-connect", f"{host}:{port}", "-groups", groups, *TLS_FLAGS[tls], "-brief", "-msg"]
    assert not any("keylog" in c.lower() for c in cmd)
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, env=clean_env())
        text = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        text = f"TIMEOUT after {timeout}s\n{exc.stdout or ''}{exc.stderr or ''}"
    return parse_brief(text), text


def record(service_id: str, host: str, port: int, groups: str, transcript_dir: Path | None, label: str,
           timeout: float = 15.0, tls: str | None = None) -> dict:
    fields, text = handshake(host, port, groups, timeout, tls)
    digest = sha256_hex(text.encode())
    if transcript_dir is not None:
        transcript_dir.mkdir(parents=True, exist_ok=True)
        (transcript_dir / f"transcript_{label}.txt").write_text(text)
    base = {
        "service_id": service_id,
        "endpoint": f"{host}:{port}",
        "client_groups_offered": groups,
        "transcript_sha256": digest,
        "timestamp": utc_now(),
    }
    if fields["established"]:
        return {"established": True, **base, **{k: fields[k] for k in ("negotiated_group", "cipher", "protocol", "cert_alg", "signature_type")}}
    # transcript files are keyed by label; callers pass unique labels
    return {"established": False, **base, "error": fields["error"]}
