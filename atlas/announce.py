"""Terminal launch screen, read only from out/results.json, the ledger file and pytest's JUnit report.

Nothing is hard-coded: module status is computed from which sections exist in results.json and
from out/pytest-junit.xml; every key number is printed with its source. Missing data prints
"not yet run".
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NOT_YET_RUN = "not yet run"
TAGLINE = ("Find vulnerable RSA/ECC, schedule the migration with QpiAI Opt, verify every wave on real TLS 1.3, "
           "and prove it with ML-DSA-65-signed evidence.")
TRACK = "Track: Post-Quantum Cryptography · PQC-01"
FOOTER = ("Lab demo · local TLS lab services on 127.0.0.1 · local single-key test ledger (no public timestamping) · "
          "simulator-scale QAOA, no quantum advantage claimed · risk, effort and shelf-life values are assumptions "
          "(config/assumptions.json)")
BANNER = r"""
  ___         ____  _   _ ___ _____ _     ____        _  _____ _        _    ____
 / _ \       / ___|| | | |_ _| ____| |   |  _ \      / \|_   _| |      / \  / ___|
| | | |_____ \___ \| |_| || ||  _| | |   | | | |    / _ \ | | | |     / _ \ \___ \
| |_| |_____| ___) |  _  || || |___| |___| |_| |   / ___ \| | | |___ / ___ \ ___) |
 \__\_\     |____/|_| |_|___|_____|_____|____/   /_/   \_\_| |_____/_/   \_\____/
"""

# module -> (folder, test files, results.json key that proves it ran)
MODULES = [
    ("contracts", "contracts", ["test_contracts"], "schema_version"),
    ("schedule", "schedule", ["test_schedule", "test_sensitivity", "test_platform_guard"], "solver_runs"),
    ("detect", "detect", ["test_detect"], "detect"),
    ("capture", "capture", ["test_capture_gates"], "handshake_evidence"),
    ("gates", "gates", ["test_gates_waves"], "gates"),
    ("ledger", "ledger", ["test_ledger", "test_merkle"], "ledger"),
    ("qaoa", "qaoa", ["test_qaoa", "test_qaoa_table"], "qaoa"),
    ("viz", "viz", ["test_viz"], None),
    ("atlas", "atlas", ["test_atlas"], None),
]


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def junit_counts(path: Path) -> dict[str, dict[str, int]]:
    """Per test module: passed / failed / skipped from pytest's JUnit XML."""
    if not path.exists():
        return {}
    out: dict[str, dict[str, int]] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        mod = case.get("classname", "").split(".")
        name = next((m for m in mod if m.startswith("test_")), None)
        if not name:
            continue
        c = out.setdefault(name, {"passed": 0, "failed": 0, "skipped": 0})
        if case.find("failure") is not None or case.find("error") is not None:
            c["failed"] += 1
        elif case.find("skipped") is not None:
            c["skipped"] += 1
        else:
            c["passed"] += 1
    return out


def module_status(results: dict | None, junit: dict, repo: Path = REPO) -> list[dict]:
    rows = []
    for name, folder, tests, key in MODULES:
        built = (repo / folder).is_dir()
        counts = {"passed": 0, "failed": 0, "skipped": 0}
        seen = False
        for t in tests:
            if t in junit:
                seen = True
                for k in counts:
                    counts[k] += junit[t][k]
        ran = key is None or (results is not None and results.get(key) not in (None, [], {}))
        if not built:
            status, mark = "pending: not built", "…"
        elif seen and counts["failed"]:
            status, mark = f"{counts['failed']} test(s) failing", "✖"
        elif not seen:
            status, mark = "pending: tests not run", "…"
        elif not ran:
            status, mark = f"built, tests pass; results {NOT_YET_RUN}", "…"
        else:
            status, mark = "built, tests passing", "✔"
        rows.append({"module": name, "mark": mark, "status": status, **counts})
    return rows


def ledger_file_check(results: dict | None, repo: Path = REPO) -> dict:
    if not results or not results.get("ledger"):
        return {"text": NOT_YET_RUN}
    from ledger.log import canonical, read_entries
    from ledger.merkle import MerkleTree

    path = repo / results["ledger"]["ledger_ref"]
    if not path.exists():
        return {"text": f"ledger file {results['ledger']['ledger_ref']} missing"}
    entries = read_entries(path)
    root = MerkleTree([canonical(e) for e in entries]).root()
    same = root == results["ledger"]["root"] and len(entries) == results["ledger"]["entry_count"]
    return {"entries_in_file": len(entries), "root_in_file": root, "matches_results": same,
            "text": "ledger file matches the anchored root" if same else "ledger file differs from the anchored root"}


def collect(results: dict | None, junit: dict, repo: Path = REPO) -> dict:
    r = results or {}
    runs = {x["run_id"]: x for x in r.get("solver_runs", [])}
    exp = r.get("exposure") or {}
    pb = exp.get("produced_by") or {}
    solver = {
        "solver": pb.get("solver", NOT_YET_RUN),
        "run_ids": pb.get("run_ids", []),
        "job_ids": [runs[i]["job_id"] if runs.get(i, {}).get("job_id") else f"none ({runs.get(i, {}).get('job_id_reason', NOT_YET_RUN)})"
                    for i in pb.get("run_ids", [])],
        "ts": max((runs[i]["ts"] for i in pb.get("run_ids", []) if i in runs), default=NOT_YET_RUN),
    }
    det = r.get("detect")
    he = r.get("handshake_evidence")
    gates = r.get("gates") or {}
    by = lambda lst, sid: next((g for g in (lst or []) if g["service_id"] == sid), {})
    handshake = [
        {"service": s["service_id"], "key_exchange": s["negotiated_group"],
         "pq_handshake": by(gates.get("pq_handshake"), s["service_id"]).get("result", NOT_YET_RUN),
         "authentication": s.get("auth_alg", NOT_YET_RUN),
         "pq_auth": by(gates.get("pq_auth"), s["service_id"]).get("result", NOT_YET_RUN),
         "hndl": s.get("label")}
        for s in (he or {}).get("sessions", [])
    ]
    q = r.get("qaoa")
    qaoa_rows = []
    for row in (q or {}).get("table", []):
        if row["status"] == "ok":
            m = row["metrics"]
            val = {k: m[k] for k in ("feasible_fraction", "approximation_ratio", "energy_ratio", "p_optimal_assets")}
        else:
            val = row["status_text"]
        qaoa_rows.append({"p": row["p"], "source": row["source"], "status": row["status"], "values": val, "job_ids": row["job_ids"]})
    led = r.get("ledger")
    ver = r.get("ledger_verification")
    if not led:
        verified = NOT_YET_RUN
    elif not ver:
        verified = "not verified since last ingest"
    elif ver["root"] != led["root"] or ver["entries_checked"] != led["entry_count"]:
        verified = "stale (verified a different root)"
    else:
        verified = "✔ verified" if ver["ok"] else f"✖ failed at index {ver['first_failure']['index']}: {ver['first_failure']['reason']}"
    pq_sessions = [s for s in (he or {}).get("sessions", []) if s.get("kex_class") == "hybrid-pq"]
    return {
        "banner": BANNER.strip("\n"),
        "tagline": TAGLINE,
        "track": TRACK,
        "generated_at": r.get("generated_at", NOT_YET_RUN),
        "modules": module_status(results, junit, repo),
        "assets": {
            "found": len(r["assets"]) if r.get("assets") else NOT_YET_RUN,
            "detect_run_id": det["run_id"] if det else NOT_YET_RUN,
            "files_scanned": det["files_scanned"] if det else NOT_YET_RUN,
            "not_vulnerable": det["inventory"]["not_vulnerable"] if det else NOT_YET_RUN,
            "drift_count": det["drift_count"] if det else NOT_YET_RUN,
        },
        "avoided": {k: [{"scenario": x["scenario"], "exposure_years_avoided": x["exposure_years_avoided"]} for x in v]
                    for k, v in (r.get("avoided") or {}).items()} or NOT_YET_RUN,
        "solver": solver,
        "handshake": handshake or NOT_YET_RUN,
        "handshake_run_id": he["run_id"] if he else NOT_YET_RUN,
        "qaoa": {"run_id": q["run_id"], "label": q["label"], "exact_objective": q["exact"]["objective"], "rows": qaoa_rows} if q else NOT_YET_RUN,
        "ledger": {"entries": led["entry_count"], "root": led["root"], "verified": verified, "alg": led["alg"],
                   "backend": led["backend"], "file_check": ledger_file_check(results, repo)} if led else NOT_YET_RUN,
        "crypto": {
            "openssl": he["openssl_version"] if he else NOT_YET_RUN,
            "kem_group": sorted({s["negotiated_group"] for s in pq_sessions}) or NOT_YET_RUN,
            "signature": f"{led['alg']} (ledger, {led['backend']})" if led else NOT_YET_RUN,
            "pq_auth": sorted({s["auth_alg"] for s in (he or {}).get("sessions", []) if s.get("auth_class") == "pq"}) or NOT_YET_RUN,
        },
        "footer": FOOTER,
    }


def render(data: dict, console) -> None:
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console.print(Text(data["banner"], style="bold cyan"))
    console.print(Text(data["tagline"], style="bold"))
    console.print(Text(data["track"], style="magenta"))
    console.print(f"[dim]results.json generated_at {data['generated_at']}[/dim]\n")

    t = Table(title="Modules", show_lines=False)
    for col in ("", "module", "status", "passed", "failed", "skipped"):
        t.add_column(col)
    for m in data["modules"]:
        style = {"✔": "green", "✖": "red"}.get(m["mark"], "yellow")
        t.add_row(f"[{style}]{m['mark']}[/{style}]", m["module"], m["status"], str(m["passed"]), str(m["failed"]), str(m["skipped"]))
    console.print(t)

    a, s = data["assets"], data["solver"]
    lines = [f"assets to migrate: [bold]{a['found']}[/bold]  (detect run {a['detect_run_id']}, {a['files_scanned']} files scanned, "
             f"not vulnerable: {a['not_vulnerable']}, static-vs-live drift findings: {a['drift_count']})"]
    if isinstance(data["avoided"], dict):
        for base, rows in data["avoided"].items():
            vals = ", ".join(f"{x['scenario']} {x['exposure_years_avoided']:.3f}" for x in rows)
            lines.append(f"exposure-years avoided {base.replace('_', ' ')}: {vals}")
    else:
        lines.append(f"exposure-years avoided: {NOT_YET_RUN}")
    lines.append(f"  source: solver {s['solver']}, run_ids {', '.join(s['run_ids']) or NOT_YET_RUN}, "
                 f"job_id {'; '.join(dict.fromkeys(s['job_ids'])) or NOT_YET_RUN}, ts {s['ts']}")
    console.print(Panel("\n".join(lines), title="Schedule (QpiAI Opt MILP vs FCFS / greedy)"))

    if isinstance(data["handshake"], list):
        h = Table(title=f"TLS 1.3 handshake evidence (capture run {data['handshake_run_id']})")
        for col in ("service", "key exchange", "pq_handshake", "authentication", "pq_auth"):
            h.add_column(col)
        for row in data["handshake"]:
            kx = row["key_exchange"] + (f"\n[red]{row['hndl']}[/red]" if row["hndl"] else "")
            h.add_row(row["service"], kx, row["pq_handshake"], row["authentication"], row["pq_auth"])
        console.print(h)
    else:
        console.print(f"TLS handshake evidence: {NOT_YET_RUN}")

    q = data["qaoa"]
    if isinstance(q, dict):
        qt = Table(title=f"QAOA cross-check (run {q['run_id']}): exact optimum {q['exact_objective']:.6f}")
        for col in ("p", "source", "feasible", "approx. ratio", "energy ratio", "P(opt set)", "job_ids"):
            qt.add_column(col)
        for row in q["rows"]:
            p = "–" if row["p"] is None else str(row["p"])
            if isinstance(row["values"], dict):
                v = row["values"]
                fmt = lambda x: NOT_YET_RUN if x is None else f"{x:.4f}"
                qt.add_row(p, row["source"], fmt(v["feasible_fraction"]), fmt(v["approximation_ratio"]), fmt(v["energy_ratio"]),
                           fmt(v["p_optimal_assets"]), ", ".join(row["job_ids"]) or "–")
            else:
                qt.add_row(p, row["source"], f"[dim]{row['values']}[/dim]", "", "", "", "–")
        console.print(qt)
        console.print(f"[dim]{q['label']}[/dim]")
    else:
        console.print(f"QAOA: {NOT_YET_RUN}")

    led, c = data["ledger"], data["crypto"]
    if isinstance(led, dict):
        style = "green" if led["verified"].startswith("✔") else "red" if led["verified"].startswith("✖") else "yellow"
        body = (f"entries {led['entries']} · root {led['root']} · [{style}]{led['verified']}[/{style}]\n"
                f"{led['file_check']['text']} · {led['alg']} via {led['backend']}")
    else:
        body = NOT_YET_RUN
    console.print(Panel(body, title="Evidence ledger"))
    kem = ", ".join(c["kem_group"]) if isinstance(c["kem_group"], list) else c["kem_group"]
    auth = ", ".join(c["pq_auth"]) if isinstance(c["pq_auth"], list) else c["pq_auth"]
    console.print(f"[bold]crypto backend:[/bold] {c['openssl']} · KEM group {kem} · signatures {c['signature']} · PQ server auth {auth}")
    console.print(Panel(data["footer"], style="yellow", title="honesty"))
