"""Static scan of a source tree for quantum-vulnerable public-key crypto, with file:line evidence.

Text files are matched line by line against detect.rules. Certificates (*.pem, *.crt, *.cer,
*.der) are parsed with `cryptography` to report the public-key algorithm and size. Private-key
bodies are never parsed or copied: only their PEM header line is reported.
The scanner only reads files; it never executes anything from the scanned tree.
"""

import fnmatch
import hashlib
import os
import re
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, rsa

from contracts.manifest import sha256_json

from .rules import RULES

SKIP_DIRS = {".git", "node_modules", "vendor", "__pycache__", ".venv", "venv", "dist", "build", ".tox", ".idea", "target"}
CERT_GLOBS = ("*.pem", "*.crt", "*.cer", "*.der")
MAX_BYTES = 1_000_000
PEM_CERT = re.compile(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)


def _matches(name: str, globs) -> bool:
    return any(fnmatch.fnmatch(name, g) for g in globs)


def _snippet(line: str) -> str:
    line = line.strip()
    return line if len(line) <= 160 else line[:157] + "..."


def describe_public_key(key) -> tuple[str, str]:
    """Return (family, human-readable algorithm) for a certificate public key."""
    if isinstance(key, rsa.RSAPublicKey):
        return "RSA", f"RSA-{key.key_size}"
    if isinstance(key, ec.EllipticCurvePublicKey):
        return "ECC", f"ECDSA-{key.curve.name}"
    if isinstance(key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
        return "ECC", type(key).__name__.replace("PublicKey", "")
    if isinstance(key, dsa.DSAPublicKey):
        return "DSA", f"DSA-{key.key_size}"
    name = type(key).__name__
    return ("PQC" if "MLDSA" in name.upper() or "SLH" in name.upper() else "UNKNOWN"), name


def scan_certificates(path: Path, rel: str) -> list[dict]:
    data = path.read_bytes()
    blocks = [(m.group(0), data[: m.start()].count(b"\n") + 1) for m in PEM_CERT.finditer(data)]
    if not blocks and path.suffix.lower() in (".der", ".cer"):
        blocks = [(data, 1)]
    findings = []
    for blob, line in blocks:
        try:
            cert = x509.load_pem_x509_certificate(blob) if blob.startswith(b"-----") else x509.load_der_x509_certificate(blob)
        except ValueError:
            continue
        family, algo = describe_public_key(cert.public_key())
        findings.append(
            {
                "file": rel,
                "line": line,
                "rule": "cert-public-key",
                "rules": ["cert-public-key"],
                "family": family,
                "use": "sig",
                "confidence": "high",
                "snippet": f"certificate subject={cert.subject.rfc4514_string()}",
                "detail": {
                    "algorithm": algo,
                    "signature_algorithm": cert.signature_algorithm_oid._name,
                    "not_after": cert.not_valid_after_utc.isoformat(),
                },
            }
        )
    return findings


def scan_text(path: Path, rel: str) -> list[dict]:
    rules = [r for r in RULES if _matches(path.name, r.globs)]
    if not rules:
        return []
    raw = path.read_bytes()
    if b"\0" in raw[:4096]:
        return []
    findings: dict[tuple, dict] = {}  # one finding per (line, family, use); extra rules are merged
    lines = raw.decode("utf-8", errors="replace").splitlines()
    for n, line in enumerate(lines, start=1):
        for r in rules:
            if not r.pattern.search(line):
                continue
            if r.unless_next and r.unless_next.search(next((x for x in lines[n:] if x.strip()), "")):
                continue
            key = (n, r.family, r.use)
            if key in findings:
                findings[key]["rules"].append(r.id)
                continue
            findings[key] = {
                "file": rel,
                "line": n,
                "rule": r.id,
                "rules": [r.id],
                "family": r.family,
                "use": r.use,
                "confidence": r.confidence,
                "snippet": "[private key header]" if "PRIVATE KEY" in line else _snippet(line),
                "detail": {"description": r.description},
            }
    return list(findings.values())


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            yield path


def scan(root) -> dict:
    root = Path(root).resolve()
    findings, files, tree = [], 0, []
    for path in iter_files(root):
        files += 1
        rel = path.relative_to(root).as_posix()
        tree.append([rel, hashlib.sha256(path.read_bytes()).hexdigest()])
        if _matches(path.name, CERT_GLOBS):
            findings += scan_certificates(path, rel)
        findings += scan_text(path, rel)
    return {
        "root": root.name,
        "tree_sha256": sha256_json(tree),
        "files_scanned": files,
        "findings": findings,
        "summary": summarize(findings),
    }


def summarize(findings: list[dict]) -> dict:
    out: dict[str, int] = {}
    for f in findings:
        out[f["family"]] = out.get(f["family"], 0) + 1
    return {
        "by_family": dict(sorted(out.items())),
        "vulnerable_findings": sum(v for k, v in out.items() if k in {"RSA", "ECC", "DH", "DSA"}),
        "pqc_findings": out.get("PQC", 0),
        "needs_live_probe": out.get("UNKNOWN", 0),
        "files_with_findings": len({f["file"] for f in findings}),
    }
