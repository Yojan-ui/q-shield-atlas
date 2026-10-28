"""Static-vs-live drift: compare what a service's files say with what its endpoint negotiates."""

VULNERABLE = {"RSA", "ECC", "DH", "DSA"}


def _families(findings: list[dict], use: str) -> set[str]:
    return {f["family"] for f in findings if f["use"] in (use, "both")}


def compare(service_id: str, findings: list[dict], live: dict) -> dict:
    """Return drift items for one service. `findings` are that service's static findings."""
    items = []
    static_kex, static_sig = _families(findings, "kex"), _families(findings, "sig")
    if not live.get("handshake_ok"):
        items.append({"kind": "probe_failed", "severity": "high", "detail": "no completed handshake; live state unknown"})
        return {"service": service_id, "endpoint": live.get("endpoint"), "live": live, "drift": items}

    kex, cert = live["kex_family"], live["cert_family"]
    if "PQC" in static_kex and kex != "PQC":
        items.append({
            "kind": "pqc_claimed_not_negotiated",
            "severity": "high",
            "detail": f"config lists a hybrid/ML-KEM group but the live handshake negotiated {live['group']} ({kex})",
        })
    if kex in VULNERABLE and kex not in static_kex and "PQC" not in static_kex:
        items.append({"kind": "undeclared_live_kex", "severity": "medium", "detail": f"live key exchange {live['group']} ({kex}) has no static evidence"})
    if cert in VULNERABLE and cert not in static_sig:
        items.append({"kind": "undeclared_live_cert", "severity": "medium", "detail": f"live certificate {live['cert_algorithm']} has no static evidence"})
    if kex == "PQC" and "PQC" not in static_kex:
        items.append({"kind": "pqc_live_not_in_config", "severity": "low", "detail": f"live negotiated {live['group']} but no static evidence of it"})
    return {
        "service": service_id,
        "endpoint": live["endpoint"],
        "live": live,
        "static": {"kex": sorted(static_kex), "sig": sorted(static_sig)},
        "drift": items,
    }
