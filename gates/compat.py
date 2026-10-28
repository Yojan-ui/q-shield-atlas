"""Gate: client compatibility matrix for one service in one deployment mode.

Clients come from config/lab.json "clients"; the expected outcome for each (mode, client) comes
from the "compat_policy" table. Two rules are enforced in code regardless of the policy:
  1. No silent downgrade: if the mode offers a PQ group and the client offers one too, the
     session must negotiate a PQ group, else the cell FAILs.
  2. A connection on a classical group is never PASS. If it matches policy it is
     "HNDL-exposed" (recorded traffic relies on classical key exchange).
Cell results: PASS | FAIL | HNDL-exposed. The gate fails if any cell FAILs.
"""

from capture.handshake import record


def _pq_groups(groups: str, allowlist) -> set[str]:
    return set(groups.split(":")) & set(allowlist)


def judge(mode: str, client: str, actual: dict, lab: dict, policy: dict) -> tuple[str, str]:
    expected = policy[mode][client]
    allow = lab["pq_group_allowlist"]
    connected, group = actual["connected"], actual.get("negotiated_group")
    mode_pq = _pq_groups(lab["modes"][mode]["groups"], allow)
    client_pq = _pq_groups(lab["clients"][client]["groups"], allow) if lab["clients"][client]["tls"] != "1.2" else set()

    if connected and mode_pq & client_pq and group not in allow:
        return "FAIL", f"silent downgrade: both sides support {sorted(mode_pq & client_pq)} but negotiated {group}"
    if expected["expect"] == "refused":
        return ("PASS", "refused as policy requires") if not connected else ("FAIL", f"policy requires refusal; connected with {group}")
    if not connected:
        return "FAIL", f"policy expects a connection on {expected['group']}; handshake refused ({actual.get('error')})"
    if group != expected["group"]:
        return "FAIL", f"policy expects {expected['group']}; negotiated {group}"
    if group not in allow:
        return "HNDL-exposed", f"connected on classical {group} as policy allows; {lab['hndl_label']}"
    return "PASS", f"negotiated {group} as policy requires"


def run_matrix(svc, lab: dict, transcript_dir, policy: dict | None = None, tag: str = "") -> dict:
    """Probe `svc` (a running ManagedService) with every client profile; return the matrix."""
    policy = policy or lab["compat_policy"]
    mode = svc.mode
    cells = []
    for client, spec in lab["clients"].items():
        rec = record(svc.service_id, svc.host, svc.port, spec["groups"], transcript_dir,
                     f"{tag}{svc.service_id}_{mode}_{client}", lab["timeouts_s"]["handshake"],
                     None if spec["tls"] == "auto" else spec["tls"])
        actual = {
            "connected": rec["established"],
            "negotiated_group": rec.get("negotiated_group"),
            "protocol": rec.get("protocol"),
            "error": rec.get("error"),
        }
        result, reason = judge(mode, client, actual, lab, policy)
        cells.append({
            "mode": mode,
            "client": client,
            "expected": policy[mode][client],
            "actual": actual,
            "result": result,
            "hndl_exposed": result == "HNDL-exposed",
            "reason": reason,
            "transcript_sha256": rec["transcript_sha256"],
            "timestamp": rec["timestamp"],
        })
    failed = [c for c in cells if c["result"] == "FAIL"]
    return {
        "gate": "compat",
        "service_id": svc.service_id,
        "mode": mode,
        "result": "FAIL" if failed else "PASS",
        "cells": cells,
        "counts": {r: sum(c["result"] == r for c in cells) for r in ("PASS", "HNDL-exposed", "FAIL")},
    }
