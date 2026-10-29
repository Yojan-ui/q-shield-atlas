"""Move page data: the recorded TLS handshakes as message lists, read-only.

Parses the `openssl s_client -brief -msg` transcripts the capture run wrote (runs/<run_id>/transcript_*.txt) into
one entry per TLS message: direction, message type, its real byte length, and for ClientHello / ServerHello the
key_share entries (group and byte size). A transcript is used only when its SHA-256 equals the hash recorded in
capture.json, so every packet on screen traces to a hashed, recorded file. No hex, randoms or keys are returned.
Bank endpoints (atlas-service.json with an "observed" block, written by tools/scan_banks.py) are returned as
"observed": their one recorded handshake, never a migration.
"""

import hashlib
import json
import re
from pathlib import Path

# RFC 8446 4.1.3: a ServerHello with this random is a HelloRetryRequest
HRR_RANDOM = bytes.fromhex("cf21ad74e59a6111be1d8c021e65b891c2a211167abb8c5e079e09e2c8a8339c")
GROUPS = {0x001d: "X25519", 0x0017: "P-256", 0x0018: "P-384", 0x11ec: "X25519MLKEM768", 0x0201: "MLKEM768", 0x0202: "MLKEM1024"}
LINE = re.compile(r"^(>>>|<<<) TLS [\d.]+, (\w+) \[length ([0-9a-f]+)\](?:, (.+))?$")


def _key_shares(kind: str, b: bytes) -> list[dict]:
    """key_share entries of a ClientHello / ServerHello body (b starts at the handshake type byte)."""
    try:
        p = 4 + 2 + 32  # type + length, legacy_version, random
        p += 1 + b[p]  # session id
        if kind == "ClientHello":
            p += 2 + int.from_bytes(b[p:p + 2], "big")  # cipher suites
            p += 1 + b[p]  # compression methods
        else:
            p += 2 + 1  # cipher suite, compression method
        end = p + 2 + int.from_bytes(b[p:p + 2], "big")
        p += 2
        while p + 4 <= end:
            et, el = int.from_bytes(b[p:p + 2], "big"), int.from_bytes(b[p + 2:p + 4], "big")
            data, p = b[p + 4:p + 4 + el], p + 4 + el
            if et != 0x0033:
                continue
            if kind == "ClientHello":
                out, q = [], 2
                while q + 4 <= len(data):
                    g, n = int.from_bytes(data[q:q + 2], "big"), int.from_bytes(data[q + 2:q + 4], "big")
                    out.append({"group": GROUPS.get(g, f"0x{g:04x}"), "bytes": n})
                    q += 4 + n
                return out
            g = int.from_bytes(data[:2], "big")
            if len(data) < 4:  # HelloRetryRequest: the server names the group it wants, no share
                return [{"group": GROUPS.get(g, f"0x{g:04x}"), "bytes": None, "requested": True}]
            return [{"group": GROUPS.get(g, f"0x{g:04x}"), "bytes": int.from_bytes(data[2:4], "big")}]
    except IndexError:
        pass
    return []


def parse_transcript(text: str) -> list[dict]:
    """One dict per TLS message (record headers and inner content-type bytes skipped)."""
    msgs, cur = [], None
    for line in text.splitlines():
        m = LINE.match(line)
        if m:
            cur = None
            arrow, rec, length, name = m.groups()
            if rec in ("RecordHeader", "InnerContent"):
                continue
            cur = {"dir": "c2s" if arrow == ">>>" else "s2c", "record": rec, "type": "Alert" if rec == "Alert" else (name or rec).strip(),
                   "bytes": int(length, 16), "_hex": []}
            if rec == "Alert":
                cur["alert"] = (name or "").strip()
            msgs.append(cur)
        elif cur is not None and line.startswith("    ") and re.fullmatch(r"[0-9a-f ]+", line.strip()):
            cur["_hex"].append(line.strip())
        else:
            cur = None
    for m in msgs:
        raw = bytes.fromhex("".join(m.pop("_hex")))
        if m["type"] in ("ClientHello", "ServerHello") and raw:
            if m["type"] == "ServerHello" and raw[6:38] == HRR_RANDOM:
                m["type"] = "HelloRetryRequest"
            m["key_share"] = _key_shares("ClientHello" if m["type"] == "ClientHello" else "ServerHello", raw)
    return msgs


def transcripts(run_dirs: list[Path], wanted: set[str]) -> dict:
    """sha256 -> {file, messages} for every transcript file whose hash is in `wanted`."""
    out = {}
    for d in run_dirs:
        if not d or not d.is_dir():
            continue
        for f in sorted(d.glob("transcript_*.txt")):
            text = f.read_text(errors="replace")
            h = hashlib.sha256(text.encode()).hexdigest()
            if h in wanted and h not in out:
                out[h] = {"file": f"runs/{d.name}/{f.name}", "messages": parse_transcript(text)}
    return out


def observed_endpoints(src: Path) -> dict:
    """asset id -> the one recorded observation of a real external endpoint (tools/scan_banks.py)."""
    out = {}
    if not src or not src.is_dir():
        return out
    for f in sorted(src.glob("*/*/atlas-service.json")):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(d.get("observed"), dict) and d.get("id"):
            out[d["id"]] = {**{k: d["observed"].get(k) for k in ("negotiated_group", "tls_version", "cert_key_algorithm", "outcome", "transcript_sha256")},
                            "source": str(f.relative_to(src))}
    return out


def move_payload(ws, results: dict | None) -> dict:
    cap_path = ws.out / "capture.json"
    try:
        cap = json.loads(cap_path.read_text())
    except (OSError, ValueError):
        cap = None
    observed = observed_endpoints(ws.src)
    if not cap:
        return {"available": False, "status_text": "not yet run", "observed": observed}
    sessions, refused = cap.get("sessions") or [], cap.get("refused_attempts") or []
    wanted = {s["transcript_sha256"] for s in sessions + refused if s.get("transcript_sha256")}
    tr = transcripts([ws.runs / cap["run_id"]], wanted)

    def attach(s):
        t = tr.get(s.get("transcript_sha256"))
        return {**s, "transcript_file": t["file"] if t else None, "messages": t["messages"] if t else None,
                "transcript_verified": bool(t)}

    return {"available": True, "run_id": cap["run_id"], "ts": cap.get("generated_at"), "openssl_version": cap.get("openssl_version"),
            "capture_sha256": hashlib.sha256(cap_path.read_bytes()).hexdigest(),
            "sessions": [attach(s) for s in sessions], "refused_attempts": [attach(s) for s in refused],
            "observed": observed,
            "note": "replay of recorded handshakes (openssl s_client -msg); message sizes are the recorded TLS lengths"}
