"""Gate: post-quantum handshake (reads capture.json only).

pq_handshake: PASS only if the negotiated group is on the configured PQ/hybrid allowlist.
pq_auth:      reported separately: PASS only if the server certificate's signature algorithm is on
              the PQ auth allowlist (ML-DSA, SLH-DSA). Classical auth is not an HNDL exposure (a
              past session cannot be retroactively impersonated) but must change before a CRQC exists.
downgrade:    PASS only if a classical-only client failed to complete a handshake with the service.
Classical sessions are labelled HNDL-exposed (harvest-now-decrypt-later: recorded traffic relies
on classical key exchange). This gate inspects handshake metadata only; it decrypts nothing.
"""

from contracts import validate


def kex_class(group: str, allowlist) -> str:
    return "hybrid-pq" if group in set(allowlist) else "classical"


def evaluate_session(session: dict, lab: dict) -> dict:
    cls = kex_class(session["negotiated_group"], lab["pq_group_allowlist"])
    passed = cls == "hybrid-pq"
    return {
        "gate": "pq_handshake",
        "service_id": session["service_id"],
        "result": "PASS" if passed else "FAIL",
        "negotiated_group": session["negotiated_group"],
        "kex_class": cls,
        "hndl_exposed": not passed,
        "label": None if passed else lab["hndl_label"],
        "reason": (
            f"{session['negotiated_group']} is on the PQ allowlist"
            if passed
            else f"{session['negotiated_group']} is classical (not on the PQ allowlist)"
        ),
        "transcript_sha256": session["transcript_sha256"],
    }


def evaluate_downgrade(capture: dict, service_id: str, lab: dict) -> dict:
    classical = lab["classical_only_client_groups"]
    refused = [a for a in capture["refused_attempts"] if a["service_id"] == service_id and a["client_groups_offered"] == classical]
    accepted = [s for s in capture["sessions"] if s["service_id"] == service_id and s.get("client_groups_offered") == classical]
    if accepted:
        result, reason = "FAIL", f"classical-only client ({classical}) completed a handshake: {accepted[0]['negotiated_group']}"
    elif refused:
        result, reason = "PASS", f"classical-only client ({classical}) was refused ({refused[0].get('error')})"
    else:
        result, reason = "NOT_RUN", "no classical-only handshake attempt recorded"
    return {"gate": "downgrade_refused", "service_id": service_id, "result": result, "reason": reason}


def evaluate_auth(session: dict, lab: dict) -> dict:
    alg = session["cert_alg"]
    passed = alg in set(lab["pq_auth_allowlist"])
    return {
        "gate": "pq_auth",
        "service_id": session["service_id"],
        "result": "PASS" if passed else "FAIL",
        "auth_alg": alg,
        "signature_type": session.get("signature_type"),
        "auth_class": "pq" if passed else "classical",
        "reason": f"server authenticates with {alg} ({session.get('signature_type')})"
        + ("" if passed else "; classical signature, replace before a CRQC exists (not an HNDL exposure)"),
    }


def evaluate(capture: dict, lab: dict) -> dict:
    validate("capture", capture)
    default_groups = lab["client_groups"]
    sessions = [s for s in capture["sessions"] if s.get("client_groups_offered", default_groups) == default_groups]
    pq = [evaluate_session(s, lab) for s in sessions]
    auth = [evaluate_auth(s, lab) for s in sessions]
    downgrade = [evaluate_downgrade(capture, sid, lab) for sid in sorted({s["service_id"] for s in sessions})]
    return {"capture_run_id": capture["run_id"], "pq_handshake": pq, "pq_auth": auth, "downgrade": downgrade}


def check_live(svc, lab: dict, transcript_dir, tag: str = "") -> dict:
    """pq_handshake gate against a running service, using the pq-capable client profile."""
    from capture.handshake import record

    client = lab["clients"]["pq-capable"]
    rec = record(svc.service_id, svc.host, svc.port, client["groups"], transcript_dir,
                 f"{tag}{svc.service_id}_{svc.mode}_pq_handshake", lab["timeouts_s"]["handshake"])
    if not rec["established"]:
        return {"gate": "pq_handshake", "service_id": svc.service_id, "result": "FAIL", "negotiated_group": None,
                "kex_class": None, "hndl_exposed": None, "label": None,
                "reason": f"pq-capable client could not connect ({rec.get('error')})",
                "transcript_sha256": rec["transcript_sha256"]}
    return evaluate_session(rec, lab)
